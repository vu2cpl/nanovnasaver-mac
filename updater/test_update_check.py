"""Unit tests for update_check.py — run: python3 -m unittest discover -s updater

Copyright (C) 2026 Manoj Kumar R <vu2cpl@gmail.com>
SPDX-License-Identifier: GPL-3.0-or-later
"""

import io
import json
import os
import plistlib
import tempfile
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


class RunSilentOnFailure(unittest.TestCase):
    """run() must return 0 and show nothing when the network fails."""

    def test_offline(self):
        class P(uc.Prefs):
            writes = []

            def read(self, key):
                return None

            def write(self, key, kind, value):
                self.writes.append(key)

        def boom(*a, **k):
            raise urllib.error.URLError("offline")

        def no_dialog(*a, **k):
            raise AssertionError("dialog shown on failure")

        saved = (uc.Prefs, uc.fetch_latest, uc.show_dialog)
        uc.Prefs, uc.show_dialog = P, no_dialog
        uc.fetch_latest = lambda current, opener=None: boom()
        try:
            with tempfile.TemporaryDirectory() as d:
                with open(os.path.join(d, "Info.plist"), "wb") as f:
                    plistlib.dump({uc.PLIST_VERSION_KEY: "0.7.3-mac1"}, f)
                env = os.environ.pop(uc.TEST_ENV, None)
                try:
                    self.assertEqual(uc.main(["--contents", d]), 0)
                finally:
                    if env is not None:
                        os.environ[uc.TEST_ENV] = env
            self.assertEqual(P.writes, [uc.KEY_LAST_CHECK])  # attempt stamped, nothing else
        finally:
            uc.Prefs, uc.fetch_latest, uc.show_dialog = saved


if __name__ == "__main__":
    unittest.main()
