#!/usr/bin/env python3
"""
Claude Annotator — a small floating scratchpad for macOS.

Workflow:
  1. Run this next to your terminal (claude / Claude Code session running there).
  2. Select some text in the terminal and Cmd+C it as you normally would.
     This window auto-detects the new clipboard content and drops it into
     the "snippet" box for you — no manual paste needed.
  3. Type your note about that snippet, press Enter (or click "Add annotation").
  4. Repeat for as many snippets as you want across the response.
  5. Click "Copy All -> Clipboard". It compiles everything into one message
     and puts it on your clipboard.
  6. Cmd+Tab back to your terminal, Cmd+V into the prompt, press Enter.

Requires: Python 3 with tkinter (ships with the python.org installer;
Homebrew users may need `brew install python-tk`).
Uses macOS's built-in pbcopy/pbpaste, no extra pip packages needed.
"""

import subprocess
import tkinter as tk
from tkinter import scrolledtext


def get_clipboard() -> str:
    try:
        return subprocess.run(
            ["pbpaste"], capture_output=True, text=True, timeout=2
        ).stdout
    except Exception:
        return ""


def set_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text, text=True)


class AnnotatorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Claude Annotator")
        root.attributes("-topmost", True)
        root.geometry("440x560")

        self.last_clip = get_clipboard()
        self.items: list[tuple[str | None, str]] = []  # (snippet_or_None, note)

        pad = {"padx": 10, "pady": 4}

        tk.Label(
            root,
            text="Selected snippet (auto-fills when you Cmd+C in your terminal):",
            anchor="w",
        ).pack(fill="x", **pad)

        self.snippet_box = scrolledtext.ScrolledText(root, height=4, wrap="word")
        self.snippet_box.pack(fill="x", **pad)

        tk.Label(root, text="Your note:", anchor="w").pack(fill="x", **pad)

        self.note_entry = tk.Entry(root)
        self.note_entry.pack(fill="x", **pad)
        self.note_entry.bind("<Return>", lambda e: self.add_item())
        self.note_entry.focus_set()

        btn_row = tk.Frame(root)
        btn_row.pack(fill="x", **pad)
        tk.Button(btn_row, text="Add annotation", command=self.add_item).pack(
            side="left"
        )
        tk.Button(
            btn_row, text="Add note only (no snippet)", command=self.add_note_only
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

        bottom_row = tk.Frame(root)
        bottom_row.pack(fill="x", padx=10, pady=(4, 2))
        tk.Button(bottom_row, text="Remove selected", command=self.remove_selected).pack(
            side="left"
        )
        tk.Button(bottom_row, text="Clear all", command=self.clear_all).pack(
            side="left", padx=6
        )
        tk.Button(
            bottom_row,
            text="Copy All -> Clipboard",
            bg="#2e7d32",
            fg="white",
            command=self.copy_all,
        ).pack(side="right")

        self.status = tk.Label(root, text="Ready.", fg="#444", anchor="w")
        self.status.pack(fill="x", padx=10, pady=(0, 8))

        self.poll_clipboard()

    def poll_clipboard(self):
        clip = get_clipboard()
        if clip != self.last_clip and clip.strip():
            self.last_clip = clip
            self.snippet_box.delete("1.0", "end")
            self.snippet_box.insert("1.0", clip.strip())
            self.note_entry.focus_set()
        self.root.after(500, self.poll_clipboard)

    def add_item(self):
        snippet = self.snippet_box.get("1.0", "end").strip()
        note = self.note_entry.get().strip()
        if not note:
            self._set_status("Type a note first.", "red")
            return
        self.items.append((snippet or None, note))
        label = f'Re: "{self._truncate(snippet)}" -> {note}' if snippet else note
        self.listbox.insert("end", label)
        self.note_entry.delete(0, "end")
        self.snippet_box.delete("1.0", "end")
        self._set_status(f"Added. {len(self.items)} queued.", "#2e7d32")

    def add_note_only(self):
        note = self.note_entry.get().strip()
        if not note:
            self._set_status("Type a note first.", "red")
            return
        self.items.append((None, note))
        self.listbox.insert("end", note)
        self.note_entry.delete(0, "end")
        self._set_status(f"Added. {len(self.items)} queued.", "#2e7d32")

    def remove_selected(self):
        selected = list(self.listbox.curselection())
        for idx in reversed(selected):
            self.listbox.delete(idx)
            del self.items[idx]
        self._set_status(f"{len(self.items)} queued.", "#444")

    def clear_all(self):
        self.items.clear()
        self.listbox.delete(0, "end")
        self._set_status("Cleared.", "#444")

    def copy_all(self):
        if not self.items:
            self._set_status("Nothing to copy yet.", "red")
            return
        blocks = []
        for snippet, note in self.items:
            if snippet:
                blocks.append(f'Re: "{snippet}"\n{note}')
            else:
                blocks.append(note)
        final_text = "Here's my feedback on your response:\n\n" + "\n\n".join(blocks)
        set_clipboard(final_text)
        # Don't let the next poll mistake our own output for a new snippet.
        self.last_clip = final_text
        self._set_status(
            "Copied! Cmd+Tab to your terminal, Cmd+V, then Enter.", "#1565c0"
        )

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
