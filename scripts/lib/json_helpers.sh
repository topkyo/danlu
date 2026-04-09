#!/usr/bin/env bash

harness_emit_json_escape() {
  local value="$1"

  printf '%s' "$value" | awk 'BEGIN { ORS = "" } {
    gsub(/\\/, "\\\\")
    gsub(/"/, "\\\"")
    gsub(/\t/, "\\t")
    gsub(/\r/, "\\r")
    gsub(/\n/, "\\n")
    print
  }'
}

harness_emit_json_string() {
  local value="$1"

  printf '"%s"' "$(harness_emit_json_escape "$value")"
}

harness_emit_json_string_or_null() {
  local value="${1:-}"

  if [[ -n "$value" ]]; then
    harness_emit_json_string "$value"
  else
    printf 'null'
  fi
}

harness_emit_json_boolean() {
  local value="$1"

  case "$value" in
    1|true|yes)
      printf 'true'
      ;;
    *)
      printf 'false'
      ;;
  esac
}

harness_emit_json_boolean_or_null() {
  local value="${1:-}"

  if [[ -n "$value" ]]; then
    harness_emit_json_boolean "$value"
  else
    printf 'null'
  fi
}

harness_emit_json_number_or_null() {
  local value="${1:-}"

  if [[ "$value" =~ ^-?[0-9]+([.][0-9]+)?$ ]]; then
    printf '%s' "$value"
  else
    printf 'null'
  fi
}

harness_extract_top_level_json_string() {
  local key="$1"
  local json_payload="$2"

  printf '%s\n' "$json_payload" | awk -v key="$key" '
    $0 ~ "^[[:space:]]*\"" key "\":[[:space:]]*\"" {
      line = $0
      sub(/^[[:space:]]*"[^"]+":[[:space:]]*"/, "", line)
      sub(/"[[:space:]]*,?[[:space:]]*$/, "", line)
      print line
      exit
    }
  '
}

harness_extract_top_level_json_literal() {
  local key="$1"
  local json_payload="$2"

  printf '%s\n' "$json_payload" | awk -v key="$key" '
    $0 ~ "^[[:space:]]*\"" key "\":[[:space:]]*" {
      line = $0
      sub(/^[[:space:]]*"[^"]+":[[:space:]]*/, "", line)
      sub(/[[:space:]]*,?[[:space:]]*$/, "", line)
      print line
      exit
    }
  '
}
