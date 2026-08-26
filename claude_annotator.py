#!/usr/bin/env python3
"""
Claude Annotator — a small floating pill for annotating Claude's replies.

The loop, hands on keyboard the whole time:

    select text, Cmd+C  ->  pill appears, focused
    type your note      ->  Enter  (queues it, throws you back to the terminal)
    select, Cmd+C       ->  type   ->  Enter  ->  ...
    Cmd+Enter           ->  compiles everything and pastes it into your terminal

The pill hides itself whenever your terminal isn't frontmost, so it's only
on screen when you're actually working with Claude.

Keys
    Enter        queue this note and return to your terminal
    Cmd+Enter    send everything
    Esc          hide (comes back next time you copy)
    click ●N     show/hide the queue
    click x      quit

Requires Python 3 with tkinter. No pip packages — it uses tkinter's own
clipboard and macOS's osascript.

Permissions (System Settings > Privacy & Security):
    Automation      needed. Lets it see which app is frontmost and switch
                    back to your terminal. macOS prompts for this.
    Accessibility   optional. Only for the final auto-paste. Without it,
                    Cmd+Enter still compiles and copies, and you paste.
"""

import json
import os
import re
import subprocess
import threading
import tkinter as tk

HERE = os.path.expanduser("~/.claude-annotator.json")

# The clipboard read is a native Tk call (~0.1ms), so poll it often.
POLL_CLIP_MS = 100
# Frontmost lookup shells out, so it runs on a background thread and the
# UI only ever reads the cached answer.
POLL_FRONT_MS = 400
SCRIPT_CACHE = os.path.expanduser("~/.claude-annotator-scripts")

W = 380
H_SMALL = 118
H_BIG = 330
RADIUS = 16

BG = "#1f1f24"
FIELD = "#2b2b32"
FG = "#ececf1"
DIM = "#8b8b96"
GREEN = "#5ec27a"
RED = "#e5806b"
BLUE = "#7aa7e8"

_FRONTMOST = (
    'tell application "System Events" to get name of '
    "first application process whose frontmost is true"
)

_ACTIVATE_PID = """on run argv
    tell application "System Events"
        set frontmost of (first application process whose unix id is ¬
            (item 1 of argv as integer)) to true
    end tell
end run"""

_SELF_NAME = """on run argv
    tell application "System Events"
        get name of (first application process whose unix id is (item 1 of argv as integer))
    end tell
end run"""

_ACTIVATE_NAME = """on run argv
    tell application "System Events"
        set frontmost of (first application process whose name is (item 1 of argv)) to true
    end tell
end run"""

_PASTE = """on run argv
    tell application "System Events"
        set frontmost of (first application process whose name is (item 1 of argv)) to true
        delay 0.25
        keystroke "v" using command down
    end tell
end run"""


def get_clipboard() -> str:
    try:
        return subprocess.run(
            ["pbpaste"], capture_output=True, text=True, timeout=2
        ).stdout
    except Exception:
        return ""


def set_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text, text=True)


_COMPILED = {}


def compiled_path(source: str):
    """Compile a script once and reuse it; osascript -e recompiles every call."""
    if source in _COMPILED:
        return _COMPILED[source]
    path = None
    try:
        os.makedirs(SCRIPT_CACHE, exist_ok=True)
        stem = os.path.join(SCRIPT_CACHE, f"{abs(hash(source)) & 0xffffffff:08x}")
        path = stem + ".scpt"
        if not os.path.exists(path):
            with open(stem + ".applescript", "w") as fh:
                fh.write(source)
            done = subprocess.run(
                ["osacompile", "-o", path, stem + ".applescript"],
                capture_output=True, timeout=15,
            )
            try:
                os.remove(stem + ".applescript")
            except OSError:
                pass
            if done.returncode != 0:
                path = None
    except Exception:
        path = None
    _COMPILED[source] = path
    return path


_LS_NAME = re.compile(r'"LSDisplayName"="([^"]*)"')


def frontmost_app():
    """Name of the frontmost app. lsappinfo is ~4x faster than System Events."""
    try:
        asn = subprocess.run(
            ["lsappinfo", "front"], capture_output=True, text=True, timeout=2
        ).stdout.strip()
        if asn:
            out = subprocess.run(
                ["lsappinfo", "info", "-only", "name", asn],
                capture_output=True, text=True, timeout=2,
            ).stdout
            found = _LS_NAME.search(out)
            if found and found.group(1):
                return found.group(1)
    except Exception:
        pass
    out, err = run_osascript(_FRONTMOST)
    return None if err else out


def run_osascript(script: str, *args: str):
    """Return (stdout, error). Exactly one of the two is None."""
    path = compiled_path(script)
    cmd = ["osascript", path, *args] if path else ["osascript", "-e", script, *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        return None, str(exc)
    if proc.returncode != 0:
        return None, (proc.stderr or "").strip() or "osascript failed"
    return proc.stdout.strip(), None


def activate_app(name: str) -> bool:
    """Bring an app forward. open(1) is ~2x faster than driving System Events."""
    try:
        done = subprocess.run(["open", "-a", name], capture_output=True, timeout=3)
        if done.returncode == 0:
            return True
    except Exception:
        pass
    _, err = run_osascript(_ACTIVATE_NAME, name)
    return err is None


def needs_accessibility(err: str) -> bool:
    low = err.lower()
    return (
        "not allowed" in low
        or "assistive" in low
        or "-1719" in low  # not authorised to send Apple events
        or "(1002)" in low  # osascript is not allowed to send keystrokes
    )


def load_pos():
    try:
        with open(HERE) as fh:
            cfg = json.load(fh)
        return int(cfg["x"]), int(cfg["y"])
    except Exception:
        return None


def save_pos(x, y):
    try:
        with open(HERE, "w") as fh:
            json.dump({"x": x, "y": y}, fh)
    except Exception:
        pass


class AnnotatorApp:
    def __init__(self, root: tk.Tk, watch: bool = True):
        self.root = root
        self.items = []  # (snippet_or_None, note)
        self.snippet = ""  # what you last copied
        self.target_app = None  # app you copied from == where we paste back
        self.status_text = "Copy something to start."
        self._self_app = None
        self._self_pid = str(os.getpid())
        self.expanded = False
        self.hidden_by_user = False
        self.visible = True
        self._clip_timer = None
        self._front_timer = None
        self._front = None  # cached frontmost app, written by the watcher
        self._stop_evt = threading.Event()
        self._watcher = None

        self.borderless = True
        try:
            # The documented macOS way to drop the title bar while staying a
            # real, focusable window. overrideredirect() looks the same but
            # can't become the key window, so typing goes nowhere.
            root.tk.call("::tk::unsupported::MacWindowStyle", "style", root._w, "plain")
        except tk.TclError:
            try:
                root.overrideredirect(True)
            except tk.TclError:
                self.borderless = False
        root.attributes("-topmost", True)
        try:
            root.attributes("-transparent", True)
        except tk.TclError:
            pass
        root.configure(bg="systemTransparent")

        pos = load_pos()
        if pos is None:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            pos = (sw - W - 40, sh - H_SMALL - 120)
        root.geometry(f"{W}x{H_SMALL}+{pos[0]}+{pos[1]}")

        self.canvas = tk.Canvas(
            root, width=W, height=H_BIG, highlightthickness=0, bg="systemTransparent"
        )
        self.canvas.pack(fill="both", expand=True)

        self.note_entry = tk.Entry(
            root,
            bg=FIELD,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            font=("SF Pro Text", 13),
            highlightthickness=0,
        )
        self.listbox = tk.Listbox(
            root,
            bg=FIELD,
            fg=DIM,
            relief="flat",
            font=("SF Pro Text", 11),
            highlightthickness=0,
            selectmode="extended",
            activestyle="none",
        )

        self._build()
        self._bind()
        self.last_clip = self._read_clipboard()
        if watch:
            self._front = frontmost_app()
            self._watcher = threading.Thread(target=self._watch_front, daemon=True)
            self._watcher.start()
        self.poll_clipboard()
        self.poll_frontmost()

    # ---------- chrome ----------

    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        pts = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self.canvas.create_polygon(pts, smooth=True, **kw)

    def _build(self):
        c = self.canvas
        c.delete("all")
        h = H_BIG if self.expanded else H_SMALL
        self.root.geometry(f"{W}x{h}")
        c.config(height=h)

        self._round_rect(1, 1, W - 1, h - 1, RADIUS, fill=BG, outline="#3a3a44")

        c.create_text(
            16, 20, anchor="w", fill=DIM, font=("SF Pro Text", 11, "italic"),
            text=self._preview(), tags="preview",
        )
        c.create_text(
            W - 16, 18, anchor="e", fill=DIM, font=("SF Pro Text", 13), text="✕",
            tags="close",
        )

        c.create_window(16, 40, anchor="nw", window=self.note_entry, width=W - 32, height=28)

        badge_y = 88 if not self.expanded else H_BIG - 26
        self.badge_id = c.create_text(
            16, badge_y, anchor="w", fill=GREEN if self.items else DIM,
            font=("SF Pro Text", 11), text=self._badge(), tags="badge",
        )
        c.create_text(
            W - 16, badge_y, anchor="e", fill=GREEN, font=("SF Pro Text", 11, "bold"),
            text="Send ⌘⏎", tags="send",
        )
        self.status_id = c.create_text(
            W / 2, badge_y, anchor="center", fill=DIM, font=("SF Pro Text", 10),
            text=self.status_text,
        )

        if self.expanded:
            c.create_window(16, 78, anchor="nw", window=self.listbox,
                            width=W - 32, height=H_BIG - 118)
        else:
            self.listbox.place_forget()

    def _preview(self):
        if not self.snippet:
            return "no snippet — copy something in your terminal"
        return f'"{self._truncate(self.snippet, 46)}"'

    def _badge(self):
        n = len(self.items)
        if not n:
            return "nothing queued"
        return f"● {n} queued  ▾" if not self.expanded else f"● {n} queued  ▴"

    def _refresh(self):
        self.canvas.itemconfig("preview", text=self._preview())
        self.canvas.itemconfig(self.badge_id, text=self._badge(),
                               fill=GREEN if self.items else DIM)
        self.canvas.itemconfig(self.status_id, text=self.status_text)

    def _set_status(self, text, color=DIM):
        self.status_text = text
        try:
            self.canvas.itemconfig(self.status_id, text=text, fill=color)
        except tk.TclError:
            pass

    # ---------- input ----------

    def _bind(self):
        c = self.canvas
        c.tag_bind("send", "<Button-1>", lambda e: self.send_to_terminal())
        c.tag_bind("badge", "<Button-1>", lambda e: self.toggle_expand())
        c.tag_bind("close", "<Button-1>", lambda e: self.quit())
        for tag in ("send", "badge", "close"):
            c.tag_bind(tag, "<Enter>", lambda e: c.config(cursor="pointinghand"))
            c.tag_bind(tag, "<Leave>", lambda e: c.config(cursor=""))

        c.bind("<Button-1>", self._drag_start)
        c.bind("<B1-Motion>", self._drag_move)
        c.bind("<ButtonRelease-1>", self._drag_end)

        if os.environ.get("CLAUDE_ANNOTATOR_DEBUG"):
            self.root.bind_all("<Key>", lambda e: print(f"[key] {e.keysym!r} -> {e.widget}", flush=True))
            self.root.bind("<FocusIn>", lambda e: print(f"[focus-in] {e.widget}", flush=True))
            self.root.bind("<FocusOut>", lambda e: print(f"[focus-out] {e.widget}", flush=True))
        self.note_entry.bind("<Return>", lambda e: self.queue_and_return())
        self.note_entry.bind("<Command-Return>", lambda e: self.send_to_terminal())
        self.root.bind("<Command-Return>", lambda e: self.send_to_terminal())
        self.root.bind("<Escape>", lambda e: self.hide(by_user=True))

    def _drag_start(self, event):
        self.note_entry.focus_set()
        self._drag = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _drag_move(self, event):
        if not getattr(self, "_drag", None):
            return
        self.root.geometry(f"+{event.x_root - self._drag[0]}+{event.y_root - self._drag[1]}")

    def _drag_end(self, _event):
        self._drag = None
        save_pos(self.root.winfo_x(), self.root.winfo_y())

    # ---------- visibility ----------

    def show(self, focus=False):
        if not self.visible:
            self.root.deiconify()
            self.root.lift()
            self.visible = True
        if focus:
            self.activate_self()

    def hide(self, by_user=False):
        if self.visible:
            self.root.withdraw()
            self.visible = False
        if by_user:
            self.hidden_by_user = True

    def _reschedule(self, attr, ms, fn):
        """Queue the next tick, replacing any tick already pending."""
        pending = getattr(self, attr)
        if pending is not None:
            try:
                self.root.after_cancel(pending)
            except tk.TclError:
                pass
        setattr(self, attr, self.root.after(ms, fn))

    def stop(self):
        """Cancel pending timers and stop the watcher thread."""
        self._stop_evt.set()
        if self._watcher is not None:
            self._watcher.join(timeout=1)
            self._watcher = None
        for timer in (self._clip_timer, self._front_timer):
            if timer is not None:
                try:
                    self.root.after_cancel(timer)
                except tk.TclError:
                    pass
        self._clip_timer = self._front_timer = None

    def quit(self):
        save_pos(self.root.winfo_x(), self.root.winfo_y())
        self.stop()
        self.root.destroy()

    def toggle_expand(self):
        self.expanded = not self.expanded
        self._build()

    def activate_self(self):
        """Raise and focus ourselves. Tk manages this without AppleScript."""
        self.root.lift()
        self.note_entry.focus_force()
        self.root.update_idletasks()
        if self.root.focus_get() is not None:
            return True
        _, err = run_osascript(_ACTIVATE_PID, self._self_pid)  # fallback
        if err:
            self._set_status("couldn't focus myself — click me", RED)
        return err is None

    def activate_target(self):
        if self.target_app:
            activate_app(self.target_app)

    def self_app_name(self):
        if self._self_app is None:
            out, _ = run_osascript(_SELF_NAME, self._self_pid)
            self._self_app = out or ""
        return self._self_app

    def _watch_front(self):
        while not self._stop_evt.wait(POLL_FRONT_MS / 1000):
            name = frontmost_app()
            if name:
                self._front = name

    def poll_frontmost(self):
        """Only be on screen while the terminal you copy from is in front."""
        front = self._front
        if front:
            if self.target_app is None:
                pass  # nothing learned yet — stay put
            elif front in (self.target_app, self.self_app_name()):
                if not self.hidden_by_user:
                    self.show()
            else:
                self.hide()
        self._reschedule("_front_timer", POLL_FRONT_MS, self.poll_frontmost)

    # ---------- clipboard ----------

    def _read_clipboard(self):
        try:
            return self.root.clipboard_get()
        except tk.TclError:
            return get_clipboard()

    def poll_clipboard(self):
        clip = self._read_clipboard()
        if clip != self.last_clip and clip.strip():
            self.last_clip = clip
            front = self._front
            from_terminal = bool(front) and front not in ("", self.self_app_name())
            if from_terminal:
                self.target_app = front
            queued = self.commit_pending()
            self.snippet = clip.strip()
            self._refresh()
            if from_terminal:
                self.hidden_by_user = False
                self.root.update_idletasks()  # draw first, then switch focus
                self.show(focus=True)
            self._set_status(
                f"queued {len(self.items)} — next note?" if queued else "type your note",
                GREEN if queued else DIM,
            )
        self._reschedule("_clip_timer", POLL_CLIP_MS, self.poll_clipboard)

    # ---------- queue ----------

    def _queue(self, snippet, note):
        self.items.append((snippet, note))
        self.listbox.insert("end", f'{self._truncate(snippet, 28)} → {note}'
                            if snippet else f"— {note}")
        self.listbox.see("end")

    def commit_pending(self) -> bool:
        note = self.note_entry.get().strip()
        if not note:
            return False
        self._queue(self.snippet or None, note)
        self.note_entry.delete(0, "end")
        self.snippet = ""
        self._refresh()
        return True

    def queue_and_return(self):
        """Enter: bank this note and hand focus straight back to the terminal."""
        if not self.commit_pending():
            self._set_status("type a note first", RED)
            return
        self._set_status(f"queued {len(self.items)} — back to you", GREEN)
        self._refresh()
        self.activate_target()

    def add_item(self):
        if not self.commit_pending():
            self._set_status("type a note first", RED)
            return
        self._set_status(f"queued {len(self.items)}", GREEN)

    def add_note_only(self):
        note = self.note_entry.get().strip()
        if not note:
            self._set_status("type a note first", RED)
            return
        self._queue(None, note)
        self.note_entry.delete(0, "end")
        self._refresh()
        self._set_status(f"queued {len(self.items)}", GREEN)

    def remove_selected(self):
        for idx in reversed(list(self.listbox.curselection())):
            self.listbox.delete(idx)
            del self.items[idx]
        self._refresh()

    def clear_all(self):
        self.items.clear()
        self.listbox.delete(0, "end")
        self._refresh()

    # ---------- output ----------

    def compile_text(self) -> str:
        blocks = [f'Re: "{s}"\n{n}' if s else n for s, n in self.items]
        return "Here's my feedback on your response:\n\n" + "\n\n".join(blocks)

    def _stage(self):
        self.commit_pending()
        if not self.items:
            return None
        text = self.compile_text()
        set_clipboard(text)
        self.last_clip = text  # don't read our own output back in
        return text

    def copy_all(self):
        if self._stage() is None:
            self._set_status("nothing to copy", RED)
            return
        self._set_status("copied — paste it yourself", BLUE)

    def send_to_terminal(self):
        if self._stage() is None:
            self._set_status("nothing to send", RED)
            return
        if not self.target_app:
            self._set_status("copied — no terminal seen yet", BLUE)
            return

        _, err = run_osascript(_PASTE, self.target_app)
        if err:
            self.activate_target()
            if needs_accessibility(err):
                self._set_status("copied — allow Accessibility to auto-paste", RED)
            else:
                self._set_status(f"copied — paste failed: {err[:24]}", RED)
            return

        count = len(self.items)
        self.clear_all()
        if self.expanded:
            self.toggle_expand()
        self._set_status(f"sent {count} — press Enter there", BLUE)
        self.hide()

    # ---------- helpers ----------

    @staticmethod
    def _truncate(text, limit=60):
        flat = " ".join((text or "").split())
        return flat if len(flat) <= limit else flat[: limit - 1] + "…"


if __name__ == "__main__":
    root = tk.Tk()
    app = AnnotatorApp(root)
    root.mainloop()
