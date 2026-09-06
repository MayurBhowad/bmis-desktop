#!/usr/bin/env bash

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"


exec "$PROJECT_ROOT/python/.venv/bin/python" \
    -m bmis_desktop.main