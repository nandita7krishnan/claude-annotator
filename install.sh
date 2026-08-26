#!/bin/bash
# Build Clanno.app and start it at login.
#   ./install.sh            install (or reinstall after code changes)
#   ./install.sh --uninstall remove app + login agent
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$HOME/Applications/Clanno.app"
PLIST="$HOME/Library/LaunchAgents/com.clanno.pill.plist"
LABEL="com.clanno.pill"

stop_agent() {
  launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
}

if [[ "${1:-}" == "--uninstall" ]]; then
  stop_agent
  rm -f "$PLIST"
  rm -rf "$APP"
  pkill -f "Clanno.app" 2>/dev/null || true
  echo "Removed Clanno.app and the login agent. Config in ~/.clanno.json was left alone."
  exit 0
fi

# An interpreter that actually has tkinter.
PYTHON="$(command -v python3)"
if ! "$PYTHON" -c "import tkinter" >/dev/null 2>&1; then
  echo "error: $PYTHON has no tkinter. Install it (brew install python-tk) and re-run." >&2
  exit 1
fi
echo "interpreter: $PYTHON"

stop_agent
pkill -f "clanno.py" 2>/dev/null || true
rm -f "$HOME/.clanno.pid"

# --- app bundle ---------------------------------------------------------
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$REPO/clanno.py" "$APP/Contents/Resources/clanno.py"

cat > "$APP/Contents/Info.plist" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Clanno</string>
  <key>CFBundleDisplayName</key><string>Clanno</string>
  <key>CFBundleIdentifier</key><string>com.clanno.pill</string>
  <key>CFBundleExecutable</key><string>Clanno</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>LSUIElement</key><true/>
  <key>NSAppleEventsUsageDescription</key>
  <string>Clanno switches back to your terminal and pastes your feedback there.</string>
</dict>
</plist>
PLIST_EOF

# The bundle's executable must BE the interpreter, not a script that execs
# one. Otherwise the running process lives outside the bundle and macOS
# attributes Accessibility to python3 rather than to Clanno.
PYHOME="$("$PYTHON" -c 'import sys; print(sys.prefix)')"
cp "$PYTHON" "$APP/Contents/MacOS/Clanno"
chmod +x "$APP/Contents/MacOS/Clanno"

if ! PYTHONHOME="$PYHOME" "$APP/Contents/MacOS/Clanno" -c "import tkinter" >/dev/null 2>&1; then
  echo "error: the bundled interpreter can't load tkinter (PYTHONHOME=$PYHOME)." >&2
  exit 1
fi

# Ad-hoc signature gives TCC a stable identity to hang permissions on.
if command -v codesign >/dev/null 2>&1; then
  codesign --force --sign - "$APP" >/dev/null 2>&1 && echo "signed (ad-hoc)" || echo "note: could not sign; permissions may reset on rebuild"
fi

# --- login agent --------------------------------------------------------
mkdir -p "$(dirname "$PLIST")"
cat > "$PLIST" <<AGENT_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$APP/Contents/MacOS/Clanno</string>
    <string>$APP/Contents/Resources/clanno.py</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>PYTHONHOME</key><string>$PYHOME</string></dict>
  <key>RunAtLoad</key><true/>
  <!-- Restart on a crash, but respect quitting via the pill's X. -->
  <key>KeepAlive</key>
  <dict><key>SuccessfulExit</key><false/></dict>
  <key>StandardErrorPath</key><string>/tmp/clanno.err.log</string>
</dict>
</plist>
AGENT_EOF

launchctl bootstrap "gui/$UID" "$PLIST" 2>/dev/null || launchctl load "$PLIST"

echo
echo "Installed:"
echo "  app        $APP"
echo "  login agent $PLIST"
echo "  logs       /tmp/clanno.err.log"
echo
echo "Grant Accessibility to Clanno (for the auto-paste):"
echo "  System Settings > Privacy & Security > Accessibility > +"
echo "  then Cmd-Shift-G and paste:  $APP"
echo
echo "Clanno now starts at login. Quit it with the pill's X; it stays gone"
echo "until next login (or: launchctl kickstart gui/$UID/$LABEL)."
