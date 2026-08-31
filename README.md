# asterisk-builder

Builds and publishes module-split [Asterisk](https://www.asterisk.org/) 22
packages for Debian 13 (trixie, amd64), served as a signed APT repository at
<https://packages.zamfono.com/debian/asterisk>.

*Unofficial packages, built by Zamfono; not affiliated with or endorsed by
Sangoma. Asterisk® is a registered trademark of Sangoma Technologies.*

## Key fingerprint

The Zamfono archive master key fingerprint is:

    181B A83E BC2D 123A A21E  5F22 F94F DC7F FFB6 2A49

Verify the keyring installed from <https://packages.zamfono.com> against it —
this README is a channel independent of that server.

## Installation

```sh
wget https://packages.zamfono.com/debian/zamfono-archive-keyring_latest_all.deb
sudo dpkg -i zamfono-archive-keyring_latest_all.deb
sudo tee /etc/apt/sources.list.d/zamfono.sources <<'EOF'
Types: deb
URIs: https://packages.zamfono.com/debian/asterisk/22
Suites: trixie
Components: main
Signed-By: /usr/share/keyrings/zamfono-archive-keyring.gpg
EOF
sudo apt update && sudo apt install asterisk
```

Full instructions — source packages, debug symbols, the `latest`/`LTS`
paths — are on the
[repository landing page](https://packages.zamfono.com/debian/asterisk).

## What you get

Debian's own `asterisk` source, unmodified — the only change is to the
packaging: the single modules package is split into functional groups
(`asterisk-modules-pjsip`, `asterisk-modules-voicemail`, …), so
`apt install asterisk` brings only the core modules and each capability is
an explicit opt-in. `asterisk-modules` is the metapackage pulling in every
group; the
[landing page](https://packages.zamfono.com/debian/asterisk) lists them all.
Matching source packages are published alongside, so every change is
inspectable with `apt source asterisk`.

## Versioning

Versions are Debian's, with a rebuild counter appended:
`1:22.10.1+dfsg+…-1` becomes `1:22.10.1+dfsg+…-1+zamfono13.1`. The suffix
sorts strictly newer than the Debian base (so these packages win over
same-version Debian ones), `13` pins the target release, and `.N` counts
rebuilds of one unchanged Debian version — it increments only when the
packaging here changes without a new Debian upload.

## How it works

A six-hourly timer compares Debian `sid`'s `asterisk` source version with
the published one; when sid is newer, one run performs:

1. **Fetch + patch** — `apt-get source` from sid; the module-split
   packaging patch must apply with zero fuzz.
2. **Build** — in a pbuilder trixie chroot: all library dependencies come
   from trixie (only `debhelper` is pinned from sid), and the compile
   itself runs network-isolated.
3. **Gates** — every build must pass: manifest coverage, `dh_missing`,
   dependency derivation, lintian (errors fail), a clean install of every
   package group in a fresh container, a module-load check in a running
   Asterisk, and upgrade + purge checks against the live repository.
4. **Publish** — the `.changes` is signed with the builder's upload key
   and uploaded to the archive host, which verifies it against its
   uploader allowlist, signs the indexes, and serves them.

The full contract lives in [`docs/specs.md`](docs/specs.md).

## Repository layout

- [`docs/specs.md`](docs/specs.md) — what this system is and does.
- `orchestrator/` — the build/gate/upload pipeline
  (`python3 -m orchestrator.cli run`).
- `manifest/modules.json` — the functional module groups (the product).
- `packaging/patches/` — the module-split packaging patch.
- `install/` — Ansible provisioning of the build host.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install pytest
.venv/bin/python -m pytest tests/unit
```

The suite is stdlib-only and runs without network or Debian tooling.

## Operations

Operator-only: `install/run.sh` provisions the build host. The access model
and procedure are in [`docs/specs.md`](docs/specs.md).

## Contributing, security, license

- [`CONTRIBUTING.md`](CONTRIBUTING.md) — issues first, PRs against `main`.
- [`SECURITY.md`](SECURITY.md) — what to report here vs. upstream, and how.
- [`LICENSE`](LICENSE) — GPL-2+ (the packaging derives from Debian's
  GPL-2 asterisk packaging).
