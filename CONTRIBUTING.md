# Contributing

Issues and patches are welcome. Please open an issue before starting on a
patch of any size — the pipeline is opinionated, and agreeing on the
approach first saves you from building something that cannot merge.

## What belongs here

Packaging and building: the module split (`manifest/modules.json` and the
packaging patch), the pbuilder build, the verification gates, the upload.
Bugs in Asterisk itself belong upstream — see the note in `SECURITY.md`.

## Pull requests

- Open a pull request against `main`; the `ci` check must be green.
- Run the unit suite locally: `python3 -m pytest tests/unit`
- Write commit messages in Conventional Commits format
  (`type(scope): description`).
- Keep changes minimal and place explanatory comments at the point of use.

By contributing you agree that your contribution is licensed under the
repository's license (GPL-2+, see `LICENSE`).
