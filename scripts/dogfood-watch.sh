#!/usr/bin/env bash
# Dogfood receipt v0 实时监控
# 用法：bash scripts/dogfood-watch.sh [attach|stop]
#
# 在 tmux session "danlu-dogfood" 里启 4 面板监控真实 vault：
#   1. LLM receipts（每次 API backend 调用：model/elapsed/preview）
#   2. Runner receipts（CLI run 状态）
#   3. Runtime history（drift-scan / 状态机事件）
#   4. Vault 文件落盘活动（raw/ wiki/ output/ 下 1 分钟内变更）
#
# Stage 2 起跑 dogfood 主流程前先：bash scripts/dogfood-watch.sh
# 然后 tmux attach -t danlu-dogfood 看现场（任意 pane Ctrl-b d 离开）

set -euo pipefail

SESSION="danlu-dogfood"
VAULT="${AIWIKI_DOGFOOD_VAULT:-/home/tim/danlu/炼丹炉}"

if [[ "${1:-start}" == "stop" ]]; then
  tmux kill-session -t "$SESSION" 2>/dev/null && echo "stopped: $SESSION" || echo "no session: $SESSION"
  exit 0
fi

if [[ "${1:-start}" == "attach" ]]; then
  exec tmux attach -t "$SESSION"
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "session 已存在: $SESSION"
  echo "  attach: tmux attach -t $SESSION"
  echo "  stop  : bash $0 stop"
  exit 0
fi

if [[ ! -d "$VAULT" ]]; then
  echo "vault 不存在: $VAULT" >&2
  exit 1
fi

mkdir -p "$VAULT/.aiwiki/logs" "$VAULT/.aiwiki/state"
# 用 touch 让 tail -F 不报 file truncated（首次 dogfood 文件还没被创建）
: >>"$VAULT/.aiwiki/logs/llm-receipts.jsonl"
: >>"$VAULT/.aiwiki/logs/runs.jsonl"
: >>"$VAULT/.aiwiki/state/runtime-history.jsonl"

# 4-pane layout
tmux new-session -d -s "$SESSION" -n trace -c "$VAULT" \
  "echo '=== LLM Receipts (.aiwiki/logs/llm-receipts.jsonl) ==='; tail -F .aiwiki/logs/llm-receipts.jsonl | python3 -c \"
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        e = json.loads(line)
        backend = e.get('backend','?')
        model = e.get('model','?')
        elapsed = e.get('elapsed_seconds') or e.get('elapsed') or '?'
        preview = (e.get('response_preview') or e.get('preview') or '')[:60]
        print(f'[LLM] {backend}/{model} {elapsed}s | {preview}')
    except Exception:
        print(f'[LLM-raw] {line[:200]}')
\""

tmux split-window -h -t "$SESSION:trace" -c "$VAULT" \
  "echo '=== Runner Runs (.aiwiki/logs/runs.jsonl) ==='; tail -F .aiwiki/logs/runs.jsonl | python3 -c \"
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        e = json.loads(line)
        cmd = e.get('command') or e.get('run_id') or '?'
        status = e.get('status','?')
        print(f'[RUN] {status} | {cmd}')
    except Exception:
        print(f'[RUN-raw] {line[:200]}')
\""

tmux select-pane -t "$SESSION:trace" -L
tmux split-window -v -t "$SESSION:trace" -c "$VAULT" \
  "echo '=== Runtime History (.aiwiki/state/runtime-history.jsonl) ==='; tail -F .aiwiki/state/runtime-history.jsonl | python3 -c \"
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        e = json.loads(line)
        kind = e.get('source_kind') or e.get('kind') or '?'
        ts = e.get('timestamp','')[:19]
        sub = e.get('event') or e.get('action') or ''
        print(f'[STATE {ts}] {kind} {sub}')
    except Exception:
        print(f'[STATE-raw] {line[:200]}')
\""

tmux select-pane -t "$SESSION:trace" -R
tmux split-window -v -t "$SESSION:trace" -c "$VAULT" \
  "echo '=== Vault file activity (raw/ wiki/ output/ .aiwiki/state/, 5s 间隔) ==='; while true; do
    found=\$(find raw wiki output .aiwiki/state -type f -mmin -0.1 2>/dev/null | head -10)
    if [[ -n \"\$found\" ]]; then
      ts=\$(date +%H:%M:%S)
      echo \"--- \$ts ---\"
      echo \"\$found\" | sed 's/^/  /'
    fi
    sleep 5
done"

# 让 4 个面板均匀
tmux select-layout -t "$SESSION:trace" tiled

echo "✓ dogfood 监控已启动"
echo "  attach: tmux attach -t $SESSION"
echo "  detach: 在 tmux 内按 Ctrl-b d"
echo "  stop  : bash $0 stop"
echo ""
echo "vault: $VAULT"
