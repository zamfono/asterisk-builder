# tests/unit/test_gates_moduleload.py
import unittest

from orchestrator.cli import parse_module_show


class ParseModuleShowTests(unittest.TestCase):
    def test_finds_failed_module_loads(self):
        output = (
            "Module                         Description                        Use Count  Status   Support Level\n"
            "res_pjsip.so                   PJSIP Core                          0          Running  core\n"
            "chan_pjsip.so                  PJSIP Channel Driver                Failed to load  Failed  extended\n"
            "3 modules loaded\n"
        )
        failures = parse_module_show(output)
        self.assertEqual(len(failures), 1)
        self.assertIn("chan_pjsip.so", failures[0])

    def test_empty_when_all_modules_running(self):
        output = (
            "Module                         Description                        Use Count  Status   Support Level\n"
            "res_pjsip.so                   PJSIP Core                          0          Running  core\n"
            "1 modules loaded\n"
        )
        self.assertEqual(parse_module_show(output), [])


if __name__ == "__main__":
    unittest.main()
