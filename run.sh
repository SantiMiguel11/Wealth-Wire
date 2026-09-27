#!/usr/bin/env bash
# Fiduciary Wire: create the venv if missing, install requirements, run one ingestion, start the server.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3.13 python3.12 python3.11 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then PY="$c"; break; fi
  done
fi
[ -n "$PY" ] || { echo "Python 3.11+ is required." >&2; exit 1; }

if [ ! -x .venv/bin/python ]; then
  echo "→ creating .venv with $PY"
  "$PY" -m venv .venv
fi
if [ ! -f .venv/.requirements.stamp ] || [ requirements.txt -nt .venv/.requirements.stamp ]; then
  echo "→ installing requirements"
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r requirements.txt
  touch .venv/.requirements.stamp
fi

echo "→ ingesting (this takes a minute: ≥2s between requests to the same host)"
.venv/bin/python -m fiduciarywire ingest || echo "!! ingestion reported no successful sources — see SOURCES.md. Starting the server anyway."

HOST="${FIDUCIARYWIRE_HOST:-${WEALTHWIRE_HOST:-127.0.0.1}}"
PORT="${FIDUCIARYWIRE_PORT:-${WEALTHWIRE_PORT:-8000}}"
echo "→ Fiduciary Wire at http://localhost:${PORT}  (re-ingests every 2 hours; Ctrl-C to stop)"
exec .venv/bin/python -m fiduciarywire serve --host "$HOST" --port "$PORT"
