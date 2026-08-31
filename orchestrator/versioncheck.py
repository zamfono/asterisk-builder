"""Debian version comparison always shells out to dpkg --compare-versions;
Python never implements the comparison algorithm itself."""
import subprocess

from orchestrator.version import ZAMFONO_SUFFIX_RE


def dpkg_compare_versions(v1: str, op: str, v2: str) -> bool:
    result = subprocess.run(["dpkg", "--compare-versions", v1, op, v2], check=False)
    return result.returncode == 0


def strip_zamfono_suffix(version: str) -> str:
    """Removes a trailing +zamfono13.N, if present, returning the plain
    Debian source version it was built from. ZAMFONO_SUFFIX_RE is anchored
    at both ends, so matching it against the *full* version greedily
    captures everything before the suffix as the "revision" group — the
    same group orchestrator.version.compute_next_zamfono_version reads
    after first splitting off the upstream part."""
    match = ZAMFONO_SUFFIX_RE.match(version)
    return match.group("revision") if match else version


def should_build(sid_version: str, latest_published_version: "str | None") -> bool:
    """True when the sid source version is newer than the Debian source
    version the latest published Zamfono version was built from (the
    +zamfono13.N suffix is always stripped before comparing — comparing
    against the raw published string would make this permanently False,
    since the suffix always sorts newer than the bare version it
    decorates), or when nothing has been published yet."""
    if latest_published_version is None:
        return True
    published_debian_version = strip_zamfono_suffix(latest_published_version)
    return dpkg_compare_versions(sid_version, "gt", published_debian_version)
