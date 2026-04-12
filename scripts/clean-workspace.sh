#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

echo "Pulizia artefatti runtime..."

rm -rf frontend/.next
rm -f frontend/tsconfig.tsbuildinfo

find backend -type d -name '__pycache__' -prune -exec rm -rf {} +
find backend -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

find . -type f -name '.DS_Store' -delete

mkdir -p runtime/logs backend/data

echo "Pulizia completata."
