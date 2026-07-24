# 炼丹炉多 Agent 全方位验收闭环（2026-07-24）

> **For agentic workers:** 按本矩阵并行派发；结果落到 `/tmp/furnace-acceptance-YYYY-MM-DD/`；主 agent 汇总裁决。迭代：fail → 修 → 重跑对应 lane → 再汇总。

**Goal:** 把「工程门禁 + Shell CDP + Dogfood live + 文档商业」合成可重复的验收闭环，支持测试→迭代→再验证。  
**Vault:** `/Users/ht/Library/Mobile Documents/iCloud~md~obsidian/Documents/炼丹炉`  
**CDP:** Obsidian `--remote-debugging-port=9228`（直连 page WebSocket；勿用会落到 about:blank 的 agent-browser 默认 connect）

---

## 四 Lane（可并行）

| Lane | Agent 职责 | 命令 / 手段 | 产出 |
|------|------------|-------------|------|
| **A 工程门禁** | Local Engineering | `bash scripts/verify.sh all` + `docs_consistency_check.sh` | `verify-all.log` |
| **B Shell CDP** | Product Shell UI live | Node+ws → CDP `Runtime.evaluate`；截图 | `shell-cdp-report.json` + `.png` |
| **C Dogfood CLI** | Vault runtime live | launcher `run-ask` / 读 reports / sticky / receipts | `dogfood-cli-report.json` |
| **D 文档商业** | SoT / COMPARE / Go-Live | 读 Scorecard + commercial + chat-entry spec | `docs-commercial-report.json` |

## 迭代节奏

```text
派发 A∥B∥C∥D → 汇总 PASS/FAIL/SKIP
        │
        ├─ A FAIL → 修代码 → 只重跑 A（或 verify_target_rules）
        ├─ B FAIL → 修 Shell → sync_product_shell_to_vault → 重跑 B
        ├─ C FAIL → 修 runtime/契约 → 临时 --root vault 复现 → 重跑 C
        └─ D FAIL → 修文档/计分 → 重跑 D
        │
        └─ 全绿或仅已知 not-yet → 写验收摘要；Live Dogfood 不宣称 AgentOS 9 live
```

## 硬规则

1. **两套门禁不混标**：Local Eng（verify）vs Live Dogfood（vault）vs Commercial（可售）。
2. **single writer**：vault 上有 `watch` 时不要并行 `compile`。
3. **CDP**：`json/list` 取 `type=page` 的 `webSocketDebuggerUrl`；eval `document.querySelector('.furnace-…')`。
4. **Ask 污染控制**：live ask 问题带日期标签如 `【accept-YYYY-MM-DD】`。
5. **不自动 push**；合入/发布另闸。

## 本轮目录

`/tmp/furnace-acceptance-2026-07-24/`

## 本轮结果（2026-07-24）

汇总：`/tmp/furnace-acceptance-2026-07-24/SYNTHESIS.md`

| Lane | 结果 |
|------|------|
| A `verify.sh all` | PASS（先修 5 个 acceptance `prompt_hash` fixture 后） |
| B Shell CDP | PASS 6/6 |
| C Dogfood CLI | PASS（含 live ask `accept-2026-07-24-一句话.md`） |
| D Docs/Commercial | 条件通过（docs_consistency 绿；Jest SoT 漂移；Go-Live ~7.8） |

工程可继续迭代；不宣称 AgentOS 9 live / 诚实可售。
