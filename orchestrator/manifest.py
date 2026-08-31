"""The module-to-package manifest is authoritative. Automatic derivation
(orchestrator/gates_deps.py) is a verification aid and must never move a
module between groups; only this file's data does that."""
import json
import re
import subprocess
from pathlib import Path

# Debian's asterisk packaging installs modules under the multiarch libdir
# (usr/lib/<triplet>/asterisk/modules), so the leading path is not fixed.
_MODULE_SO_RE = re.compile(r"/asterisk/modules/([^ /]+\.so)$")

ALLOWED_GROUPS = frozenset(
    {
        "asterisk-modules-core",
        "asterisk-modules-pjsip",
        "asterisk-modules-amr",
        "asterisk-modules-mp3",
        "asterisk-modules-opus",
        "asterisk-modules-voicemail",
        "asterisk-modules-voicemail-odbc",
        # app_voicemail upstream also supports an IMAP storage backend, but
        # it links against libc-client (uw-imap), which Debian removed from
        # the archive; there is no asterisk-modules-voicemail-imap group
        # until a replacement library is packaged.
        "asterisk-modules-odbc",
        "asterisk-modules-postgresql",
        "asterisk-modules-mysql",
        "asterisk-modules-sqlite3",
        "asterisk-modules-fax",
        "asterisk-modules-dahdi",
        "asterisk-modules-mobile",
        "asterisk-modules-ooh323",
        "asterisk-modules-snmp",
        "asterisk-modules-xmpp",
        "asterisk-modules-ldap",
        "asterisk-modules-lua",
        "asterisk-modules-radius",
        "asterisk-modules-calendar",
        "asterisk-modules-jack",
        "asterisk-modules-hep",
        "asterisk-modules-ari",
        "asterisk-modules-prometheus",
    }
)


class ManifestError(Exception):
    pass


def load_manifest(path: "str | Path") -> dict:
    return json.loads(Path(path).read_text())


def validate_structure(manifest: dict) -> "list[str]":
    errors = []
    groups = manifest.get("groups", {})

    for group_name in groups:
        if group_name not in ALLOWED_GROUPS:
            errors.append(f"unknown group in manifest: {group_name!r}")

    seen: "dict[str, str]" = {}
    for group_name, group in groups.items():
        for module in group.get("modules", []):
            if module in seen:
                errors.append(
                    f"module {module!r} listed in both "
                    f"{seen[module]!r} and {group_name!r}"
                )
            else:
                seen[module] = group_name

    declared_packages = set(groups) | {"asterisk-modules"}
    for dep in manifest.get("cross_group_dependencies", []):
        if dep["package"] not in declared_packages:
            errors.append(f"cross_group_dependencies names unknown package {dep['package']!r}")
        if dep["depends_on"] not in declared_packages:
            errors.append(f"cross_group_dependencies depends on unknown package {dep['depends_on']!r}")

    return errors


def validate_full_coverage(manifest: dict, built_modules: "list[str]") -> "list[str]":
    classified = {
        module
        for group in manifest.get("groups", {}).values()
        for module in group.get("modules", [])
    }
    return [module for module in built_modules if module not in classified]


def emitted_groups(manifest: dict, built_modules: "list[str]") -> "list[str]":
    built = set(built_modules)
    return [
        group_name
        for group_name, group in manifest.get("groups", {}).items()
        if built.intersection(group.get("modules", []))
    ]


def built_modules_from_debs(deb_paths: "list[str]") -> "list[str]":
    """Lists every loadable module .so across a set of built .deb files, via
    dpkg-deb -c — the same tool debhelper itself uses to inspect package
    contents. This is the built_modules input to validate_full_coverage and
    emitted_groups on every real run."""
    modules: "list[str]" = []
    for deb_path in deb_paths:
        result = subprocess.run(
            ["dpkg-deb", "-c", deb_path], check=True, capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            match = _MODULE_SO_RE.search(line)
            if match:
                modules.append(match.group(1))
    return modules
