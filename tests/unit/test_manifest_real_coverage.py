import unittest
from pathlib import Path

from orchestrator.manifest import ALLOWED_GROUPS, load_manifest, validate_structure

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "manifest" / "modules.json"


class RealManifestStructureTests(unittest.TestCase):
    def test_manifest_file_exists_and_is_structurally_valid(self):
        manifest = load_manifest(MANIFEST_PATH)
        self.assertEqual(validate_structure(manifest), [])

    def test_every_group_key_is_one_of_the_allowed_groups(self):
        manifest = load_manifest(MANIFEST_PATH)
        self.assertTrue(set(manifest["groups"]).issubset(ALLOWED_GROUPS))
