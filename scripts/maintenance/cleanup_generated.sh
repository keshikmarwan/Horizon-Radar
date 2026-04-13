#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "Cleaning generated caches in ${ROOT_DIR}"

find "${ROOT_DIR}" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "${ROOT_DIR}" -type d -name ".pytest_cache" -prune -exec rm -rf {} +
find "${ROOT_DIR}" -type d -name ".mypy_cache" -prune -exec rm -rf {} +
find "${ROOT_DIR}" -type d -name ".ruff_cache" -prune -exec rm -rf {} +

if [ -d "${ROOT_DIR}/frontend/.next" ]; then
  rm -rf "${ROOT_DIR}/frontend/.next"
fi

echo "Done."
