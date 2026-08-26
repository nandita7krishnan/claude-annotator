#!/usr/bin/env python3
"""
Smoke test for claude_annotator.

Drives the whole annotate -> compile -> send flow against a real (hidden)
Tk window. No dependencies beyond what the app itself needs:

    python3 test_annotator.py

osascript is stubbed out, so this never actually switches apps or sends
keystrokes. Your clipboard is saved on entry and restored on exit.
"""

import sys
import tkinter as tk

import claude_annotator as ca
from claude_annotator import AnnotatorApp, get_clipboard, set_clipboard

SNIPPET_A = "def foo():\n    return 1"
SNIPPET_B = "x = compute()"


class FakeScript:
    """Stands in for run_osascript. Records paste attempts."""

    def __init__(self, front="Terminal", paste_error=None):
        self.front = front
        self.paste_error = paste_error
        self.pasted_to = []

    def __call__(self, script, *args):
        if script is ca._FRONTMOST:
            return self.front, None
        if script is ca._SELF_NAME:
            return "Python", None
        if script is ca._PASTE:
            if self.paste_error:
                return None, self.paste_error
            self.pasted_to.append(args[0])
            return "", None
        raise AssertionError(f"unexpected script: {script[:40]}")


def new_app(fake):
    ca.run_osascript = fake
    # Start from a clipboard value no test uses, so the app's initial
    # last_clip never accidentally matches the first snippet we copy.
    set_clipboard("<<test fixture>>")
    root = tk.Tk()
    root.withdraw()
    return root, AnnotatorApp(root)


def copies(app, text):
    """Simulate a Cmd+C elsewhere, then one poll tick."""
    set_clipboard(text)
    app.poll_clipboard()


def check(fails, cond, msg):
    if not cond:
        fails.append(msg)


def test_auto_queue(fails):
    fake = FakeScript()
    root, app = new_app(fake)
    try:
        # Copy, type a note, then copy again -- the note queues itself.
        copies(app, SNIPPET_A)
        check(fails, app.snippet_box.get("1.0", "end").strip() == SNIPPET_A,
              "auto-fill did not load first snippet")
        app.note_entry.insert(0, "should return 2")
        copies(app, SNIPPET_B)

        check(fails, len(app.items) == 1, f"auto-queue: {app.items!r}")
        check(fails, app.items[0] == (SNIPPET_A, "should return 2"),
              f"auto-queue paired wrongly: {app.items!r}")
        check(fails, app.note_entry.get() == "", "note field not cleared")
        check(fails, app.snippet_box.get("1.0", "end").strip() == SNIPPET_B,
              "second snippet not loaded")

        # The app it saw you copy from becomes the paste target.
        check(fails, app.target_app == "Terminal", f"target_app: {app.target_app!r}")
    finally:
        root.destroy()


def test_no_note_just_replaces(fails):
    root, app = new_app(FakeScript())
    try:
        copies(app, SNIPPET_A)
        copies(app, SNIPPET_B)  # no note typed in between
        check(fails, app.items == [], f"queued with no note: {app.items!r}")
        check(fails, app.snippet_box.get("1.0", "end").strip() == SNIPPET_B,
              "snippet not replaced")
    finally:
        root.destroy()


def test_note_without_snippet(fails):
    """A typed note with no snippet must not get glued onto the next snippet."""
    root, app = new_app(FakeScript())
    try:
        app.note_entry.insert(0, "overall: too verbose")
        copies(app, SNIPPET_A)
        check(fails, app.items == [(None, "overall: too verbose")],
              f"stray note mishandled: {app.items!r}")
    finally:
        root.destroy()


def test_send(fails):
    fake = FakeScript()
    root, app = new_app(fake)
    try:
        copies(app, SNIPPET_A)
        app.note_entry.insert(0, "should return 2")
        copies(app, SNIPPET_B)
        app.note_entry.insert(0, "name this")

        # Sending commits the note still being typed -- no trailing click.
        app.send_to_terminal()

        expected = (
            "Here's my feedback on your response:\n\n"
            f'Re: "{SNIPPET_A}"\nshould return 2\n\n'
            f'Re: "{SNIPPET_B}"\nname this'
        )
        check(fails, get_clipboard() == expected,
              f"compiled text:\n{get_clipboard()!r}\nexpected:\n{expected!r}")
        check(fails, fake.pasted_to == ["Terminal"], f"paste target: {fake.pasted_to!r}")
        check(fails, app.items == [], "queue not cleared after successful send")
        check(fails, app.listbox.size() == 0, "listbox not cleared after send")

        # Regression: the next poll must not read our own output back in.
        app.poll_clipboard()
        echoed = app.snippet_box.get("1.0", "end").strip()
        check(fails, not echoed, f"clipboard echo: {echoed[:60]!r}")
    finally:
        root.destroy()


def test_send_without_accessibility(fails):
    fake = FakeScript(paste_error="execution error: not allowed assistive access (-1719)")
    root, app = new_app(fake)
    try:
        copies(app, SNIPPET_A)
        app.note_entry.insert(0, "note")
        app.send_to_terminal()
        check(fails, "Accessibility" in app.status.cget("text"),
              f"unhelpful status: {app.status.cget('text')!r}")
        check(fails, len(app.items) == 1, "queue lost after a failed paste")
        check(fails, get_clipboard().startswith("Here's my feedback"),
              "text not on clipboard as fallback")
    finally:
        root.destroy()


def test_remove_selected(fails):
    root, app = new_app(FakeScript())
    try:
        copies(app, SNIPPET_A)
        app.note_entry.insert(0, "first")
        app.add_item()
        app.note_entry.insert(0, "second")
        app.add_note_only()
        app.listbox.selection_set(0)
        app.remove_selected()
        check(fails, app.items == [(None, "second")], f"remove_selected: {app.items!r}")
    finally:
        root.destroy()


def main():
    saved = get_clipboard()
    real = ca.run_osascript
    fails = []
    try:
        for test in (
            test_auto_queue,
            test_no_note_just_replaces,
            test_note_without_snippet,
            test_send,
            test_send_without_accessibility,
            test_remove_selected,
        ):
            before = len(fails)
            test(fails)
            print(f"  {'FAIL' if len(fails) > before else 'ok  '}  {test.__name__}")
    finally:
        ca.run_osascript = real
        set_clipboard(saved)

    if fails:
        print("\nFAILURES:")
        for f in fails:
            print(" -", f)
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
