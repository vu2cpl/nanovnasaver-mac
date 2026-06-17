# NanoVNASaver.app — Mac build recipe

[NanoVNA-Saver](https://github.com/NanoVNA-Saver/nanovna-saver) ships official binaries for Windows and Raspberry Pi only. This repo builds a self-contained `.app` bundle for macOS (Apple Silicon), then slims it from the default ~1.3 GB pip install down to ~250 MB by stripping unused Qt modules and the x86_64 universal-binary slices.

## Usage

```bash
./build.sh                 # builds v0.7.3 → ~/Applications/NanoVNASaver.app
./build.sh v0.7.3          # explicit version
./build.sh v0.7.3 /Applications/NanoVNASaver.app   # custom destination
```

Requires Python 3.10+ at `/opt/homebrew/bin/python3.12` (override with `PYTHON=...`). Apple Silicon assumed — the `lipo` thinning step is skipped on Intel.

## What the script does

1. Creates a fresh `.app` bundle with `Contents/{MacOS,Resources}` layout.
2. Builds an isolated Python venv inside `Contents/Resources/venv/`.
3. Adds a `python` symlink (the upstream `setup.py` calls bare `python` and breaks without it).
4. `pip install`s NanoVNASaver from the GitHub tag.
5. Compiles `.ui` and `.qrc` files manually with `pyside6-uic` / `pyside6-rcc` — the wheel install skips this step.
6. Patches the generated `about.py` to fix a broken `import main_rc` (changes it to `from . import main_rc`).
   - **macOS UI sizing fixes** — upstream hard-codes control sizes (`setFixedHeight(20)`, `setFixedWidth(60)`) tuned for Windows/Linux. On macOS the native control chrome (taller fields, focus-ring margins, larger system font) needs more room, so Qt clips text (`50kHz`→`50kH`, `Sweep`→`Sweer`, `Rescan`→`Rescar`). The script relaxes the fixed sizes to minimums and widens the control column slightly.
7. Writes a bash launcher at `Contents/MacOS/NanoVNASaver` that execs the bundled venv Python; logs go to `~/Library/Logs/NanoVNASaver/nanovnasaver.log`.
8. Generates `Info.plist` and a multi-resolution `.icns` from the committed [`assets/AppIcon.png`](assets/AppIcon.png) — a 1024px macOS-style icon (rounded square + the NanoVNASaver Smith-chart logo). Regenerate it with [`assets/make_icon.py`](assets/make_icon.py). Falls back to the upstream 128px logo if the asset is missing.
9. **Slim Qt** — keeps only the frameworks NanoVNASaver actually imports (`QtCore`, `QtGui`, `QtWidgets`) plus safe runtime deps (`QtNetwork`, `QtDBus`, `QtPrintSupport`, `QtSvg`, `QtSvgWidgets`). Deletes everything else, including `QtWebEngineCore` (~590 MB of Chromium), all 3D/Qml/Multimedia/Charts/etc., plus `Qt/qml`, `Qt/translations`, `Qt/metatypes`, `Qt/libexec`.
10. **Slim plugins** — keeps `platforms`, `imageformats`, `styles`, `iconengines`, `tls`, `networkinformation`, `platforminputcontexts`, `generic`. Drops the rest.
11. **Thin** — runs `lipo -thin arm64` over every universal Mach-O in the bundle, since Python itself is arm64-only and the x86_64 slices are dead weight.

## Result

| Stage | Size |
|---|---|
| Raw `pip install` | ~1.3 GB |
| After Qt slim | ~360 MB |
| After arm64 thin | ~250 MB |

App runs natively on Apple Silicon (no Rosetta).

## TODO

- [ ] **Universal2 build (Intel + Apple Silicon in one bundle).** Requires installing python.org's universal2 Python 3.12 (one-time `sudo installer -pkg`), then rebuilding with the `lipo -thin` step skipped. Result is a single `.app` that runs natively on both architectures. Alternative: separate `arm64` and `x86_64` zips on the release page (build the Intel one with `arch -x86_64` + `lipo -thin x86_64`).
- [ ] Proper Developer ID codesigning + notarization, so the `xattr` quarantine workaround is no longer needed.
- [ ] CI: GitHub Actions on `macos-14` (arm64) and `macos-13` (Intel) runners to auto-build on tag push.

## License

Licensed under the [GNU General Public License v3.0 or later](LICENSE) (GPL-3.0-or-later), matching the [upstream NanoVNA-Saver license](https://github.com/NanoVNA-Saver/nanovna-saver/blob/main/licenses/LICENSE.txt). The bundled `.app` redistributes the upstream Python source and PySide6 (LGPL-3.0); both are compatible with GPL-3.0.

## Why each fix is needed

These are upstream quirks that make a vanilla `pip install` non-functional on macOS:

- **`python` symlink** — `setuptools_wrapper.py` calls `subprocess.call(['python', ...])`. A fresh venv only has `python3`, so the wheel build aborts with `FileNotFoundError`.
- **Manual UI compile** — the wheel-build hook tries to invoke `pyside6-uic` but the generated files don't end up in the installed package. Importing `NanoVNASaver` fails with `ModuleNotFoundError: NanoVNASaver.Windows.ui.about`.
- **`main_rc` import** — `pyside6-uic` writes `import main_rc` (top-level) but the file lives inside the package. Python 3 raises `ModuleNotFoundError: No module named 'main_rc'`.
