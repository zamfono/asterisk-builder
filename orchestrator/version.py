"""Computes the Zamfono `+zamfono13.N` version suffix. Never compares versions
itself — that is `dpkg --compare-versions`'s job (see orchestrator/versioncheck.py)."""
import re
from collections.abc import Iterable

ZAMFONO_SUFFIX_RE = re.compile(r"^(?P<revision>.+)\+zamfono13\.(?P<n>\d+)$")


class VersionError(Exception):
    """Raised when a Debian version string cannot be split into upstream+revision."""


def split_debian_version(version: str) -> tuple[str, str]:
    """Splits a Debian version into (upstream_with_epoch, debian_revision).

    Raises VersionError if there is no debian_revision (native package version).
    """
    if "-" not in version:
        raise VersionError(
            f"{version!r} has no Debian revision; Zamfono only imports "
            "non-native Debian source versions"
        )
    upstream, _, revision = version.rpartition("-")
    return upstream, revision


def compute_next_zamfono_version(
    debian_version: str, published_versions: "Iterable[str]"
) -> str:
    """Returns the next `<debian_version>+zamfono13.N` version, N starting at 1
    and incrementing past the highest N already published for this exact
    debian_version."""
    upstream, revision = split_debian_version(debian_version)
    highest_n = 0
    for published in published_versions:
        try:
            published_upstream, published_revision = split_debian_version(published)
        except VersionError:
            continue
        if published_upstream != upstream:
            continue
        match = ZAMFONO_SUFFIX_RE.match(published_revision)
        if not match or match.group("revision") != revision:
            continue
        highest_n = max(highest_n, int(match.group("n")))
    return f"{upstream}-{revision}+zamfono13.{highest_n + 1}"
