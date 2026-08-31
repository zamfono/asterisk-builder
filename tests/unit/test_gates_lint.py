import unittest

from orchestrator.gates_lint import check_dh_missing, lintian_gate_errors, parse_lintian


class CheckDhMissingTests(unittest.TestCase):
    def test_finds_the_dh_missing_failure_line(self):
        log = (
            "   dh_missing\n"
            "dh_missing: warning: usr/lib/asterisk/modules/chan_new.so exists in "
            "debian/tmp but is not installed to anywhere \n"
            "dh_missing: error: missing files, aborting\n"
        )
        errors = check_dh_missing(log)
        self.assertEqual(len(errors), 2)
        self.assertIn("chan_new.so", errors[0])

    def test_empty_when_nothing_uninstalled(self):
        self.assertEqual(check_dh_missing("   dh_missing\n"), [])


class ParseLintianTests(unittest.TestCase):
    def test_splits_errors_and_warnings(self):
        output = (
            "W: asterisk-modules-core: no-manual-page usr/sbin/asterisk\n"
            "E: asterisk: missing-copyright-file\n"
            "W: asterisk: hardening-no-fortify-functions usr/sbin/asterisk\n"
        )
        errors, warnings = parse_lintian(output)
        self.assertEqual(errors, ["E: asterisk: missing-copyright-file"])
        self.assertEqual(
            warnings,
            [
                "W: asterisk-modules-core: no-manual-page usr/sbin/asterisk",
                "W: asterisk: hardening-no-fortify-functions usr/sbin/asterisk",
            ],
        )

    def test_no_errors_no_warnings_on_clean_output(self):
        self.assertEqual(parse_lintian(""), ([], []))


class LintianGateErrorsTests(unittest.TestCase):
    def test_passes_clean_output_with_exit_zero(self):
        self.assertEqual(lintian_gate_errors(0, ""), [])

    def test_reports_parsed_errors_on_a_policy_violation_exit(self):
        output = "E: asterisk: missing-copyright-file\n"
        self.assertEqual(lintian_gate_errors(2, output), ["E: asterisk: missing-copyright-file"])

    def test_fails_the_gate_on_a_tool_error_even_with_no_e_lines(self):
        # lintian exits 1 on a run-time error and prints no E: line, so
        # parse_lintian alone would find nothing to fail gate 5 on.
        errors = lintian_gate_errors(1, "internal error: cannot read package\n")
        self.assertEqual(len(errors), 1)
        self.assertIn("lintian exited 1", errors[0])


if __name__ == "__main__":
    unittest.main()
