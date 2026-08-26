#!/usr/bin/env python3
"""
Claude Annotator — a small floating scratchpad for macOS.

Workflow:
  1. Run this next to your terminal (claude / Claude Code session running there).
  2. Select some text in the terminal and Cmd+C it as you normally would.
     This window auto-detects the new clipboard content and drops it into
     the "snippet" box for you — no manual paste needed.
  3. Type your note about that snippet.
  4. Copy the next snippet. Your previous note is queued automatically —
     no Enter, no button. Repeat for as many spots as you like.
  5. Click "Send to <app>". It compiles everything, copies it, switches
     back to the app you copied from, and pastes it there.

It pastes but deliberately does NOT press Enter, so you always get to
read the message and send it yourself.

Requires: Python 3 with tkinter (ships with the python.org installer;
Homebrew users may need `brew install python-tk`).
Uses macOS's built-in pbcopy/pbpaste, no extra pip packages needed.

The auto-paste additionally needs Accessibility permission for whichever
app runs this script (System Settings > Privacy & Security > Accessibility).
Without it everything still works — the text lands on your clipboard and
you paste it yourself.
"""

import os
import subprocess
import tkinter as tk
from tkinter import scrolledtext

POLL_MS = 500

_FRONTMOST = (
    'tell application "System Events" to get name of '
    "first application process whose frontmost is true"
)

_SELF_NAME = """on run argv
    tell application "System Events"
        get name of (first application process whose unix id is (item 1 of argv as integer))
    end tell
end run"""

_PASTE = """on run argv
    set appName to item 1 of argv
    tell application "System Events"
        set frontmost of (first application process whose name is appName) to true
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


def run_osascript(script: str, *args: str):
    """Return (stdout, error). Exactly one of the two is None."""
    try:
        proc = subprocess.run(
            ["osascript", "-e", script, *args],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        return None, str(exc)
    if proc.returncode != 0:
        return None, (proc.stderr or "").strip() or "osascript failed"
    return proc.stdout.strip(), None


def needs_accessibility(err: str) -> bool:
    low = err.lower()
    return (
        "not allowed" in low
        or "assistive" in low
        or "-1719" in low  # not authorised to send Apple events
        or "(1002)" in low  # osascript is not allowed to send keystrokes
    )


class AnnotatorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Claude Annotator")
        root.attributes("-topmost", True)
        root.geometry("440x580")

        self.last_clip = get_clipboard()
        self.items: list = []  # (snippet_or_None, note)
        self.target_app = None  # app we last saw you copy from
        self._self_app = None  # our own process name, resolved lazily

        pad = {"padx": 10, "pady": 4}

        tk.Label(
            root,
            text="Selected snippet (auto-fills when you Cmd+C in your terminal):",
            anchor="w",
        ).pack(fill="x", **pad)

        self.snippet_box = scrolledtext.ScrolledText(root, height=4, wrap="word")
        self.snippet_box.pack(fill="x", **pad)

        tk.Label(
            root,
            text="Your note (just copy the next snippet — this queues itself):",
            anchor="w",
        ).pack(fill="x", **pad)

        self.note_entry = tk.Entry(root)
        self.note_entry.pack(fill="x", **pad)
        self.note_entry.bind("<Return>", lambda e: self.add_item())
        self.note_entry.focus_set()

        btn_row = tk.Frame(root)
        btn_row.pack(fill="x", **pad)
        tk.Button(btn_row, text="Queue it now", command=self.add_item).pack(side="left")
        tk.Button(
            btn_row, text="Note only (no snippet)", command=self.add_note_only
        ).pack(side="left", padx=6)

        tk.Label(root, text="Queued annotations:", anchor="w").pack(fill="x", **pad)

        list_frame = tk.Frame(root)
        list_frame.pack(fill="both", expand=True, padx=10, pady=4)
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        self.listbox = tk.Listbox(
            list_frame, height=12, yscrollcommand=scrollbar.set, selectmode="extended"
        )
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.listbox.yview)

        edit_row = tk.Frame(root)
        edit_row.pack(fill="x", padx=10, pady=(4, 2))
        tk.Button(edit_row, text="Remove selected", command=self.remove_selected).pack(
            side="left"
        )
        tk.Button(edit_row, text="Clear all", command=self.clear_all).pack(
            side="left", padx=6
        )
        tk.Button(edit_row, text="Copy only", command=self.copy_all).pack(side="right")

        self.send_btn = tk.Button(
            root,
            text="Send to terminal",
            bg="#2e7d32",
            fg="white",
            height=2,
            command=self.send_to_terminal,
        )
        self.send_btn.pack(fill="x", padx=10, pady=(2, 4))

        self.status = tk.Label(root, text="Ready.", fg="#444", anchor="w")
        self.status.pack(fill="x", padx=10, pady=(0, 8))

        self.poll_clipboard()

    # ---------- clipboard watching ----------

    def poll_clipboard(self):
        clip = get_clipboard()
        if clip != self.last_clip and clip.strip():
            self.last_clip = clip
            self.remember_front_app()
            queued = self.commit_pending()
            self.snippet_box.delete("1.0", "end")
            self.snippet_box.insert("1.0", clip.strip())
            self.note_entry.focus_set()
            if queued:
                self._set_status(
                    f"Queued ({len(self.items)}). Note for this one?", "#2e7d32"
                )
            else:
                self._set_status("Snippet ready — type your note.", "#444")
        self.root.after(POLL_MS, self.poll_clipboard)

    def self_app_name(self):
        if self._self_app is None:
            out, _ = run_osascript(_SELF_NAME, str(os.getpid()))
            self._self_app = out or ""
        return self._self_app

    def remember_front_app(self):
        """Whatever was frontmost when you hit Cmd+C is the app to paste back into."""
        name, err = run_osascript(_FRONTMOST)
        if err or not name or name == self.self_app_name():
            return
        if name != self.target_app:
            self.target_app = name
            self.send_btn.config(text=f"Send to {name}")

    # ---------- queueing ----------

    def _queue(self, snippet, note):
        self.items.append((snippet, note))
        label = f'Re: "{self._truncate(snippet)}" -> {note}' if snippet else note
        self.listbox.insert("end", label)
        self.listbox.see("end")

    def commit_pending(self) -> bool:
        """Queue whatever is typed right now. Returns True if anything was queued."""
        note = self.note_entry.get().strip()
        if not note:
            return False
        snippet = self.snippet_box.get("1.0", "end").strip()
        self._queue(snippet or None, note)
        self.note_entry.delete(0, "end")
        self.snippet_box.delete("1.0", "end")
        return True

    def add_item(self):
        if not self.commit_pending():
            self._set_status("Type a note first.", "red")
            return
        self._set_status(f"Added. {len(self.items)} queued.", "#2e7d32")

    def add_note_only(self):
        note = self.note_entry.get().strip()
        if not note:
            self._set_status("Type a note first.", "red")
            return
        self._queue(None, note)
        self.note_entry.delete(0, "end")
        self._set_status(f"Added. {len(self.items)} queued.", "#2e7d32")

    def remove_selected(self):
        for idx in reversed(list(self.listbox.curselection())):
            self.listbox.delete(idx)
            del self.items[idx]
        self._set_status(f"{len(self.items)} queued.", "#444")

    def clear_all(self):
        self.items.clear()
        self.listbox.delete(0, "end")
        self._set_status("Cleared.", "#444")

    # ---------- output ----------

    def compile_text(self) -> str:
        blocks = []
        for snippet, note in self.items:
            blocks.append(f'Re: "{snippet}"\n{note}' if snippet else note)
        return "Here's my feedback on your response:\n\n" + "\n\n".join(blocks)

    def _stage(self):
        """Queue anything pending and put the compiled text on the clipboard."""
        self.commit_pending()
        if not self.items:
            return None
        text = self.compile_text()
        set_clipboard(text)
        # Don't let the next poll mistake our own output for a new snippet.
        self.last_clip = text
        return text

    def copy_all(self):
        if self._stage() is None:
            self._set_status("Nothing to copy yet.", "red")
            return
        self._set_status(
            "Copied! Cmd+Tab to your terminal, Cmd+V, then Enter.", "#1565c0"
        )

    def send_to_terminal(self):
        if self._stage() is None:
            self._set_status("Nothing to send yet.", "red")
            return
        if not self.target_app:
            self._set_status(
                "Copied — but I haven't seen you copy from anywhere yet.", "#1565c0"
            )
            return

        _, err = run_osascript(_PASTE, self.target_app)
        if err:
            if needs_accessibility(err):
                self._set_status(
                    "Copied. Allow Accessibility for auto-paste, or paste it yourself.",
                    "red",
                )
            else:
                self._set_status(f"Copied, but paste failed: {err[:44]}", "red")
            return

        count = len(self.items)
        self.clear_all()
        self._set_status(
            f"Pasted {count} into {self.target_app}. Press Enter there to send.",
            "#1565c0",
        )

    # ---------- helpers ----------

    @staticmethod
    def _truncate(text: str, limit: int = 60) -> str:
        flat = " ".join(text.split())
        return flat if len(flat) <= limit else flat[: limit - 1] + "…"

    def _set_status(self, text: str, color: str):
        self.status.config(text=text, fg=color)


if __name__ == "__main__":
    root = tk.Tk()
    app = AnnotatorApp(root)
    root.mainloop()
