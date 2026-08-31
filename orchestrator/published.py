"""Reads the published asterisk source version from the public repository's
own Sources index. The archive is the single source of truth for "what is
published", so the builder keeps no local published-version state and
self-heals when the archive is restored from backup or rebuilt. The window
between a finished upload and its ingest is seconds against a six-hourly
timer, so a stale read cannot double-build in practice."""
import email.parser
import gzip
import urllib.error
import urllib.request

SOURCES_URL = (
    "https://packages.zamfono.com/debian/asterisk/22/"
    "dists/trixie/main/source/Sources.gz"
)


def parse_sources_versions(text: str, package: str = "asterisk") -> "list[str]":
    versions = []
    for stanza in text.split("\n\n"):
        if not stanza.strip():
            continue
        parsed = email.parser.Parser().parsestr(stanza, headersonly=True)
        if parsed["Package"] == package and parsed["Version"] is not None:
            versions.append(parsed["Version"].strip())
    return versions


def published_asterisk_versions() -> "list[str]":
    try:
        with urllib.request.urlopen(SOURCES_URL, timeout=60) as response:
            data = response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            # a fresh archive has no Sources index yet
            return []
        raise
    return parse_sources_versions(gzip.decompress(data).decode())
