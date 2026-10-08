# Handover — NanoVNASaver Mac build

_Last updated 2026-10-08._

Built a self-contained `.app` for NanoVNA-Saver (no upstream macOS binary exists), slimmed it heavily, and published it on GitHub (`vu2cpl/nanovnasaver-mac`, now a public repo).

## What changed

### 2026-10-08 — launch-time update check (unreleased — ships with the next release)

Part of Manoj's all-apps decision: every app gets an in-app check against its own GitHub releases in its next release — no Sparkle, no extra servers.

- **Where:** the wrapper layer, not upstream. `updater/update_check.py` (stdlib-only Python) is copied by `build.sh` to `Contents/Resources/update_check.py`; the bash launcher starts it detached (`( … & )` subshell, `-I`, stdin from /dev/null, output to the app log) and then `exec`s the app as before. No upstream file is patched for this.
- **What:** one anonymous `GET https://api.github.com/repos/vu2cpl/nanovnasaver-mac/releases/latest` (`Accept: application/vnd.github+json`, `User-Agent: nanovnasaver-mac/<version>`, 10 s timeout) at most once per 24 h (the attempt is stamped before the request, so offline launches do not retry until the next day). `tag_name` vs the bundle's version compared as integer tuples (`v0.7.3-mac1` → (0,7,3,1), missing parts = 0). If newer: osascript `display dialog` ~10 s after launch (so it sits on top of the app window), with the app icon — Download (opens the release `html_url`, only if it is under this repo's releases) / Skip This Version / Later. Not shown if the app has already quit. Never downloads anything.
- **Version source:** new Info.plist key `NVNASMacReleaseVersion` = `<upstream tag>-<MAC_REV>`; `MAC_REV` is a new `build.sh` env var, default `mac1`. `CFBundleShortVersionString` stays the upstream version (`0.7.3`).
- **Prefs:** `defaults` domain `org.nanovna.saver` (the bundle id; upstream uses INI files in `~/.config/NanoVNASaver/`, so the domain was unused): `CheckForUpdates` (default on), `UpdateLastCheck`, `UpdateSkippedVersion`.
- **Test hook:** `NVNAS_UPDATE_TEST_VERSION=0.0.1` pretends to be that version, ignores the throttle and the skip, writes no prefs. `--dry-run` fetches and prints only. `--dialog-timeout N` closes the dialog by itself (testing).
- **Upstream's own check:** About → "Check for updates" scrapes the upstream tags page; manual only, never automatic, untouched. It can report an upstream version before a Mac build of it exists.
- **Tests (2026-10-08):** `python3 -m unittest discover -s updater` — 18 pass. Live dry run read `v0.7.3-mac1` → "current". 404, 406 (HTML endpoint) and an unreachable host (10.0 s timeout) all silent, exit 0. Full `build.sh` run into a scratch dir (261 MB, `NVNASMacReleaseVersion` = `0.7.3-mac1`); its launcher returned in 1.6 s with the check still running, and that check met a real `403 rate limit exceeded` (the shack IP's 60/h anonymous quota was used up by the day's update-check testing across apps) — logged, no dialog. With the release data injected: dialog shown once with the test hook (app icon, three buttons, closed by `--dialog-timeout`); no dialog when the app PID had exited; throttle, Skip (and a newer tag re-prompting) and `CheckForUpdates false` verified against a scratch defaults domain. Not launched as a full GUI app; no NanoVNA connected.
- **When cutting the next release:** build with `MAC_REV=mac2` (or `mac1` on a new upstream tag) so `NVNASMacReleaseVersion` matches the release tag exactly — a mismatch makes every user see an update prompt for the release they already have. Mention the update check in the release notes.

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
| Remote | https://github.com/vu2cpl/nanovnasaver-mac (public) |
| Latest release | `v0.7.3-mac1` — `NanoVNASaver-v0.7.3-mac1-arm64.zip` (85 MB zip, 253 MB extracted). HEAD also has the PR #1 macOS-polish changes and the update check (2026-10-08); release artifact has not been re-cut. |
| Update check | `updater/update_check.py` → `Contents/Resources/update_check.py`, started by the launcher; prefs in `defaults` domain `org.nanovna.saver` |
| Built app | `/Applications/NanoVNASaver.app` (ad-hoc codesigned, native arm64) |
| Logs | `~/Library/Logs/NanoVNASaver/nanovnasaver.log` |

## Three undocumented build quirks (wheel-install fixes)

All three are handled inside `build.sh`:

1. Need `python` symlink in venv — upstream `setup.py` calls bare `python`
2. UI files (`about.py`, `main_rc.py`) must be compiled manually with `pyside6-uic` / `pyside6-rcc` after install — wheel doesn't ship them
3. Generated `about.py` has `import main_rc` → must be patched to `from . import main_rc`

Plus a fourth category of build-time patches for **macOS UI sizing** (see "What got done" above) — these are platform-specific tweaks, not wheel-install fixes, but live in the same script for the same reason: they're applied to the installed source tree before bundling.

## TODO

- [ ] **Next release** (`v0.7.3-mac2` or similar): build with the matching `MAC_REV`, note the new update check in the release notes. Ships PR #1 polish + the update check.
- [ ] **Not self-contained against Homebrew:** the bundle's `venv/bin/python3.12` is a symlink to `/opt/homebrew/opt/python@3.12/bin/python3.12` (seen 2026-10-08 on the installed copy; `python -m venv` symlinks by default). A Mac without Homebrew `python@3.12` would have no interpreter for the app. Not yet tested on such a Mac. A relocatable Python (python.org framework copied in, or python-build-standalone) would fix it — overlaps with the universal2 item.
- [ ] **Universal2 build** — install python.org universal2 Python 3.12, skip the lipo-thin step → single `.app` for both Intel + Apple Silicon
- [ ] Proper Developer ID codesigning + notarization (kill the `xattr -dr com.apple.quarantine` step)
- [ ] CI: GitHub Actions on `macos-14` + `macos-13` runners

## Memory written for future Claude sessions

- `nanovnasaver_app.md` — what the bundle is, where it lives, what was kept/stripped
- `nanovnasaver_build_recipe.md` — the three wheel-install quirks + macOS UI sizing patches
- `project_working_dirs.md` (pre-existing) — flags `~/projects/` as canonical, not `~/Documents/Claude/code/`

Pick up by reading those three plus this file and `README.md`. Next concrete task is the universal2 / Intel build.
