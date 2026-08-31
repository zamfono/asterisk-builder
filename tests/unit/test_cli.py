import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator.cli import (
    _changes_referenced_files,
    _container_check,
    _fetch_and_patch,
    _run_module_load_and_upgrade_gates,
    _safe_name,
    main,
)


class ContainerCheckTests(unittest.TestCase):
    def test_uses_the_fully_qualified_base_image(self):
        # A bare "debian:13" relies on Docker's implicit docker.io
        # expansion; podman defines no unqualified-search-registries on
        # Debian 13 and fails closed on a short name instead.
        fake_run = MagicMock(return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""))
        with patch("subprocess.run", fake_run):
            _container_check("zamfono-test", Path("/srv/workspace"), "true")
        argv = fake_run.call_args.args[0]
        self.assertIn("docker.io/library/debian:13", argv)


class RunModuleLoadAndUpgradeGatesTests(unittest.TestCase):
    CANDIDATE_VERSION = "1:20.9.0-1+zamfono13.1"

    def _container_name(self):
        return f"zamfono-lifecycle-{_safe_name(self.CANDIDATE_VERSION)}"

    def test_pre_cleans_the_lifecycle_container_name_before_creating_it(self):
        # A reboot or kill between creation and the `finally` cleanup can
        # leave the fixed name behind; without this pre-clean, every retry
        # of this candidate would fail on the name collision.
        fake_run = MagicMock(return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""))
        with patch("orchestrator.cli.subprocess.run", fake_run):
            _run_module_load_and_upgrade_gates(Path("/srv/workspace/x"), self.CANDIDATE_VERSION, None)
        argvs = [call.args[0] for call in fake_run.call_args_list]
        container_name = self._container_name()
        run_d_index = argvs.index(
            ["podman", "run", "-d", "--name", container_name,
             "-v", "/srv/workspace/x:/out", "-w", "/out",
             "docker.io/library/debian:13", "sleep", "infinity"]
        )
        self.assertIn(["podman", "rm", "-f", container_name], argvs[:run_d_index])

    def test_fails_without_crashing_when_service_asterisk_start_fails(self):
        container_name = self._container_name()

        def fake_run(argv, **kwargs):
            if argv[:3] == ["podman", "exec", container_name] and argv[3:] == ["service", "asterisk", "start"]:
                return subprocess.CompletedProcess(argv, 1, stdout="", stderr="start failed")
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        with patch("orchestrator.cli.subprocess.run", fake_run):
            errors = _run_module_load_and_upgrade_gates(Path("/srv/workspace/x"), self.CANDIDATE_VERSION, None)

        self.assertEqual(len(errors), 1)
        self.assertIn("service asterisk start failed", errors[0])

    def test_fails_when_the_module_show_probe_exits_nonzero(self):
        # Asterisk exiting or crashing right after `service start` leaves
        # the probe with a nonzero exit and no module list — the broken
        # candidate must not pass the module-load gate on an empty parse.
        container_name = self._container_name()

        def fake_run(argv, **kwargs):
            if argv[:3] == ["podman", "exec", container_name] and "module show" in argv:
                return subprocess.CompletedProcess(argv, 1, stdout="", stderr="Unable to connect")
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        with patch("orchestrator.cli.subprocess.run", fake_run):
            errors = _run_module_load_and_upgrade_gates(Path("/srv/workspace/x"), self.CANDIDATE_VERSION, None)

        self.assertEqual(len(errors), 1)
        self.assertIn("module show probe failed", errors[0])

    def test_fails_when_the_module_show_probe_returns_empty_output(self):
        container_name = self._container_name()

        def fake_run(argv, **kwargs):
            if argv[:3] == ["podman", "exec", container_name] and "module show" in argv:
                return subprocess.CompletedProcess(argv, 0, stdout="   \n", stderr="")
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        with patch("orchestrator.cli.subprocess.run", fake_run):
            errors = _run_module_load_and_upgrade_gates(Path("/srv/workspace/x"), self.CANDIDATE_VERSION, None)

        self.assertEqual(len(errors), 1)
        self.assertIn("module show probe failed", errors[0])

    def test_parses_module_show_failures_when_the_probe_runs_cleanly(self):
        container_name = self._container_name()
        module_show_output = (
            "Module                         Description   Use Count  Status   Support Level\n"
            "chan_pjsip.so                  PJSIP Channel  0          Failed  extended\n"
            "1 modules loaded\n"
        )

        def fake_run(argv, **kwargs):
            if argv[:3] == ["podman", "exec", container_name] and "module show" in argv:
                return subprocess.CompletedProcess(argv, 0, stdout=module_show_output, stderr="")
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        with patch("orchestrator.cli.subprocess.run", fake_run):
            errors = _run_module_load_and_upgrade_gates(Path("/srv/workspace/x"), self.CANDIDATE_VERSION, None)

        self.assertEqual(len(errors), 1)
        self.assertIn("chan_pjsip.so", errors[0])


class RunSubcommandTests(unittest.TestCase):
    @patch("orchestrator.cli.acquire_lock", return_value=None)
    def test_run_exits_zero_without_side_effects_when_lock_is_held(self, _acquire_lock):
        exit_code = main(["run"])
        self.assertEqual(exit_code, 0)


class FetchAndPatchTests(unittest.TestCase):
    @patch("orchestrator.cli.install_patches")
    @patch("orchestrator.cli.set_changelog_version_cmd", return_value=["true"])
    @patch("orchestrator.cli._write_sid_sourcelist")
    def test_discards_a_stale_workspace_left_by_a_previous_failed_attempt(
        self, _write_sid_sourcelist, _set_changelog_version_cmd, install_patches
    ):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "candidate"
            stale_source = workspace / "source"
            stale_source.mkdir(parents=True)
            (stale_source / "already-patched-marker").write_text("x")

            def fake_run(argv, **_kwargs):
                if "source" in argv:
                    # simulates `apt-get source` extracting a fresh tree
                    (workspace / "asterisk-20.9.0").mkdir()
                return subprocess.CompletedProcess(argv, 0)

            with patch("orchestrator.cli.subprocess.run", side_effect=fake_run):
                _fetch_and_patch(workspace, "1:20.9.0-1", "1:20.9.0-1+zamfono13.1")

            # A retry must not nest the fresh tree inside the stale one, nor
            # patch on top of the stale, already-patched source.
            self.assertFalse((workspace / "source" / "already-patched-marker").exists())
            self.assertFalse((workspace / "source" / "asterisk-20.9.0").exists())
            install_patches.assert_called_once()


if __name__ == "__main__":
    unittest.main()


class ChangesReferencedFilesTest(unittest.TestCase):
    def test_reads_filenames_from_the_files_stanza_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            changes = Path(tmp) / "x.changes"
            changes.write_text(
                "Format: 1.8\n"
                "Checksums-Sha256:\n"
                " abc 1 not-a-files-entry.deb\n"
                "Files:\n"
                " deadbeef 123 comm optional asterisk_1.0_amd64.deb\n"
                " cafebabe 456 comm optional asterisk_1.0.dsc\n"
            )
            self.assertEqual(
                _changes_referenced_files(changes),
                ["asterisk_1.0_amd64.deb", "asterisk_1.0.dsc"],
            )
