#!/usr/bin/env bash
# relocate_aiwiki_state_out_of_icloud.sh
#
# Move dogfood vault `.aiwiki/state` off iCloud Drive to local Application Support
# and replace it with a symlink. Prevents iCloud from forking hot JSONL append files
# such as `execution-policy-decisions N.jsonl`.
#
# Usage:
#   bash scripts/relocate_aiwiki_state_out_of_icloud.sh
#   FURNACE_DOGFOOD_VAULT=/path/to/vault bash scripts/relocate_aiwiki_state_out_of_icloud.sh
#   AIWIKI_LOCAL_STATE_HOME="$HOME/Library/Application Support/aiwiki/my-state" \
#     bash scripts/relocate_aiwiki_state_out_of_icloud.sh
#
# Idempotent: if `$VAULT/.aiwiki/state` already symlinks to `$AIWIKI_LOCAL_STATE_HOME`,
# prints ok and exits 0. On failure, restores the renamed backup directory and removes
# a broken symlink when possible.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT="${FURNACE_DOGFOOD_VAULT:-/Users/ht/Library/Mobile Documents/iCloud~md~obsidian/Documents/炼丹炉}"
LOCAL_STATE_HOME="${AIWIKI_LOCAL_STATE_HOME:-$HOME/Library/Application Support/aiwiki/dogfood-state}"
STATE_LINK="$VAULT/.aiwiki/state"
CANONICAL_JSONL="execution-policy-decisions.jsonl"

if [[ ! -d "$VAULT/.aiwiki" ]]; then
  echo "vault .aiwiki dir not found: $VAULT/.aiwiki" >&2
  exit 1
fi

if [[ -L "$STATE_LINK" ]]; then
  target="$(readlink "$STATE_LINK")"
  if [[ "$target" == "$LOCAL_STATE_HOME" ]]; then
    echo "ok    $STATE_LINK -> $LOCAL_STATE_HOME (already relocated)"
    if [[ -f "$STATE_LINK/$CANONICAL_JSONL" ]]; then
      echo "lines $CANONICAL_JSONL: $(wc -l < "$STATE_LINK/$CANONICAL_JSONL")"
    fi
    exit 0
  fi
  echo "BLOCKED: $STATE_LINK symlinks elsewhere: $target" >&2
  exit 1
fi

if [[ ! -d "$STATE_LINK" ]]; then
  echo "BLOCKED: $STATE_LINK is neither directory nor expected symlink" >&2
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$VAULT/.aiwiki/state.icloud-backup-$STAMP"
TMP="/tmp/aiwiki-state-transit-$STAMP"

mkdir -p "$(dirname "$LOCAL_STATE_HOME")"
mkdir -p "$LOCAL_STATE_HOME"

sync_state() {
  local src="$1"
  local dst="$2"
  if rsync -a "$src/" "$dst/"; then
    return 0
  fi
  echo "direct rsync failed; retrying via $TMP" >&2
  rm -rf "$TMP"
  mkdir -p "$TMP"
  rsync -a "$src/" "$TMP/"
  rsync -a "$TMP/" "$dst/"
  rm -rf "$TMP"
}

restore_on_error() {
  if [[ -L "$STATE_LINK" ]]; then
    rm -f "$STATE_LINK"
  fi
  if [[ -d "$BACKUP_DIR" && ! -e "$STATE_LINK" ]]; then
    mv "$BACKUP_DIR" "$STATE_LINK"
    echo "restored $STATE_LINK from $BACKUP_DIR" >&2
  fi
}
trap restore_on_error ERR

echo "sync  $STATE_LINK/ -> $LOCAL_STATE_HOME/"
sync_state "$STATE_LINK" "$LOCAL_STATE_HOME"

if [[ ! -f "$LOCAL_STATE_HOME/$CANONICAL_JSONL" ]]; then
  echo "WARN: missing $CANONICAL_JSONL in local copy; check iCloud download/eviction" >&2
fi

echo "move  $STATE_LINK -> $BACKUP_DIR"
mv "$STATE_LINK" "$BACKUP_DIR"
ln -s "$LOCAL_STATE_HOME" "$STATE_LINK"

trap - ERR

echo "ok    $STATE_LINK -> $(readlink "$STATE_LINK")"
echo "backup $BACKUP_DIR"
if [[ -f "$STATE_LINK/$CANONICAL_JSONL" ]]; then
  echo "lines $CANONICAL_JSONL: $(wc -l < "$STATE_LINK/$CANONICAL_JSONL")"
fi
