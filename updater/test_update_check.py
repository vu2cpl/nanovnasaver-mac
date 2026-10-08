"""Unit tests for update_check.py — run: python3 -m unittest discover -s updater

Copyright (C) 2026 Manoj Kumar R <vu2cpl@gmail.com>
SPDX-License-Identifier: GPL-3.0-or-later
"""

import io
import json
import os
import plistlib
import tempfile
import time
import unittest
import urllib.error

import update_check as uc


class VersionTuple(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(uc.version_tuple("v0.7.3-mac1"), (0, 7, 3, 1))
        self.assertEqual(uc.version_tuple("0.7.3-mac1"), (0, 7, 3, 1))
        self.assertEqual(uc.version_tuple("V1.2"), (1, 2))
        self.assertEqual(uc.version_tuple("0.7.10-mac12"), (0, 7, 10, 12))
        self.assertEqual(uc.version_tuple(" v0.7.3 "), (0, 7, 3))
        self.assertEqual(uc.version_tuple(""), ())
        self.assertEqual(uc.version_tuple("mac"), ())
        self.assertEqual(uc.version_tuple(None), ())


class Compare(unittest.TestCase):
    def test_numeric_not_lexical(self):
        self.assertTrue(uc.is_newer("v0.7.10-mac1", "0.7.9-mac1"))
        self.assertTrue(uc.is_newer("v0.7.3-mac10", "0.7.3-mac9"))

    def test_mac_revision(self):
        self.assertTrue(uc.is_newer("v0.7.3-mac2", "0.7.3-mac1"))
        self.assertFalse(uc.is_newer("v0.7.3-mac1", "0.7.3-mac1"))
        self.assertFalse(uc.is_newer("v0.7.3-mac1", "0.7.3-mac2"))

    def test_upstream_bump_beats_mac_revision(self):
        self.assertTrue(uc.is_newer("v0.7.4-mac1", "0.7.3-mac5"))
        self.assertFalse(uc.is_newer("v0.7.3-mac5", "0.7.4-mac1"))

    def test_missing_parts_are_zero(self):
        self.assertEqual(uc.compare_versions("v0.7.3", "0.7.3-mac0"), 0)
        self.assertEqual(uc.compare_versions("1.0", "1.0.0.0"), 0)
        self.assertTrue(uc.is_newer("v0.7.3-mac1", "0.7.3"))
        self.assertFalse(uc.is_newer("v0.7.3", "0.7.3-mac1"))

    def test_test_hook_version(self):
        self.assertTrue(uc.is_newer("v0.7.3-mac1", "0.0.1"))

    def test_garbage_tag_never_newer(self):
        self.assertFalse(uc.is_newer("latest", "0.7.3-mac1"))
        self.assertFalse(uc.is_newer("", "0.0.1"))


class CheckDue(unittest.TestCase):
    def test_throttle(self):
        day = uc.CHECK_INTERVAL
        self.assertTrue(uc.check_due(1000.0, None))
        self.assertFalse(uc.check_due(1000.0 + day - 1, 1000.0))
        self.assertTrue(uc.check_due(1000.0 + day, 1000.0))
        self.assertTrue(uc.check_due(1000.0, 5000.0))  # clock went back


class Decide(unittest.TestCase):
    def test_decisions(self):
        self.assertEqual(uc.decide("v0.7.3-mac1", "0.7.3-mac1", None), "current")
        self.assertEqual(uc.decide("v0.7.3-mac2", "0.7.3-mac1", None), "update")
        self.assertEqual(uc.decide("v0.7.3-mac2", "0.7.3-mac1", "v0.7.3-mac2"), "skipped")
        self.assertEqual(uc.decide("v0.7.3-mac3", "0.7.3-mac1", "v0.7.3-mac2"), "update")
        self.assertEqual(uc.decide("v0.7.3-mac2", "0.7.3-mac1", ""), "update")
        self.assertEqual(uc.decide("v0.7.3-mac2", "0.7.3-mac1", "junk"), "update")


class ReleasePage(unittest.TestCase):
    def test_uses_repo_html_url(self):
        url = "https://github.com/vu2cpl/nanovnasaver-mac/releases/tag/v0.7.3-mac2"
        self.assertEqual(uc.release_page("v0.7.3-mac2", url), url)

    def test_rejects_foreign_url(self):
        self.assertEqual(
            uc.release_page("v0.7.3-mac2", "https://evil.example/x"),
            "https://github.com/vu2cpl/nanovnasaver-mac/releases/tag/v0.7.3-mac2",
        )
        self.assertEqual(
            uc.release_page("v1 ; rm", "https://github.com/vu2cpl/nanovnasaver-mac.evil/"),
            "https://github.com/vu2cpl/nanovnasaver-mac/releases/latest",
        )


class ParseRelease(unittest.TestCase):
    def test_good(self):
        body = json.dumps({"tag_name": "v0.7.3-mac1", "html_url": "https://x"}).encode()
        self.assertEqual(uc.parse_release(body), ("v0.7.3-mac1", "https://x"))

    def test_bad(self):
        for body in (b"not json", b"[]", b"{}", json.dumps({"tag_name": 5}).encode(),
                     json.dumps({"tag_name": "v1\"; do shell script"}).encode()):
            with self.assertRaises(ValueError):
                uc.parse_release(body)


class _Resp(io.BytesIO):
    status = 200


class _Resp203(_Resp):
    status = 203


class Fetch(unittest.TestCase):
    def test_request_shape(self):
        seen = {}

        def opener(req, timeout):
            seen["url"] = req.full_url
            seen["headers"] = dict(req.header_items())
            seen["timeout"] = timeout
            return _Resp(json.dumps({"tag_name": "v0.7.3-mac1"}).encode())

        self.assertEqual(uc.fetch_latest("0.7.3-mac1", opener), ("v0.7.3-mac1", None))
        self.assertEqual(seen["url"], "https://api.github.com/repos/vu2cpl/nanovnasaver-mac/releases/latest")
        self.assertEqual(seen["timeout"], 10)
        self.assertEqual(seen["headers"], {
            "Accept": "application/vnd.github+json",
            "User-agent": "nanovnasaver-mac/0.7.3-mac1",
        })

    def test_non_200_is_a_failure(self):
        body = json.dumps({"tag_name": "v0.7.3-mac1"}).encode()
        with self.assertRaises(ValueError):
            uc.fetch_latest("0.7.3-mac1", lambda req, timeout: _Resp203(body))

    def test_http_error_propagates_for_silent_handling(self):
        def opener(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 403, "rate limited", {}, None)

        with self.assertRaises(urllib.error.HTTPError):
            uc.fetch_latest("0.7.3-mac1", opener)


class BundleVersion(unittest.TestCase):
    def test_reads_plist_key(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "Info.plist"), "wb") as f:
                plistlib.dump({uc.PLIST_VERSION_KEY: "0.7.3-mac1"}, f)
            self.assertEqual(uc.bundle_version(d), "0.7.3-mac1")

    def test_missing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(uc.bundle_version(d))
            with open(os.path.join(d, "Info.plist"), "wb") as f:
                plistlib.dump({"CFBundleShortVersionString": "0.7.3"}, f)
            self.assertIsNone(uc.bundle_version(d))


class _FakePrefs(uc.Prefs):
    """In-memory stand-in for the app's defaults domain."""

    store: dict = {}
    writes: list = []

    def read(self, key):
        v = self.store.get(key)
        return None if v is None else str(v)

    def write(self, key, kind, value):
        self.writes.append(key)
        self.store[key] = value


class Run(unittest.TestCase):
    """run() end to end with fake prefs, fetch and dialog: what is stamped when."""

    def setUp(self):
        _FakePrefs.store, _FakePrefs.writes = {}, []
        self.fetches = 0
        self.dialogs = []
        self.result = ("v0.7.3-mac1", None)
        self.saved = (uc.Prefs, uc.fetch_latest, uc.show_dialog, uc.SHOW_NOT_BEFORE)
        self.env = os.environ.pop(uc.TEST_ENV, None)

        def fetch(current, opener=None):
            self.fetches += 1
            if isinstance(self.result, BaseException):
                raise self.result
            return self.result

        def dialog(tag, current, icon, give_up_after=None):
            self.dialogs.append((tag, current))
            return uc.BTN_LATER

        uc.Prefs, uc.fetch_latest, uc.show_dialog, uc.SHOW_NOT_BEFORE = (
            _FakePrefs, fetch, dialog, 0.0)

    def tearDown(self):
        uc.Prefs, uc.fetch_latest, uc.show_dialog, uc.SHOW_NOT_BEFORE = self.saved
        os.environ.pop(uc.TEST_ENV, None)
        if self.env is not None:
            os.environ[uc.TEST_ENV] = self.env

    def run_with(self, version="0.7.3-mac1", *extra):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "Info.plist"), "wb") as f:
                plistlib.dump({uc.PLIST_VERSION_KEY: version}, f)
            self.assertEqual(uc.main(["--contents", d, *extra]), 0)

    # -- only a successful check is stamped

    def test_success_current_stamps(self):
        self.run_with()
        self.assertEqual(self.fetches, 1)
        self.assertEqual(_FakePrefs.writes, [uc.KEY_LAST_CHECK])
        self.assertEqual(self.dialogs, [])
        self.assertAlmostEqual(float(_FakePrefs.store[uc.KEY_LAST_CHECK]), time.time(), delta=5)

    def test_success_newer_stamps_and_asks(self):
        self.result = ("v0.7.3-mac2", None)
        self.run_with()
        self.assertEqual(_FakePrefs.writes, [uc.KEY_LAST_CHECK])  # Later saves nothing more
        self.assertEqual(self.dialogs, [("v0.7.3-mac2", "0.7.3-mac1")])

    def test_failures_stamp_nothing(self):
        failures = (
            urllib.error.URLError("offline"),
            TimeoutError("timed out"),
            urllib.error.HTTPError(uc.API_URL, 403, "rate limit exceeded", {}, None),
            urllib.error.HTTPError(uc.API_URL, 500, "server error", {}, None),
            ValueError("HTTP 203"),
            ValueError("release JSON is not an object"),
            json.JSONDecodeError("Expecting value", "<html>", 0),
        )
        for failure in failures:
            with self.subTest(failure=repr(failure)):
                _FakePrefs.store, _FakePrefs.writes = {}, []
                self.result = failure
                self.run_with()
                self.assertEqual(_FakePrefs.writes, [])
                self.assertEqual(self.dialogs, [])

    def test_failure_keeps_the_last_success(self):
        _FakePrefs.store[uc.KEY_LAST_CHECK] = "1000"  # long ago: due
        self.result = urllib.error.URLError("offline")
        self.run_with()
        self.assertEqual(self.fetches, 1)
        self.assertEqual(_FakePrefs.store[uc.KEY_LAST_CHECK], "1000")

    def test_offline_launch_retries_at_next_launch(self):
        self.result = urllib.error.URLError("offline")
        self.run_with()
        self.result = ("v0.7.3-mac1", None)
        self.run_with()  # next launch, minutes later: not throttled
        self.assertEqual(self.fetches, 2)
        self.assertEqual(_FakePrefs.writes, [uc.KEY_LAST_CHECK])
        self.run_with()  # and after that success, throttled for 24 h
        self.assertEqual(self.fetches, 2)

    def test_stamp_is_never_in_the_future(self):
        p = _FakePrefs()
        p.set_last_check(1000.9)
        self.assertEqual(p.last_check(), 1000.0)
        self.assertFalse(uc.check_due(1000.95, p.last_check()))

    def test_recent_success_throttles(self):
        _FakePrefs.store[uc.KEY_LAST_CHECK] = f"{time.time() - 60:.0f}"
        self.run_with()
        self.assertEqual(self.fetches, 0)
        self.assertEqual(_FakePrefs.writes, [])

    # -- development builds

    def test_dev_version_detection(self):
        for v in ("0.7.4.dev1-mac1", "0.7.4-DEV-mac2", "development-mac1", "Dev"):
            self.assertTrue(uc.is_dev_version(v), v)
        for v in ("0.7.3-mac1", "", None):
            self.assertFalse(uc.is_dev_version(v), v)

    def test_dev_build_does_not_check(self):
        for v in ("0.7.4.dev1-mac1", "0.7.4-DEV-mac2"):
            with self.subTest(version=v):
                self.run_with(v)
                self.assertEqual(self.fetches, 0)
                self.assertEqual(_FakePrefs.writes, [])

    def test_test_hook_still_checks_a_dev_build(self):
        os.environ[uc.TEST_ENV] = "0.0.1"
        self.run_with("0.7.4.dev1-mac1")
        self.assertEqual(self.fetches, 1)
        self.assertEqual(self.dialogs, [("v0.7.3-mac1", "0.0.1")])
        self.assertEqual(_FakePrefs.writes, [])  # test mode saves nothing

    def test_dry_run_checks_a_dev_build_and_saves_nothing(self):
        self.run_with("0.7.4.dev1-mac1", "--dry-run")
        self.assertEqual(self.fetches, 1)
        self.assertEqual(_FakePrefs.writes, [])
        self.assertEqual(self.dialogs, [])


if __name__ == "__main__":
    unittest.main()
