"""Gates: upgrade and purge. Both scripts are handed to a
docker.io/library/debian:13 container shell by
`orchestrator.cli._run_module_load_and_upgrade_gates`; apt and dpkg do all
the install/upgrade/purge work, this module only builds the script text.

The upgrade check installs the previously published version from the live
public repository — the exact transition every subscribed host performs —
then upgrades to the indexed candidate directory mounted at /out.
[trusted=yes] on both sources: this gate checks the upgrade path, not
archive signatures (the packages host's verification covers those), and the
candidate is unsigned by design at this point."""

PREVIOUS_APT_LINE = (
    "deb [trusted=yes] https://packages.zamfono.com/debian/asterisk/22 trixie main"
)


def upgrade_check_script(previous_version: str, candidate_version: str) -> str:
    return (
        "set -e\n"
        "apt-get update\n"
        # the debian:13 base image ships no TLS trust store, and the
        # previous version arrives over HTTPS:
        "apt-get install -y ca-certificates\n"
        f"echo '{PREVIOUS_APT_LINE}' > /etc/apt/sources.list.d/zamfono-previous.list\n"
        "apt-get update\n"
        f"apt-get install -y asterisk={previous_version} asterisk-modules-core={previous_version}\n"
        "cp /etc/asterisk/asterisk.conf /tmp/asterisk.conf.before-upgrade\n"
        "rm /etc/apt/sources.list.d/zamfono-previous.list\n"
        "echo 'deb [trusted=yes] file:/out ./' > /etc/apt/sources.list.d/zamfono-candidate.list\n"
        "apt-get update\n"
        f"apt-get install -y asterisk={candidate_version} asterisk-modules-core={candidate_version}\n"
        "diff /tmp/asterisk.conf.before-upgrade /etc/asterisk/asterisk.conf\n"
    )


def purge_check_script() -> str:
    # Runs in the lifecycle container after the full install and module-load
    # check, so every candidate package is already present.
    return (
        "set -e\n"
        "apt-get purge -y 'asterisk*'\n"
        # A complete purge drops the names from the dpkg database entirely,
        # and dpkg-query exits 1 when its pattern matches nothing: that is
        # the outcome this gate wants, so the status listing must not
        # decide it.
        "dpkg -l 'asterisk*' || true\n"
    )
