import tempfile
import unittest
from pathlib import Path

from orchestrator.cli import find_extracted_source_dir


class FindExtractedSourceDirTests(unittest.TestCase):
    def test_finds_the_sole_matching_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest_dir = Path(tmp)
            (dest_dir / "asterisk-20.9.0~dfsg").mkdir()
            (dest_dir / "asterisk_20.9.0~dfsg-1.dsc").touch()  # not a directory, must be ignored

            result = find_extracted_source_dir(dest_dir, "asterisk")

            self.assertEqual(result, dest_dir / "asterisk-20.9.0~dfsg")

    def test_raises_when_no_directory_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(LookupError):
                find_extracted_source_dir(tmp, "asterisk")

    def test_raises_when_more_than_one_directory_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest_dir = Path(tmp)
            (dest_dir / "asterisk-20.9.0~dfsg").mkdir()
            (dest_dir / "asterisk-20.8.0~dfsg").mkdir()
            with self.assertRaises(LookupError):
                find_extracted_source_dir(dest_dir, "asterisk")


if __name__ == "__main__":
    unittest.main()
