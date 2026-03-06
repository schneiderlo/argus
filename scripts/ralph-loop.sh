#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNS_DIR="$ROOT_DIR/artifacts/agent_runs"
VERIFY_DIR="$ROOT_DIR/artifacts/verify"
MAX_ITERS="${RALPH_MAX_ITERS:-0}"
SLEEP_SECONDS="${RALPH_SLEEP_SECONDS:-2}"
STOP_ON_PASS="${RALPH_STOP_ON_PASS:-1}"
CODEX_JSON="${CODEX_JSON:-1}"
CODEX_MODEL="${CODEX_MODEL:-}"

mkdir -p "$RUNS_DIR" "$VERIFY_DIR"

has_open_items() {
  rg -q '^- \[ \]' "$ROOT_DIR/fix_plan.md"
}

has_dirty_worktree() {
  [[ -n "$(git -C "$ROOT_DIR" status --porcelain)" ]]
}

write_metadata() {
  local metadata_file="$1"
  local iteration="$2"
  local codex_exit="$3"
  local verify_exit="$4"
  cat >"$metadata_file" <<EOF
iteration=$iteration
timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
codex_exit=$codex_exit
verify_exit=$verify_exit
EOF
}

iteration=1
while :; do
  if [[ "$MAX_ITERS" -gt 0 && "$iteration" -gt "$MAX_ITERS" ]]; then
    break
  fi

  timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
  run_dir="$RUNS_DIR/${timestamp}-iter-$(printf '%04d' "$iteration")"
  mkdir -p "$run_dir"

  cp "$ROOT_DIR/PROMPT.md" "$run_dir/prompt.md"
  if [[ -f "$VERIFY_DIR/latest.txt" ]]; then
    cp "$VERIFY_DIR/latest.txt" "$run_dir/previous-verify.txt"
  fi

  codex_cmd=(codex exec --full-auto -C "$ROOT_DIR" --output-last-message "$run_dir/last-message.md")
  if [[ -n "$CODEX_MODEL" ]]; then
    codex_cmd+=(-m "$CODEX_MODEL")
  fi
  if [[ "$CODEX_JSON" == "1" ]]; then
    codex_cmd+=(--json)
  fi

  echo "=== Ralph iteration $iteration ==="
  echo "run_dir=$run_dir"

  set +e
  if [[ "$CODEX_JSON" == "1" ]]; then
    "${codex_cmd[@]}" - < "$ROOT_DIR/PROMPT.md" | tee "$run_dir/codex-events.jsonl"
  else
    "${codex_cmd[@]}" - < "$ROOT_DIR/PROMPT.md" | tee "$run_dir/codex-output.txt"
  fi
  codex_exit=$?

  "$ROOT_DIR/scripts/verify.sh" >"$run_dir/verify.txt" 2>&1
  verify_exit=$?
  set -e

  if [[ "$verify_exit" -eq 0 ]] && has_dirty_worktree; then
    {
      printf '\n'
      echo "Process failure: verification passed but the git worktree is still dirty."
      echo "Commit or otherwise clean the completed increment before the iteration can count as successful."
    } | tee -a "$run_dir/verify.txt"
    verify_exit=1
  fi

  cp "$run_dir/verify.txt" "$VERIFY_DIR/latest.txt"
  if [[ "$verify_exit" -eq 0 ]]; then
    cp "$run_dir/verify.txt" "$VERIFY_DIR/latest-success.txt"
  fi
  printf '%s\n' "$run_dir" > "$ROOT_DIR/artifacts/latest-run.txt"
  write_metadata "$run_dir/metadata.env" "$iteration" "$codex_exit" "$verify_exit"

  echo "codex_exit=$codex_exit"
  echo "verify_exit=$verify_exit"

  if [[ "$STOP_ON_PASS" == "1" && "$verify_exit" -eq 0 ]] && ! has_open_items; then
    echo "Verification passed and no open fix-plan items remain."
    exit 0
  fi

  iteration=$((iteration + 1))
  sleep "$SLEEP_SECONDS"
done
