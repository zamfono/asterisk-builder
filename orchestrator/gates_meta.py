"""Gate 9: asterisk-modules must depend on every group emitted by this
build, at the exact candidate version, and remain Architecture: all.
Also (spec, Packaging policy): asterisk depends on the core module package
only, and may suggest but must not depend on or recommend asterisk-modules."""
from orchestrator.gates_deps import deb_field
from orchestrator.manifest import emitted_groups

CORE_PACKAGE = "asterisk-modules-core"
META_PACKAGE = "asterisk-modules"


def check_meta_package(
    manifest: dict,
    built_modules: "list[str]",
    meta_deb_path: str,
    candidate_version: str,
) -> "list[str]":
    errors = []

    architecture = deb_field(meta_deb_path, "Architecture")
    if architecture != "all":
        errors.append(f"asterisk-modules Architecture is {architecture!r}, expected 'all'")

    depends_field = deb_field(meta_deb_path, "Depends")
    for group in emitted_groups(manifest, built_modules):
        expected = f"{group} (= {candidate_version})"
        if expected not in depends_field:
            errors.append(f"asterisk-modules Depends is missing {expected!r}")

    return errors


def _dependency_package_names(field_value: str) -> "list[str]":
    # Debian control fields are comma-separated "pkg (op version)" tokens;
    # a substring check for "asterisk-modules" would false-positive on
    # "asterisk-modules-core", so each token's package name is isolated
    # before comparing.
    names = []
    for token in field_value.split(","):
        token = token.strip()
        if token:
            names.append(token.split(" ", 1)[0])
    return names


def check_asterisk_core_only_dependency(deb_paths: "dict[str, str]") -> "list[str]":
    if "asterisk" not in deb_paths:
        return ["asterisk package was not built"]

    errors = []
    depends_names = _dependency_package_names(deb_field(deb_paths["asterisk"], "Depends"))
    if CORE_PACKAGE not in depends_names:
        errors.append(f"asterisk does not Depend on {CORE_PACKAGE}")
    if META_PACKAGE in depends_names:
        errors.append(f"asterisk must not Depend on {META_PACKAGE} (Suggests only)")

    recommends_names = _dependency_package_names(deb_field(deb_paths["asterisk"], "Recommends"))
    if META_PACKAGE in recommends_names:
        errors.append(f"asterisk must not Recommend {META_PACKAGE} (Suggests only)")

    return errors
