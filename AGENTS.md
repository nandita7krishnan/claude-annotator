# Notes for agents working on Clanno

Read this before changing `clanno.py`. Most of it is things that were
learned by getting them wrong first.

## What this is

A single-file macOS tkinter app (`clanno.py`, ~500 lines) plus a test file
and an installer. No pip dependencies, deliberately — it uses tkinter's own
clipboard, `osascript`, `lsappinfo`, and `open(1)`. Keep it that way unless
there's a strong reason; the zero-dependency install is a feature.

```
clanno.py        the whole app
test_clanno.py   14 tests, plain python, no pytest
install.sh       builds ~/Applications/Clanno.app + a LaunchAgent,
                 plus "Open Clanno.app", a Spotlight-only opener
icon.py          regenerates Clanno.icns from a handful of shape constants
Clanno.icns      committed, so installing doesn't need to build it
```

## Running things

```bash
python3 clanno.py        # foreground, no install needed
python3 test_clanno.py   # ~10s; exits non-zero on failure
./install.sh             # rebuild the installed app after changing clanno.py
```

`install.sh` is not automatic — **editing `clanno.py` does not update the
installed app.** The bundle has its own copy in `Contents/Resources/`.

`python3 icon.py` rebuilds `Clanno.icns` (~50s) and is only needed if you
change the icon's shape constants; `install.sh` just copies the committed
file. It draws from signed distance fields with no PIL and no supersampling,
so each size in the iconset is rendered from the vector description rather
than downscaled instead of being resampled from one big bitmap.

Two things there are load-bearing. `stroke()` culls by bounding box before
testing segments — without it a single render takes minutes, not seconds.
And **`MARKS` is deliberately short**: the marks were scattered much more
densely at first and 16px turned into pink noise, so resist adding more.
macOS also caches icons aggressively; if a rebuilt bundle still shows the
old one, that's the Finder cache, not the plist.

Only one instance runs at a time (pidfile at `~/.clanno.pid`). If you launch
it for testing, kill it before launching again, or the guard will refuse.

## Hard-won constraints

Do not undo these without reading why.

**Borderless windows must use `MacWindowStyle "plain"`, not
`overrideredirect(True)`.** An `overrideredirect` window looks identical but
can never become the macOS *key window*, so it never receives keystrokes —
the app renders perfectly and silently ignores everything you type.
`focus_get()` and programmatic `insert()` both report success in that state,
so neither proves anything. Only a human typing proves it.

**The app bundle's executable must BE the interpreter.** `install.sh` copies
`python3` to `Contents/MacOS/Clanno` and passes the script as an argument,
with `PYTHONHOME` set in the LaunchAgent so `sys.prefix` resolves. If you
"simplify" this to a shell script that `exec`s python, the running process
lives outside the bundle, macOS identifies it as `python3`, and the
Accessibility permission has nothing to attach to — auto-paste breaks with
no obvious cause.

**Nothing that shells out may run on the UI thread's hot path.**
`osascript` costs ~130–220ms per call. Frontmost detection runs on a
background thread (`_watch_front`) and the UI reads the cached
`self._front`. The watcher writes a plain attribute and never touches Tk —
keep it that way.

**But the cache is too stale to judge a copy by.** `_front` lags reality by
up to a poll interval plus a lookup, so a copy made just after switching to
an editor gets attributed to the terminal and the pill jumps in front of the
editor and eats the keystrokes. `poll_clipboard` therefore calls
`confirm_front()` (~50ms, `lsappinfo`) when the clipboard actually *changes*
— once per Cmd+C, not the 100ms poll, so it is not the hot path. Don't
"optimise" it back to reading `_front`. For the same reason `_watch_front`
swallows exceptions: a dead watcher freezes `_front` on the terminal, and
then every copy anywhere looks like ours.

**Prefer the cheap tool.** `lsappinfo` (~45ms) over System Events (~178ms)
for frontmost. `open -a` (~74ms) over System Events for activation. Tk's own
`lift()` + `focus_force()` (~68ms, no subprocess) over AppleScript for
raising ourselves. AppleScript is compiled once into `~/.clanno-scripts`;
`osascript -e` recompiles on every call.

**A copy out of the input box is not annotation material.** Claude Code's
prompt is pinned to the bottom of the terminal window, so selecting your own
draft there -- to move it, to retype it -- is a real copy from a real
terminal and passes every other check. The pill used to jump in and eat the
next keystrokes. `from_input_box()` compares the pointer (where the
selection ended) against the front window's bounds and ignores copies made
in the bottom `input_box_px`. Asking the terminal what was actually selected
would need the Accessibility API, hence PyObjC. Two properties are
deliberate: it **fails open** -- an unmeasurable window is treated as a
normal copy, because focusing is the wanted default -- and the copy is
ignored *entirely*, for the same reason `min_chars` copies are.
`front_window_bounds()` runs once per copy, never on the poll.

**Window geometry: ask the terminal, not System Events.** Reading `position`
and `size` through System Events needs *Accessibility* -- it fails with
`-1719 osascript is not allowed assistive access` -- and that grant dies on
every ad-hoc rebuild, so the check would silently fail open forever after
any `./install.sh`. A terminal's own dictionary (`tell application "Terminal"
to get bounds of front window`, ~200ms) needs only Automation, which
survives. So the app dictionary is tried first and System Events is the
fallback for terminals with no dictionary (Ghostty, kitty, Alacritty). Note
the two return different shapes: `bounds` is {left, top, right, bottom},
System Events gives position + size. Automation prompts once per app
identity, i.e. again after every rebuild.

**Only copies from a terminal count.** The allowlist is `DEFAULT_TERMINALS`
plus the user's `terminals` config. A check like "any app that isn't us" is
wrong: it makes an editor the paste target and steals focus mid-work.

**Copies under `min_chars` must be ignored *entirely*** — not merely
"captured without focus". `commit_pending()` runs on every accepted copy, so
a stray one-character copy that gets accepted will queue whatever
half-finished note is currently in the field, against the wrong snippet.

**Config writes must merge.** `save_config()` reads, updates, writes. An
earlier `save_pos()` wrote `{x, y}` over the whole file and would have
deleted the user's `terminals` list on their first drag.

**Cancel Tk timers.** `stop()` cancels the clipboard and frontmost timers
and joins the watcher. `_reschedule()` cancels any pending tick before
queueing a new one, so calling a poll function directly (as tests do) can't
leak timers that fire against a destroyed window.

**Output is one line by default.** Claude Code collapses multi-line pastes
to `[Pasted text #1 +N lines]`, so block formatting means the user can't see
what they're about to send. `compact=False` restores blocks.

## Testing conventions

Tests must never touch the user's real environment. The harness:

- stubs `ca.run_osascript` with `FakeScript`, which dispatches on script
  *identity* (`script is ca._PASTE`) — so any new AppleScript needs a
  module-level constant, not an inline string, or `FakeScript` will raise
- stubs `ca.activate_app` so no test ever switches apps
- stubs `app._pointer_xy`, and `FakeScript` answers `_WINDOW_BOUNDS` with a
  fake 1000x800 window, so `from_input_box()` is decided by the test rather
  than by wherever the real mouse is sitting; `copies(pointer=...)` says
  where a selection ended
- points `ca.HERE` at a temp file so no test reads or writes `~/.clanno.json`
- saves and restores the clipboard around the whole run -- note this means
  the suite drives the *real* pasteboard, so copying anything while it runs
  makes tests fail with the stray text as the snippet. Re-run before
  believing a failure you saw while using the machine.
- constructs `AnnotatorApp(root, watch=False)` so no watcher thread runs,
  and sets `app._front` directly to simulate the frontmost app
- replaces `app.show`/`app.hide` with recorders, so no window appears

Follow that shape for new tests. If a test starts switching apps or opening
windows, the harness has been bypassed.

## The log

The app writes one line per copy to stderr -- `/tmp/clanno.err.log` under
the LaunchAgent. It records the clipboard change, the frontmost app, the
pointer, the window bounds and the verdict. It exists because the
input-box check fails open, and a silent fail-open is indistinguishable
from the check simply being wrong; both look like "the pill still steals
focus". Keep it: it is one line per Cmd+C, not per poll.

Two things that wasted time reading it. **Don't truncate that file while
the app is running** -- launchd holds the fd at its offset, so `: > log`
leaves a sparse file whose leading NULs make `cat` look empty. Read with
`tr -d '\0' < /tmp/clanno.err.log`, and to reset it, delete it and
kickstart the agent. And **a TCC prompt takes frontmost**, so while one is
on screen every copy is attributed to `UserNotificationCenter` and ignored
as "not a terminal" -- an unanswered permission dialog looks exactly like
the app being dead.

## Verification discipline

This project has burned real time on confident-but-unverified claims. Some
specifics:

- **Measure before optimizing.** The latency was almost entirely AppleScript
  on the UI thread; guesses about poll intervals would have missed it.
- **A passing indirect signal is not proof.** Both window styles reported a
  real `FocusIn`; only one could actually receive keystrokes.
- **A probe with no GUI window is invisible to System Events.** Process
  identity checks need a real Tk window or they return nothing useful.
- **Assert on every string replacement** when patching files
  programmatically. A silent no-match once shipped a commit whose README
  change never applied.

## Things deliberately not done

- **No PyObjC.** It isn't installed on any interpreter on the target
  machine, and adding it would break the zero-dependency install. It would
  make activation near-instant if that ever changes.
- **No Developer ID signing.** The bundle is ad-hoc signed, so its code
  identity changes on every rebuild and macOS drops the Accessibility grant.
  Documented rather than solved; a real certificate is the only fix.
- **No Dock icon.** `LSUIElement` is true. The pill has its own `✕`.
