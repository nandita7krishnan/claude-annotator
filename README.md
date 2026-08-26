# Clanno

A small floating pill for annotating Claude Code's replies. Highlight
something Claude said, type what you think, repeat — then it compiles every
note into one message and pastes it back into your terminal.

```
  ╭────────────────────────────╮
  │  "def foo(): return 1"   ✕ │
  │   should return 2▌         │
  │   ● 3 queued     Send ⌘⏎   │
  ╰────────────────────────────╯
```

Borderless, ~380×118, always on top, and it hides itself whenever your
terminal isn't frontmost — so it's only on screen when you're working.

macOS only. It leans on AppleScript and macOS clipboard tooling throughout.

---

## Install

**1. Check you have Python 3 with tkinter.**

```bash
python3 -c "import tkinter; print('ok')"
```

If that errors, install tkinter: `brew install python-tk` (Homebrew), or use
the python.org installer, which bundles it. Anaconda's Python works too.
There are no pip dependencies.

**2. Clone and install.**

```bash
git clone https://github.com/nandita7krishnan/claude-annotator.git
cd claude-annotator
./install.sh
```

That builds `~/Applications/Clanno.app` (bundling a copy of whichever
`python3` is first on your PATH) and installs a LaunchAgent so Clanno
starts at every login. It's running immediately — no reboot.

**3. Grant the two permissions.** See below. Clanno is usable after step 2,
but the auto-paste won't work until you've done step 3.

### Uninstall

```bash
./install.sh --uninstall
```

Removes the app and the LaunchAgent. Your `~/.clanno.json` is left alone.

---

## Permissions

Two separate macOS permissions, and they behave very differently.

### Automation — required, prompts you

Lets Clanno see which app is frontmost and switch back to your terminal.
**macOS will show a dialog** the first time ("Clanno wants to control
System Events"). Click OK. Nothing works without this.

### Accessibility — optional, does NOT prompt you

Only needed for the final auto-paste. **macOS shows no dialog for this —
it silently refuses**, so you must add Clanno by hand. Without it,
`Cmd+Enter` still compiles everything onto your clipboard and tells you to
paste it yourself; you just lose the last bit of automation.

To grant it:

1. Open **System Settings > Privacy & Security > Accessibility**.
2. In Finder, open your **home folder > Applications** (this is *not* the
   main `/Applications`). Or run `open ~/Applications`.
3. **Drag `Clanno` from that Finder window into the Accessibility list**,
   and make sure its toggle is **on**.

Prefer the **+** button? Click it, then press **Command-Shift-G** (this
opens a "Go to Folder" box), type `~/Applications`, press Return, pick
Clanno.

> **Don't bother searching for "Clanno" in that file picker.** If your
> Spotlight index is read-only or disabled — which is common — the search
> finds nothing no matter what. Navigate to the path instead.

> **Re-running `./install.sh` may cost you this grant.** It rebuilds and
> ad-hoc re-signs the bundle, which changes its code identity, and macOS
> keys the permission on that. Just drag it in again. Fixing this properly
> needs a paid Developer ID certificate.

> **Running `python3 clanno.py` directly instead of the app?** Then the
> permission belongs to *your terminal*, not to Clanno — grant it to
> Terminal/iTerm instead. Note that's a much broader grant: every script
> that terminal runs can then send keystrokes.

---

## Using it

The loop is **copy → type → Enter**, repeated. Hands stay on the keyboard.

1. Select text in your terminal and press **Cmd+C**, as you normally would.
2. The pill appears, already focused, showing your snippet.
3. Type your note and press **Enter**. That queues it *and* throws focus
   back to your terminal.
4. Select the next thing, Cmd+C, type, Enter. Repeat as often as you like.
5. Press **Cmd+Enter**. It compiles the batch, switches to your terminal,
   and pastes.
6. Read it and press Enter yourself.

**It never presses Enter for you.** Nothing is sent until you've seen it.

### Keys

| Key | Does |
|---|---|
| `Enter` | queue this note, hand focus back to the terminal |
| `Cmd+Enter` | compile everything and paste it into your terminal |
| `Esc` | hide (returns on your next copy) |
| click `● N queued` | expand/collapse the queue |
| click `✕` | quit |

Drag the pill from anywhere on it; it remembers where you left it.

### What gets pasted

One line:

```
Feedback on your response — Re: "snippet one" → note one  |  Re: "snippet two" → note two
```

One line on purpose: Claude Code collapses any multi-line paste into
`[Pasted text #1 +N lines]`, so a block format means you'd never see what
you're about to send. Snippet whitespace is flattened, not dropped, so
multi-line code still reads sensibly.

---

## Configuration

Optional. `~/.clanno.json`, created on first drag:

```json
{
  "terminals": ["My Terminal"],
  "min_chars": 3,
  "autofocus": true,
  "compact": true
}
```

| Key | Default | Meaning |
|---|---|---|
| `terminals` | — | **Extra** apps to treat as terminals, added to the built-ins |
| `min_chars` | `3` | Copies shorter than this are ignored entirely |
| `autofocus` | `true` | `false` = never take your keyboard; you click in when ready |
| `compact` | `true` | `false` = multi-line block output instead of one line |
| `x`, `y` | — | Window position; written for you when you drag the pill |

Built-in terminals: Terminal, iTerm2, iTerm, Warp, Alacritty, kitty,
WezTerm, Ghostty, Hyper, Tabby, rio, Contour.

### How it decides things

- **What counts as a copy**: only copies made in a terminal. Copying in an
  editor, browser, or chat app is ignored completely — no snippet, no focus
  grab, no change of paste target.
- **What's big enough**: copies under `min_chars` are ignored, so a stray
  prompt character can't take your keyboard mid-sentence.
- **Which terminal to paste into**: whichever terminal you last copied from.
- **When to be on screen**: only while that terminal (or the pill) is
  frontmost.

---

## Troubleshooting

**Nothing happens when I copy.** Is your terminal in the built-in list? If
not, add it under `terminals` in `~/.clanno.json` and restart Clanno
(`launchctl kickstart -k gui/$UID/com.clanno.pill`). Also check the copy was
at least `min_chars` long.

**"copied — allow Accessibility to auto-paste".** The Accessibility grant is
missing or was reset. See Permissions above.

**The pill never appears.** Check it's running and read the log:

```bash
launchctl print gui/$UID/com.clanno.pill | grep -E "state|pid"
cat /tmp/clanno.err.log
```

**"Clanno is already running (pid N)".** Only one instance is allowed —
two would fight over the clipboard. Quit the other with its `✕`, or
`kill N`.

**It grabs focus when I didn't want it to.** Set `"autofocus": false`. The
pill still catches snippets; you click in when you actually want to write.

**I want it gone right now.** `./install.sh --uninstall`.

---

## Development

```bash
python3 clanno.py          # run in the foreground, no install
python3 test_clanno.py     # 14 tests, ~10s, no pytest needed
```

Tests stub out AppleScript and app-switching, so they never steal focus or
switch apps, and they save and restore your clipboard. Contributor notes and
architecture are in [AGENTS.md](AGENTS.md).

## License

MIT — see [LICENSE](LICENSE).

## Speed

The copy → focus path is deliberately kept off the critical path:

| | naive | now |
|---|---|---|
| clipboard poll | 350ms (`pbpaste` subprocess) | 100ms (native Tk, 0.1ms/read) |
| frontmost app | 178ms, blocking | 0ms — cached by a background thread |
| raise the pill | 224ms (AppleScript) | ~68ms (Tk raises itself) |
| back to terminal | 161ms (System Events) | ~74ms (`open -a`) |
| **copy → ready to type** | **~580ms** | **~120ms** |
