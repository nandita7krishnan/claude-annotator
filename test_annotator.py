#!/usr/bin/env python3
"""
Smoke test for claude_annotator.

Runs the whole annotate -> compile flow against a real (hidden) Tk window.
No dependencies beyond what the app itself needs:

    python3 test_annotator.py

Your clipboard is saved on entry and restored on exit, so running this
does not clobber whatever you had copied.
"""

import sys
import tkinter as tk

from claude_annotator import AnnotatorApp, get_clipboard, set_clipboard

SNIPPET = "def foo():\n    return 1"
EXPECTED = (
    "Here's my feedback on your response:\n\n"
    'Re: "def foo():\n    return 1"\nthis should return 2\n\n'
    "overall: looks good"
)


def run(fails):
    root = tk.Tk()
    root.withdraw()
    app = AnnotatorApp(root)
    try:
        # Copying in the terminal auto-fills the snippet box.
        set_clipboard(SNIPPET)
        app.poll_clipboard()
        got = app.snippet_box.get("1.0", "end").strip()
        if got != SNIPPET:
            fails.append(f"auto-fill: {got!r}")

        # Annotating a snippet queues it and clears the box.
        app.note_entry.insert(0, "this should return 2")
        app.add_item()
        if len(app.items) != 1:
            fails.append(f"add_item: {app.items!r}")
        if app.snippet_box.get("1.0", "end").strip():
            fails.append("snippet box not cleared after add")

        # A note not tied to any snippet.
        app.note_entry.insert(0, "overall: looks good")
        app.add_note_only()

        app.copy_all()
        out = get_clipboard()
        if out != EXPECTED:
            fails.append(f"copy_all output:\n{out!r}\nexpected:\n{EXPECTED!r}")

        # Regression: the next poll must not read our own output back in
        # as a fresh snippet.
        app.poll_clipboard()
        echoed = app.snippet_box.get("1.0", "end").strip()
        if echoed:
            fails.append(f"clipboard echo: {echoed[:60]!r}")

        # Removing by listbox index removes the matching item.
        app.listbox.selection_set(0)
        app.remove_selected()
        if len(app.items) != 1 or app.items[0][1] != "overall: looks good":
            fails.append(f"remove_selected: {app.items!r}")
    finally:
        root.destroy()


def main():
    saved = get_clipboard()
    fails = []
    try:
        run(fails)
    finally:
        set_clipboard(saved)

    if fails:
        print("FAILURES:")
        for f in fails:
            print(" -", f)
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
