"""Gate 4: dependency derivation. ${shlibs:Depends} generation is entirely
dh_shlibdeps's job (invoked automatically by dpkg-buildpackage); this module
only inspects its output and the built .debs via dpkg-deb, and cross-checks
the manifest's explicit cross_group_dependencies."""
import re
import subprocess

# Only the messages that mean an ELF dependency stayed unresolved: a
# library with no package behind it, or one dpkg-shlibdeps could not find
# at all. Its other warnings report resolved-but-suboptimal linkage
# (symbols a plugin gets from the program that dlopens it, a dependency
# the linker could have dropped) and are not dependency failures.
_UNRESOLVED_SHLIBS_RE = re.compile(
    r"^dpkg-shlibdeps: (?:error: .*"
    r"|warning: (?:could not find any packages for|couldn't find library).*)$",
    re.MULTILINE,
)


def deb_field(deb_path: str, field: str) -> str:
    result = subprocess.run(
        ["dpkg-deb", "-f", deb_path, field], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def check_cross_group_dependencies(
    manifest: dict, deb_paths: "dict[str, str]", candidate_version: str
) -> "list[str]":
    errors = []
    for dep in manifest.get("cross_group_dependencies", []):
        package, depends_on = dep["package"], dep["depends_on"]
        if package not in deb_paths:
            errors.append(f"{package!r} has a declared dependency but was not built")
            continue
        if depends_on not in deb_paths:
            errors.append(f"{package!r} depends on {depends_on!r}, which was not built")
            continue
        depends_field = deb_field(deb_paths[package], "Depends")
        expected = f"{depends_on} (= {candidate_version})"
        if expected not in depends_field:
            errors.append(
                f"{package!r} Depends field does not contain {expected!r}: {depends_field!r}"
            )
    return errors


def check_unresolved_shlibs(build_log_text: str) -> "list[str]":
    return _UNRESOLVED_SHLIBS_RE.findall(build_log_text)
