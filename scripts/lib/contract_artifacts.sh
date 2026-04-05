#!/usr/bin/env bash

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

harness_is_valid_gate_artifact_path() {
  local harness_dir="$1"
  local path="$2"
  [[ "$path" == "$harness_dir/gates/"* && "$path" == *.md ]]
}
