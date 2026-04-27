---
title: "炼丹炉 M7 路线图 — 9 分收口"
kind: "execution-plan"
status: "active"
owner: "tim"
created_at: "2026-04-28"
related_docs:
  - docs/Furnace Agent Architecture.md
  - docs/Furnace Evolution Mechanics.md
  - docs/Furnace Next Execution Plan.md
  - docs/Furnace M6.7 Roadmap.md
---

# 炼丹炉 M7 — 9 分收口路线图

> **生成依据**：2026-04-28 oracle 独立评估（综合分 7.8/10），Next Execution Plan 4 大产品缺口，及 9+ Feasibility Contract 6 条约束。
> **Source of Truth**：`docs/Furnace Agent Architecture.md` §2.2、`docs/Furnace Next Execution Plan.md`。
> **当前基线**：M6.7.7 完成，1322 tests / 93% coverage，verify pass，acceptance 12/12。

---

## 0. 主题与判断

M6.x 已完成「功能与结构骨架」。M7 的唯一目的是**把综合评分从 7.8 推到 9.0+**，方法不是再堆 primitive，而是收敛已建能力 + 修正名实不符。

**5 个真实短板（按 ROI）**：

1. acceptance 未进入 verify 主门 — `verify.sh` 不调用 acceptance gate
2. scoped primitives 名实不符 — lane apply 仍调用全局 `compile_wiki/lint_wiki/nightly_health`
3. universal input / today feed 仅"有组件"非"唯一心智" — Product Shell 仍暴露 AskBox/DropZone + 7 public commands
4. metrics 偏名义完成 — `_read_review_counts` 是空实现，无趋势/delta
5. kill switch 仅命令级 — 无系统级 autonomy policy

---

## 1. Milestone 索引

| ID | 主题 | 维度 | ROI | 依赖 |
|---|---|---|---|---|
| **M7.0** | Gate Unification — verify 调用 acceptance | 测试 | 极高 | 无 |
| **M7.1** | Scoped Lane Hardening — lane primitive 真按 scope 执行 | 代码 | 极高 | M7.0 |
| **M7.2** | Product Surface Convergence — 首屏只留 Universal Input + Today | UI | 高 | M7.0 |
| **M7.3** | Metrics v2 — review reader + history + delta | 代码 | 高 | M7.0 |
| **M7.4** | System Kill Switch + Model Policy — `autonomy-policy.json` | 代码 | 中-高 | M7.0 |

执行顺序：M7.0 → M7.1 → M7.2 → M7.3 → M7.4，每个走完整 harness 闭环（contract → 实现 → verify → 回写 PROGRESS → commit）。

---

## 2. M7.0 — Gate Unification

**目标**：让 `bash scripts/verify.sh` 一次性跑通 unit + acceptance，使 "verify pass" 成为真实 baseline。

**问题事实**：
- `scripts/verify.sh:19` 只跑 `unittest discover`
- `scripts/run_acceptance.sh` 用 pytest，独立执行
- 当前 README/AGENTS/PROGRESS 把 `verify.sh` 当作主门，但实际不覆盖 acceptance 12 cases

**核心做法**：
- `scripts/verify.sh` 末尾追加 `bash scripts/run_acceptance.sh`
- 不破坏现有 ruff / coverage / unittest 链路
- coverage 仍以 unittest 为基准（acceptance 是 e2e 补充）
- 修改后立即 5 次连续运行验证稳定性

**Stop Lines**：
- 不改 acceptance 测试本身
- 不改 receipt/audit/shell-summary schema
- 不引入新依赖

**Gate**：
- `bash scripts/verify.sh` pass（unit ≥1322 + acceptance 12/12）
- 5 次连续 pass

---

## 3. M7.1 — Scoped Lane Hardening

**目标**：修正"scoped preview + global apply"，让 lane primitive 真正按 `scope_preview.source_ids` 等 scope 限定执行；若短期做不到完全 scope，至少在 receipt 中显式标记 `scope_enforced=false`，消除文档/代码名实不符。

**问题事实**：
- `src/aiwiki/runner/alchemy.py:2126-2131` lane apply 仍直接调用：
  - `compile_wiki(root)`
  - `lint_wiki(root)`
  - `nightly_health(root)`
- dry-run preview 有 `scope_preview`，但 apply 不消费它
- 这违反 9+ Contract 第 3 条 "Scoped primitives only"

**核心做法（务实分级）**：

**Level A（最小诚实改动，必做）**：
- lane primitive receipt 顶层增加字段：
  - `scope_declared`：dry-run preview 中的 scope（source_ids / concept_slugs / judgment_refs）
  - `scope_enforced`：bool，当前实现下置 `false`
  - `scope_enforcement_reason`：字符串，如 `"primitive_global_only"`
- 在 receipt 中如实记录"声明 scope 但执行全局"
- 文档同步：架构 SoT §2.1 把 lane primitive 标记从 implemented 调整为 partial(scope_enforced=false)

**Level B（实质改动，能做就做）**：
- 给 `compile_wiki` / `lint_wiki` 增加可选参数 `scope_filter: dict | None = None`，None 时全局（向后兼容）
- lane primitive 调用时传入 `scope_filter=scope_preview`
- compile/lint 内部按 scope_filter 限定遍历
- nightly 短期保持全局（nightly 本质就是全局健康检查），receipt 标 `scope_enforced=false reason=nightly_global_by_design`

**测试**：
- 新增 unit test 断言 receipt 含 `scope_enforced` / `scope_declared`
- 若做 Level B，新增 test 验证 scope filter 真生效

**Stop Lines**：
- 不改 lane apply 的 dry-run gate / apply_supported / runtime-history audit 语义
- 不改 receipt schema 既有字段（只增字段）
- 不改变 `compile_wiki / lint_wiki / nightly_health` 默认全局行为（保持向后兼容）

**Gate**：
- `bash scripts/verify.sh` pass
- 新增 lane scope receipt unit tests pass
- 文档与代码状态对齐

---

## 4. M7.2 — Product Surface Reconciliation（已收敛，仅 SoT 对齐）

**状态**：first-screen surface 已 converged。M7.2 实际改动 = 文档纠偏 + 防回归 contract test。

**事实核对（2026-04-28 explorer + oracle 双检）**：
- `.obsidian/plugins/furnace-product-shell/src/render_home.js` 首屏只挂 `renderUniversalInput → renderTodayFeed → renderAdvancedDrawer`
- `renderAskBox` / `renderDropZone` 仍存在于 `render_input.js` 作为 legacy/compat helper（modal 仍可调用），**首屏 view 不挂载**
- 8 个 core commands 是 command palette 快捷别名 + 投喂入口（`drop-url/file/image` 由 AGENTS.md "维持直接投喂入口"明确要求）
- 22 个 advanced commands 已按 `showAdvancedCommands` 设置门控
- `aiwiki today` 5-section 输出是 `tests/test_acceptance_loop.py:599-627`、`tests/test_cli.py:193-249`、`tests/test_product_shell_today_feed.py` 多处契约绑定

**结论**：原路线图把"首屏心智收敛"和"command palette 快捷入口数量"混淆。强行藏 core commands 或改 today single-feed 是负收益破坏。

**M7.2 落地动作**（已完成）：
1. `tests/test_product_shell_smoke.py` 新增 `ProductShellFirstScreenContract`：6 个断言，首屏只挂 Universal Input + Today + Advanced，**不挂** AskBox / DropZone。防止未来回归 dashboard 心智。
2. 路线图本节状态更新为 `converged`。
3. 不改 core commands、不改 today、不删 legacy helpers（legacy surface cleanup 留 future milestone 单独做）。

**对 9+ Contract 影响**：基本无实质提分（M7.2 对应架构 §1 用户面投影，不是 §2.2 六条核心可行性约束）。价值在防止未来误回退，而非提分。

**Stop Lines**：
- 不改 core 8 commands
- 不改 today 输出 / 不加 `--sections` flag
- 不删 `renderAskBox` / `renderDropZone`
- 不改 dispatch.py / parsers.py


---

## 5. M7.3 — Metrics v2

**目标**：metrics 从"健康面板"升级为"复利证据"。

**问题事实**：
- `src/aiwiki/metrics_io.py:68-69` `_read_review_counts` 空实现
- `output_file_back_rate` 看 `derived_from`，非 file-back 行为本身
- 无趋势/delta，证明不了"知识复利"

**核心做法**：

**Stage A（必做）**：
- 实现 `_read_review_counts` —— 真实读取 review queue / receipt
- 实现 `_read_file_back_rate` 真实版 —— 基于 `.aiwiki/state/runtime-history.jsonl` 中 `event_type=file-back` 事件
- metrics keys 不变（保持 schema 兼容）

**Stage B（必做）**：
- 新增 `.aiwiki/state/metrics-history.jsonl`，每次 `aiwiki metrics` / nightly 追加一条 snapshot
- 新增 `aiwiki metrics --delta 7d` / `--delta 30d`，输出窗口对比
- shell summary metrics block 增加 `delta_7d` 字段（可选）

**Stop Lines**：
- 不改 7 个核心 metric key 名
- 不改 nightly schema
- 不引入数据库 / 时序库（用 jsonl append-only）

**Gate**：
- `bash scripts/verify.sh` pass
- 新增 metrics reader unit tests
- 新增 metrics-history append/delta unit tests
- acceptance 同 fixture 跑两次能产生 delta（fixture 内置 monkeypatch 时钟）

---

## 6. M7.4 — System Kill Switch + Model Policy

**目标**：把安全边界从"CLI discipline"提升为"runtime policy"。补齐 9+ Contract 第 6 条 "Kill switch by design"。

**问题事实**：
- 无 `.aiwiki/state/autonomy-policy.json`
- 无 `AIWIKI_DISABLE_AUTOMATION=1` env
- `config.py:291-309` codex 默认 `gpt-5.4`、nvidia 默认 `kimi-k2.5`，与架构 §2.1 "model 显式选择"冲突

**核心做法**：

**Kill Switch**：
- 新增 `.aiwiki/state/autonomy-policy.json`：
  ```json
  {
    "schema_version": 1,
    "disable_lane_apply": false,
    "disable_alchemy_auto": false,
    "disable_l3_generate": false,
    "disable_external_llm": false
  }
  ```
- 新增 `aiwiki autonomy-status` / `aiwiki autonomy-disable <flag>` / `aiwiki autonomy-enable <flag>` CLI
- env override：`AIWIKI_DISABLE_AUTOMATION=1` 强制全部 disable
- runner 在每个受控 apply / generate 入口先读 policy；disabled 时返回 structured `skipped` + reason，不写盘

**Model Policy**：
- 新增 `AIWIKI_REQUIRE_EXPLICIT_MODEL=1` 模式：未显式设置 `AIWIKI_LLM_MODEL` 时报错
- 默认仍允许 backend default（向后兼容），但 `llm-check` 输出新增 `model_source: explicit | backend_default`
- shell summary / receipt 同步暴露 `model_source`

**Stop Lines**：
- 默认行为向后兼容（policy 文件不存在 = 全 enable，等同当前行为）
- 不改 receipt 既有字段
- 不引入第三方依赖

**Gate**：
- `bash scripts/verify.sh` pass
- 新增 autonomy-policy unit tests（每个 disable flag 独立断言）
- 新增 model_source 断言

---

## 7. 9 分判据

M7.0 ~ M7.4 全部完成后，重新对 9+ Contract 6 条评分，目标：

| Contract | M6.7 末分数 | M7 后目标 |
|---|---:|---:|
| Observe before schedule | 8.5 | 9.0+ |
| Manual-first before automation | 8.8 | 9.0+ |
| Scoped primitives only | 7.0 | **9.0+**（M7.1） |
| Compatibility adapters | 8.2 | 8.5+ |
| No hidden backend choice | 8.3 | **9.0+**（M7.4 model policy） |
| Kill switch by design | 7.4 | **9.0+**（M7.4 autonomy） |

加权综合分目标：**8.6 ~ 9.0**（M7.2 已确认为零提分项 —— 用户面已收敛，仅 SoT 对齐 + 防回归）。

---

## 8. 执行方式

每个 milestone 默认走 harness 流程：

```text
读 SoT → 写 .codex/contracts/active.md → 实现 → bash scripts/verify.sh → 归档 contract → 回写 PROGRESS.md → 本地 commit
```

`ask_policy=blockers-only`，`execution_mode=autonomous-closed-loop`。

---

## 9. Stop Lines（M7 总）

- 任何 milestone 需要破坏 `raw/ → wiki/ → output/` 分层
- 任何 milestone 需要改 receipt / audit / shell-summary 既有字段（只能新增）
- 任何 milestone 需要引入 hosted service / multi-user sync / heavy RAG / fine-tuning
- 任何 milestone 连续 3 轮调试 verify 不通过 → 升级
- 任何 milestone 触发 acceptance 大面积 golden 改动（>20%）→ 升级
