# Handover — NanoVNASaver Mac build

_Last updated 2026-10-09._

Built a self-contained `.app` for NanoVNA-Saver (no upstream macOS binary exists), slimmed it heavily, and published it on GitHub (`vu2cpl/nanovnasaver-mac`, now a public repo).

## What changed

### 2026-10-09 — update check follow-up + `MAC_REV` required (unreleased — ships with the next release)

Manoj's decisions for the update check (same day as the bundled Python below):

- **Stamp only a successful check.** `UpdateLastCheck` is now written only after HTTP 200 + JSON with a usable `tag_name` (newer or not), right after the fetch and before any dialog. Offline, timeout, any HTTP error incl. the 403 rate limit, a non-200 status or bad JSON stamp nothing, so the next launch tries again (the check is launch-only, so no in-memory back-off). Before this, the attempt was stamped before the request and an offline launch silenced the check for a day. The 24 h throttle (`check_due`) is unchanged, it now counts from the last success.
- **Development builds don't check by themselves.** A release version containing "dev" (any case, e.g. `0.7.4.dev1-mac1`, or `development-mac1` from a branch build) logs one line and exits before any request. `NVNAS_UPDATE_TEST_VERSION` still checks (it already ignored the throttle and the skip), and so does the manual `--dry-run`. Note `MAC_REV` must still match `^mac[0-9]+$`, so "dev" can only come from the upstream tag/branch passed to `build.sh`.
- **`build.sh` refuses to build without an explicit `MAC_REV`.** The `mac1` default is gone: an unset or empty `MAC_REV` prints an error with the example `MAC_REV=mac2 ./build.sh v0.7.3` (to stderr) and exits 1 before any work — no download, no `rm -rf` of the destination. Usage comment, README (Usage + the `MAC_REV` paragraph) updated.
- **Tests (2026-10-09):** `python3 -m unittest discover -s updater` — 18 → 28 pass. New `Run` cases drive `main()` with fake prefs/fetch/dialog: a successful check stamps (current and newer), seven failure kinds stamp nothing, a failure keeps the last success's time, an offline launch is retried at the next launch and then throttled after the success, a recent success throttles, dev detection (any case), a dev build makes no request, the test hook and `--dry-run` still check a dev build and save nothing; plus `fetch_latest` treating HTTP 203 as a failure. `bash -n build.sh` clean; `build.sh` run with `MAC_REV` unset, empty and `foo` exited 1 at once with nothing created (scratch destination and cache). No live GitHub call, no rebuild, `/Applications/NanoVNASaver.app` untouched — it is still the `f5ce279` build, which has the old stamp-the-attempt behaviour.

### 2026-10-09 — the app carries its own Python (unreleased — ships with the next release)

Manoj: "fix it, bundle python in the app" (after the update-check work found the bundle's `venv/bin/python3.12` was a symlink to Homebrew's `python@3.12`, so the app could not start on a Mac without it; size was never the reason — `python -m venv` symlinks by default).

- **What:** `build.sh` now bundles CPython 3.12.15 from Astral's python-build-standalone (`cpython-3.12.15+20261003-aarch64-apple-darwin-install_only_stripped.tar.gz`, 23.8 MB, release `20261003`), pinned by version + SHA-256 (`ad8d0c63…b481a2`, from the release's SHA256SUMS), downloaded once into `~/Library/Caches/nanovnasaver-mac` (`NVNAS_CACHE` overrides) and unpacked to `Contents/Resources/python/`. NanoVNASaver is pip-installed straight into it — no venv; the launcher runs `Resources/python/bin/python3`. The `PYTHON=` build variable and the Homebrew requirement are gone.
- **Why this Python:** relocatable by design (what `uv` installs), links only `/usr/lib` and `/System` libraries, OpenSSL built in with its default CA file at macOS's `/private/etc/ssl/cert.pem`, and already has `bin/python`. Copying Homebrew's Python instead would have meant rewriting the links of OpenSSL, SQLite, xz and mpdecimal, replacing its `site-packages` symlink, and fixing its CA path (`/opt/homebrew/etc/openssl@3`) — HTTPS would have failed without Homebrew.
- **New build steps:** 12 slims the bundled Python (Tk/Tcl, IDLE, turtle demos, headers, `share/`); 13 fails the build if any Mach-O load command points outside `/usr/lib`, `/System` or the bundle (`@rpath`/`@loader_path`/`@executable_path`), or any symlink points outside the bundle. Run read-only against the installed v0.7.3-mac1 app, the symlink check flags exactly `venv/bin/python3.12 -> /opt/homebrew/opt/python@3.12/bin/python3.12`.
- **Size:** 1.4 GB → 306 MB (was ~252 MB); the zip will grow by roughly 15–20 MB.
- **Tested 2026-10-09** (scratch build, 38 s with a warm cache): under `sandbox-exec` denying reads of `/opt/homebrew` and `/usr/local` — where Homebrew's own Python cannot even exec — the bundled Python ran and imported ssl/sqlite3/lzma/decimal/ctypes; `update_check.py --dry-run` reached GitHub over HTTPS ("latest v0.7.3-mac1 … current"); `python3 -m NanoVNASaver` opened its full main window with a scratch `HOME`, and `vmmap`/`lsof` showed 0 Homebrew files mapped. Launched normally (`open`, through the launcher, a copy with the update check removed so no prefs were written) Launch Services registered it as "NanoVNASaver", bundle id `org.nanovna.saver`, Version 0.7.3 — the Dock/menu show the app, not "python3" (that name appears only when its Python is started by hand). The real `~/.config/NanoVNASaver/*.ini` (7 Jul) were untouched and no `org.nanovna.saver` preferences were created. No NanoVNA connected. Not yet run on a second Mac.

### 2026-10-08 — launch-time update check (unreleased — ships with the next release)

Part of Manoj's all-apps decision: every app gets an in-app check against its own GitHub releases in its next release — no Sparkle, no extra servers.

- **Where:** the wrapper layer, not upstream. `updater/update_check.py` (stdlib-only Python) is copied by `build.sh` to `Contents/Resources/update_check.py`; the bash launcher starts it detached (`( … & )` subshell, `-I`, stdin from /dev/null, output to the app log) and then `exec`s the app as before. No upstream file is patched for this.
- **What:** one anonymous `GET https://api.github.com/repos/vu2cpl/nanovnasaver-mac/releases/latest` (`Accept: application/vnd.github+json`, `User-Agent: nanovnasaver-mac/<version>`, 10 s timeout) at most once per 24 h (as first built the attempt was stamped before the request, so offline launches did not retry until the next day — changed 2026-10-09, see above: only a successful check is stamped). `tag_name` vs the bundle's version compared as integer tuples (`v0.7.3-mac1` → (0,7,3,1), missing parts = 0). If newer: osascript `display dialog` ~10 s after launch (so it sits on top of the app window), with the app icon — Download (opens the release `html_url`, only if it is under this repo's releases) / Skip This Version / Later. Not shown if the app has already quit. Never downloads anything.
- **Version source:** new Info.plist key `NVNASMacReleaseVersion` = `<upstream tag>-<MAC_REV>`; `MAC_REV` is a new `build.sh` env var (defaulted to `mac1` at first; required, no default, since 2026-10-09). `CFBundleShortVersionString` stays the upstream version (`0.7.3`).
- **Prefs:** `defaults` domain `org.nanovna.saver` (the bundle id; upstream uses INI files in `~/.config/NanoVNASaver/`, so the domain was unused): `CheckForUpdates` (default on), `UpdateLastCheck`, `UpdateSkippedVersion`.
- **Test hook:** `NVNAS_UPDATE_TEST_VERSION=0.0.1` pretends to be that version, ignores the throttle and the skip, writes no prefs. `--dry-run` fetches and prints only. `--dialog-timeout N` closes the dialog by itself (testing).
- **Upstream's own check:** About → "Check for updates" scrapes the upstream tags page; manual only, never automatic, untouched. It can report an upstream version before a Mac build of it exists.
- **Tests (2026-10-08):** `python3 -m unittest discover -s updater` — 18 pass. Live dry run read `v0.7.3-mac1` → "current". 404, 406 (HTML endpoint) and an unreachable host (10.0 s timeout) all silent, exit 0. Full `build.sh` run into a scratch dir (261 MB, `NVNASMacReleaseVersion` = `0.7.3-mac1`); its launcher returned in 1.6 s with the check still running, and that check met a real `403 rate limit exceeded` (the shack IP's 60/h anonymous quota was used up by the day's update-check testing across apps) — logged, no dialog. With the release data injected: dialog shown once with the test hook (app icon, three buttons, closed by `--dialog-timeout`); no dialog when the app PID had exited; throttle, Skip (and a newer tag re-prompting) and `CheckForUpdates false` verified against a scratch defaults domain. Not launched as a full GUI app; no NanoVNA connected.
- **When cutting the next release:** build with `MAC_REV=mac2` (or `mac1` on a new upstream tag) so `NVNASMacReleaseVersion` matches the release tag exactly — a mismatch makes every user see an update prompt for the release they already have (`build.sh` now refuses to run without `MAC_REV`). Mention the update check in the release notes.

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
| Update check | `updater/update_check.py` → `Contents/Resources/update_check.py`, started by the launcher; prefs in `defaults` domain `org.nanovna.saver`; stamps only successful checks and skips dev builds since 2026-10-09 (unreleased) |
| Built app | `/Applications/NanoVNASaver.app` — local build of `f5ce279` (bundled Python, update check), installed 2026-10-09 04:50 on Manoj's "install the new build in applications": 306 MB, `NVNASMacReleaseVersion` 0.7.3-mac1, not codesigned (neither was the copy it replaced, now in the Trash). Verified with /opt/homebrew + /usr/local hidden: NanoVNASaver/PySide6/numpy/ssl import, update check "current". Manoj opened it 2026-10-09: "works fine". (The "Check for updates" he saw in About is upstream's manual check of NanoVNA-Saver's own releases; ours runs silently at launch, no button.) |
| Logs | `~/Library/Logs/NanoVNASaver/nanovnasaver.log` |

## Three undocumented build quirks (wheel-install fixes)

All three are handled inside `build.sh`:

1. Need a `python` command — upstream `setup.py` calls bare `python` (the bundled python-build-standalone Python has `bin/python`; the old venv needed a symlink)
2. UI files (`about.py`, `main_rc.py`) must be compiled manually with `pyside6-uic` / `pyside6-rcc` after install — wheel doesn't ship them
3. Generated `about.py` has `import main_rc` → must be patched to `from . import main_rc`

Plus a fourth category of build-time patches for **macOS UI sizing** (see "What got done" above) — these are platform-specific tweaks, not wheel-install fixes, but live in the same script for the same reason: they're applied to the installed source tree before bundling.

## TODO

- [ ] **Next release** (`v0.7.3-mac2` or similar): build with the matching `MAC_REV` (required now), note the new update check in the release notes. Ships PR #1 polish, the bundled Python and the update check (with the 2026-10-09 follow-up).
- [x] ~~**Not self-contained against Homebrew**~~ — DONE 2026-10-09: the app bundles its own Python (python-build-standalone 3.12.15), see "What changed". The released v0.7.3-mac1 zip still has the Homebrew symlink until the next release; the installed `/Applications` copy was replaced with a build of `f5ce279` on 2026-10-09.
- [ ] **Universal2 build** — install python.org universal2 Python 3.12, skip the lipo-thin step → single `.app` for both Intel + Apple Silicon
- [ ] Proper Developer ID codesigning + notarization (kill the `xattr -dr com.apple.quarantine` step)
- [ ] CI: GitHub Actions on `macos-14` + `macos-13` runners

## Memory written for future Claude sessions

- `nanovnasaver_app.md` — what the bundle is, where it lives, what was kept/stripped
- `nanovnasaver_build_recipe.md` — the three wheel-install quirks + macOS UI sizing patches
- `project_working_dirs.md` (pre-existing) — flags `~/projects/` as canonical, not `~/Documents/Claude/code/`

Pick up by reading those three plus this file and `README.md`. Next concrete task is the universal2 / Intel build.
