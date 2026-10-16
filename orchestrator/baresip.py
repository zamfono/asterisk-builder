"""baresip: built from the upstream release tarballs of baresip/baresip and
its library baresip/re (libre), which upstream tags in lockstep at the same
version. Debian's baresip is stuck at 1.1.0, so unlike asterisk there is no
Debian source to follow: the primary follows the latest upstream GitHub
release, packs both tarballs into one source package (libre as its `re`
component tarball) with the packaging in packaging/baresip/debian, and
publishes it to its own archive. Followers build the published source, as
for asterisk.

The upstream tarballs are unsigned (lightweight tags, no release assets):
they are trusted on GitHub's TLS alone. Once published, the archive's
signed Sources index is what followers verify against."""
import json
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

PACKAGE = "baresip"
ARCHIVE_URL = "https://packages.zamfono.com/debian/baresip"
INDEX_BASE_URL = f"{ARCHIVE_URL}/dists/trixie/main/"
ARCHIVE_SOURCELIST_CONTENT = (
    f"deb-src [signed-by=/etc/zamfono/zamfono-archive-keyring.gpg] {ARCHIVE_URL} trixie main\n"
)
ARCHIVE_APT_LINE = f"deb [trusted=yes] {ARCHIVE_URL} trixie main"
# The upload account's chroot holds one incoming directory per archive.
UPLOAD_DIR = "/incoming-baresip"
PACKAGING_DIR = "packaging/baresip/debian"
LATEST_RELEASE_URL = "https://api.github.com/repos/baresip/baresip/releases/latest"
TARBALL_URL = "https://github.com/baresip/{repo}/archive/refs/tags/v{version}.tar.gz"
# The tag ends up in file names, URLs and the package version: anything
# but a plain release number is refused.
_RELEASE_RE = re.compile(r"v(\d+\.\d+\.\d+)")
# Load failures only, as asterisk's module-load gate: libre's loader reports
# a module that does not link (a missing library or symbol, what the
# packaging controls) as `dl: mod: <file> (<dlerror>)` or `dl: dlsym: ...`.
# A module that links but declines to start without hardware or a terminal
# (evdev, stdio in the gate container) is reported by baresip as `module
# <name>: <errno>` with no `dl:` line, and is not a packaging failure.
# Matched with colours off (-c).
_MODULE_FAILURE_RE = re.compile(r"^dl: .*$", re.MULTILINE)


def parse_release_tag(tag: str) -> str:
    match = _RELEASE_RE.fullmatch(tag)
    if not match:
        raise ValueError(f"unexpected baresip release tag {tag!r}")
    return match.group(1)


def latest_upstream_version() -> str:
    """The latest non-prerelease upstream version, e.g. "4.12.0"."""
    with urllib.request.urlopen(LATEST_RELEASE_URL, timeout=60) as response:
        return parse_release_tag(json.load(response)["tag_name"])


def debian_version(upstream_version: str) -> str:
    """The Debian base version the +zamfono13.N suffix is appended to."""
    return f"{upstream_version}-1"


def _download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=300) as response, open(dest, "wb") as out:
        shutil.copyfileobj(response, out)


def _extract(tarball: Path, dest: Path) -> None:
    """Extracts a GitHub tag tarball's single top-level directory into dest."""
    dest.mkdir(parents=True)
    subprocess.run(["tar", "-xzf", str(tarball), "-C", str(dest), "--strip-components=1"], check=True)


def fetch_upstream(workspace: Path, upstream_version: str) -> None:
    """Downloads both upstream tarballs as the .orig and .orig-re tarballs
    and assembles workspace/source from them and the packaging."""
    shutil.rmtree(workspace, ignore_errors=True)  # see cli._fetch_and_patch
    workspace.mkdir(parents=True)
    orig = workspace / f"{PACKAGE}_{upstream_version}.orig.tar.gz"
    orig_re = workspace / f"{PACKAGE}_{upstream_version}.orig-re.tar.gz"
    _download(TARBALL_URL.format(repo="baresip", version=upstream_version), orig)
    _download(TARBALL_URL.format(repo="re", version=upstream_version), orig_re)
    source = workspace / "source"
    _extract(orig, source)
    _extract(orig_re, source / "re")
    shutil.copytree(PACKAGING_DIR, source / "debian")


def create_changelog_cmd(version: str) -> "list[str]":
    return [
        "dch", "--create", "--package", PACKAGE,
        "--newversion", version,
        "--distribution", "trixie", "--force-distribution",
        f"Zamfono build of upstream baresip {version.partition('-')[0]}",
    ]


def module_load_failures(output: str) -> "list[str]":
    return _MODULE_FAILURE_RE.findall(output)


# Loads every shipped module into one running baresip for a few seconds;
# its output is checked with module_load_failures (baresip itself still
# starts and exits 0 when modules fail). A config without module_path
# loads modules from the working directory: the compiled-in path only
# goes into the default config baresip writes itself.
SMOKE_SCRIPT = (
    "mkdir -p /tmp/smoke\n"
    "{ for d in /usr/lib/*/baresip/modules; do echo \"module_path $d\"; done\n"
    "  for m in /usr/lib/*/baresip/modules/*.so; do echo \"module $(basename \"$m\")\"; done\n"
    "} > /tmp/smoke/config\n"
    "baresip -c -f /tmp/smoke -t 3 2>&1\n"
)


def upgrade_check_script(previous_version: str, candidate_version: str) -> str:
    return (
        "set -e\n"
        "apt-get update\n"
        "apt-get install -y ca-certificates\n"
        f"echo '{ARCHIVE_APT_LINE}' > /etc/apt/sources.list.d/zamfono-previous.list\n"
        "apt-get update\n"
        f"apt-get install -y {PACKAGE}={previous_version}\n"
        "rm /etc/apt/sources.list.d/zamfono-previous.list\n"
        "echo 'deb [trusted=yes] file:/out ./' > /etc/apt/sources.list.d/zamfono-candidate.list\n"
        "apt-get update\n"
        f"apt-get install -y {PACKAGE}={candidate_version}\n"
    )


PURGE_SCRIPT = (
    f"apt-get purge -y {PACKAGE}\n"
    # nothing of the package may survive the purge (an `!` command would
    # not trip set -e, hence the explicit exit)
    f"if dpkg -L {PACKAGE} >/dev/null 2>&1 || ls -d /usr/lib/*/baresip >/dev/null 2>&1;"
    f" then echo '{PACKAGE} left files behind' >&2; exit 1; fi\n"
)


def gate_script(repo_setup: str) -> str:
    """The lifecycle container's script: install from the candidate repo,
    load every module, purge."""
    return f"set -e\n{repo_setup}\napt-get install -y {PACKAGE}\n" + SMOKE_SCRIPT + PURGE_SCRIPT
