#!/usr/bin/env bash
# Build sdist + wheel into dist/ for local release verification.
# Does NOT upload to PyPI (twine upload is out of scope until ops enables it).
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON="${PYTHON:-python3}"

if ! "$PYTHON" -m build --version >/dev/null 2>&1; then
  echo "error: python -m build is required; install with:" >&2
  echo "  $PYTHON -m pip install build" >&2
  exit 1
fi

rm -rf dist/
"$PYTHON" -m build --outdir dist/

echo "Release artifacts written to dist/:"
ls -la dist/
