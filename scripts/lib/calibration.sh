#!/usr/bin/env bash

harness_default_calibration_file() {
  local harness_dir="$1"

  case "$harness_dir" in
    .claude)
      printf '%s\n' "$harness_dir/CALIBRATION.md"
      ;;
    .codex)
      printf '%s\n' "$harness_dir/workflows/CALIBRATION.md"
      ;;
    *)
      printf '%s\n' "$harness_dir/CALIBRATION.md"
      ;;
  esac
}

harness_default_calibration_agent() {
  local harness_dir="$1"

  case "$harness_dir" in
    .claude)
      printf '%s\n' "Claude"
      ;;
    .codex)
      printf '%s\n' "Codex"
      ;;
    *)
      printf '%s\n' "Unknown"
      ;;
  esac
}

harness_detect_project_tier() {
  local project_root="$1"
  local tier_file="$project_root/.open-harness-tier"
  local tier=""

  [[ -f "$tier_file" ]] || return 1

  tier="$(tr '[:upper:]' '[:lower:]' < "$tier_file" | tr -d '[:space:]')"
  case "$tier" in
    lite|standard|strict)
      printf '%s\n' "$tier"
      ;;
    *)
      return 1
      ;;
  esac
}

harness_calibration_zero_hit_threshold() {
  local tier="$1"

  case "$tier" in
    lite)
      printf '%s\n' "2"
      ;;
    standard|strict)
      printf '%s\n' "3"
      ;;
    *)
      return 1
      ;;
  esac
}

harness_normalize_calibration_counter() {
  local value="$1"

  case "$value" in
    ''|*[!0-9]*)
      printf '%s\n' ""
      ;;
    *)
      printf '%s\n' "$value"
      ;;
  esac
}

harness_normalize_calibration_boolean() {
  local value="${1:-}"

  value="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
  case "$value" in
    yes|y|true|1)
      printf '%s\n' "yes"
      ;;
    no|n|false|0)
      printf '%s\n' "no"
      ;;
    not-applicable|na|n/a)
      printf '%s\n' "not-applicable"
      ;;
    *)
      printf '%s\n' ""
      ;;
  esac
}

harness_calibration_mode_recorded() {
  local mode="${1:-}"

  mode="$(printf '%s' "$mode" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
  case "$mode" in
    ''|not-run|skipped|skip|na|n/a|not-applicable)
      return 1
      ;;
    *)
      return 0
      ;;
  esac
}

harness_emit_calibration_entries() {
  local calibration_file="$1"

  awk '
    BEGIN {
      OFS = "\t"
      reset_entry()
    }

    function reset_entry() {
      date = ""
      agent = ""
      task = ""
      review_mode = ""
      review_hit = ""
      review_miss = ""
      review_false_positive = ""
      runtime_mode = ""
      runtime_hit = ""
      runtime_miss = ""
      runtime_false_positive = ""
      contract_scope_changed = ""
      new_session = ""
      progress_read = ""
      notes = ""
      entry_seen = 0
    }

    function emit_entry() {
      if (!entry_seen) {
        return
      }

      if (date == "") {
        return
      }

      print \
        date, \
        agent, \
        task, \
        review_mode, \
        review_hit, \
        review_miss, \
        review_false_positive, \
        runtime_mode, \
        runtime_hit, \
        runtime_miss, \
        runtime_false_positive, \
        contract_scope_changed, \
        new_session, \
        progress_read, \
        notes
    }

    /^- / {
      line = $0
      sub(/^- /, "", line)

      key = line
      sub(/:.*/, "", key)
      value = line
      sub(/^[^:]*:[[:space:]]*/, "", value)

      if (key == "Date") {
        emit_entry()
        reset_entry()
        entry_seen = 1
        date = value
        next
      }

      if (!entry_seen) {
        next
      }

      if (key == "Agent") {
        agent = value
      } else if (key == "Task") {
        task = value
      } else if (key == "qa-review Mode") {
        review_mode = value
      } else if (key == "qa-review Hit") {
        review_hit = value
      } else if (key == "qa-review Miss") {
        review_miss = value
      } else if (key == "qa-review False Positive") {
        review_false_positive = value
      } else if (key == "qa-runtime Mode") {
        runtime_mode = value
      } else if (key == "qa-runtime Hit") {
        runtime_hit = value
      } else if (key == "qa-runtime Miss") {
        runtime_miss = value
      } else if (key == "qa-runtime False Positive") {
        runtime_false_positive = value
      } else if (key == "Contract Scope Changed" || key == "Checklist Change") {
        contract_scope_changed = value
      } else if (key == "New Session") {
        new_session = value
      } else if (key == "PROGRESS Read") {
        progress_read = value
      } else if (key == "Notes") {
        notes = value
      }
    }

    END {
      emit_entry()
    }
  ' "$calibration_file"
}
