import subprocess
import unittest
from unittest import mock
from unittest.mock import MagicMock

from orchestrator.versioncheck import (
    dpkg_compare_versions,
    should_build,
    strip_zamfono_suffix,
)


class DpkgCompareVersionsTests(unittest.TestCase):
    def test_builds_correct_argv_and_returns_true_on_zero_exit(self):
        fake_run = MagicMock(return_value=subprocess.CompletedProcess([], 0))
        with mock.patch("subprocess.run", fake_run):
            result = dpkg_compare_versions("2.0-1", "gt", "1.0-1")
        self.assertTrue(result)
        fake_run.assert_called_once_with(
            ["dpkg", "--compare-versions", "2.0-1", "gt", "1.0-1"],
            check=False,
        )

    def test_returns_false_on_nonzero_exit(self):
        fake_run = MagicMock(return_value=subprocess.CompletedProcess([], 1))
        with mock.patch("subprocess.run", fake_run):
            result = dpkg_compare_versions("1.0-1", "gt", "2.0-1")
        self.assertFalse(result)


class StripZamfonoSuffixTests(unittest.TestCase):
    def test_removes_the_zamfono_suffix(self):
        self.assertEqual(strip_zamfono_suffix("20.8.0~dfsg-1+zamfono13.1"), "20.8.0~dfsg-1")

    def test_removes_only_the_highest_n(self):
        self.assertEqual(strip_zamfono_suffix("20.8.0~dfsg-1+zamfono13.12"), "20.8.0~dfsg-1")

    def test_leaves_a_version_without_the_suffix_untouched(self):
        self.assertEqual(strip_zamfono_suffix("20.9.0~dfsg-1"), "20.9.0~dfsg-1")


class ShouldBuildTests(unittest.TestCase):
    def test_builds_when_nothing_published_yet(self):
        result = should_build("20.9.0~dfsg-1", None)
        self.assertTrue(result)

    def test_compares_sid_against_the_debian_version_with_the_zamfono_suffix_stripped(self):
        calls = []

        def fake_compare(a, op, b):
            calls.append((a, op, b))
            return True

        with mock.patch("orchestrator.versioncheck.dpkg_compare_versions", fake_compare):
            result = should_build("20.9.0~dfsg-1", "20.8.0~dfsg-1+zamfono13.1")
        self.assertTrue(result)
        # the +zamfono13.1 suffix must never reach dpkg --compare-versions:
        # it always sorts newer than the bare debian version it decorates,
        # which would make should_build permanently return False once
        # anything has been published for that debian version.
        self.assertEqual(calls, [("20.9.0~dfsg-1", "gt", "20.8.0~dfsg-1")])

    def test_skips_when_sid_matches_the_stripped_debian_version_of_the_latest_publish(self):
        calls = []

        def fake_compare(a, op, b):
            calls.append((a, op, b))
            return False  # dpkg: equal versions are not "gt"

        with mock.patch("orchestrator.versioncheck.dpkg_compare_versions", fake_compare):
            result = should_build("20.8.0~dfsg-1", "20.8.0~dfsg-1+zamfono13.1")
        self.assertFalse(result)
        self.assertEqual(calls, [("20.8.0~dfsg-1", "gt", "20.8.0~dfsg-1")])


if __name__ == "__main__":
    unittest.main()
