# Claude Annotator

A small floating pill that sits next to your terminal while you're working
with Claude Code. Highlight something in Claude's reply, say what you think,
and it compiles every note into one message and pastes it back for you.

```
  ╭────────────────────────────╮
  │  "def foo(): return 1"     │
  │   should return 2▌         │
  │   ● 3 queued      Send ⌘⏎  │
  ╰────────────────────────────╯
```

It stays out of the way: no title bar, ~380x118, and it hides itself
whenever your terminal isn't the frontmost app.

## The loop

Hands stay on the keyboard the whole time.

1. Select text in your terminal and press **Cmd+C**, same as always.
2. The pill appears, already focused, with your snippet shown above the
   note field.
3. Type your note and press **Enter**. That queues it *and* throws focus
   back to your terminal.
4. Select the next thing, Cmd+C, type, Enter. Repeat.
5. Press **Cmd+Enter**. It compiles the batch, switches to your terminal,
   and pastes.
6. Read it over and press Enter yourself.

It never presses Enter for you, so nothing is sent until you've seen it.

## Keys

| | |
|---|---|
| `Enter` | queue this note, return to the terminal |
| `Cmd+Enter` | send everything |
| `Esc` | hide (comes back next time you copy) |
| click `● N queued` | show/hide the queue |
| click `✕` | quit |

Drag the pill from anywhere on it. It remembers where you left it.

## Setup

Requires Python 3 with tkinter.

- python.org installer: tkinter is already included.
- Homebrew: `brew install python-tk`.

No pip packages — it uses tkinter's own clipboard and macOS's `osascript`.

```bash
python3 claude_annotator.py
```

### Permissions

Both live in **System Settings > Privacy & Security**.

- **Automation** — required. Lets the pill see which app is frontmost and
  switch back to your terminal. macOS prompts for this the first time.
- **Accessibility** — optional, for the final auto-paste only. Add the app
  that runs the script (Terminal, iTerm, …). macOS shows *no prompt* for
  this and silently refuses instead, so you have to add it by hand.
  Without it, `Cmd+Enter` still compiles and copies everything and tells
  you to paste it yourself.

## How it decides things

- **Which terminal to paste into**: whichever app was frontmost the last
  time you copied. Copy from it once and the pill learns it.
- **When to grab focus**: only when you copied from that terminal. Copying
  in a browser won't yank you out of what you were doing.
- **When to be on screen**: only while that terminal (or the pill itself)
  is frontmost. `Esc` keeps it away until your next copy.

## Notes / limitations

- Copying the exact same text twice in a row doesn't register — it watches
  for clipboard *changes*.
- A successful send clears the queue. A failed one keeps it, so a missing
  permission never costs you your notes.
- Works with any terminal (Terminal.app, iTerm2, Warp, …).
- The pill has no Dock icon or title bar, so quit with `✕`, not Cmd+Q.

## Tests

```bash
python3 test_annotator.py
```

Drives the whole loop against a hidden window. `osascript` is stubbed, so
it never switches apps or sends keystrokes, and it saves and restores your
clipboard.
