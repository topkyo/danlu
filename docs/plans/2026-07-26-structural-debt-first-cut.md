# 结构债第一刀 Implementation Plan

> **For agentic workers:** Load `executing-plans`（2 tasks）。用 `subteam` 审实质性 diff。然后 `finishing`。Checkboxes track progress.

**Goal:** 断 `content↔memory` import 环，并外提 machine-memory auto-resolution，零行为变更。  
**Spec:** `docs/specs/2026-07-26-structural-debt-first-cut.md`  
**Architecture:** 纯符号搬家 + 原模块 re-export；不改 apply/revert TX、不改产品 CLI。  
**Tech stack:** Python 3.10+ / `bash scripts/verify.sh`

---

## Files touched

| File | Action | Responsibility |
|------|--------|----------------|
| `src/aiwiki/memory/action_rank.py` | create | `action_priority_rank` / `action_status_rank` |
| `src/aiwiki/memory/action_core.py` | modify | 删定义；re-export rank + placeholder |
| `src/aiwiki/content/concepts.py` | modify | 内联 `placeholder_concept_slugs`；直引 `action_rank`；删 lazy wrappers |
| `src/aiwiki/execution/machine_memory_auto_resolution.py` | create | auto-resolution 簇 |
| `src/aiwiki/execution/machine_memory_actions.py` | modify | 删簇；re-export 公开符号 |
| `docs/specs/2026-07-26-structural-debt-first-cut.md` | modify | Status → Implemented |
| `PROGRESS.md` | modify | 头条记一笔 |

---

## Task 1: Knife B — 断 content↔memory 环

**Depends on:** none

**Files:**
- Create: `src/aiwiki/memory/action_rank.py`
- Modify: `src/aiwiki/memory/action_core.py`
- Modify: `src/aiwiki/content/concepts.py`

- [x] **Step 1:** 新建 `action_rank.py`，搬入：

```python
"""Pure rank helpers for machine-memory actions (no content deps)."""

from __future__ import annotations


def action_priority_rank(priority: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(priority, 9)


def action_status_rank(status: str) -> int:
    return {"proposed": 0, "accepted": 1, "deferred": 2, "resolved": 3, "rejected": 4}.get(status, 9)
```

- [x] **Step 2:** 在 `concepts.py` 将 `_placeholder_concept_slugs` / `_action_priority_rank` 换成：
  - 模块级 `from ..memory.action_rank import action_priority_rank`
  - 公开函数 `placeholder_concept_slugs(root)`：循环 `wiki/concepts/*.md`，用 `preserved_section(..., "Summary", "")` + `_concept_summary_matches_legacy_placeholder`（**禁止** import `content.memory`）
  - 调用点改用上述符号；删除两个 lazy wrapper
- [x] **Step 3:** `action_core.py`：删除三函数定义；改为

```python
from ..content.concepts import placeholder_concept_slugs
from .action_rank import action_priority_rank, action_status_rank
```

  （`placeholder` 从 concepts re-export 时注意：`action_core` 已 eager import `content.concepts` 的其它符号——合并 import 块，避免循环：此时 concepts **不再** import action_core，故安全。）

- [x] **Step 4:** 门禁检查：

```bash
rg 'from \.\.memory\.action_core|memory\.action_core' src/aiwiki/content/concepts.py
# expect: no matches
PYTHONPATH=src python3 -c "
from aiwiki.content import concepts
from aiwiki.memory import action_core, action_rank
assert concepts.placeholder_concept_slugs is not None
assert action_core.action_priority_rank is action_rank.action_priority_rank
assert action_core.placeholder_concept_slugs is concepts.placeholder_concept_slugs
print('ok', action_rank.action_priority_rank('high'))
"
```

- [x] **Verify:** `bash scripts/verify.sh python-static smoke`
- [x] **Commit:** `refactor: break content↔memory cycle via action_rank + concepts placeholder`

---

## Task 2: Knife A — 外提 auto-resolution

**Depends on:** Task 1（串行审 diff；文件集不相交但同轮交付）

**Files:**
- Create: `src/aiwiki/execution/machine_memory_auto_resolution.py`
- Modify: `src/aiwiki/execution/machine_memory_actions.py`

- [x] **Step 1:** 确认迁出边界（当前约 L90–557）：常量 `AUTO_RESOLUTION_*`、policy/escalation helpers、`auto_resolve_machine_memory_actions`。若某 helper 被 apply/revert 引用则**留原文件**，新模块从原文件 import。
- [x] **Step 2:** 新建 `machine_memory_auto_resolution.py`，剪切上述符号；补齐其依赖 import（从 true owners，不经 facade）。
- [x] **Step 3:** `machine_memory_actions.py` 删除已迁定义；顶部或底部 re-export：

```python
from .machine_memory_auto_resolution import (
    auto_resolve_machine_memory_actions,
    machine_memory_action_auto_resolution_policy,
)
```

  （若还有其它曾公开符号被迁出，一并 re-export。）

- [x] **Step 4:** LOC / import 抽检：

```bash
wc -l src/aiwiki/execution/machine_memory_actions.py \
      src/aiwiki/execution/machine_memory_auto_resolution.py
PYTHONPATH=src python3 -c "
from aiwiki.execution.machine_memory_actions import (
    auto_resolve_machine_memory_actions,
    apply_machine_memory_action,
)
from aiwiki.execution import machine_memory_auto_resolution as ar
assert auto_resolve_machine_memory_actions is ar.auto_resolve_machine_memory_actions
print('ok')
"
```

- [x] **Verify:** `bash scripts/verify.sh python-static smoke acceptance`
- [x] **Commit:** `refactor: extract machine_memory_auto_resolution from actions monolith`

---

## Final verify

- [x] `bash scripts/verify.sh all`
- [x] Spec Status → `Implemented`；PROGRESS 头条记 Knife B+A
- [x] Commit（若上两项未进前两个 commit）：`docs: structural-debt first-cut done`

---

## Out of scope（本 plan 明确不做）

- apply/revert 拆分、TX helper 与 `utils/io` 合并  
- Shell TS、恢复单元测试、改 Scorecard 分数  
