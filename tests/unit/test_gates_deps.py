import subprocess
import unittest
from unittest import mock
from unittest.mock import MagicMock

from orchestrator import gates_deps
from orchestrator.gates_deps import (
    check_cross_group_dependencies,
    check_unresolved_shlibs,
    deb_field,
)

MANIFEST = {
    "groups": {
        "asterisk-modules-core": {"modules": ["res_pjsip.so"]},
        "asterisk-modules-pjsip": {"modules": ["chan_pjsip.so"]},
    },
    "cross_group_dependencies": [
        {"package": "asterisk-modules-pjsip", "depends_on": "asterisk-modules-core"}
    ],
}


class DebFieldTests(unittest.TestCase):
    def test_shells_out_to_dpkg_deb(self):
        fake_run = MagicMock(
            return_value=subprocess.CompletedProcess([], 0, stdout="asterisk-modules-core (= 1.0)\n")
        )
        with mock.patch.object(gates_deps.subprocess, "run", fake_run):
            result = deb_field("/out/asterisk-modules-pjsip_1.0_amd64.deb", "Depends")
        self.assertEqual(result, "asterisk-modules-core (= 1.0)")
        fake_run.assert_called_once_with(
            ["dpkg-deb", "-f", "/out/asterisk-modules-pjsip_1.0_amd64.deb", "Depends"],
            check=True, capture_output=True, text=True,
        )


class CheckCrossGroupDependenciesTests(unittest.TestCase):
    def test_passes_when_depends_field_names_the_target_at_exact_version(self):
        deb_paths = {
            "asterisk-modules-pjsip": "/out/asterisk-modules-pjsip_1.0_amd64.deb",
            "asterisk-modules-core": "/out/asterisk-modules-core_1.0_amd64.deb",
        }

        def fake_run(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 0, stdout="asterisk-modules-core (= 1.0)\n")

        with mock.patch.object(gates_deps.subprocess, "run", fake_run):
            errors = check_cross_group_dependencies(MANIFEST, deb_paths, "1.0")
        self.assertEqual(errors, [])

    def test_fails_when_depends_field_is_missing_the_exact_version(self):
        deb_paths = {
            "asterisk-modules-pjsip": "/out/asterisk-modules-pjsip_1.0_amd64.deb",
            "asterisk-modules-core": "/out/asterisk-modules-core_1.0_amd64.deb",
        }

        def fake_run(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 0, stdout="asterisk-modules-core\n")

        with mock.patch.object(gates_deps.subprocess, "run", fake_run):
            errors = check_cross_group_dependencies(MANIFEST, deb_paths, "1.0")
        self.assertEqual(len(errors), 1)
        self.assertIn("asterisk-modules-pjsip", errors[0])

    def test_fails_when_the_declared_dependency_package_was_never_built(self):
        deb_paths = {"asterisk-modules-pjsip": "/out/asterisk-modules-pjsip_1.0_amd64.deb"}
        errors = check_cross_group_dependencies(MANIFEST, deb_paths, "1.0")
        self.assertEqual(len(errors), 1)
        self.assertIn("asterisk-modules-core", errors[0])


class CheckUnresolvedShlibsTests(unittest.TestCase):
    def test_finds_dpkg_shlibdeps_warnings(self):
        log = (
            "dh_shlibdeps\n"
            "dpkg-shlibdeps: warning: could not find any packages for libfoo.so.1 "
            "(wanted by debian/asterisk/usr/sbin/asterisk)\n"
        )
        errors = check_unresolved_shlibs(log)
        self.assertEqual(len(errors), 1)
        self.assertIn("libfoo.so.1", errors[0])

    def test_ignores_warnings_that_are_not_unresolved_dependencies(self):
        # A plugin resolves these symbols from the program that dlopens it,
        # and an avoidable link is not a missing one.
        log = (
            "dpkg-shlibdeps: warning: symbol ast_option_pjproject_log_level used by "
            "debian/asterisk/usr/lib/libasteriskpj.so.2 found in none of the libraries\n"
            "dpkg-shlibdeps: warning: package could avoid a useless dependency if "
            "debian/asterisk/usr/sbin/asterisk was not linked against libstdc++.so.6\n"
        )
        self.assertEqual(check_unresolved_shlibs(log), [])

    def test_empty_when_no_warnings_present(self):
        self.assertEqual(check_unresolved_shlibs("dh_shlibdeps\nOK\n"), [])


if __name__ == "__main__":
    unittest.main()
