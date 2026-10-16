"""Builds the candidate in a pbuilder trixie chroot. A primary build packs
its patched source tree into a .dsc with dpkg-source first; a follower build
downloaded the published .dsc and builds it as is. The chroot is then
updated (the base tarball only needs to be current at build time) before
pbuilder builds from that .dsc.
The whole log is captured and returned: the dh_missing gate greps it, and it
is the durable record of a run whose workspace does not survive success."""
import subprocess
from dataclasses import dataclass
from pathlib import Path

PBUILDERRC = "/etc/zamfono/pbuilderrc"
# --build=full: the .changes must carry the source (.dsc + tarballs — the
# archive publishes deb-src). -sa: a new upstream version's tarballs are
# never in the pool yet, and a .changes without them fails ingestion; on a
# rebuild reprepro verifies matching checksums instead, so -sa is always
# safe.
FULL_BUILD_OPTS = "-sa --build=full"
# A follower uploads only its architecture's binaries: the source and the
# Architecture: all packages are already published by the primary.
ARCH_BUILD_OPTS = "--build=any"


@dataclass
class BuildResult:
    success: bool
    log: str


def _run_logged(cmd: "list[str]", cwd: Path, log_parts: "list[str]") -> bool:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    log_parts.append(f"$ {' '.join(cmd)}\n{result.stdout}{result.stderr}")
    return result.returncode == 0


def run_build(workspace: str, debbuildopts: str = FULL_BUILD_OPTS) -> BuildResult:
    workspace_path = Path(workspace)
    log_parts: "list[str]" = []
    if (workspace_path / "source").is_dir() and not _run_logged(
        ["dpkg-source", "-b", "source"], workspace_path, log_parts
    ):
        return BuildResult(False, "\n".join(log_parts))
    dsc_paths = list(workspace_path.glob("*.dsc"))
    if len(dsc_paths) != 1:
        log_parts.append(
            f"expected exactly one .dsc in {workspace_path}, found {len(dsc_paths)}"
        )
        return BuildResult(False, "\n".join(log_parts))
    if not _run_logged(
        ["pbuilder", "update", "--configfile", PBUILDERRC], workspace_path, log_parts
    ):
        return BuildResult(False, "\n".join(log_parts))
    success = _run_logged(
        [
            "pbuilder", "build",
            "--configfile", PBUILDERRC,
            "--buildresult", str(workspace_path),
            "--debbuildopts", debbuildopts,
            str(dsc_paths[0]),
        ],
        workspace_path,
        log_parts,
    )
    return BuildResult(success, "\n".join(log_parts))
