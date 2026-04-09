#!/usr/bin/env bash

# Shared gate artifact parser/validator.
# Callers may optionally provide fail/pass/require_file hooks; otherwise
# this helper falls back to safe default behavior.

harness_gate_fail() {
  local message="$1"

  if declare -F fail >/dev/null 2>&1; then
    fail "$message"
  fi

  echo "[FAIL] $message" >&2
  exit 1
}

harness_gate_pass() {
  local message="$1"

  if declare -F pass >/dev/null 2>&1; then
    pass "$message"
    return 0
  fi

  echo "[PASS] $message"
}

harness_gate_require_file() {
  local path="$1"

  if declare -F require_file >/dev/null 2>&1; then
    require_file "$path" || harness_gate_fail "Missing required file: $path"
    return 0
  fi

  [[ -f "$path" ]] || harness_gate_fail "Missing required file: $path"
}

harness_extract_artifact_status() {
  local path="$1"
  awk -F': ' '/^status:/{print $2; exit}' "$path"
}

harness_extract_artifact_header() {
  local key="$1"
  local path="$2"
  awk -v key="$key" '
    index($0, key ": ") == 1 {
      sub("^" key ": ", "", $0)
      print
      exit
    }
  ' "$path"
}

harness_extract_artifact_contract_sha() {
  local path="$1"
  awk -F': ' '/^contract_sha:/{print $2; exit}' "$path"
}

harness_extract_artifact_worktree_fingerprint() {
  local path="$1"
  awk -F': ' '/^worktree_fingerprint:/{print $2; exit}' "$path"
}

harness_extract_gate_execution_mode() {
  local gate_name="$1"
  local path="$2"

  case "$gate_name" in
    qa-review)
      harness_extract_artifact_header "reviewer_mode" "$path"
      ;;
    qa-runtime)
      harness_extract_artifact_header "runtime_mode" "$path"
      ;;
    *)
      harness_gate_fail "Unknown gate name for execution mode extraction: $gate_name"
      ;;
  esac
}

harness_validate_gate_execution_mode() {
  local gate_name="$1"
  local mode="$2"

  case "$gate_name" in
    qa-review)
      case "$mode" in
        isolated-agent|external-agent|fresh-session|same-context|human)
          return 0
          ;;
      esac
      ;;
    qa-runtime)
      case "$mode" in
        scripted|isolated-agent|same-context|human)
          return 0
          ;;
      esac
      ;;
  esac

  return 1
}

harness_validate_gate_execution_metadata() {
  local gate_name="$1"
  local path="$2"
  local status="$3"
  local mode=""
  local fallback_reason=""
  local review_findings_count=""
  local review_findings_highest_severity=""

  [[ "$status" == "pass" ]] || return 0

  case "$gate_name" in
    qa-review)
      mode="$(harness_extract_gate_execution_mode "$gate_name" "$path")"
      [[ -n "$mode" ]] || harness_gate_fail "$gate_name artifact missing reviewer_mode: $path"
      harness_validate_gate_execution_mode "$gate_name" "$mode" || harness_gate_fail "$gate_name artifact reviewer_mode is '$mode' (expected isolated-agent, external-agent, fresh-session, same-context, or human)"
      if [[ "$mode" == "same-context" ]]; then
        fallback_reason="$(harness_extract_artifact_header "reviewer_fallback_reason" "$path")"
        [[ -n "$fallback_reason" ]] || harness_gate_fail "$gate_name artifact missing reviewer_fallback_reason for same-context fallback: $path"
      fi
      review_findings_count="$(harness_extract_artifact_header "review_findings_count" "$path")"
      if [[ -n "$review_findings_count" && ! "$review_findings_count" =~ ^[0-9]+$ ]]; then
        harness_gate_fail "$gate_name artifact has invalid review_findings_count: $path"
      fi
      if [[ -n "$review_findings_count" && "$review_findings_count" != "0" ]]; then
        harness_gate_fail "$gate_name pass artifact cannot record non-zero review_findings_count: $path"
      fi
      review_findings_highest_severity="$(harness_extract_artifact_header "review_findings_highest_severity" "$path")"
      [[ -z "$review_findings_highest_severity" ]] || harness_gate_fail "$gate_name pass artifact cannot record review_findings_highest_severity: $path"
      ;;
    qa-runtime)
      mode="$(harness_extract_gate_execution_mode "$gate_name" "$path")"
      [[ -n "$mode" ]] || harness_gate_fail "$gate_name artifact missing runtime_mode: $path"
      harness_validate_gate_execution_mode "$gate_name" "$mode" || harness_gate_fail "$gate_name artifact runtime_mode is '$mode' (expected scripted, isolated-agent, same-context, or human)"
      ;;
  esac
}

harness_check_gate_file() {
  local gate_name="$1"
  local path="$2"
  local required="$3"
  local expected_contract_sha="$4"
  local expected_worktree_fingerprint="$5"
  local status=""
  local artifact_contract_sha=""
  local artifact_worktree_fingerprint=""

  if [[ "$required" == "not-required" ]]; then
    if [[ -f "$path" ]]; then
      status="$(harness_extract_artifact_status "$path")"
      artifact_contract_sha="$(harness_extract_artifact_contract_sha "$path")"
      artifact_worktree_fingerprint="$(harness_extract_artifact_worktree_fingerprint "$path")"
      [[ -n "$status" ]] || harness_gate_fail "$gate_name artifact missing status: $path"
      [[ "$artifact_contract_sha" == "$expected_contract_sha" ]] || harness_gate_fail "$gate_name artifact contract_sha mismatch"
      [[ "$artifact_worktree_fingerprint" == "$expected_worktree_fingerprint" ]] || harness_gate_fail "$gate_name artifact worktree_fingerprint mismatch"
      harness_validate_gate_execution_metadata "$gate_name" "$path" "$status"
      case "$status" in
        pass|not-required)
          harness_gate_pass "$gate_name not required ($status)"
          ;;
        *)
          harness_gate_fail "$gate_name optional artifact status is '$status' (expected pass or not-required)"
          ;;
      esac
    else
      harness_gate_pass "$gate_name not required"
    fi
    return 0
  fi

  harness_gate_require_file "$path"
  status="$(harness_extract_artifact_status "$path")"
  artifact_contract_sha="$(harness_extract_artifact_contract_sha "$path")"
  artifact_worktree_fingerprint="$(harness_extract_artifact_worktree_fingerprint "$path")"
  [[ -n "$status" ]] || harness_gate_fail "$gate_name artifact missing status: $path"
  [[ "$artifact_contract_sha" == "$expected_contract_sha" ]] || harness_gate_fail "$gate_name artifact contract_sha mismatch"
  [[ "$artifact_worktree_fingerprint" == "$expected_worktree_fingerprint" ]] || harness_gate_fail "$gate_name artifact worktree_fingerprint mismatch"
  harness_validate_gate_execution_metadata "$gate_name" "$path" "$status"
  [[ "$status" == "pass" ]] || harness_gate_fail "$gate_name status is $status"
  harness_gate_pass "$gate_name passed"
}
