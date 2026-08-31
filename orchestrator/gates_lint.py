"""Gates 3 and 5. dh_missing and lintian are both real Debian tools invoked
by the build (dh_missing via debhelper's dh sequence, lintian as a separate
post-build command); this module only parses their output."""


def check_dh_missing(build_log_text: str) -> "list[str]":
    """Failure lines from a dh_missing run: the per-file reports plus the abort.

    dh_missing names each uninstalled file on a `warning:` line and only the
    final `missing files, aborting` line is an `error:`, so both prefixes are
    needed for the gate report to name the files."""
    return [
        line
        for line in build_log_text.splitlines()
        if line.startswith("dh_missing: error:") or "is not installed to anywhere" in line
    ]


def parse_lintian(output: str) -> "tuple[list[str], list[str]]":
    errors = [line for line in output.splitlines() if line.startswith("E: ")]
    warnings = [line for line in output.splitlines() if line.startswith("W: ")]
    return errors, warnings


def lintian_gate_errors(returncode: int, output: str) -> "list[str]":
    """Gate 5's failures: the parsed E: lines, plus a synthetic failure when
    lintian itself did not run to completion. lintian exits 0 for a clean
    package and 2 for a --fail-on error policy violation (already visible as
    E: lines); any other exit code is a run-time tool error (e.g. 1, a read
    or internal failure) that prints no E: line and must not pass the gate
    as clean."""
    errors, _warnings = parse_lintian(output)
    if returncode not in (0, 2):
        errors = errors + [f"lintian exited {returncode} without completing: {output.strip()}"]
    return errors
