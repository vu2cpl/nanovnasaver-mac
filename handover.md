# Handover — NanoVNASaver Mac build

Built a self-contained `.app` for NanoVNA-Saver (no upstream macOS binary exists), slimmed it heavily, and published it to a private GitHub repo.

## What got done

- **1.3 GB → 253 MB** via two passes:
  - Stripped unused Qt frameworks/plugins (kept QtCore/Gui/Widgets + Network/DBus/PrintSupport/Svg/SvgWidgets)
  - `lipo -thin arm64` on 66 universal2 Mach-O files (Python is arm64-only → x86_64 slices were dead weight)
- Wrapped all of it in a reproducible `build.sh` script.
- Released **v0.7.3-mac1** (arm64) on GitHub.

## Current state

| Thing | Where |
|---|---|
| Source repo | `~/projects/nanovnasaver-mac/` |
| Remote | https://github.com/vu2cpl/nanovnasaver-mac (private) |
| Latest release | `v0.7.3-mac1` — `NanoVNASaver-v0.7.3-mac1-arm64.zip` (85 MB zip, 253 MB extracted) |
| Built app | `/Applications/NanoVNASaver.app` (ad-hoc codesigned, native arm64) |
| Logs | `~/Library/Logs/NanoVNASaver/nanovnasaver.log` |

## Three undocumented build quirks

All three are handled inside `build.sh`:

1. Need `python` symlink in venv — upstream `setup.py` calls bare `python`
2. UI files (`about.py`, `main_rc.py`) must be compiled manually with `pyside6-uic` / `pyside6-rcc` after install — wheel doesn't ship them
3. Generated `about.py` has `import main_rc` → must be patched to `from . import main_rc`

## TODO

- [ ] **Universal2 build** — install python.org universal2 Python 3.12, skip the lipo-thin step → single `.app` for both Intel + Apple Silicon
- [ ] Proper Developer ID codesigning + notarization (kill the `xattr -dr com.apple.quarantine` step)
- [ ] CI: GitHub Actions on `macos-14` + `macos-13` runners

## Memory written for future Claude sessions

- `nanovnasaver_app.md` — what the bundle is, where it lives, what was kept/stripped
- `nanovnasaver_build_notes.md` — the three build quirks
- `project_working_dirs.md` (pre-existing) — flags `~/projects/` as canonical, not `~/Documents/Claude/code/`

Pick up by reading those three plus this file and `README.md`. Next concrete task is the universal2 / Intel build.
