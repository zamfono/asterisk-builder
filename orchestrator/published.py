"""Reads the published asterisk versions from the public repository's own
indexes: the source version from Sources, an architecture's binary version
from that architecture's Packages. The archive is the single source of
truth for "what is published", so the builder keeps no local state and
self-heals when the archive is restored from backup or rebuilt. A run
returns only once the archive lists its upload (cli._wait_until_published),
so the next run never reads an index that predates it."""
import email.parser
import gzip
import urllib.error
import urllib.request

INDEX_BASE_URL = "https://packages.zamfono.com/debian/asterisk/22/dists/trixie/main/"


def parse_sources_versions(text: str, package: str = "asterisk") -> "list[str]":
    """Works on Packages indexes too: both are Package/Version stanzas."""
    versions = []
    for stanza in text.split("\n\n"):
        if not stanza.strip():
            continue
        parsed = email.parser.Parser().parsestr(stanza, headersonly=True)
        if parsed["Package"] == package and parsed["Version"] is not None:
            versions.append(parsed["Version"].strip())
    return versions


def _index_versions(index_path: str) -> "list[str]":
    try:
        with urllib.request.urlopen(INDEX_BASE_URL + index_path, timeout=60) as response:
            data = response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            # a fresh archive (or a newly added architecture) has no index yet
            return []
        raise
    return parse_sources_versions(gzip.decompress(data).decode())


def published_asterisk_versions() -> "list[str]":
    return _index_versions("source/Sources.gz")


def published_binary_versions(arch: str) -> "list[str]":
    return _index_versions(f"binary-{arch}/Packages.gz")
