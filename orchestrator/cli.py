"""asterisk-builder's entry point. `check` only reports whether a newer sid
source exists (no side effects). `run` is what the systemd timer invokes:
check, and only if newer, fetch/patch/build/gate/sign/upload; always under
the host lock. Gates that only need the already-produced build artifacts
and the containerized install gates run in one non-fail-fast pass so a
candidate's full gate report is visible before it is discarded; the
lifecycle gates (module load, upgrade, purge) run afterwards, only once
that pass is clean. Publishing is debsign + an sftp batch upload; ingest
and serving are the packages host's job."""
import argparse
import concurrent.futures
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from orchestrator.gates_deps import check_cross_group_dependencies, check_unresolved_shlibs
from orchestrator.gates_lint import check_dh_missing, lintian_gate_errors, parse_lintian
from orchestrator.gates_meta import check_asterisk_core_only_dependency, check_meta_package
from orchestrator.gates_upgrade import purge_check_script, upgrade_check_script
from orchestrator.lock import acquire_lock
from orchestrator.manifest import (
    built_modules_from_debs,
    load_manifest,
    validate_full_coverage,
    validate_structure,
)
from orchestrator.packaging_overlay import install_patches, set_changelog_version_cmd
from orchestrator.pbuilder import run_build
from orchestrator.published import published_asterisk_versions
from orchestrator.sid_source import (
    SID_SOURCELIST_CONTENT,
    parse_showsrc_version,
    prepare_apt_state,
    scoped_apt_opts,
)
from orchestrator.version import compute_next_zamfono_version
from orchestrator.versioncheck import should_build

RUNTIME_DIR = "/var/lib/zamfono/asterisk-builder/run"
# `.list`, not `.sources` — apt selects its parser by file extension.
SID_SOURCELIST_PATH = f"{RUNTIME_DIR}/sid.list"
APT_STATE_DIR = f"{RUNTIME_DIR}/apt"
LOCK_PATH = f"{RUNTIME_DIR}/lock"
WORKSPACE_BASE = "/var/lib/zamfono/asterisk-builder/workspace"
MANIFEST_PATH = "manifest/modules.json"
# One line: the key id debsign signs .changes with. Host-local, never in Git.
UPLOAD_KEYID_FILE = "/etc/zamfono/asterisk-builder/upload-keyid"
# The chrooted upload account on the packages host; its forced
# internal-sftp session starts in /incoming.
UPLOAD_TARGET = "zamfono-upload@10.250.0.2"
CHANGELOG_NAME = "Zamfono Packaging"
CHANGELOG_EMAIL = "packages@zamfono.com"
# [trusted=yes]: the candidate is unsigned by design (the .changes is
# signed for upload; the archive Release is signed on the packages host).
CANDIDATE_REPO_SETUP = (
    "echo 'deb [trusted=yes] file:/out ./' > /etc/apt/sources.list.d/zamfono-candidate.list"
    " && apt-get update"
)


def _safe_name(version: str) -> str:
    """Maps a Debian version to a filesystem- and container-name-safe string."""
    return re.sub(r"[^A-Za-z0-9_.-]", "-", version)


def _write_sid_sourcelist() -> None:
    prepare_apt_state(APT_STATE_DIR)
    Path(SID_SOURCELIST_PATH).write_text(SID_SOURCELIST_CONTENT)


def _index_candidate_repo(workspace: Path) -> None:
    """dpkg-scanpackages (dpkg-dev) writes the flat Packages index the gate
    containers' candidate apt source reads."""
    result = subprocess.run(
        ["dpkg-scanpackages", "--multiversion", "."],
        cwd=workspace, check=True, capture_output=True, text=True,
    )
    (workspace / "Packages").write_text(result.stdout)


def find_extracted_source_dir(dest_dir: "str | Path", package: str) -> Path:
    """Locates the single directory `apt-get source` extracted."""
    dest_dir = Path(dest_dir)
    matches = [p for p in dest_dir.glob(f"{package}-*") if p.is_dir()]
    if len(matches) != 1:
        raise LookupError(
            f"expected exactly one {package}-* directory in {dest_dir}, found {len(matches)}"
        )
    return matches[0]


def parse_module_show(output: str) -> "list[str]":
    """Module-load gate: failure lines from `asterisk -rx "module show"` —
    every packaged module must load without an unresolved hard module or
    shared-library dependency in a running Asterisk instance."""
    return [
        line
        for line in output.splitlines()
        if "Failed" in line and not line.lower().startswith("module")
    ]


def sid_asterisk_version() -> str:
    _write_sid_sourcelist()
    # scoped_apt_opts pins Dir::Etc::sourcelist to the throwaway sid-only
    # list above, so neither command ever touches the host's real (trixie)
    # apt configuration.
    apt_opts = scoped_apt_opts(SID_SOURCELIST_PATH, APT_STATE_DIR)
    subprocess.run(["apt-get", *apt_opts, "update"], check=True)
    result = subprocess.run(
        ["apt-cache", *apt_opts, "showsrc", "asterisk"],
        capture_output=True, text=True, check=True,
    )
    return parse_showsrc_version(result.stdout)


def _cmd_check(_args) -> int:
    sid_version = sid_asterisk_version()
    published = published_asterisk_versions()
    latest_published = published[0] if published else None
    if should_build(sid_version, latest_published):
        print(f"newer sid asterisk source available: {sid_version} (published: {latest_published})")
    else:
        print(f"up to date: sid={sid_version} published={latest_published}")
    return 0


def _fetch_and_patch(workspace: Path, sid_version: str, zamfono_version: str) -> None:
    _write_sid_sourcelist()
    # A failed attempt's workspace is kept for diagnosis, so a retry for the
    # same candidate can find workspace/source already populated and patched:
    # shutil.move below would then nest the freshly extracted tree inside it
    # instead of replacing it, and install_patches would reapply onto the
    # stale tree. Discarding it here, at the start of the next attempt,
    # keeps it inspectable right up until a new attempt needs the space.
    shutil.rmtree(workspace, ignore_errors=True)
    # Downloaded into the workspace root, not a subdirectory: a `3.0
    # (quilt)` source build reads the .orig tarball from the source tree's
    # parent, which is where the build also writes its products.
    workspace.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["apt-get", *scoped_apt_opts(SID_SOURCELIST_PATH, APT_STATE_DIR), "source", f"asterisk={sid_version}"],
        cwd=workspace, check=True,
    )
    extracted = find_extracted_source_dir(workspace, "asterisk")
    source_dir = workspace / "source"
    shutil.move(str(extracted), str(source_dir))
    # apt-get source leaves the sid .dsc next to the tarballs; run_build
    # later generates the Zamfono .dsc with dpkg-source -b and must find
    # exactly one, so the fetched one is junk once the tree is extracted.
    for fetched_dsc in workspace.glob("*.dsc"):
        fetched_dsc.unlink()
    install_patches(source_dir, "packaging/patches")
    # Stamps zamfono_version into debian/changelog's top entry — without
    # this, the build runs under the raw sid version and every
    # ${binary:Version}-based gate check fails. DEBEMAIL and DEBFULLNAME
    # name the author of that entry; left unset, dch composes one from the
    # build account and the host name, which lintian rejects as a bogus
    # mail host.
    subprocess.run(
        set_changelog_version_cmd(zamfono_version),
        cwd=source_dir, check=True,
        env={**os.environ, "DEBEMAIL": CHANGELOG_EMAIL, "DEBFULLNAME": CHANGELOG_NAME},
    )


def _deb_paths_by_package(workspace: Path) -> "dict[str, str]":
    return {p.name.split("_", 1)[0]: str(p) for p in workspace.glob("*.deb")}


def _container_check(name: str, workspace: Path, script: str) -> bool:
    """Runs `script` in a throwaway docker.io/library/debian:13 container
    with the candidate directory mounted at /out; True when it exits 0.
    The image reference is fully qualified: Debian defines no
    unqualified-search-registries, so podman will not expand a bare
    "debian:13" on its own. --rm removes the container on exit; the
    pre-clean covers only a prior run killed hard enough to skip that."""
    subprocess.run(["podman", "rm", "-f", name], capture_output=True)
    result = subprocess.run(
        [
            "podman", "run", "--rm", "--name", name,
            "-v", f"{workspace}:/out", "-w", "/out",
            "docker.io/library/debian:13", "sh", "-c", script,
        ],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def _run_gates_for_candidate(workspace: Path, candidate_version: str, build_log: str) -> "list[tuple[str, list[str]]]":
    manifest = load_manifest(MANIFEST_PATH)
    deb_paths = _deb_paths_by_package(workspace)
    built_modules = built_modules_from_debs(list(deb_paths.values()))

    changes_paths = list(workspace.glob("*.changes"))
    lintian_output = ""
    lintian_returncode = 0
    if changes_paths:
        lintian_result = subprocess.run(
            ["lintian", "--fail-on", "error", str(changes_paths[0])],
            capture_output=True, text=True,
        )
        lintian_output = lintian_result.stdout + lintian_result.stderr
        lintian_returncode = lintian_result.returncode
    lintian_errors = lintian_gate_errors(lintian_returncode, lintian_output)
    # Warnings are not gate failures, but the spec requires them retained.
    # They are printed to this process's stdout, which systemd captures into
    # the journal — the durable build log for a run whose workspace does not
    # survive success.
    _lintian_errors, lintian_warnings = parse_lintian(lintian_output)
    for warning in lintian_warnings:
        print(f"lintian warning: {warning}")

    gates = [
        (
            "manifest coverage",
            lambda: validate_structure(manifest) + validate_full_coverage(manifest, built_modules),
        ),
        ("dh_missing", lambda: check_dh_missing(build_log)),
        (
            "dependency derivation",
            lambda: check_unresolved_shlibs(build_log)
            + check_cross_group_dependencies(manifest, deb_paths, candidate_version)
            + check_asterisk_core_only_dependency(deb_paths),
        ),
        ("lintian", lambda: lintian_errors),
        (
            "meta-package coverage",
            lambda: check_meta_package(manifest, built_modules, deb_paths["asterisk-modules"], candidate_version)
            if "asterisk-modules" in deb_paths
            else ["asterisk-modules package was not built"],
        ),
        (
            "minimal install",
            lambda: []
            if _container_check(
                f"zamfono-minimal-{_safe_name(candidate_version)}",
                workspace,
                f"{CANDIDATE_REPO_SETUP} && apt-get install -y asterisk asterisk-modules-core",
            )
            else ["minimal asterisk + asterisk-modules-core install failed"],
        ),
    ]
    for package in deb_paths:
        if package in ("asterisk", "asterisk-config", "asterisk-modules-core", "asterisk-modules"):
            continue
        # dbgsym packages are debhelper's automatic detached-symbol
        # companions, not module groups: they carry no module and are
        # installable only alongside the package they shadow.
        if package.endswith("-dbgsym"):
            continue
        gates.append(
            (
                f"optional install: {package}",
                lambda pkg=package: []
                if _container_check(
                    f"zamfono-install-{pkg}",
                    workspace,
                    f"{CANDIDATE_REPO_SETUP} && apt-get install -y {pkg}",
                )
                else [f"install failed for {pkg}"],
            )
        )

    # Not fail-fast: every gate runs so a candidate's full gate report is
    # visible in one pass before it is discarded. The gates are independent
    # (each container gate uses its own throwaway container), and the
    # install gates dominate wall-clock, so they run concurrently, one
    # worker per core.
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count()) as pool:
        error_lists = list(pool.map(lambda gate: gate[1](), gates))
    return [
        (name, errors)
        for (name, _check), errors in zip(gates, error_lists)
        if errors
    ]


def _run_module_load_and_upgrade_gates(workspace: Path, candidate_version: str, published: "str | None") -> "list[str]":
    container_name = f"zamfono-lifecycle-{_safe_name(candidate_version)}"
    subprocess.run(["podman", "rm", "-f", container_name], capture_output=True)
    subprocess.run(
        [
            "podman", "run", "-d", "--name", container_name,
            "-v", f"{workspace}:/out", "-w", "/out",
            "docker.io/library/debian:13", "sleep", "infinity",
        ],
        check=True,
    )
    try:
        # asterisk-modules depends on every emitted group, so these two
        # names pull in the complete candidate.
        install = subprocess.run(
            ["podman", "exec", container_name, "sh", "-c",
             f"{CANDIDATE_REPO_SETUP} && apt-get install -y asterisk asterisk-modules"],
            capture_output=True, text=True,
        )
        if install.returncode != 0:
            return [f"full install for module-load check failed: {install.stdout + install.stderr}"]

        start_result = subprocess.run(
            ["podman", "exec", container_name, "service", "asterisk", "start"],
            capture_output=True, text=True,
        )
        if start_result.returncode != 0:
            return [f"service asterisk start failed: {start_result.stdout + start_result.stderr}"]

        # `service asterisk start` returns before the control socket exists;
        # probing immediately hits "Unable to connect to remote asterisk".
        # `core waitfullybooted` blocks until Asterisk is up, and the retry
        # covers the moments before the socket itself appears.
        boot_wait = subprocess.run(
            ["podman", "exec", container_name, "sh", "-c",
             'for i in $(seq 1 60); do asterisk -rx "core waitfullybooted" 2>/dev/null && exit 0; sleep 1; done; exit 1'],
            capture_output=True, text=True,
        )
        if boot_wait.returncode != 0:
            return [f"asterisk did not become fully booted: {boot_wait.stdout + boot_wait.stderr}"]

        module_show = subprocess.run(
            ["podman", "exec", container_name, "asterisk", "-rx", "module show"],
            capture_output=True, text=True,
        )
        # A running Asterisk instance always lists at least the modules it
        # loaded; a nonzero exit or empty stdout means Asterisk exited
        # before or during the probe rather than reporting no failures.
        if module_show.returncode != 0 or not module_show.stdout.strip():
            errors = [
                f"module show probe failed: returncode {module_show.returncode}: "
                f"{module_show.stdout + module_show.stderr}"
            ]
        else:
            errors = list(parse_module_show(module_show.stdout))

        if published is not None:
            # A fresh container, not the lifecycle one: the upgrade check
            # starts from the previous version, and the candidate already
            # installed above could only be downgraded.
            upgrade_name = f"zamfono-upgrade-{_safe_name(candidate_version)}"
            subprocess.run(["podman", "rm", "-f", upgrade_name], capture_output=True)
            upgrade_result = subprocess.run(
                [
                    "podman", "run", "--rm", "--name", upgrade_name,
                    "-v", f"{workspace}:/out",
                    "-w", "/out", "docker.io/library/debian:13", "sh", "-c",
                    upgrade_check_script(published, candidate_version),
                ],
                capture_output=True, text=True,
            )
            if upgrade_result.returncode != 0:
                errors.append(f"upgrade check failed: {upgrade_result.stdout + upgrade_result.stderr}")

        purge_result = subprocess.run(
            ["podman", "exec", container_name, "sh", "-c", purge_check_script()],
            capture_output=True, text=True,
        )
        if purge_result.returncode != 0:
            errors.append(f"purge check failed: {purge_result.stdout + purge_result.stderr}")

        return errors
    finally:
        subprocess.run(["podman", "rm", "-f", container_name])


def _changes_referenced_files(changes_path: Path) -> "list[str]":
    """Filenames from the .changes Files: stanza (5th field per line)."""
    names = []
    in_files = False
    for line in changes_path.read_text().splitlines():
        if in_files and line.startswith(" "):
            names.append(line.split()[4])
        else:
            in_files = line.startswith("Files:")
    return names


def _sign_and_upload(workspace: Path) -> None:
    keyid = Path(UPLOAD_KEYID_FILE).read_text().strip()
    # pbuilder leaves a companion *_source.changes next to the full
    # *_amd64.changes; the full one already carries source and binaries,
    # and it is the only one uploaded.
    changes_paths = [
        p for p in workspace.glob("*.changes")
        if not p.name.endswith("_source.changes")
    ]
    if len(changes_paths) != 1:
        raise LookupError(
            f"expected exactly one .changes in {workspace}, found {len(changes_paths)}"
        )
    changes = changes_paths[0]
    subprocess.run(["debsign", "--no-re-sign", "-k", keyid, str(changes)], check=True)
    # Plain OpenSSH sftp in batch mode (-b aborts on the first error): the
    # upload account's chroot forces internal-sftp and starts in /incoming,
    # so `put` lands files there. The .changes itself is transferred last —
    # ingestion on the packages host triggers on *.changes, and everything
    # it references must already be present.
    batch = "".join(
        f"put {workspace / name}\n" for name in _changes_referenced_files(changes)
    ) + f"put {changes}\n"
    subprocess.run(
        ["sftp", "-b", "-", UPLOAD_TARGET],
        input=batch, text=True, check=True,
    )


def _cmd_run(_args) -> int:
    lock = acquire_lock(LOCK_PATH)
    if lock is None:
        print("another run holds the lock; exiting without changes")
        return 0
    try:
        sid_version = sid_asterisk_version()
        published = published_asterisk_versions()
        latest_published = published[0] if published else None
        if not should_build(sid_version, latest_published):
            print(f"up to date: sid={sid_version} published={latest_published}")
            return 0

        zamfono_version = compute_next_zamfono_version(sid_version, published)
        workspace = Path(WORKSPACE_BASE) / _safe_name(zamfono_version)

        _fetch_and_patch(workspace, sid_version, zamfono_version)

        build_result = run_build(str(workspace))
        # _fetch_and_patch creates the workspace; a run that never got that
        # far still reports the log on stderr below.
        if workspace.is_dir():
            (workspace / "build.log").write_text(build_result.log)
        if not build_result.success:
            print(build_result.log, file=sys.stderr)
            return 1

        _index_candidate_repo(workspace)
        cheap_failures = _run_gates_for_candidate(workspace, zamfono_version, build_result.log)
        if cheap_failures:
            for name, errors in cheap_failures:
                print(f"gate ({name}) failed: {errors}", file=sys.stderr)
            return 1

        lifecycle_errors = _run_module_load_and_upgrade_gates(workspace, zamfono_version, latest_published)
        if lifecycle_errors:
            print("lifecycle gates failed:\n" + "\n".join(lifecycle_errors), file=sys.stderr)
            return 1

        _sign_and_upload(workspace)
        shutil.rmtree(workspace, ignore_errors=True)  # successful build trees are removed
        return 0
    finally:
        lock.close()


def main(argv: "list[str]") -> int:
    parser = argparse.ArgumentParser(prog="orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check").set_defaults(func=_cmd_check)
    subparsers.add_parser("run").set_defaults(func=_cmd_run)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
