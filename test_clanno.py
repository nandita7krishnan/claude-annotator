#!/usr/bin/env python3
"""
Smoke test for clanno.

Drives the copy -> type -> Enter -> send loop against a real (hidden) Tk
window. No dependencies beyond what the app itself needs:

    python3 test_clanno.py

osascript is stubbed, so this never switches apps or sends keystrokes,
and show/hide are recorded rather than performed so no window appears.
Your clipboard is saved on entry and restored on exit.
"""

import sys
import tkinter as tk

import clanno as ca
from clanno import AnnotatorApp, get_clipboard, set_clipboard

SNIPPET_A = "def foo():\n    return 1"
SNIPPET_B = "x = compute()"


class FakeScript:
    """Stands in for run_osascript. Records what the app tried to drive."""

    def __init__(self, front="Terminal", paste_error=None):
        self.front = front
        self.paste_error = paste_error
        self.pasted_to = []
        self.activated = []

    def __call__(self, script, *args):
        if script is ca._FRONTMOST:
            return self.front, None
        if script is ca._SELF_NAME:
            return "Python", None
        if script is ca._ACTIVATE_PID:
            self.activated.append("self")
            return "", None
        if script is ca._ACTIVATE_NAME:
            self.activated.append(args[0])
            return "", None
        if script is ca._PASTE:
            if self.paste_error:
                return None, self.paste_error
            self.pasted_to.append(args[0])
            return "", None
        raise AssertionError(f"unexpected script: {script[:40]!r}")


def new_app(fake):
    ca.run_osascript = fake
    # Never really switch apps during a test run.
    ca.activate_app = lambda name: (fake.activated.append(name), True)[1]
    # Start from a clipboard value no test uses, so the app's initial
    # last_clip never accidentally matches the first snippet we copy.
    set_clipboard("<<test fixture>>")
    root = tk.Tk()
    root.withdraw()
    app = AnnotatorApp(root, watch=False)  # no watcher thread in tests
    # Record visibility decisions instead of actually showing a window.
    app.shown, app.hidden = [], []
    app.show = lambda focus=False: app.shown.append(focus)
    app.hide = lambda by_user=False: app.hidden.append(by_user)
    return root, app


def copies(app, text, front="Terminal"):
    """Simulate a Cmd+C in `front`, then one poll tick."""
    app._fake.front = front
    app._front = front  # what the watcher thread would have cached
    set_clipboard(text)
    app.root.update()
    app.poll_clipboard()


def check(fails, cond, msg):
    if not cond:
        fails.append(msg)


def build(fake):
    root, app = new_app(fake)
    app._fake = fake
    return root, app


def test_auto_queue(fails):
    root, app = build(FakeScript())
    try:
        copies(app, SNIPPET_A)
        check(fails, app.snippet == SNIPPET_A, f"snippet not loaded: {app.snippet!r}")
        app.note_entry.insert(0, "should return 2")
        copies(app, SNIPPET_B)
        check(fails, app.items == [(SNIPPET_A, "should return 2")],
              f"auto-queue: {app.items!r}")
        check(fails, app.note_entry.get() == "", "note field not cleared")
        check(fails, app.snippet == SNIPPET_B, f"second snippet: {app.snippet!r}")
        check(fails, app.target_app == "Terminal", f"target_app: {app.target_app!r}")
    finally:
        app.stop()
        root.destroy()


def test_enter_returns_focus(fails):
    """Enter must queue AND hand focus back, so you never touch the mouse."""
    fake = FakeScript()
    root, app = build(fake)
    try:
        copies(app, SNIPPET_A)
        app.note_entry.insert(0, "too verbose")
        app.queue_and_return()
        check(fails, app.items == [(SNIPPET_A, "too verbose")], f"queue: {app.items!r}")
        check(fails, "Terminal" in fake.activated,
              f"focus not returned to terminal: {fake.activated!r}")
    finally:
        app.stop()
        root.destroy()


def test_only_captures_from_terminals(fails):
    """Copying in an editor must be ignored entirely -- the original bug."""
    fake = FakeScript()
    root, app = build(fake)
    try:
        copies(app, SNIPPET_A, front="Terminal")
        check(fails, app.shown and app.shown[-1] is True,
              f"should have grabbed focus from the terminal: {app.shown!r}")

        # Every one of these is a plausible app to copy from mid-session.
        for editor in ("Code", "TextEdit", "Safari", "Slack", "Notes"):
            app.shown.clear()
            before_target, before_snippet = app.target_app, app.snippet
            copies(app, f"copied inside {editor}", front=editor)
            check(fails, app.shown == [],
                  f"{editor}: grabbed focus from a non-terminal: {app.shown!r}")
            check(fails, app.target_app == before_target,
                  f"{editor}: paste target drifted to {app.target_app!r}")
            check(fails, app.snippet == before_snippet,
                  f"{editor}: captured a snippet it should have ignored: {app.snippet!r}")
            check(fails, app.items == [],
                  f"{editor}: queued something from a non-terminal: {app.items!r}")
    finally:
        app.stop()
        root.destroy()


def test_terminal_matching(fails):
    """Other terminals work, and the allowlist is case-insensitive."""
    for name in ("iTerm2", "Ghostty", "WezTerm", "warp"):
        fake = FakeScript()
        root, app = build(fake)
        try:
            copies(app, SNIPPET_A, front=name)
            check(fails, app.target_app == name, f"{name} not recognised as a terminal")
            check(fails, app.snippet == SNIPPET_A, f"{name}: snippet not captured")
        finally:
            app.stop()
            root.destroy()


def test_config_is_not_clobbered(fails):
    """Saving the window position must not wipe a user's terminals list."""
    import json
    with open(ca.HERE, "w") as fh:               # ca.HERE is a temp file here
        json.dump({"terminals": ["My Terminal"]}, fh)
    ca.save_pos(12, 34)
    cfg = json.load(open(ca.HERE))
    check(fails, cfg.get("terminals") == ["My Terminal"],
          f"save_pos wiped user config: {cfg!r}")
    check(fails, (cfg.get("x"), cfg.get("y")) == (12, 34), f"position not saved: {cfg!r}")
    check(fails, "my terminal" in ca.terminal_names(),
          "custom terminal not picked up from config")


def test_hides_when_terminal_not_front(fails):
    fake = FakeScript()
    root, app = build(fake)
    try:
        copies(app, SNIPPET_A, front="Terminal")
        app.shown.clear(); app.hidden.clear()

        app._front = "Safari"
        app.poll_frontmost()
        check(fails, app.hidden, "did not hide when terminal lost focus")

        app.shown.clear(); app.hidden.clear()
        app._front = "Terminal"
        app.poll_frontmost()
        check(fails, app.shown, "did not come back when terminal returned")

        # Esc means stay gone until the next copy.
        app.hidden_by_user = True
        app.shown.clear()
        app.poll_frontmost()
        check(fails, app.shown == [], "reappeared after being dismissed with Esc")
    finally:
        app.stop()
        root.destroy()


def test_note_without_snippet(fails):
    root, app = build(FakeScript())
    try:
        app.note_entry.insert(0, "overall: too verbose")
        copies(app, SNIPPET_A)
        check(fails, app.items == [(None, "overall: too verbose")],
              f"stray note mishandled: {app.items!r}")
    finally:
        app.stop()
        root.destroy()


def test_send(fails):
    fake = FakeScript()
    root, app = build(fake)
    try:
        copies(app, SNIPPET_A)
        app.note_entry.insert(0, "should return 2")
        copies(app, SNIPPET_B)
        app.note_entry.insert(0, "name this")

        app.send_to_terminal()  # commits the note still being typed

        expected = (
            "Feedback on your response — "
            'Re: "def foo(): return 1" → should return 2  |  '
            'Re: "x = compute()" → name this'
        )
        check(fails, get_clipboard() == expected,
              f"compiled:\n{get_clipboard()!r}\nexpected:\n{expected!r}")
        check(fails, fake.pasted_to == ["Terminal"], f"paste target: {fake.pasted_to!r}")
        check(fails, app.items == [], "queue not cleared after send")
        check(fails, app.hidden, "did not hide itself after sending")

        app.root.update()
        app.poll_clipboard()
        check(fails, not app.snippet, f"clipboard echo: {app.snippet[:40]!r}")
    finally:
        app.stop()
        root.destroy()


def test_send_without_accessibility(fails):
    fake = FakeScript(
        paste_error="System Events got an error: osascript is not allowed "
        "to send keystrokes. (1002)"
    )
    root, app = build(fake)
    try:
        copies(app, SNIPPET_A)
        app.note_entry.insert(0, "note")
        app.send_to_terminal()
        check(fails, "Accessibility" in app.status_text,
              f"unhelpful status: {app.status_text!r}")
        check(fails, len(app.items) == 1, "queue lost after a failed paste")
        check(fails, get_clipboard().startswith("Feedback on your response"),
              "text not on clipboard as fallback")
    finally:
        app.stop()
        root.destroy()


def test_compact_is_one_line(fails):
    """The whole point: Claude Code only collapses multi-line pastes."""
    root, app = build(FakeScript())
    try:
        copies(app, SNIPPET_A)          # a snippet that contains a newline
        app.note_entry.insert(0, "should return 2")
        app.add_item()
        app.note_entry.insert(0, "general point")
        app.add_note_only()
        out = app.compile_text()
        check(fails, "\n" not in out, f"compact output has newlines: {out!r}")
        check(fails, "def foo(): return 1" in out, f"snippet mangled: {out!r}")
        check(fails, "general point" in out, f"note-only lost: {out!r}")
    finally:
        app.stop()
        root.destroy()


def test_block_mode_still_available(fails):
    root, app = build(FakeScript())
    try:
        app.compact = False
        copies(app, SNIPPET_A)
        app.note_entry.insert(0, "should return 2")
        app.add_item()
        out = app.compile_text()
        check(fails, out == "Here's my feedback on your response:\n\n"
                            f'Re: "{SNIPPET_A}"\nshould return 2',
              f"block mode broken: {out!r}")
    finally:
        app.stop()
        root.destroy()


def test_trivial_copies_are_ignored(fails):
    """A stray prompt char must not capture, queue, or steal the keyboard."""
    root, app = build(FakeScript())
    try:
        copies(app, SNIPPET_A)
        app.note_entry.insert(0, "half-typed note")
        app.shown.clear()

        for junk in (">", "x", "ab", "  \n "):
            copies(app, junk)
            check(fails, app.shown == [],
                  f"{junk!r} grabbed focus: {app.shown!r}")
            check(fails, app.snippet == SNIPPET_A,
                  f"{junk!r} overwrote the snippet: {app.snippet!r}")
            check(fails, app.items == [],
                  f"{junk!r} queued the half-typed note: {app.items!r}")
            check(fails, app.note_entry.get() == "half-typed note",
                  f"{junk!r} cleared the note being typed")
    finally:
        app.stop()
        root.destroy()


def test_autofocus_can_be_disabled(fails):
    root, app = build(FakeScript())
    try:
        app.autofocus = False
        copies(app, SNIPPET_A)
        check(fails, app.snippet == SNIPPET_A, "passive mode dropped the snippet")
        check(fails, app.shown == [False],
              f"passive mode still grabbed focus: {app.shown!r}")
    finally:
        app.stop()
        root.destroy()


def test_remove_selected(fails):
    root, app = build(FakeScript())
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
        app.stop()
        root.destroy()


def main():
    import os as _os
    import tempfile

    saved = get_clipboard()
    # Never read or write the real ~/.clanno.json during tests.
    real_here = ca.HERE
    fd, ca.HERE = tempfile.mkstemp(suffix=".json")
    _os.close(fd)
    real_script, real_save = ca.run_osascript, ca.save_pos
    real_activate = ca.activate_app
    fails = []
    try:
        for test in (
            test_auto_queue,
            test_enter_returns_focus,
            test_only_captures_from_terminals,
            test_terminal_matching,
            test_config_is_not_clobbered,
            test_hides_when_terminal_not_front,
            test_note_without_snippet,
            test_send,
            test_send_without_accessibility,
            test_compact_is_one_line,
            test_block_mode_still_available,
            test_trivial_copies_are_ignored,
            test_autofocus_can_be_disabled,
            test_remove_selected,
        ):
            before = len(fails)
            test(fails)
            print(f"  {'FAIL' if len(fails) > before else 'ok  '}  {test.__name__}")
    finally:
        ca.run_osascript, ca.save_pos = real_script, real_save
        ca.activate_app = real_activate
        _os.unlink(ca.HERE)
        ca.HERE = real_here
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
