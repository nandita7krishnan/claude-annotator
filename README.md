# Claude Annotator

A tiny floating scratchpad that sits next to your terminal and helps you
collect annotations on Claude's response, then pastes them back in as one
message.

## Setup

Requires Python 3 with tkinter.

- If you installed Python from python.org: tkinter is already included.
- If you installed Python via Homebrew: run `brew install python-tk`.

No other dependencies — it uses macOS's built-in `pbcopy`/`pbpaste`.

For the "Send to..." button to paste for you, the app running this script
(Terminal, iTerm, etc.) needs Accessibility permission:
**System Settings > Privacy & Security > Accessibility**. macOS will ask
the first time. If you skip it, everything still works — the message lands
on your clipboard and you paste it yourself.

## Run

```bash
python3 claude_annotator.py
```

This opens a small always-on-top window. Position it next to your terminal.

## Usage

The loop is: **copy, type, copy, type, ... send.** No clicking in between.

1. In your terminal, select the piece of Claude's response you want to
   comment on and press Cmd+C, same as always.
2. The annotator auto-detects the clipboard change and fills the
   "Selected snippet" box — no manual paste.
3. Type your note.
4. Now just copy the next snippet. Typing a note and copying again queues
   the previous one automatically — you don't press Enter or click anything.
   Repeat for as many spots as you like.
5. Click **"Send to <your terminal>"**. It queues whatever you were still
   typing, compiles the whole batch, switches back to the app you copied
   from, and pastes.
6. Read it over and press Enter yourself.

The compiled message looks like:

```
Here's my feedback on your response:

Re: "snippet one"
note one

Re: "snippet two"
note two
```

### The other buttons

- **Note only (no snippet)** — a general comment not tied to any snippet.
  (Typing a note with nothing in the snippet box and then copying something
  queues it as a note-only item too.)
- **Queue it now** / Enter — commit the current pair without copying
  anything new.
- **Remove selected** / **Clear all** — fix mistakes in the queue.
- **Copy only** — compile to the clipboard without switching apps.

## Notes / limitations

- It pastes but never presses Enter, so nothing is sent until you read it
  and hit Enter yourself.
- "Send to..." targets whichever app was frontmost the last time you
  copied something — that's how it knows which terminal you mean. Copy
  something from that terminal at least once first.
- It works with any terminal (Terminal.app, iTerm2, Warp, etc.) since it's
  just reading/writing the system clipboard.
- The clipboard poll runs every 500ms, so there's a brief delay between
  copying and seeing the snippet appear.
- Because it watches for clipboard *changes*, copying the exact same text
  twice in a row doesn't register as a new snippet.
- A successful send clears the queue. A failed one keeps it, so you don't
  lose work if the paste doesn't go through.
