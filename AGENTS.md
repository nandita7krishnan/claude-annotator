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
install.sh       builds ~/Applications/Clanno.app + a LaunchAgent
```

## Running things

```bash
python3 clanno.py        # foreground, no install needed
python3 test_clanno.py   # ~10s; exits non-zero on failure
./install.sh             # rebuild the installed app after changing clanno.py
```

`install.sh` is not automatic — **editing `clanno.py` does not update the
installed app.** The bundle has its own copy in `Contents/Resources/`.

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

**Prefer the cheap tool.** `lsappinfo` (~45ms) over System Events (~178ms)
for frontmost. `open -a` (~74ms) over System Events for activation. Tk's own
`lift()` + `focus_force()` (~68ms, no subprocess) over AppleScript for
raising ourselves. AppleScript is compiled once into `~/.clanno-scripts`;
`osascript -e` recompiles on every call.

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
- points `ca.HERE` at a temp file so no test reads or writes `~/.clanno.json`
- saves and restores the clipboard around the whole run
- constructs `AnnotatorApp(root, watch=False)` so no watcher thread runs,
  and sets `app._front` directly to simulate the frontmost app
- replaces `app.show`/`app.hide` with recorders, so no window appears

Follow that shape for new tests. If a test starts switching apps or opening
windows, the harness has been bypassed.

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
