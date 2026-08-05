#!/usr/bin/env bash
# Emit verify.sh targets based on changed paths.
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
    ! -path './.venv/*' \
    ! -path './node_modules/*' \
    ! -path './dist/*' \
    ! -path './build/*' |
    sed 's#^\./##'
}

emit_targets_for_path() {
  local path="$1"

  case "$path" in
    AGENTS.md|PROGRESS.md|README.md|docs/*|docs/**/*|*.md)
      echo scripts
      return 0
      ;;
    .claude/*|.claude/**/*|.opencode/*|.opencode/**/*)
      echo scripts
      return 0
      ;;
    scripts/verify.sh|scripts/verify_target_rules.sh)
      echo scripts
      return 0
      ;;
    LICENSE|CHANGELOG.md)
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
      return 0
      ;;
    scripts/*.sh)
      echo scripts
      return 0
      ;;
    schema/*.json|schema/**/*.json)
      echo python-static
      return 0
      ;;
    .obsidian/plugins/furnace-product-shell/package.json|.obsidian/plugins/furnace-product-shell/package-lock.json|.obsidian/plugins/furnace-product-shell/build.sh|.obsidian/plugins/furnace-product-shell/*.js|.obsidian/plugins/furnace-product-shell/src/*|.obsidian/plugins/furnace-product-shell/src/**/*|.obsidian/plugins/furnace-product-shell/*.css)
      echo product-shell-static
      return 0
      ;;
    src/aiwiki/cli.py|src/aiwiki/cli/*|src/aiwiki/cli/**/*)
      echo python-static
      echo cli-smoke
      return 0
      ;;
    src/aiwiki/utils/security.py|src/aiwiki/vault/*|src/aiwiki/vault/**/*|src/aiwiki/autonomy_policy.py|src/aiwiki/cli/llm_check_render.py|src/aiwiki/cli/__main__.py)
      # Guarded by tests/test_security.py / test_vault_plugin.py / test_library_surfaces.py.
      echo python-static
      echo unit
      return 0
      ;;
    src/aiwiki/execution/*|src/aiwiki/execution/**/*|src/aiwiki/memory/*|src/aiwiki/memory/**/*|src/aiwiki/runner/*|src/aiwiki/runner/**/*|src/aiwiki/compile/*|src/aiwiki/compile/**/*)
      # Core pipeline modules: static checks alone miss contract regressions.
      echo python-static
      echo acceptance
      echo llm-integration
      return 0
      ;;
    src/aiwiki/*.py|src/aiwiki/*/*.py|src/aiwiki/*/*/*.py)
      echo python-static
      return 0
      ;;
    tests/test_acceptance_loop.py|tests/acceptance/*|tests/acceptance/**/*)
      echo acceptance
      return 0
      ;;
    tests/test_llm_integration.py)
      echo llm-integration
      return 0
      ;;
    tests/test_security.py|tests/test_vault_plugin.py|tests/test_library_surfaces.py)
      echo unit
      return 0
      ;;
    tests/*.py|tests/*/*.py|tests/*/*/*.py)
      echo python-static
      return 0
      ;;
    *)
      return 0
      ;;
  esac
}

main() {
  local path=""
  local -a targets=()
  local seen=""

  while IFS= read -r path; do
    [[ -n "$path" ]] || continue
    while IFS= read -r target; do
      [[ -n "$target" ]] || continue
      case " $seen " in
        *" $target "*) ;;
        *)
          targets+=("$target")
          seen+=" $target"
          ;;
      esac
    done < <(emit_targets_for_path "$path")
  done < <(changed_files | awk 'NF' | sort -u)

  if [[ ${#targets[@]} -eq 0 ]]; then
    echo scripts
    return 0
  fi

  printf '%s\n' "${targets[@]}"
}

main "$@"
