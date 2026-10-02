#!/bin/sh
# Run from any directory. Re-running preserves secrets and persistent volumes.
set -eu
cd "$(dirname "$0")/.."
docker compose version >/dev/null
git submodule sync --recursive
git submodule update --init --recursive
if [ ! -f .env ]; then
    (umask 077; cp .env.example .env)
fi
python3 scripts/configure_env.py .env
docker compose up -d --build --wait --wait-timeout 180
