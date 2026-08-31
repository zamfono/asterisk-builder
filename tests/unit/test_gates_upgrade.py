import unittest

from orchestrator.gates_upgrade import purge_check_script, upgrade_check_script


class UpgradeScriptTests(unittest.TestCase):
    def test_upgrade_script_installs_previous_from_the_public_repo(self):
        script = upgrade_check_script("2:22.4-1+zamfono13.1", "2:22.5-1+zamfono13.1")
        self.assertIn(
            "https://packages.zamfono.com/debian/asterisk/22 trixie main", script
        )
        self.assertIn("apt-get install -y ca-certificates", script)
        self.assertIn("asterisk=2:22.4-1+zamfono13.1", script)

    def test_upgrade_script_then_upgrades_to_the_candidate_from_out(self):
        script = upgrade_check_script("1", "2")
        self.assertIn("file:/out", script)
        self.assertLess(script.index("asterisk=1"), script.index("asterisk=2"))

    def test_preserves_configuration_across_the_upgrade(self):
        script = upgrade_check_script("1", "2")
        self.assertIn("diff /tmp/asterisk.conf.before-upgrade /etc/asterisk/asterisk.conf", script)


class PurgeScriptTests(unittest.TestCase):
    def test_purges_and_tolerates_an_empty_dpkg_listing(self):
        script = purge_check_script()
        self.assertIn("apt-get purge -y 'asterisk*'", script)
        # dpkg-query exits 1 when the pattern matches nothing — the purge
        # gate's success case — so the listing must not fail the script.
        self.assertIn("dpkg -l 'asterisk*' || true", script)


if __name__ == "__main__":
    unittest.main()
