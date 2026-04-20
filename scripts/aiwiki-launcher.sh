#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

for candidate in "$HOME/.local/bin" "$HOME/.local/npm/bin" "$HOME/bin"; do
  if [ -d "$candidate" ]; then
    case ":${PATH:-}:" in
      *":$candidate:"*) ;;
      *) PATH="$candidate${PATH:+:$PATH}" ;;
    esac
  fi
done
export PATH
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

exec python3 -m aiwiki.cli --root "$PROJECT_ROOT" "$@"
