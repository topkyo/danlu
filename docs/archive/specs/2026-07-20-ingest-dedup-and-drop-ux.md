# Ingest Dedup and Drop UX Semantics

**Date:** 2026-07-20  
**Status:** Approved (chat: dedup A + Shell A + implementation approach 1)

## Goal

两次 dogfood 误导对齐为产品契约：

1. **投料幂等**：同一规范化 URL 再 drop 默认复用已有 `raw/` + manifest entry，不产生 `vphone-aio-2/3/4` 式重复；需要新版本时显式 `--refresh`。
2. **投料 ≠ 自动出报告**：纯投料成功立刻「已收料」；「排队生成报告 / 生成被阻断」只属于提问路径。Runtime 本就不对纯投料自动 `run-ask`；本轮修正 Product Shell 文案与 pending 状态机，消除过满承诺。

## Constraints

- 分层不变：`raw/` 唯一事实输入；派生不覆盖 raw；stdlib-first。
- Shell/CLI 默认 LLM 路由不变。
- 不改变「材料 + 问题 → auto ask」行为。
- 不自动清理历史已存在的 `-N` 重复文件（可另开清理任务）。
- 本轮不做 content-sha 去重、本地 `drop repo` 目录路径去重、Shell「强制重抓」按钮。
- `requires-python >= 3.10`；Obsidian launcher 已挑 ≥3.10，但 ingest 代码不得依赖 GUI PATH。

## Design

### Architecture

两条并行切片，共享契约字段 `reused` / `duplicate_of`：

```
drop / drop plan / fetch_raw / drop_url
  → normalize_ingest_url(original + targets)
  → manifest lookup by normalized key
  → hit & !refresh → return existing entry (reused=true), no new file
  → miss | refresh → write/update single stored_path, append or update manifest

Product Shell submit
  → kind=material|files (no question) → completePendingMaterialDrop → done(raw)「已收料」
  → kind=ask|material-question|files+question → received「排队生成报告」→ reconcile outputs
```

### Components

| 区域 | 变更 |
|------|------|
| `normalize_ingest_url`（新 helper，建议 `src/aiwiki/drop/common.py` 或 `input_router.py` 旁） | scheme/host 小写；去 fragment；去常见 tracking query；GitHub repo/blob/tree 与 `rewrite_github_raw_url` 对齐为同一 canonical 键（单测锁死：`github.com/o/r` ≡ 对应 raw README URL） |
| Manifest 查找 | 读 `.aiwiki/state/manifest.json`；匹配 `ingest_metadata` / `original_path` / `final_url` / planner targets 规范化后相等；`source_type` 含 `url-drop`、`planner-fetch-raw` 等 URL 类 |
| `drop_url` / `executor._execute_fetch_raw` | 写盘前短路；命中返回已有 `stored_path`/`id` + `reused: true`；`--refresh` 覆盖同一路径并更新 sha/metadata，仍不 `_unique_path` 新 `-N` |
| CLI | `drop` / `drop url` / `drop plan` 路径支持 `--refresh`（argparse）；Shell 重试**不得**隐式 refresh |
| Product Shell pending | 纯投料禁止无条件 `markPendingSubmissionReceived`；失败标题「投料失败」；提问路径可保留「生成被阻断」 |
| `reconcilePendingSubmissions` | material/files 无 ask → 只匹配 `recent_raw_inputs`/receipts，不抢 `recent_outputs` |
| 文案 | placeholder/hint/Today feed/pending 对齐「投料→入 raw」与「提问→出报告」；`reused` 时副文「已存在，未重复入库」 |
| 测试 | llm-integration：幂等两次 drop、GitHub 双形态、`--refresh`；Jest：纯投料文案/状态、提问路径仍等报告 |

### Data flow

**幂等命中**

```
URL → normalize → manifest hit → { path, id, reused: true, duplicate_of } → Shell「已收料」
```

**首次 / refresh**

```
URL → fetch → write same or new stored_path → manifest update/append → auto compile (existing)
```

**纯投料 Shell**

```
submit material → CLI drop → materialPaths → completePendingMaterialDrop → done(raw)
```

**提问 Shell**

```
submit question → run-ask → received → reconcile recent_outputs → done(outputs)
```

### Error handling

- 规范化失败 / 非 URL 投料：不走 URL 幂等键（本地 path/repo 本轮不幂等）。
- `--refresh` 但无已有 entry：等价于首次 drop。
- fetch 全失败：保持现有 fail-loud（不写 placeholder-only raw）；幂等命中且未 refresh 时不重新 fetch。
- Shell CLI 非 0：纯投料 →「投料失败」；提问 →「生成被阻断」或「提问失败」（实现选一，提问路径推荐保留「生成被阻断」）。

### Testing

- `bash scripts/verify.sh llm-integration`：新增幂等 / GitHub canonical / refresh 用例。
- `bash scripts/verify.sh product-shell-static`：Jest 锁定纯投料「已收料」、无「排队生成报告」；提问路径仍有报告文案。
- 手工 dogfood（可选）：Obsidian 对同一 github URL 投两次，收件箱不增第二份。

## Out of scope

- 自动合并或删除历史 `*-2.md` 重复 raw
- content-sha 去重；本地目录 `drop repo` 幂等
- Shell UI「强制重抓」按钮（CLI `--refresh` 足够）
- 改变 auto-ask 合并输入行为
- 改变 compile / watcher / nightly 语义

## Open questions

(none — resolved in chat: dedup=A, Shell=A, approach=1)
