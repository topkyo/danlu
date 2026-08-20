#!/usr/bin/env bash
# Print the first available Python >=3.10 interpreter and exit.
# Obsidian GUI / launchd / systemd often provide a minimal PATH where
# `python3` is Apple /usr/bin/python3 (3.9); prefer explicit candidates.
set -euo pipefail

for candidate in \
  ${AIWIKI_PYTHON:+"$AIWIKI_PYTHON"} \
  /usr/local/bin/python3 \
  /opt/homebrew/bin/python3 \
  "$HOME/.local/bin/python3" \
  python3.14 python3.13 python3.12 python3.11 python3.10 \
  python3; do
  [ -n "$candidate" ] || continue
  if ! command -v "$candidate" >/dev/null 2>&1 && [ ! -x "$candidate" ]; then
    continue
  fi
  version="$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
  case "$version" in
    3.1[0-9]|3.[2-9][0-9]|[4-9].*)
      printf '%s\n' "$candidate"
      exit 0
      ;;
  esac
done
echo "error: need Python >= 3.10 for aiwiki. Set AIWIKI_PYTHON." >&2
exit 1
