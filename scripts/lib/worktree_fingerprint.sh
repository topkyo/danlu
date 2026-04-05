#!/usr/bin/env bash

harness_is_git_worktree() {
  local project_root="$1"
  git -C "$project_root" rev-parse --is-inside-work-tree >/dev/null 2>&1
}

harness_is_gate_artifact_path() {
  local harness_dir="$1"
  local path="$2"
  [[ "$path" == "$harness_dir/gates/"* && "$path" == *.md ]]
}

harness_emit_file_hash() {
  local path="$1"
  printf 'FILE %s %s\n' "$path" "$(sha256sum -- "$path" | awk '{print $1}')"
}

harness_compute_git_worktree_fingerprint() {
  local project_root="$1"
  local harness_dir="$2"
  local head=""
  local status_output=""
  local path=""

  head="$(git -C "$project_root" rev-parse HEAD 2>/dev/null || echo NO_GIT_HEAD)"
  status_output="$(git -C "$project_root" status --porcelain=v1 --untracked-files=all -- . 2>/dev/null || true)"

  (
    cd "$project_root" || exit 1
    {
      printf 'HEAD %s\n' "$head"
      printf 'STATUS\n%s\n' "$status_output"
      if [[ -n "$status_output" ]]; then
        while IFS= read -r line; do
          path="${line:3}"
          if [[ "$path" == *" -> "* ]]; then
            path="${path##* -> }"
          fi
          if harness_is_gate_artifact_path "$harness_dir" "$path"; then
            continue
          fi
          if [[ -f "$path" ]]; then
            harness_emit_file_hash "$path"
          elif [[ -d "$path" ]]; then
            printf 'DIR %s\n' "$path"
            while IFS= read -r nested; do
              if harness_is_gate_artifact_path "$harness_dir" "$nested"; then
                continue
              fi
              harness_emit_file_hash "$nested"
            done < <(find "$path" -type f | sort)
          else
            printf 'MISSING %s\n' "$path"
          fi
        done <<< "$status_output" | sort
      fi
    } | sha256sum | awk '{print $1}'
  )
}

harness_compute_plain_tree_fingerprint() {
  local project_root="$1"
  local harness_dir="$2"
  local path=""

  (
    cd "$project_root" || exit 1
    {
      printf 'HEAD %s\n' 'NO_GIT_HEAD'
      printf 'STATUS\n%s\n' 'NO_GIT_WORKTREE'
      while IFS= read -r path; do
        path="${path#./}"
        [[ "$path" == ".git" || "$path" == .git/* ]] && continue
        harness_is_gate_artifact_path "$harness_dir" "$path" && continue
        harness_emit_file_hash "$path"
      done < <(find . -type f | sort)
    } | sha256sum | awk '{print $1}'
  )
}

harness_compute_project_fingerprint() {
  local project_root="$1"
  local harness_dir="$2"

  if harness_is_git_worktree "$project_root"; then
    harness_compute_git_worktree_fingerprint "$project_root" "$harness_dir"
  else
    harness_compute_plain_tree_fingerprint "$project_root" "$harness_dir"
  fi
}
