import os
from pathlib import Path

from orchestrator.pbuilder import run_build


def _stub(bindir: Path, name: str, script: str) -> None:
    path = bindir / name
    path.write_text(f"#!/bin/sh\n{script}")
    path.chmod(0o755)


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    (workspace / "source").mkdir(parents=True)
    return workspace


def test_failed_dpkg_source_fails_with_its_output_in_the_log(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _stub(bindir, "dpkg-source", "echo boom >&2\nexit 1\n")
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    result = run_build(str(_workspace(tmp_path)))
    assert not result.success
    assert "boom" in result.log


def test_successful_build_runs_pbuilder_on_the_generated_dsc(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    # the dpkg-source stub emits the .dsc that run_build must hand to pbuilder
    _stub(bindir, "dpkg-source", "touch asterisk_1.0-1.dsc\n")
    _stub(bindir, "pbuilder", 'echo "pbuilder args: $@"\n')
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    result = run_build(str(_workspace(tmp_path)))
    assert result.success
    assert "asterisk_1.0-1.dsc" in result.log


def test_missing_dsc_after_dpkg_source_fails(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _stub(bindir, "dpkg-source", "exit 0\n")
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    result = run_build(str(_workspace(tmp_path)))
    assert not result.success
    assert ".dsc" in result.log


def test_follower_builds_the_downloaded_dsc_without_repacking(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    # a follower workspace holds the downloaded .dsc and no source tree;
    # dpkg-source must not run, so its stub fails loudly
    _stub(bindir, "dpkg-source", "exit 1\n")
    _stub(bindir, "pbuilder", 'echo "pbuilder args: $@"\n')
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "asterisk_1.0-1.dsc").touch()
    result = run_build(str(workspace), "--build=any")
    assert result.success
    assert "--debbuildopts --build=any" in result.log
    assert "asterisk_1.0-1.dsc" in result.log
