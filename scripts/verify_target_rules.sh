#!/usr/bin/env bash
# Project-owned verify-auto rules for ai-wiki.
# Sourced by scripts/resolve_verify_targets.sh when closed_loop.sh uses --verify-auto.

select_for_path() {
  local path="$1"

  path_is_runtime_artifact "$path" && return 0

  case "$path" in
    AGENTS.md|CLAUDE.md|PROGRESS.md|README.md|docs/*|docs/**/*|*.md)
      add_target scripts "protocol/documentation changed: $path"
      return 0
      ;;
    scripts/verify.sh|scripts/verify_target_rules.sh)
      add_target scripts "verify routing changed: $path"
      return 0
      ;;
    scripts/run_acceptance.sh|tests/fixtures/acceptance/*|tests/fixtures/acceptance/**/*)
      add_target scripts "acceptance runner or fixtures changed: $path"
      add_target acceptance "acceptance surface changed: $path"
      return 0
      ;;
    scripts/*.sh)
      add_target scripts "project shell script changed: $path"
      return 0
      ;;
    .obsidian/plugins/furnace-product-shell/package.json|.obsidian/plugins/furnace-product-shell/package-lock.json|.obsidian/plugins/furnace-product-shell/build.sh|.obsidian/plugins/furnace-product-shell/*.js|.obsidian/plugins/furnace-product-shell/src/*|.obsidian/plugins/furnace-product-shell/src/**/*|.obsidian/plugins/furnace-product-shell/*.css)
      add_target product-shell-static "Product Shell source changed: $path"
      return 0
      ;;
    src/aiwiki/cli.py|src/aiwiki/cli/*|src/aiwiki/cli/**/*)
      add_target python-static "Python CLI source changed: $path"
      add_target unit "Python CLI source changed: $path"
      add_target cli-smoke "Python CLI source changed: $path"
      return 0
      ;;
    src/aiwiki/*.py|src/aiwiki/*/*.py|src/aiwiki/*/*/*.py)
      add_target python-static "Python runtime source changed: $path"
      add_target unit "Python runtime source changed: $path"
      return 0
      ;;
    tests/*.py|tests/*/*.py|tests/*/*/*.py)
      add_target python-static "Python test changed: $path"
      add_target unit "Python test changed: $path"
      return 0
      ;;
    pyproject.toml|requirements*.txt|setup.cfg|tox.ini)
      add_target python-static "Python tool configuration changed: $path"
      add_target unit "Python tool configuration changed: $path"
      return 0
      ;;
  esac

  add_target scripts "fallback for unclassified path: $path"
}
