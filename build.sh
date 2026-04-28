#!/bin/bash
# Build a self-contained, slimmed NanoVNASaver.app for Apple Silicon Macs.
#
# Upstream ships no macOS binary, only Windows/RasPi. This script builds one
# from source, applies three undocumented fixes, then strips ~80% of the
# install (unused Qt modules + x86_64 slices) for a ~250 MB native arm64 app.
#
# Usage:  ./build.sh [version-tag] [destination]
# e.g.:   ./build.sh v0.7.3 ~/Applications/NanoVNASaver.app

set -euo pipefail

TAG="${1:-v0.7.3}"
APP="${2:-$HOME/Applications/NanoVNASaver.app}"
PYTHON="${PYTHON:-/opt/homebrew/bin/python3.12}"

if [ ! -x "$PYTHON" ]; then
    echo "ERROR: need Python 3.10+ at $PYTHON (set \$PYTHON to override)"
    exit 1
fi

if [[ "$(uname -m)" != "arm64" ]]; then
    echo "WARNING: this script is tuned for Apple Silicon. x86_64 thinning will fail."
fi

WORK=$(mktemp -d)
trap "rm -rf $WORK" EXIT

echo "==> Building NanoVNASaver.app ($TAG) at $APP"

# 1. Fresh bundle layout
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# 2. Self-contained venv, with `python` symlink (setup.py needs it)
echo "==> Creating venv"
"$PYTHON" -m venv "$APP/Contents/Resources/venv"
ln -sf python3 "$APP/Contents/Resources/venv/bin/python"
"$APP/Contents/Resources/venv/bin/pip" install --quiet --upgrade pip

# 3. Install NanoVNASaver from GitHub tag
echo "==> Installing NanoVNASaver $TAG (this is slow)"
PATH="$APP/Contents/Resources/venv/bin:$PATH" \
    "$APP/Contents/Resources/venv/bin/pip" install --quiet \
    "git+https://github.com/NanoVNA-Saver/nanovna-saver.git@$TAG"

# 4. Clone source for UI files (wheel doesn't compile them)
echo "==> Compiling UI files (.ui/.qrc → .py)"
git clone --quiet --depth 1 --branch "$TAG" \
    https://github.com/NanoVNA-Saver/nanovna-saver.git "$WORK/src"

UI_SRC="$WORK/src/src/NanoVNASaver/Windows/ui"
UI_DST="$APP/Contents/Resources/venv/lib/python3.12/site-packages/NanoVNASaver/Windows/ui"
"$APP/Contents/Resources/venv/bin/pyside6-uic" "$UI_SRC/about.ui" -o "$UI_DST/about.py"
"$APP/Contents/Resources/venv/bin/pyside6-rcc" "$UI_SRC/main.qrc"  -o "$UI_DST/main_rc.py"
cp "$UI_SRC/icon_48x48.png" "$UI_SRC/logo_128x128.png" "$UI_DST/"

# 5. Fix broken `import main_rc` in generated about.py
sed -i '' 's/^import main_rc$/from . import main_rc/' "$UI_DST/about.py"

# 6. Build launcher
cat > "$APP/Contents/MacOS/NanoVNASaver" <<'EOF'
#!/bin/bash
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$APP_DIR/Resources/venv/bin/python3"
LOGDIR="$HOME/Library/Logs/NanoVNASaver"
mkdir -p "$LOGDIR"
exec "$PYTHON" -m NanoVNASaver "$@" >>"$LOGDIR/nanovnasaver.log" 2>&1
EOF
chmod +x "$APP/Contents/MacOS/NanoVNASaver"

# 7. Info.plist
cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>            <string>NanoVNASaver</string>
    <key>CFBundleDisplayName</key>     <string>NanoVNASaver</string>
    <key>CFBundleExecutable</key>      <string>NanoVNASaver</string>
    <key>CFBundleIdentifier</key>      <string>org.nanovna.saver</string>
    <key>CFBundleVersion</key>         <string>${TAG#v}</string>
    <key>CFBundleShortVersionString</key><string>${TAG#v}</string>
    <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
    <key>CFBundlePackageType</key>     <string>APPL</string>
    <key>CFBundleSignature</key>       <string>????</string>
    <key>CFBundleIconFile</key>        <string>NanoVNASaver.icns</string>
    <key>LSMinimumSystemVersion</key>  <string>11.0</string>
    <key>NSHighResolutionCapable</key> <true/>
</dict>
</plist>
EOF

# 8. Build .icns from bundled logo
echo "==> Building app icon"
ICONSET="$WORK/NanoVNASaver.iconset"
mkdir -p "$ICONSET"
SRC="$UI_SRC/logo_128x128.png"
for s in 16 32 64 128 256 512 1024; do
    sips -z "$s" "$s" "$SRC" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
done
cp "$ICONSET/icon_32x32.png"     "$ICONSET/icon_16x16@2x.png"
cp "$ICONSET/icon_64x64.png"     "$ICONSET/icon_32x32@2x.png"
cp "$ICONSET/icon_256x256.png"   "$ICONSET/icon_128x128@2x.png"
cp "$ICONSET/icon_512x512.png"   "$ICONSET/icon_256x256@2x.png"
cp "$ICONSET/icon_1024x1024.png" "$ICONSET/icon_512x512@2x.png"
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/NanoVNASaver.icns"

BEFORE=$(du -sh "$APP" | awk '{print $1}')

# 9. Slim Qt frameworks + bindings
echo "==> Slimming Qt"
PY="$APP/Contents/Resources/venv/lib/python3.12/site-packages/PySide6"
KEEP_FW="QtCore QtGui QtWidgets QtDBus QtNetwork QtPrintSupport QtSvg QtSvgWidgets"

for fw in "$PY/Qt/lib"/*.framework; do
    name=$(basename "$fw" .framework); keep=0
    for k in $KEEP_FW; do [ "$name" = "$k" ] && keep=1; done
    [ $keep -eq 0 ] && rm -rf "$fw"
done

for so in "$PY"/*.abi3.so; do
    name=$(basename "$so" .abi3.so); keep=0
    for k in $KEEP_FW; do [ "$name" = "$k" ] && keep=1; done
    [ $keep -eq 0 ] && rm -f "$so"
done

rm -rf "$PY/Qt/qml" "$PY/Qt/translations" "$PY/Qt/metatypes" "$PY/Qt/libexec"

# 10. Slim Qt plugins
KEEP_PLUG="platforms imageformats styles iconengines tls networkinformation platforminputcontexts generic"
for d in "$PY/Qt/plugins"/*; do
    name=$(basename "$d"); keep=0
    for k in $KEEP_PLUG; do [ "$name" = "$k" ] && keep=1; done
    [ $keep -eq 0 ] && rm -rf "$d"
done

# 11. Thin universal binaries to arm64 only
if [[ "$(uname -m)" == "arm64" ]]; then
    echo "==> Thinning universal binaries → arm64"
    while IFS= read -r f; do
        if file "$f" 2>/dev/null | grep -q "Mach-O universal binary"; then
            if lipo -thin arm64 "$f" -output "$f.thin" 2>/dev/null; then
                mv "$f.thin" "$f"
            else
                rm -f "$f.thin"
            fi
        fi
    done < <(find "$APP" -type f)
fi

AFTER=$(du -sh "$APP" | awk '{print $1}')
echo
echo "Done. $APP"
echo "Size: $BEFORE → $AFTER"
echo "Launch: open '$APP'"
