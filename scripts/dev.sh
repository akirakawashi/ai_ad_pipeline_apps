#!/usr/bin/env bash

set -euo pipefail

project_root="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
  pwd
)"
runtime_dir="$project_root/.runtime"
backend_env_file="$project_root/apps/backend/.env"
worker_pid_file="$runtime_dir/worker.pid"
worker_path="$project_root/apps/backend/src/worker.py"
python_path="$project_root/.venv/bin/python"

cd "$project_root"
mkdir -p "$runtime_dir/worker"

is_service_running() {
  docker compose ps --status running --services | grep -qx "$1"
}

start_missing_infrastructure() {
  local missing_services=()

  for service in postgres minio; do
    if ! is_service_running "$service"; then
      missing_services+=("$service")
    fi
  done

  if [[ ${#missing_services[@]} -gt 0 ]]; then
    echo "Starting Docker services: ${missing_services[*]}"
    docker compose up --detach "${missing_services[@]}"
  else
    echo "PostgreSQL and MinIO are already running"
  fi
}

wait_for_postgres() {
  echo "Waiting for PostgreSQL"
  local attempt
  for attempt in {1..60}; do
    if docker compose exec -T postgres sh -c \
      'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
      >/dev/null 2>&1; then
      return
    fi
    sleep 1
  done

  echo "PostgreSQL did not become ready in 60 seconds" >&2
  exit 1
}

wait_for_minio() {
  echo "Waiting for MinIO"
  local attempt
  for attempt in {1..60}; do
    if "$python_path" -c \
      "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9000/minio/health/live')" \
      >/dev/null 2>&1; then
      return
    fi
    sleep 1
  done

  echo "MinIO did not become ready in 60 seconds" >&2
  exit 1
}

apply_migrations() {
  echo "Applying Alembic migrations"
  docker compose run --rm migrate
}

start_backend() {
  if is_service_running backend; then
    echo "Backend is already running"
    return
  fi

  echo "Starting backend"
  docker compose up --detach backend
}

wait_for_backend() {
  echo "Waiting for backend"
  local attempt
  for attempt in {1..60}; do
    if "$python_path" -c \
      "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthcheck')" \
      >/dev/null 2>&1; then
      return
    fi
    sleep 1
  done

  echo "Backend did not become ready in 60 seconds" >&2
  docker compose logs --tail=100 backend >&2
  exit 1
}

worker_is_running() {
  if [[ ! -f "$worker_pid_file" ]]; then
    return 1
  fi

  local worker_pid
  worker_pid="$(cat "$worker_pid_file")"
  if ! kill -0 "$worker_pid" 2>/dev/null; then
    rm -f "$worker_pid_file"
    return 1
  fi

  if [[ ! -r "/proc/$worker_pid/cmdline" ]] || \
    ! tr '\0' ' ' <"/proc/$worker_pid/cmdline" | grep -Fq "$worker_path"; then
    rm -f "$worker_pid_file"
    return 1
  fi
}

start_worker() {
  if worker_is_running; then
    echo "Worker is already running with PID $(cat "$worker_pid_file")"
    return
  fi

  rm -f "$worker_pid_file"
  echo "Starting local worker"
  if [[ -f "$backend_env_file" ]]; then
    set -a
    source "$backend_env_file"
    set +a
  fi
  "$python_path" "$worker_path" &
  local worker_pid=$!
  echo "$worker_pid" >"$worker_pid_file"

  cleanup_worker() {
    if kill -0 "$worker_pid" 2>/dev/null; then
      kill "$worker_pid"
      wait "$worker_pid" 2>/dev/null || true
    fi
    rm -f "$worker_pid_file"
  }

  trap cleanup_worker EXIT INT TERM
  wait "$worker_pid"
}

stop_stack() {
  if worker_is_running; then
    local worker_pid
    worker_pid="$(cat "$worker_pid_file")"
    echo "Stopping local worker with PID $worker_pid"
    kill "$worker_pid"
    rm -f "$worker_pid_file"
  fi

  docker compose down
}

case "${1:-up}" in
  up)
    if [[ ! -x "$python_path" ]]; then
      echo "Project environment was not found: $python_path" >&2
      echo "Run: uv sync" >&2
      exit 1
    fi

    start_missing_infrastructure
    wait_for_postgres
    wait_for_minio
    apply_migrations
    start_backend
    wait_for_backend
    start_worker
    ;;
  down)
    stop_stack
    ;;
  logs)
    docker compose logs --follow backend postgres minio
    ;;
  *)
    echo "Usage: ./scripts/dev.sh [up|down|logs]" >&2
    exit 2
    ;;
esac
