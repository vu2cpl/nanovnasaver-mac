#!/usr/bin/env python3
"""Launch-time update check for the NanoVNASaver macOS build.

Asks GitHub for the latest release of vu2cpl/nanovnasaver-mac (the Mac
packaging users actually install) and, if it is newer than this bundle,
shows a native dialog: Download (opens the release page) / Skip This
Version / Later. Nothing is ever downloaded or installed automatically.

The bundle launcher (Contents/MacOS/NanoVNASaver, written by build.sh)
starts this script detached in the background, so it never delays the
app. Every failure (offline, HTTP error, rate limit, bad JSON, missing
plist key) is silent: one line in the app log, no dialog.

Only a successful check -- HTTP 200 and JSON with a usable tag_name,
newer or not -- stamps UpdateLastCheck, so the next check is 24 h after
it. A failed one stamps nothing, so the next launch simply tries again.
A development build (release version containing "dev", any case) never
checks by itself. (Manoj's decisions, 2026-10-09.)

Upstream NanoVNASaver's own "Check for updates" button (About window)
is left as it is: it only runs on demand and looks at the upstream
repo's tags, which carry no macOS build.

Preferences (macOS defaults, domain = the bundle identifier):
  CheckForUpdates       bool    default true; false turns the check off
  UpdateLastCheck       float   epoch seconds of the last successful check
  UpdateSkippedVersion  string  release tag the user chose to skip

  defaults write org.nanovna.saver CheckForUpdates -bool false

Test hook (inert unless set): NVNAS_UPDATE_TEST_VERSION=0.0.1 makes the
check pretend to be that version, ignores the 24 h throttle, the
skipped version and the development-build skip, and writes no
preferences. The off switch still wins.

Uses only the Python standard library plus /usr/bin/defaults,
/usr/bin/osascript and /usr/bin/open.

Copyright (C) 2026 Manoj Kumar R <vu2cpl@gmail.com>
SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import subprocess
import sys
import time
import urllib.request
from typing import Callable, Optional

REPO = "vu2cpl/nanovnasaver-mac"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases"
HTTP_TIMEOUT = 10  # seconds
CHECK_INTERVAL = 24 * 60 * 60  # next check 24 h after the last successful one
SHOW_NOT_BEFORE = 10.0  # seconds after launch: the app window is up, the dialog lands on top
MAX_BODY = 1_000_000  # bytes read from the API response

DEFAULTS_DOMAIN = "org.nanovna.saver"  # CFBundleIdentifier set by build.sh
PLIST_VERSION_KEY = "NVNASMacReleaseVersion"  # e.g. "0.7.3-mac1", set by build.sh
KEY_ENABLED = "CheckForUpdates"
KEY_LAST_CHECK = "UpdateLastCheck"
KEY_SKIPPED = "UpdateSkippedVersion"
TEST_ENV = "NVNAS_UPDATE_TEST_VERSION"

DIALOG_TITLE = "NanoVNASaver for Mac"
BTN_DOWNLOAD = "Download"
BTN_SKIP = "Skip This Version"
BTN_LATER = "Later"

_TAG_OK = re.compile(r"^[vV]?[0-9][0-9A-Za-z.\-]{0,40}$")


def log(msg: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"{stamp} [update-check] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------- pure logic


def version_tuple(version: str) -> tuple[int, ...]:
    """'v0.7.3-mac1' -> (0, 7, 3, 1): strip a leading v, keep the integers."""
    v = (version or "").strip()
    if v[:1] in ("v", "V"):
        v = v[1:]
    return tuple(int(n) for n in re.findall(r"\d+", v))


def compare_versions(a: str, b: str) -> int:
    """-1 / 0 / 1 like cmp(); missing trailing parts count as 0."""
    ta, tb = version_tuple(a), version_tuple(b)
    n = max(len(ta), len(tb))
    ta += (0,) * (n - len(ta))
    tb += (0,) * (n - len(tb))
    return (ta > tb) - (ta < tb)


def is_newer(latest: str, current: str) -> bool:
    """True when `latest` (a release tag) is newer than `current`.

    A tag with no digits at all is never treated as newer.
    """
    if not version_tuple(latest):
        return False
    return compare_versions(latest, current) > 0


def is_dev_version(version: Optional[str]) -> bool:
    """True for a development build: the release version contains "dev" (any case)."""
    return "dev" in (version or "").lower()


def check_due(now: float, last: Optional[float], interval: float = CHECK_INTERVAL) -> bool:
    """True when no check has succeeded within `interval` seconds.

    A last-check time in the future (clock moved back) counts as due.
    """
    if last is None:
        return True
    return now - last >= interval or now < last


def decide(latest: str, current: str, skipped: Optional[str]) -> str:
    """'update' | 'skipped' | 'current'."""
    if not is_newer(latest, current):
        return "current"
    if skipped and version_tuple(skipped) and compare_versions(skipped, latest) >= 0:
        return "skipped"
    return "update"


def display_version(tag: str) -> str:
    return tag[1:] if tag[:1] in ("v", "V") else tag


def release_page(tag: str, html_url: Optional[str]) -> str:
    """The release page to open, never anything outside this repo's releases."""
    if isinstance(html_url, str) and html_url.startswith(RELEASES_URL + "/"):
        return html_url
    if _TAG_OK.match(tag or ""):
        return f"{RELEASES_URL}/tag/{tag}"
    return f"{RELEASES_URL}/latest"


def parse_release(body: bytes) -> tuple[str, Optional[str]]:
    """(tag_name, html_url) from the API JSON; raises ValueError if unusable."""
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("release JSON is not an object")
    tag = data.get("tag_name")
    if not isinstance(tag, str) or not _TAG_OK.match(tag):
        raise ValueError(f"unusable tag_name: {tag!r}")
    html = data.get("html_url")
    return tag, html if isinstance(html, str) else None


# ------------------------------------------------------------- side effects


def fetch_latest(current: str, opener: Callable = urllib.request.urlopen) -> tuple[str, Optional[str]]:
    req = urllib.request.Request(
        API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"nanovnasaver-mac/{current}",
        },
    )
    with opener(req, timeout=HTTP_TIMEOUT) as resp:
        status = getattr(resp, "status", 200)
        if status != 200:
            raise ValueError(f"HTTP {status}")
        return parse_release(resp.read(MAX_BODY))


class Prefs:
    """Reads/writes the app's macOS defaults through /usr/bin/defaults."""

    def __init__(self, domain: str = DEFAULTS_DOMAIN):
        self.domain = domain

    def read(self, key: str) -> Optional[str]:
        try:
            r = subprocess.run(
                ["/usr/bin/defaults", "read", self.domain, key],
                capture_output=True, text=True, timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout.strip() if r.returncode == 0 else None

    def write(self, key: str, kind: str, value: str) -> None:
        try:
            subprocess.run(
                ["/usr/bin/defaults", "write", self.domain, key, kind, value],
                capture_output=True, timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            pass

    def enabled(self) -> bool:
        v = self.read(KEY_ENABLED)
        return v is None or v.strip().lower() not in ("0", "false", "no", "off")

    def last_check(self) -> Optional[float]:
        v = self.read(KEY_LAST_CHECK)
        try:
            return float(v) if v is not None else None
        except ValueError:
            return None

    def set_last_check(self, when: float) -> None:
        self.write(KEY_LAST_CHECK, "-float", f"{when:.0f}")

    def skipped(self) -> Optional[str]:
        return self.read(KEY_SKIPPED) or None

    def set_skipped(self, tag: str) -> None:
        self.write(KEY_SKIPPED, "-string", tag)


_DIALOG_SCRIPT = """on run argv
    set msg to item 1 of argv
    set ttl to item 2 of argv
    set iconPath to item 3 of argv
    set btns to {"%(later)s", "%(skip)s", "%(download)s"}
    activate
    if iconPath is "" then
        set r to display dialog msg with title ttl buttons btns default button "%(download)s" cancel button "%(later)s"%(giveup)s
    else
        set r to display dialog msg with title ttl buttons btns default button "%(download)s" cancel button "%(later)s" with icon (POSIX file iconPath)%(giveup)s
    end if
    return button returned of r
end run"""


def show_dialog(new_tag: str, current: str, icon: Optional[str], give_up_after: Optional[int] = None) -> str:
    """Native dialog via osascript; returns the button title.

    Esc, a timed-out dialog (empty button) or any osascript error count as Later.
    The message, title and icon path go in as argv, never into the script text.
    """
    giveup = f" giving up after {int(give_up_after)}" if give_up_after else ""
    script = _DIALOG_SCRIPT % {
        "later": BTN_LATER, "skip": BTN_SKIP, "download": BTN_DOWNLOAD, "giveup": giveup,
    }
    msg = (
        f"NanoVNASaver for Mac {display_version(new_tag)} is available "
        f"— you have {display_version(current)}.\n\n"
        "Download opens the release page in your browser."
    )
    icon_arg = icon if icon and os.path.isfile(icon) else ""
    try:
        r = subprocess.run(
            ["/usr/bin/osascript", "-e", script, msg, DIALOG_TITLE, icon_arg],
            capture_output=True, text=True,
        )
    except (OSError, subprocess.SubprocessError) as e:
        log(f"dialog failed: {e}")
        return BTN_LATER
    choice = r.stdout.strip()
    return choice if r.returncode == 0 and choice in (BTN_DOWNLOAD, BTN_SKIP) else BTN_LATER


def bundle_version(contents_dir: str) -> Optional[str]:
    try:
        with open(os.path.join(contents_dir, "Info.plist"), "rb") as f:
            v = plistlib.load(f).get(PLIST_VERSION_KEY)
    except (OSError, plistlib.InvalidFileException, ValueError):
        return None
    return v if isinstance(v, str) and version_tuple(v) else None


def pid_alive(pid: Optional[int]) -> bool:
    if not pid:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# ------------------------------------------------------------------- main


def run(args: argparse.Namespace) -> int:
    started = time.monotonic()
    prefs = Prefs()
    if not prefs.enabled():
        return 0

    real_version = bundle_version(args.contents)
    if real_version is None:
        log(f"no {PLIST_VERSION_KEY} in {args.contents}/Info.plist; not checking")
        return 0

    test_version = os.environ.get(TEST_ENV, "").strip()
    test_mode = bool(test_version)
    current = test_version if test_mode else real_version
    if test_mode:
        log(f"TEST MODE: pretending to be {current} (real {real_version}); no prefs written")

    automatic = not (test_mode or args.dry_run)
    if automatic and is_dev_version(real_version):
        log(f"{real_version} is a development build; not checking")
        return 0
    if automatic and not check_due(time.time(), prefs.last_check()):
        return 0

    try:
        tag, html = fetch_latest(real_version)
    except Exception as e:  # offline, HTTP error, rate limit, bad JSON: all silent
        log(f"check failed ({type(e).__name__}: {e}); trying again at the next launch")
        return 0
    if automatic:
        # Only a successful check is stamped (HTTP 200 + usable tag_name), so a
        # launch while offline or rate-limited is retried at the next launch.
        prefs.set_last_check(time.time())

    skipped = None if (test_mode or args.dry_run) else prefs.skipped()
    verdict = decide(tag, current, skipped)
    log(f"latest {tag}, have {current}: {verdict}")
    if args.dry_run or verdict != "update":
        return 0

    wait = SHOW_NOT_BEFORE - (time.monotonic() - started)
    if wait > 0:
        time.sleep(wait)
    if not pid_alive(args.pid):
        log("app has quit; not showing the dialog")
        return 0

    icon = os.path.join(args.contents, "Resources", "NanoVNASaver.icns")
    choice = show_dialog(tag, current, icon, args.dialog_timeout)
    log(f"user chose: {choice}")
    if choice == BTN_DOWNLOAD:
        subprocess.run(["/usr/bin/open", release_page(tag, html)], capture_output=True, timeout=30)
    elif choice == BTN_SKIP and not test_mode:
        prefs.set_skipped(tag)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="NanoVNASaver for Mac update check")
    p.add_argument("--contents", required=True, help="path to NanoVNASaver.app/Contents")
    p.add_argument("--pid", type=int, default=0, help="app PID; no dialog once it has exited")
    p.add_argument("--dry-run", action="store_true",
                   help="fetch and compare only: no throttle, no dialog, no prefs written")
    p.add_argument("--dialog-timeout", type=int, default=0,
                   help="seconds before the dialog closes itself as Later (testing)")
    args = p.parse_args(argv)
    try:
        return run(args)
    except Exception as e:  # never let the check disturb anything
        log(f"unexpected error ({type(e).__name__}: {e})")
        return 0


if __name__ == "__main__":
    sys.exit(main())
