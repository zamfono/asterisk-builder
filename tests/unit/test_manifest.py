import json
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from orchestrator.manifest import (
    ManifestError,
    built_modules_from_debs,
    emitted_groups,
    load_manifest,
    validate_full_coverage,
    validate_structure,
)

FABRICATED_MANIFEST = {
    "groups": {
        "asterisk-modules-core": {"modules": ["res_pjsip.so", "app_dial.so"]},
        "asterisk-modules-pjsip": {"modules": ["chan_pjsip.so"]},
        "asterisk-modules-opus": {"modules": ["codec_opus.so"]},
    },
    "cross_group_dependencies": [
        {"package": "asterisk-modules-pjsip", "depends_on": "asterisk-modules-core"}
    ],
}


class LoadManifestTests(unittest.TestCase):
    def test_loads_json_from_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "modules.json"
            path.write_text(json.dumps(FABRICATED_MANIFEST))
            self.assertEqual(load_manifest(path), FABRICATED_MANIFEST)


class ValidateStructureTests(unittest.TestCase):
    def test_no_errors_for_a_well_formed_manifest(self):
        self.assertEqual(validate_structure(FABRICATED_MANIFEST), [])

    def test_rejects_a_group_name_outside_the_allowed_groups(self):
        manifest = {
            "groups": {"asterisk-modules-not-a-real-group": {"modules": ["foo.so"]}},
            "cross_group_dependencies": [],
        }
        errors = validate_structure(manifest)
        self.assertTrue(any("asterisk-modules-not-a-real-group" in e for e in errors))

    def test_rejects_a_module_listed_in_two_groups(self):
        manifest = {
            "groups": {
                "asterisk-modules-core": {"modules": ["res_pjsip.so"]},
                "asterisk-modules-pjsip": {"modules": ["res_pjsip.so"]},
            },
            "cross_group_dependencies": [],
        }
        errors = validate_structure(manifest)
        self.assertTrue(any("res_pjsip.so" in e for e in errors))


class ValidateFullCoverageTests(unittest.TestCase):
    def test_empty_when_every_built_module_is_classified(self):
        built = ["res_pjsip.so", "app_dial.so", "chan_pjsip.so", "codec_opus.so"]
        self.assertEqual(validate_full_coverage(FABRICATED_MANIFEST, built), [])

    def test_fails_closed_on_an_unclassified_module(self):
        built = ["res_pjsip.so", "chan_new_thing.so"]
        errors = validate_full_coverage(FABRICATED_MANIFEST, built)
        self.assertEqual(errors, ["chan_new_thing.so"])


class EmittedGroupsTests(unittest.TestCase):
    def test_only_groups_with_at_least_one_built_module_are_emitted(self):
        built = ["res_pjsip.so", "app_dial.so"]  # no pjsip/opus modules built this run
        self.assertEqual(emitted_groups(FABRICATED_MANIFEST, built), ["asterisk-modules-core"])


class BuiltModulesFromDebsTests(unittest.TestCase):
    def test_lists_every_module_so_across_all_built_debs(self):
        def fake_run(argv, **kwargs):
            deb_path = argv[-1]
            contents = {
                "/out/asterisk-modules-core_1.0_amd64.deb": (
                    "drwxr-xr-x root/root 0 usr/lib/asterisk/modules/\n"
                    "-rw-r--r-- root/root 0 usr/lib/asterisk/modules/res_pjsip.so\n"
                ),
                "/out/asterisk-modules-pjsip_1.0_amd64.deb": (
                    "-rw-r--r-- root/root 0 usr/lib/asterisk/modules/chan_pjsip.so\n"
                ),
            }[deb_path]
            return subprocess.CompletedProcess(argv, 0, stdout=contents)

        with mock.patch("subprocess.run", fake_run):
            result = built_modules_from_debs(
                [
                    "/out/asterisk-modules-core_1.0_amd64.deb",
                    "/out/asterisk-modules-pjsip_1.0_amd64.deb",
                ]
            )
        self.assertEqual(sorted(result), ["chan_pjsip.so", "res_pjsip.so"])


if __name__ == "__main__":
    unittest.main()
