#!/usr/bin/env bash

set -euo pipefail

export COMPOSE_PARALLEL_LIMIT="${COMPOSE_PARALLEL_LIMIT:-1}"

project_root="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
  pwd
)"

cd "$project_root"

action="up"
if [[ $# -gt 0 && "${1:-}" != -* ]]; then
  action="$1"
  shift
fi

case "$action" in
  up)
    docker compose up --remove-orphans "$@"
    ;;
  down)
    docker compose down "$@"
    ;;
  logs)
    docker compose logs --follow "$@"
    ;;
  *)
    echo "Usage: uv dev [up|down|logs] [docker compose options]" >&2
    exit 2
    ;;
esac
