#!/bin/bash
# Build a self-contained, slimmed NanoVNASaver.app for Apple Silicon Macs.
#
# Upstream ships no macOS binary, only Windows/RasPi. This script builds one
# from source, applies three undocumented fixes, then strips ~80% of the
# install (unused Qt modules + x86_64 slices) for a ~250 MB native arm64 app.
#
# Usage:  ./build.sh [version-tag] [destination]
# e.g.:   ./build.sh v0.7.3 ~/Applications/NanoVNASaver.app
#
# Copyright (C) 2026 Manoj Kumar R <vu2cpl@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# See LICENSE for the full text of the GNU General Public License v3.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

# 5b. macOS UI fixes — upstream hard-codes control sizes (setFixedHeight(20),
#     setFixedWidth(60)) tuned for Windows/Linux. On macOS the native control
#     chrome (taller fields, focus-ring margins, larger system font) needs more
#     room, so Qt clips text: "50kHz"->"50kH", "Sweep"->"Sweer", "Rescan"->"Rescar".
#     Relax the fixed sizes to minimums and widen the control column slightly.
echo "==> Applying macOS UI sizing fixes"
PKG="$APP/Contents/Resources/venv/lib/python3.12/site-packages/NanoVNASaver"
# Let controls grow to their natural macOS height instead of clipping at 20px
sed -i '' 's/setFixedHeight(20)/setMinimumHeight(24)/g' \
    "$PKG/Controls/SweepControl.py" "$PKG/Controls/MarkerControl.py"
# Frequency input fields: 60px min is too narrow for values like "1.000GHz"
sed -i '' 's/self.setMinimumWidth(60)/self.setMinimumWidth(80)/' \
    "$PKG/Controls/SweepControl.py"
sed -i '' 's/setMinimumHeight(20)/setMinimumHeight(24)/g' "$PKG/Marker/Widget.py"
# Rescan/Manage buttons: 60px fixed width clips the label text
sed -i '' 's/setFixedWidth(60)/setMinimumWidth(72)/g' "$PKG/Controls/SerialControl.py"
# Widen the left control column so the two-column Start/Stop|Center/Span forms
# fit without clipping labels (macOS fonts are wider, and the 80px freq fields +
# divider leave too little room for the "Center" label at 280px).
sed -i '' 's/self.setMaximumWidth(250)/self.setMaximumWidth(300)/' \
    "$PKG/Controls/Control.py"
# Marker readout boxes have no trailing stretch, so a taller window inflates the
# three Marker boxes to fill the column instead of keeping them compact. Add a
# stretch after the markers so the slack collects below them and the boxes stay
# at their natural height (upstream left this as a commented-out TODO).
perl -i -pe 's/^(        scroll2 = QtWidgets\.QScrollArea\(\))$/        self.marker_data_layout.addStretch(1)\n$1/' \
    "$PKG/NanoVNASaver.py"
# The S11/S21 summary boxes have no width cap, so they stretch horizontally to
# fill the column when the window is resized. The Marker group boxes cap their
# width at 340*scale_factor (Marker/Widget.py setScale) — give S11/S21 the same
# cap so their width stays fixed on resize and matches the markers exactly.
# scale_factor is already set by this point (the DisplaySettings window triggers
# changeFont during __init__, before these boxes are built) and has a safe
# class-level default of 1.0, so this can't raise.
perl -i -pe 's/^(        (s11|s21)_control_box\.setTitle\("S\d+"\))$/$1\n        $2_control_box.setMaximumWidth(int(340 * self.scale_factor))/' \
    "$PKG/NanoVNASaver.py"
# Same width cap for the "Analysis ..." button so it doesn't stretch on resize.
perl -i -pe 's/^(        btn_show_analysis = QtWidgets\.QPushButton\("Analysis \.\.\."\))$/$1\n        btn_show_analysis.setMaximumWidth(int(340 * self.scale_factor))/' \
    "$PKG/NanoVNASaver.py"

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

# 8. Build .icns from the committed 1024px macOS app icon.
#    Falls back to the upstream 128px logo if the asset is missing (e.g. when
#    the script is run standalone outside the repo).
echo "==> Building app icon"
ICONSET="$WORK/NanoVNASaver.iconset"
mkdir -p "$ICONSET"
if [ -f "$SCRIPT_DIR/assets/AppIcon.png" ]; then
    SRC="$SCRIPT_DIR/assets/AppIcon.png"
else
    echo "    (assets/AppIcon.png not found — falling back to upstream logo)"
    SRC="$UI_SRC/logo_128x128.png"
fi
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
