# 结构债第一刀：断 content↔memory 环 + 外提 auto-resolution

**Date:** 2026-07-26  
**Status:** Implemented 2026-07-26（Knife B + Knife A；`verify.sh all` PASS）  
**Context:** 全量扫描独立评分指出循环依赖与巨石文件；Commercial Go-Live 主线外的工程债切片。

## Goal（两刀，可独立 verify）

1. **Knife B — 断环**：消除 `content/concepts.py` ↔ `memory/action_core.py` 的唯一闭合 import 环；行为零变化。  
2. **Knife A — 减巨石**：从 `execution/machine_memory_actions.py`（~1382 LOC）外提 auto-resolution 簇到独立模块；apply/revert TX 不动；行为零变化。

顺序：**先 B 后 A**（解环为后续改 concepts/action_core 开路；A 不依赖 B，但串行更易审）。

## Non-goals

| 不做 | 理由 |
|------|------|
| 拆 apply/revert TX | 互调复杂；无专用单测；本轮风险过高 |
| 合并 TX helper 到 `utils/io` | 实现细节（`mkstemp` vs `.restore.tmp`）有 drift；另题 |
| Product Shell TS / esbuild | 偏离本切片 |
| 恢复 144 单元测试 | 验证仍靠 acceptance + llm-integration + python-static |
| 改 L3 / auto-adopt / 产品 CLI | 边界已定；本轮纯搬家 |
| 删除 `action_core` re-export | 调用方多；保留兼容面 |

## Design

### Knife B — 断环

**现状环**

```
memory/action_core.py ──eager──► content.concepts
content/concepts.py   ──lazy───► memory.action_core
  (_placeholder_concept_slugs / _action_priority_rank)
```

**改法**

| 符号 | 新家 | 说明 |
|------|------|------|
| `action_priority_rank` / `action_status_rank` | 新 `memory/action_rank.py` | 纯函数，零 content 依赖 |
| `placeholder_concept_slugs` | **迁入** `content/concepts.py` | 用已有 `preserved_section` + `_concept_summary_matches_legacy_placeholder`（等价于 `concept_summary_is_placeholder`，**不**经 `content.memory`，避免 concepts↔content.memory 新环） |
| `concepts.py` lazy wrappers | **删除** | 直接用本模块 `placeholder_concept_slugs` + `from ..memory.action_rank import action_priority_rank` |
| `action_core` | **re-export** 上述符号 | `app_linting/*`、`repair_plan`、`app_shell/*` 等调用方零改 |

**验收**：`concepts` 不再 import `action_core`；`PYTHONPATH=src python3 -c` 双向加载 OK；环边消失。

### Knife A — 外提 auto-resolution

**迁出范围**（约 L90–557，以当前文件为准）：

- 常量：`AUTO_RESOLUTION_*`
- 异常类若仅 auto-resolution 用则随迁；若 apply/revert 共用则留原文件
- `_clear_auto_resolution_exception_metadata`、`_auto_resolution_receipt_path`
- `_fallback_policy_fields` / `_policy_fields`（若仅 auto-resolution 用）
- `machine_memory_action_auto_resolution_policy`
- `_build_auto_resolution_escalation_receipt` / `_apply_auto_resolution_escalation`
- `auto_resolve_machine_memory_actions`

**新文件**：`src/aiwiki/execution/machine_memory_auto_resolution.py`  
**原文件**：删除上述定义；**re-export** 公开符号（至少 `auto_resolve_machine_memory_actions`、`machine_memory_action_auto_resolution_policy`），保证外部 import 路径不变。  
**不动**：`apply_machine_memory_action` / `revert_machine_memory_action` / review / query / TX snapshot helpers（除非确认仅 auto-resolution 私用）。

## Success criteria

- [ ] Knife B：`rg 'from \.\.memory\.action_core' src/aiwiki/content/concepts.py` → 无匹配  
- [ ] Knife A：`machine_memory_actions.py` LOC 明显下降（目标 ~900 段）；新模块可独立 import  
- [ ] 行为：无产品语义变更；公开符号仍可从原模块 import  
- [ ] Verify：`bash scripts/verify.sh python-static smoke acceptance` PASS；收口 `all` PASS  
- [ ] PROGRESS 记一笔；本 spec Status → Implemented

## Risks

| 风险 | 缓解 |
|------|------|
| re-export 漏符号 | 迁前 `rg` 全量引用面；迁后 python-static |
| auto-resolution 与 apply 共享私有 helper | 共享则留原文件或双向 import 私有函数；禁止新 facade 层 |
| acceptance 不覆盖 auto_resolve 路径 | 本轮只搬家；不改分支语义；smoke + static 证加载 |
