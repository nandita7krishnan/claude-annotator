# Claude Annotator

A tiny floating scratchpad that sits next to your terminal and helps you
collect annotations on Claude's response, then compiles them into one
message you paste back in.

## Setup

Requires Python 3 with tkinter.

- If you installed Python from python.org: tkinter is already included.
- If you installed Python via Homebrew: run `brew install python-tk`.

No other dependencies — it uses macOS's built-in `pbcopy`/`pbpaste`.

## Run

```bash
python3 claude_annotator.py
```

This opens a small always-on-top window. Position it next to your terminal.

## Usage

1. In your terminal, select the piece of Claude's response you want to
   comment on and press Cmd+C, same as always.
2. The annotator window auto-detects the clipboard change and fills the
   "Selected snippet" box for you — no manual paste.
3. Type your note in the "Your note" field and press Enter (or click
   "Add annotation"). It gets added to the queued list below.
4. Repeat for as many spots in the response as you want. Use
   "Add note only" for a comment that isn't tied to a specific snippet.
5. Made a mistake? Select an item in the list and click "Remove selected",
   or "Clear all" to start over.
6. When you're done, click "Copy All -> Clipboard". This compiles
   everything into one message like:

   ```
   Here's my feedback on your response:

   Re: "snippet one"
   note one

   Re: "snippet two"
   note two
   ```

7. Cmd+Tab back to your terminal, Cmd+V into Claude's prompt, press Enter.

## Tests

```bash
python3 test_annotator.py
```

Drives the full annotate -> compile flow against a hidden Tk window. It
saves and restores your clipboard, so it won't clobber what you have copied.

## Notes / limitations

- This does not touch your terminal directly — it only prepares text on
  your clipboard. You still paste and send it yourself, so there's no risk
  of it firing off a message before you're ready.
- It works with any terminal (Terminal.app, iTerm2, Warp, etc.) since it's
  just reading/writing the system clipboard.
- The clipboard poll runs every 500ms, so there's a brief delay between
  copying in the terminal and seeing it appear in the snippet box.
