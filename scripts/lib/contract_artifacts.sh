#!/usr/bin/env bash

harness_contract_has_section() {
  local contract_file="$1"
  local section_name="$2"
  grep -q "^## $section_name\$" "$contract_file"
}

harness_extract_contract_section_value() {
  local contract_file="$1"
  local section_name="$2"
  local item_name="$3"

  awk -v section_name="$section_name" -v item_name="$item_name" '
    $0 == "## " section_name {in_section=1; next}
    /^## / && in_section {in_section=0}
    in_section && index($0, "`" item_name "`:") {
      sub(/^.*: /, "", $0)
      gsub(/`/, "", $0)
      print
      exit
    }
  ' "$contract_file"
}

harness_extract_contract_requirement() {
  local contract_file="$1"
  local gate_name="$2"

  harness_extract_contract_section_value "$contract_file" "Gate Requirements" "$gate_name"
}

harness_extract_contract_artifact_path() {
  local contract_file="$1"
  local gate_name="$2"

  harness_extract_contract_section_value "$contract_file" "Gate Artifacts" "$gate_name"
}

harness_extract_contract_gate_note() {
  local contract_file="$1"
  local gate_name="$2"

  awk -v gate_name="$gate_name" '
    $0 == "## Gate Requirements" {in_section=1; next}
    /^## / && in_section {in_section=0}
    in_section && index($0, "  calibration_note: " gate_name " ") == 1 {
      sub("^  calibration_note: " gate_name " ", "", $0)
      print
      exit
    }
  ' "$contract_file"
}

harness_json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

harness_format_contract_gate_note_json() {
  local kind="$1"
  local action="$2"
  local target="$3"
  local source="$4"
  local note_date="$5"
  local basis="$6"

  printf '{"kind":"%s","action":"%s","target":"%s","source":"%s","date":"%s","basis":"%s"}' \
    "$(harness_json_escape "$kind")" \
    "$(harness_json_escape "$action")" \
    "$(harness_json_escape "$target")" \
    "$(harness_json_escape "$source")" \
    "$(harness_json_escape "$note_date")" \
    "$(harness_json_escape "$basis")"
}

harness_extract_contract_gate_note_field() {
  local contract_file="$1"
  local gate_name="$2"
  local field_name="$3"
  local note=""

  note="$(harness_extract_contract_gate_note "$contract_file" "$gate_name")"
  [[ -n "$note" ]] || return 1

  printf '%s\n' "$note" | awk -v field_name="$field_name" '
    BEGIN {
      pattern = "\"" field_name "\":\""
    }

    {
      start = index($0, pattern)
      if (!start) {
        exit 1
      }

      value = substr($0, start + length(pattern))
      output = ""
      escaped = 0

      for (i = 1; i <= length(value); i++) {
        ch = substr(value, i, 1)

        if (escaped) {
          if (ch == "\"" || ch == "\\") {
            output = output ch
          } else {
            output = output "\\" ch
          }
          escaped = 0
          continue
        }

        if (ch == "\\") {
          escaped = 1
          continue
        }

        if (ch == "\"") {
          print output
          exit 0
        }

        output = output ch
      }

      exit 1
    }
  '
}

harness_contract_gate_note_format_status() {
  local contract_file="$1"
  local gate_name="$2"
  local note=""
  local required_fields=(
    kind
    action
    target
    source
    date
    basis
  )
  local field_name=""

  note="$(harness_extract_contract_gate_note "$contract_file" "$gate_name")"
  if [[ -z "$note" ]]; then
    printf '%s\n' "missing"
    return 0
  fi

  for field_name in "${required_fields[@]}"; do
    if ! harness_extract_contract_gate_note_field "$contract_file" "$gate_name" "$field_name" >/dev/null; then
      printf '%s\n' "legacy"
      return 0
    fi
  done

  printf '%s\n' "structured"
}

harness_replace_contract_requirement() {
  local contract_file="$1"
  local gate_name="$2"
  local new_value="$3"
  local tmp_file=""

  tmp_file="$(mktemp)"

  awk -v gate_name="$gate_name" -v new_value="$new_value" '
    $0 == "## Gate Requirements" {in_section=1}
    /^## / && $0 != "## Gate Requirements" && in_section {in_section=0}
    in_section && index($0, "`" gate_name "`:") {
      sub(/required|not-required/, new_value)
    }
    {print}
  ' "$contract_file" > "$tmp_file"

  mv "$tmp_file" "$contract_file"
}

harness_upsert_contract_gate_note() {
  local contract_file="$1"
  local gate_name="$2"
  local note="$3"
  local tmp_file=""

  tmp_file="$(mktemp)"

  awk -v gate_name="$gate_name" -v note="$note" '
    BEGIN {
      note_prefix = "  calibration_note: " gate_name " "
      note_line = note_prefix note
    }

    $0 == "## Gate Requirements" {
      in_section = 1
      print
      next
    }

    in_section && /^## / {
      if (after_gate) {
        print note_line
        after_gate = 0
      }
      in_section = 0
      print
      next
    }

    in_section && index($0, "`" gate_name "`:") {
      print
      after_gate = 1
      next
    }

    after_gate {
      if (index($0, note_prefix) == 1) {
        print note_line
        after_gate = 0
        next
      }

      print note_line
      after_gate = 0
    }

    { print }

  END {
    if (after_gate) {
      print note_line
    }
  }
  ' "$contract_file" > "$tmp_file"

  mv "$tmp_file" "$contract_file"
}

harness_contract_section_has_list_items() {
  local contract_file="$1"
  local section_name="$2"

  awk -v section_name="$section_name" '
    $0 == "## " section_name {in_section=1; next}
    /^## / && in_section {in_section=0}
    in_section && /^- / {found=1}
    END {exit found ? 0 : 1}
  ' "$contract_file"
}

harness_is_valid_gate_artifact_path() {
  local harness_dir="$1"
  local path="$2"
  [[ "$path" == "$harness_dir/gates/"* && "$path" == *.md ]]
}
