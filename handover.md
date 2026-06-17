# Handover — NanoVNASaver Mac build

Built a self-contained `.app` for NanoVNA-Saver (no upstream macOS binary exists), slimmed it heavily, and published it to a private GitHub repo.

## What got done

- **1.3 GB → 252 MB** via two passes:
  - Stripped unused Qt frameworks/plugins (kept QtCore/Gui/Widgets + Network/DBus/PrintSupport/Svg/SvgWidgets)
  - `lipo -thin arm64` on 66 universal2 Mach-O files (Python is arm64-only → x86_64 slices were dead weight)
- Wrapped all of it in a reproducible `build.sh` script.
- Released **v0.7.3-mac1** (arm64) on GitHub.
- **macOS polish (PR #1, merged 2026-06-17):**
  - Committed 1024px macOS-style app icon at `assets/AppIcon.png` (rounded square + Smith-chart logo) — build.sh now builds `.icns` from it instead of upscaling the upstream 128px logo. Regenerate with `assets/make_icon.py` (Pillow).
  - Relaxed upstream's `setFixedHeight(20)` / `setFixedWidth(60)` on `SweepControl` / `MarkerControl` / `SerialControl` / `Marker/Widget.py` to minimums (24h, 80w / 72w) — macOS native control chrome was clipping text (`50kHz`→`50kH`, `Sweep`→`Sweer`, `Rescan`→`Rescar`, `Center`→`Cent`). Widened the left control column from 250→300px so the two-column Start/Stop|Center/Span forms fit.
  - Added trailing `addStretch(1)` to `marker_data_layout` so the three Marker boxes stay compact on resize instead of inflating to fill the scrollable column.
  - Capped S11/S21 summary boxes + "Analysis ..." button at `int(340 * scale_factor)` (same cap the Marker boxes use) — they no longer stretch horizontally on resize.

## Current state

| Thing | Where |
|---|---|
| Source repo | `~/projects/nanovnasaver-mac/` |
| Remote | https://github.com/vu2cpl/nanovnasaver-mac (private) |
| Latest release | `v0.7.3-mac1` — `NanoVNASaver-v0.7.3-mac1-arm64.zip` (85 MB zip, 253 MB extracted). Local build at HEAD is 252 MB and includes the PR #1 macOS-polish changes; release artifact has not been re-cut. |
| Built app | `/Applications/NanoVNASaver.app` (ad-hoc codesigned, native arm64) |
| Logs | `~/Library/Logs/NanoVNASaver/nanovnasaver.log` |

## Three undocumented build quirks (wheel-install fixes)

All three are handled inside `build.sh`:

1. Need `python` symlink in venv — upstream `setup.py` calls bare `python`
2. UI files (`about.py`, `main_rc.py`) must be compiled manually with `pyside6-uic` / `pyside6-rcc` after install — wheel doesn't ship them
3. Generated `about.py` has `import main_rc` → must be patched to `from . import main_rc`

Plus a fourth category of build-time patches for **macOS UI sizing** (see "What got done" above) — these are platform-specific tweaks, not wheel-install fixes, but live in the same script for the same reason: they're applied to the installed source tree before bundling.

## TODO

- [ ] **Universal2 build** — install python.org universal2 Python 3.12, skip the lipo-thin step → single `.app` for both Intel + Apple Silicon
- [ ] Proper Developer ID codesigning + notarization (kill the `xattr -dr com.apple.quarantine` step)
- [ ] CI: GitHub Actions on `macos-14` + `macos-13` runners

## Memory written for future Claude sessions

- `nanovnasaver_app.md` — what the bundle is, where it lives, what was kept/stripped
- `nanovnasaver_build_recipe.md` — the three wheel-install quirks + macOS UI sizing patches
- `project_working_dirs.md` (pre-existing) — flags `~/projects/` as canonical, not `~/Documents/Claude/code/`

Pick up by reading those three plus this file and `README.md`. Next concrete task is the universal2 / Intel build.
