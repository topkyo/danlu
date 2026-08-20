#!/usr/bin/env bash
# sync_product_shell_to_vault.sh
#
# Rebuild the Product Shell plugin bundle in this repo and (re-)link it into the
# dogfood Obsidian vault. Run this after editing anything under
# .obsidian/plugins/furnace-product-shell/src/ or whenever iCloud Drive has
# flattened the vault's main.js / styles.css symlinks back into regular files.
#
# Conventions enforced by this script:
#   - The repo side (.obsidian/plugins/furnace-product-shell/) is the single
#     source of truth for the plugin bundle. src/*.js is rebuilt into
#     main.js via ./build.sh before any link is (re-)established.
#   - The dogfood vault side links only build outputs (main.js, styles.css)
#     back to the repo, so any future code or CSS change is immediately
#     visible after a restart. manifest.json stays a parallel copy (rare
#     churn; if iCloud replaces a link, the plugin would refuse to load);
#     data.json stays local because it holds user settings (API keys, etc).
#   - FURNACE_DOGFOOD_VAULT is required and must be the vault plugin dir:
#     <vault>/.obsidian/plugins/furnace-product-shell
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

PLUGIN_ID="furnace-product-shell"
REPO_BASE="$PROJECT_ROOT/.obsidian/plugins/$PLUGIN_ID"
if [[ -z "${FURNACE_DOGFOOD_VAULT:-}" ]]; then
  echo "set FURNACE_DOGFOOD_VAULT to the vault plugin dir:" >&2
  echo "  <vault>/.obsidian/plugins/$PLUGIN_ID" >&2
  exit 1
fi
VAULT_BASE="$FURNACE_DOGFOOD_VAULT"

if [[ ! -d "$REPO_BASE" ]]; then
  echo "repo plugin dir not found: $REPO_BASE" >&2
  exit 1
fi
if [[ ! -d "$VAULT_BASE" ]]; then
  echo "vault plugin dir not found: $VAULT_BASE" >&2
  echo "FURNACE_DOGFOOD_VAULT must be <vault>/.obsidian/plugins/$PLUGIN_ID" >&2
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "node is required to rebuild main.js" >&2
  exit 1
fi

# 1. Rebuild main.js from src/*.js in the repo side.
(
  cd "$REPO_BASE"
  bash build.sh
)

# 2. Re-establish symlinks for build outputs (idempotent).
ensure_symlink() {
  local name="$1"
  local repo_path="$REPO_BASE/$name"
  local vault_path="$VAULT_BASE/$name"

  if [[ ! -e "$repo_path" ]]; then
    echo "skip $name: missing on repo side at $repo_path" >&2
    return 0
  fi

  if [[ -L "$vault_path" ]] && [[ "$(readlink "$vault_path")" == "$repo_path" ]]; then
    echo "ok    $vault_path"
    return 0
  fi

  rm -f "$vault_path"
  ln -s "$repo_path" "$vault_path"
  echo "linked $vault_path -> $repo_path"
}

ensure_symlink main.js
ensure_symlink styles.css

# 3. Read-only sanity report so the user can see the post-sync state at a
#    glance; manifest.json / data.json are intentionally untouched.
echo "vault plugin dir after sync:"
ls -la "$VAULT_BASE"
