import subprocess
import unittest
from unittest import mock

from orchestrator.gates_meta import check_asterisk_core_only_dependency, check_meta_package

MANIFEST = {
    "groups": {
        "asterisk-modules-core": {"modules": ["res_pjsip.so"]},
        "asterisk-modules-pjsip": {"modules": ["chan_pjsip.so"]},
        "asterisk-modules-opus": {"modules": ["codec_opus.so"]},
    },
    "cross_group_dependencies": [],
}


class CheckMetaPackageTests(unittest.TestCase):
    def test_passes_when_every_emitted_group_is_depended_on_at_exact_version(self):
        built_modules = ["res_pjsip.so", "chan_pjsip.so"]  # opus not built this run

        def fake_run(argv, **kwargs):
            if argv[-1] == "Depends":
                stdout = (
                    "asterisk-modules-core (= 1.0), asterisk-modules-pjsip (= 1.0)\n"
                )
            elif argv[-1] == "Architecture":
                stdout = "all\n"
            else:
                stdout = ""
            return subprocess.CompletedProcess(argv, 0, stdout=stdout)

        with mock.patch("subprocess.run", fake_run):
            errors = check_meta_package(MANIFEST, built_modules, "/out/asterisk-modules_1.0_all.deb", "1.0")
        self.assertEqual(errors, [])

    def test_fails_when_an_emitted_group_is_missing_from_depends(self):
        built_modules = ["res_pjsip.so", "chan_pjsip.so"]

        def fake_run(argv, **kwargs):
            if argv[-1] == "Depends":
                stdout = "asterisk-modules-core (= 1.0)\n"
            elif argv[-1] == "Architecture":
                stdout = "all\n"
            else:
                stdout = ""
            return subprocess.CompletedProcess(argv, 0, stdout=stdout)

        with mock.patch("subprocess.run", fake_run):
            errors = check_meta_package(MANIFEST, built_modules, "/out/asterisk-modules_1.0_all.deb", "1.0")
        self.assertEqual(len(errors), 1)
        self.assertIn("asterisk-modules-pjsip", errors[0])

    def test_fails_when_architecture_is_not_all(self):
        built_modules = ["res_pjsip.so"]

        def fake_run(argv, **kwargs):
            if argv[-1] == "Depends":
                stdout = "asterisk-modules-core (= 1.0)\n"
            elif argv[-1] == "Architecture":
                stdout = "amd64\n"
            else:
                stdout = ""
            return subprocess.CompletedProcess(argv, 0, stdout=stdout)

        with mock.patch("subprocess.run", fake_run):
            errors = check_meta_package(MANIFEST, built_modules, "/out/asterisk-modules_1.0_all.deb", "1.0")
        self.assertTrue(any("Architecture" in e for e in errors))


class CheckAsteriskCoreOnlyDependencyTests(unittest.TestCase):
    def test_passes_when_asterisk_depends_on_core_only(self):
        def fake_run(argv, **kwargs):
            field = argv[-1]
            if field == "Depends":
                stdout = "asterisk-modules-core (= 1.0), libc6 (>= 2.34)\n"
            elif field == "Recommends":
                stdout = ""
            else:
                stdout = ""
            return subprocess.CompletedProcess(argv, 0, stdout=stdout)

        with mock.patch("subprocess.run", fake_run):
            errors = check_asterisk_core_only_dependency(
                {"asterisk": "/out/asterisk_1.0_amd64.deb", "asterisk-modules-core": "/out/asterisk-modules-core_1.0_amd64.deb"},
            )
        self.assertEqual(errors, [])

    def test_fails_when_asterisk_depends_on_the_meta_package(self):
        # "asterisk-modules-core" contains "asterisk-modules" as a
        # substring — the check must not false-positive on that.
        def fake_run(argv, **kwargs):
            field = argv[-1]
            if field == "Depends":
                stdout = "asterisk-modules-core (= 1.0), asterisk-modules (= 1.0)\n"
            else:
                stdout = ""
            return subprocess.CompletedProcess(argv, 0, stdout=stdout)

        with mock.patch("subprocess.run", fake_run):
            errors = check_asterisk_core_only_dependency(
                {"asterisk": "/out/asterisk_1.0_amd64.deb"}
            )
        self.assertEqual(len(errors), 1)
        self.assertIn("Depend", errors[0])

    def test_fails_when_asterisk_recommends_the_meta_package(self):
        def fake_run(argv, **kwargs):
            field = argv[-1]
            if field == "Depends":
                stdout = "asterisk-modules-core (= 1.0)\n"
            elif field == "Recommends":
                stdout = "asterisk-modules (= 1.0)\n"
            else:
                stdout = ""
            return subprocess.CompletedProcess(argv, 0, stdout=stdout)

        with mock.patch("subprocess.run", fake_run):
            errors = check_asterisk_core_only_dependency(
                {"asterisk": "/out/asterisk_1.0_amd64.deb"}
            )
        self.assertEqual(len(errors), 1)
        self.assertIn("Recommend", errors[0])

    def test_fails_when_core_is_missing_from_depends(self):
        def fake_run(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 0, stdout="")

        with mock.patch("subprocess.run", fake_run):
            errors = check_asterisk_core_only_dependency(
                {"asterisk": "/out/asterisk_1.0_amd64.deb"}
            )
        self.assertEqual(len(errors), 1)
        self.assertIn("asterisk-modules-core", errors[0])


if __name__ == "__main__":
    unittest.main()
