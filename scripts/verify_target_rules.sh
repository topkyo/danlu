#!/usr/bin/env bash
# Project-owned AgentStack verify-auto rules for ai-wiki.
set -euo pipefail

changed_files() {
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if git rev-parse --verify HEAD >/dev/null 2>&1; then
      git diff --name-only HEAD -- || true
      git diff --name-only --cached -- || true
    fi
    git ls-files --others --exclude-standard || true
    return 0
  fi

  find . -type f \
    ! -path './.git/*' \
    ! -path './.agentstack/evidence/*' \
    ! -path './.agentstack/local/*' \
    ! -path './.agentstack/render-conflicts/*' \
    ! -path './.venv/*' \
    ! -path './node_modules/*' \
    ! -path './dist/*' \
    ! -path './build/*' |
    sed 's#^\./##'
}

emit_targets_for_path() {
  local path="$1"

  case "$path" in
    .agentstack/evidence/*|.agentstack/local/*|.agentstack/render-conflicts/*)
      return 0
      ;;
    AGENTS.md|CLAUDE.md|PROGRESS.md|README.md|docs/*|docs/**/*|*.md)
      echo scripts
      return 0
      ;;
    .agents/*|.agents/**/*|.agentstack/*|.agentstack/**/*|.claude/*|.claude/**/*|.opencode/*|.opencode/**/*)
      echo scripts
      return 0
      ;;
    scripts/verify.sh|scripts/verify_target_rules.sh|scripts/agentstack|scripts/agentstack-*)
      echo scripts
      return 0
      ;;
    scripts/run_acceptance.sh|tests/fixtures/acceptance/*|tests/fixtures/acceptance/**/*)
      echo scripts
      echo acceptance
      return 0
      ;;
    scripts/*.py)
      echo scripts
      echo unit
      return 0
      ;;
    scripts/*.sh)
      echo scripts
      return 0
      ;;
    schema/*.json|schema/**/*.json)
      echo python-static
      echo unit
      return 0
      ;;
    .obsidian/plugins/furnace-product-shell/package.json|.obsidian/plugins/furnace-product-shell/package-lock.json|.obsidian/plugins/furnace-product-shell/build.sh|.obsidian/plugins/furnace-product-shell/*.js|.obsidian/plugins/furnace-product-shell/src/*|.obsidian/plugins/furnace-product-shell/src/**/*|.obsidian/plugins/furnace-product-shell/*.css)
      echo product-shell-static
      return 0
      ;;
    src/aiwiki/cli.py|src/aiwiki/cli/*|src/aiwiki/cli/**/*)
      echo python-static
      echo unit
      echo cli-smoke
      return 0
      ;;
    src/aiwiki/*.py|src/aiwiki/*/*.py|src/aiwiki/*/*/*.py)
      echo python-static
      echo unit
      return 0
      ;;
    tests/*.py|tests/*/*.py|tests/*/*/*.py)
      echo python-static
      echo unit
      return 0
      ;;
    pyproject.toml|requirements*.txt|setup.cfg|tox.ini)
      echo python-static
      echo unit
      return 0
      ;;
  esac

  echo scripts
}

files="$(changed_files | awk 'NF' | sort -u)"

if [ -z "$files" ]; then
  echo smoke
  exit 0
fi

while IFS= read -r path; do
  [ -n "$path" ] || continue
  emit_targets_for_path "$path"
done <<< "$files" | awk 'NF' | sort -u
