"""Applies Zamfono's own packaging changes to a dpkg-source -x extracted
Debian source tree, and stamps the computed Zamfono version into
debian/changelog before the build ever starts — dpkg-buildpackage reads the
package version solely from the top changelog entry, so skipping this step
leaves every built artifact carrying the raw sid version instead of
+zamfono13.N. This module only edits the source tree and builds the dch
command line; orchestrator.cli._fetch_and_patch runs both, in this order, on
the host before the source tree is bind-mounted into the container."""
import subprocess
from pathlib import Path


def install_patches(source_dir: "str | Path", overlay_dir: "str | Path") -> "list[str]":
    """Applies every overlay patch in sorted-filename order, with zero fuzz
    tolerance, so a rejected or ambiguous change aborts before the container
    ever starts. The overlay edits debian/ packaging files, which the quilt
    patch system does not cover: dpkg-source -b takes debian/ verbatim into
    the .debian.tar and then applies debian/patches/series on top of it, so a
    series patch touching debian/ is applied a second time and fails."""
    source_dir = Path(source_dir)
    # patch runs with cwd=source_dir, so a caller-relative overlay path is
    # resolved here, against the caller's cwd, and not inside the source
    # tree.
    overlay_dir = Path(overlay_dir).resolve()
    applied = sorted(p.name for p in overlay_dir.glob("*.patch"))
    for name in applied:
        subprocess.run(
            [
                "patch", "--strip=1", "--fuzz=0", "--no-backup-if-mismatch",
                "--input", str(overlay_dir / name),
            ],
            cwd=source_dir,
            check=True,
        )
    return applied


def set_changelog_version_cmd(new_version: str) -> "list[str]":
    return [
        "dch",
        "--newversion", new_version,
        "--distribution", "trixie",
        "--force-distribution",
        "Zamfono rebuild for Debian 13",
    ]
