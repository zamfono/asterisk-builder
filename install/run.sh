#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip install --quiet --requirement requirements.txt
exec ./.venv/bin/ansible-playbook playbook.yaml "$@"
