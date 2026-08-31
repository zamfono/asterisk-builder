# `zamfono/asterisk-builder` Specification

## Purpose

`zamfono/asterisk-builder` defines the build host `asterisk-builder`. It builds
Debian 13 (trixie) amd64 packages of **Asterisk 22** from Debian's `asterisk` source
package, split into functional module groups, verifies every build against a set of
gates, and uploads the result over the private network to the Zamfono packages host
(`zamfono/packages`), which publishes it.

**Scope is locked: one version, one distro** — Asterisk 22 on Debian 13/amd64. The
build starts from Debian's source package (building from upstream tarballs would
lose AMR support and all of Debian's packaging).

## Non-goals

- **Archive management.** The builder never runs `reprepro`, never signs
  `Release` files, and never holds the archive signing key. Its only key is its
  upload key.
- **Multi-version / multi-distro machinery.** The repository URL layout leaves room
  for more lines later; only Asterisk 22 / trixie is built.
- **Publish orchestration.** Publishing is `debsign` + an SFTP batch upload; ingest and serving
  are the packages host's job.

## Build pipeline

1. **Trigger:** a systemd timer runs the freshness check six-hourly. It compares
   the `asterisk` source version in Debian `sid` against the last published
   version; nothing newer → exit.
2. **Fetch:** `apt-get source asterisk` from sid. Building sid source on trixie
   requires `debhelper` (and its version-locked binaries) from **unstable**, pinned
   so only debhelper is raised.
3. **Patch:** the module-split packaging patch must apply with **zero fuzz**
   against the fetched source; fuzz means the Debian packaging moved and the patch
   needs a rebase, not a forced apply.
4. **Version:** append `+zamfono13.N` to the Debian source version. `N` starts at 1
   for each newly imported Debian version, and the result must compare strictly
   newer (`dpkg --compare-versions`) than the last published version.
5. **Build:** `pbuilder` with a trixie base chroot (one base tarball, kept current
   with `pbuilder update`). The build phase runs network-isolated: a networked prep
   phase fetches everything, the compile itself runs offline — cheap, real
   supply-chain hardening.
6. **Gates:** every gate must pass (see below); any failure aborts before upload.
7. **Sign and upload:** `debsign` the `.changes` with the builder upload key, then
   an OpenSSH `sftp` batch upload over the private network into the packages host's
   incoming directory (the upload account's forced `internal-sftp` accepts nothing
   else, and trixie's `dput` offers no sftp method). The `.changes` file is
   transferred after everything it references, because ingestion on the packages
   host triggers on `*.changes`.
8. **Upload content:** the full `.changes` — binaries, source (`.dsc` + tarballs,
   so the archive can publish `deb-src`), and the `-dbgsym` packages (routed into a
   debug suite by the packages host).

## The module split (the product)

The functional module grouping is the point of this repository:

- `manifest/modules.json` defines the functional groups (25 today) and their
  module coverage; the `asterisk` core package depends only on
  `asterisk-modules-core`.
- `app_test.so` stays in `core`: it is an operator-facing tone/echo test tool
  (`TestServer`/`TestClient`).
- `test_*.so` and `res_stasis_test.so` are excluded: Asterisk test-framework
  modules. `res_stasis_test` escapes the `test_*` glob and must be removed
  explicitly. Verified against Asterisk `loader.c`.
- There is no `asterisk-modules-voicemail-imap` group: `app_voicemail`'s IMAP
  backend links `libc-client` (uw-imap), which Debian removed. Revisit only if a
  replacement is packaged.

## Gates

The gates are the quality bar; they run on every build:

- **Manifest coverage** — every shipped module is assigned to exactly one group in
  `manifest/modules.json`, and the manifest names no module the build did not
  produce.
- **`dh_missing`** — no built file is silently dropped from all packages.
- **Dependency derivation** — package dependencies derive correctly from the split.
- **Lintian** — errors fail the build; warnings are retained in the build output
  for review, and do not fail it.
- **Install** — the packages install cleanly on a pristine trixie system.
- **Module load** — every packaged module loads in a running Asterisk. This gate
  flags **load failures only**, deliberately: `module show` prints
  `Running`/`Not Running` (never "Failed"), and a dependency-declined module is
  indistinguishable there from a config- or hardware-absent one (Debian's
  `modules.conf.sample` noloads `res_hep*`/`app_voicemail_odbc`, and modules like
  `chan_dahdi` show `Not Running` without hardware). Any "Not Running" or
  present-set check false-positives on every build. Investigated three times;
  settled — do not "fix" it.
- **Meta-package coverage** — the meta packages pull in the intended groups.
- **Upgrade** — upgrading from the previously published version succeeds.
- **Purge** — removing and purging leaves the system clean.

## Keys

- The builder holds exactly one signing identity: its **upload key**, used by
  `debsign` on `.changes` files. The packages host authorizes it in reprepro's
  `conf/uploaders` — that listing is what makes this builder allowed to publish.
- The archive signing key never exists on this host. A builder compromise therefore
  cannot sign the archive, regardless of how the build runs.
- SSH to the packages host uses the private network with
  `StrictHostKeyChecking=yes` and a provisioned `known_hosts` entry for the packages
  host.

## Provisioning

Provisioned with Ansible, run by hand from the operator's machine — deployment is a
manual playbook run, never a service. This repository carries `install/`:

- `playbook.yaml` — the host's full configuration (full system upgrade with a
  reboot when one is required, pbuilder and its base chroot,
  the build/gate scripts, the systemd timer and service, the debhelper pin,
  unattended security upgrades with automatic reboot at 03:00 — clear of the
  00/06/12/18 build windows). An interrupted build is simply repeated at the
  next timer firing, with one exception: a reboot during the base-chroot
  update can truncate `base-trixie.tgz`, which an operator must recreate
  (`rm` it and re-run the playbook); the 03:00 window makes that a
  non-event in practice.
- `run.sh` — entry point: creates/updates a local virtualenv from the pin file,
  runs the playbook.
- `requirements.txt` — pins the exact `ansible-core` version. `ansible.builtin`
  covers every task; no collections are installed.

No credentials in the repository: the operator's `ssh-agent` supplies the SSH key;
host verification is the operator's normal `~/.ssh/known_hosts`. The builder's
upload key (GPG) and its SSH key toward the packages host are provisioned
host-locally, outside Git.

## Network interface

- The builder offers no public services; the Hetzner Cloud Firewall blocks all
  public inbound, always. The operator administers it over the private network
  (`root@10.250.0.3`) with the packages host as SSH jump host; authentication
  is key-only.
- Outbound: Debian mirrors (source fetch, chroot maintenance) and SFTP to the
  packages host (`10.250.0.2`) for uploads.
- The packages host never reaches back into the builder.

## Verification

The gates are the per-build bar. Repository-level verification runs the real flow
end to end on the real hosts — a converged `changed=0` playbook run is not proof of
correct behavior:

1. A full build on the provisioned host passes all gates.
2. The resulting upload lands on the packages host, is ingested, and the packages
   install on a fresh trixie client via `apt`.
3. A version bump produces a `+zamfono13.N` version strictly newer than the last
   published one.
4. The timer's no-op path (sid has nothing newer) exits without building or
   uploading.

## Related repositories

- `zamfono/packages` — the archive host that ingests this builder's uploads, signs
  the published indexes, and serves them.
