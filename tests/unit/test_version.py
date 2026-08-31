import unittest

from orchestrator.version import (
    VersionError,
    compute_next_zamfono_version,
    split_debian_version,
)


class SplitDebianVersionTests(unittest.TestCase):
    def test_splits_upstream_and_revision(self):
        self.assertEqual(split_debian_version("20.9.0~dfsg-1"), ("20.9.0~dfsg", "1"))

    def test_splits_with_epoch(self):
        self.assertEqual(split_debian_version("1:20.9.0-2"), ("1:20.9.0", "2"))

    def test_rejects_native_version_without_revision(self):
        with self.assertRaises(VersionError):
            split_debian_version("20.9.0")


class ComputeNextZamfonoVersionTests(unittest.TestCase):
    def test_first_import_of_a_debian_version_is_n1(self):
        result = compute_next_zamfono_version("20.9.0~dfsg-1", [])
        self.assertEqual(result, "20.9.0~dfsg-1+zamfono13.1")

    def test_increments_n_for_repeat_import_of_same_debian_version(self):
        published = ["20.9.0~dfsg-1+zamfono13.1"]
        result = compute_next_zamfono_version("20.9.0~dfsg-1", published)
        self.assertEqual(result, "20.9.0~dfsg-1+zamfono13.2")

    def test_ignores_published_versions_from_a_different_debian_version(self):
        published = ["20.8.0~dfsg-1+zamfono13.3"]
        result = compute_next_zamfono_version("20.9.0~dfsg-1", published)
        self.assertEqual(result, "20.9.0~dfsg-1+zamfono13.1")

    def test_ignores_published_versions_with_a_different_revision(self):
        published = ["20.9.0~dfsg-2+zamfono13.5"]
        result = compute_next_zamfono_version("20.9.0~dfsg-1", published)
        self.assertEqual(result, "20.9.0~dfsg-1+zamfono13.1")

    def test_takes_the_highest_existing_n_plus_one(self):
        published = [
            "20.9.0~dfsg-1+zamfono13.1",
            "20.9.0~dfsg-1+zamfono13.4",
            "20.9.0~dfsg-1+zamfono13.2",
        ]
        result = compute_next_zamfono_version("20.9.0~dfsg-1", published)
        self.assertEqual(result, "20.9.0~dfsg-1+zamfono13.5")


if __name__ == "__main__":
    unittest.main()
