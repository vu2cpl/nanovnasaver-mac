# NanoVNASaver.app — Mac build recipe

[NanoVNA-Saver](https://github.com/NanoVNA-Saver/nanovna-saver) ships official binaries for Windows and Raspberry Pi only. This repo builds a self-contained `.app` bundle for macOS (Apple Silicon), with its own Python inside, then slims it from the default ~1.4 GB pip install down to ~305 MB by stripping unused Qt modules and the x86_64 universal-binary slices. It runs on a Mac without Homebrew or any other Python installed.

## Usage

```bash
MAC_REV=mac2 ./build.sh                 # builds v0.7.3 → ~/Applications/NanoVNASaver.app (release version 0.7.3-mac2)
MAC_REV=mac2 ./build.sh v0.7.3          # explicit version
MAC_REV=mac2 ./build.sh v0.7.3 /Applications/NanoVNASaver.app   # custom destination
```

`MAC_REV` is required — see below.

Needs `git`, `curl` and the Xcode command-line tools (`lipo`, `otool`, `sips`, `iconutil`) — no Homebrew and no installed Python. The build downloads a pinned relocatable CPython (3.12.15 from Astral's [python-build-standalone](https://github.com/astral-sh/python-build-standalone), ~24 MB) once, checks its SHA-256 against the value in `build.sh`, caches it in `~/Library/Caches/nanovnasaver-mac` (override with `NVNAS_CACHE=...`) and bundles it. Apple Silicon assumed — the `lipo` thinning step is skipped on Intel.

The bundle carries a **release version** = upstream tag + this repo's packaging revision, e.g. `0.7.3-mac2` (Info.plist key `NVNASMacReleaseVersion`). The revision comes from `MAC_REV` (`mac1`, `mac2`, …), which has **no default**: without it `build.sh` prints an error with an example and exits before doing any work or downloads. It must match the GitHub release tag the build is published as, because the update check compares the two — a mismatch would tell every user about an "update" to the version they already run:

```bash
MAC_REV=mac2 ./build.sh v0.7.3     # bundle for release tag v0.7.3-mac2
```

## What the script does

1. Creates a fresh `.app` bundle with `Contents/{MacOS,Resources}` layout.
2. Unpacks the bundled Python into `Contents/Resources/python/` (fetched once and checksum-verified, see above). It is relocatable, links only macOS system libraries, and its OpenSSL reads macOS's own `/private/etc/ssl/cert.pem`, so HTTPS (the update check) works without Homebrew.
3. That Python already provides a `python` command, which the upstream `setup.py` calls bare (it breaks without it).
4. `pip install`s NanoVNASaver from the GitHub tag straight into the bundled Python (no venv).
5. Compiles `.ui` and `.qrc` files manually with `pyside6-uic` / `pyside6-rcc` — the wheel install skips this step.
6. Patches the generated `about.py` to fix a broken `import main_rc` (changes it to `from . import main_rc`).
   - **macOS UI sizing fixes** — upstream hard-codes control sizes (`setFixedHeight(20)`, `setFixedWidth(60)`) tuned for Windows/Linux. On macOS the native control chrome (taller fields, focus-ring margins, larger system font) needs more room, so Qt clips text (`50kHz`→`50kH`, `Sweep`→`Sweer`, `Rescan`→`Rescar`). The script relaxes the fixed sizes to minimums and widens the control column slightly.
7. Writes a bash launcher at `Contents/MacOS/NanoVNASaver` that execs the bundled Python; logs go to `~/Library/Logs/NanoVNASaver/nanovnasaver.log`. Before the exec it starts the [update check](#update-check) (`Contents/Resources/update_check.py`, copied from [`updater/`](updater/)) detached in the background.
8. Generates `Info.plist` and a multi-resolution `.icns` from the committed [`assets/AppIcon.png`](assets/AppIcon.png) — a 1024px macOS-style icon (rounded square + the NanoVNASaver Smith-chart logo). Regenerate it with [`assets/make_icon.py`](assets/make_icon.py). Falls back to the upstream 128px logo if the asset is missing.
9. **Slim Qt** — keeps only the frameworks NanoVNASaver actually imports (`QtCore`, `QtGui`, `QtWidgets`) plus safe runtime deps (`QtNetwork`, `QtDBus`, `QtPrintSupport`, `QtSvg`, `QtSvgWidgets`). Deletes everything else, including `QtWebEngineCore` (~590 MB of Chromium), all 3D/Qml/Multimedia/Charts/etc., plus `Qt/qml`, `Qt/translations`, `Qt/metatypes`, `Qt/libexec`.
10. **Slim plugins** — keeps `platforms`, `imageformats`, `styles`, `iconengines`, `tls`, `networkinformation`, `platforminputcontexts`, `generic`. Drops the rest.
11. **Thin** — runs `lipo -thin arm64` over every universal Mach-O in the bundle, since Python itself is arm64-only and the x86_64 slices are dead weight.
12. **Slim the bundled Python** — drops Tk/Tcl, IDLE, turtle demos and the C headers, which a Qt app never uses at run time.
13. **Self-contained check** — fails the build if any binary in the bundle loads a library from outside macOS or the bundle (e.g. `/opt/homebrew`), or any symlink points outside the bundle.

## Result

| Stage | Size |
|---|---|
| Raw `pip install` (with bundled Python) | ~1.4 GB |
| After Qt slim, arm64 thin and Python slim | ~305 MB |

The bundled Python accounts for about 50 MB of that; until 2026-10-09 the app (~250 MB) borrowed Homebrew's `python@3.12` instead and did not start without it.

App runs natively on Apple Silicon (no Rosetta).

## Update check

*Unreleased — ships with the next release (v0.7.3-mac1 does not have it).*

At launch, at most once every 24 hours, the app asks GitHub for the latest release of **this** repo (`vu2cpl/nanovnasaver-mac`, the Mac build you install) — one anonymous `GET https://api.github.com/repos/vu2cpl/nanovnasaver-mac/releases/latest`, no token, 10 s timeout, nothing else sent. If that release is newer than the one you are running (numeric compare, so `v0.7.3-mac2` > `0.7.3-mac1` and `v0.7.4-mac1` > `0.7.3-mac9`), a native macOS dialog appears about 10 seconds after launch:

> NanoVNASaver for Mac 0.7.3-mac2 is available — you have 0.7.3-mac1.

- **Download** opens the release page in your browser. Nothing is downloaded or installed automatically.
- **Skip This Version** hides that release; you are asked again only when a newer one appears.
- **Later** (or Esc) asks again after the next 24 h.

The check runs in a separate background process started by the launcher, so it never delays the app, and it is silent on any failure (offline, rate-limited, GitHub error) apart from one line in `~/Library/Logs/NanoVNASaver/nanovnasaver.log`. The 24 hours count from the last check that got an answer (HTTP 200 with a release tag): a launch while offline or rate-limited saves nothing, so the next launch simply tries again. A development build (release version containing `dev`) never checks by itself.

Turn it off (or back on):

```bash
defaults write org.nanovna.saver CheckForUpdates -bool false
defaults delete org.nanovna.saver CheckForUpdates     # back to the default (on)
```

Other keys in the same domain: `UpdateLastCheck` (time of the last successful check) and `UpdateSkippedVersion` (the skipped release tag); `defaults delete org.nanovna.saver` resets all three. Upstream NanoVNA-Saver keeps its own settings in `~/.config/NanoVNASaver/` and is not affected.

Upstream's own **About → Check for updates** button is unchanged: it runs only when clicked and looks at the upstream repo's tags, which are the Python releases, not this Mac build.

For developers:

```bash
python3 -m unittest discover -s updater            # unit tests (version compare, throttle, parsing, what gets stamped, dev skip)
# live check, prints the verdict, no dialog, nothing saved (point --contents at a built bundle):
python3 updater/update_check.py --contents /Applications/NanoVNASaver.app/Contents --dry-run
# show the dialog once: pretend to be 0.0.1 (ignores the 24 h limit, the skip and a dev build, saves nothing)
NVNAS_UPDATE_TEST_VERSION=0.0.1 python3 updater/update_check.py --contents /Applications/NanoVNASaver.app/Contents
```

## TODO

- [ ] **Universal2 build (Intel + Apple Silicon in one bundle).** Requires installing python.org's universal2 Python 3.12 (one-time `sudo installer -pkg`), then rebuilding with the `lipo -thin` step skipped. Result is a single `.app` that runs natively on both architectures. Alternative: separate `arm64` and `x86_64` zips on the release page (build the Intel one with `arch -x86_64` + `lipo -thin x86_64`).
- [ ] Proper Developer ID codesigning + notarization, so the `xattr` quarantine workaround is no longer needed.
- [ ] CI: GitHub Actions on `macos-14` (arm64) and `macos-13` (Intel) runners to auto-build on tag push.

## License

Licensed under the [GNU General Public License v3.0 or later](LICENSE) (GPL-3.0-or-later), matching the [upstream NanoVNA-Saver license](https://github.com/NanoVNA-Saver/nanovna-saver/blob/main/licenses/LICENSE.txt). The bundled `.app` redistributes the upstream Python source, PySide6 (LGPL-3.0) and CPython from [python-build-standalone](https://github.com/astral-sh/python-build-standalone) (PSF License, plus the licences of the libraries it builds in); all are compatible with GPL-3.0.

## Why each fix is needed

These are upstream quirks that make a vanilla `pip install` non-functional on macOS:

- **`python` command** — `setuptools_wrapper.py` calls `subprocess.call(['python', ...])`. A fresh venv only has `python3`, so the wheel build aborts with `FileNotFoundError`. The bundled python-build-standalone Python ships `bin/python`, so no symlink is needed any more; `build.sh` puts its `bin/` first on `PATH` for the install.
- **Manual UI compile** — the wheel-build hook tries to invoke `pyside6-uic` but the generated files don't end up in the installed package. Importing `NanoVNASaver` fails with `ModuleNotFoundError: NanoVNASaver.Windows.ui.about`.
- **`main_rc` import** — `pyside6-uic` writes `import main_rc` (top-level) but the file lives inside the package. Python 3 raises `ModuleNotFoundError: No module named 'main_rc'`.
