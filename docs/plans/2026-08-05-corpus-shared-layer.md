# `aiwiki.corpus` Shared Layer — Implementation Plan

> **For agentic workers:** Load `executing-plans` (2+ tasks). Use `subteam` after substantive tasks. Then `finishing`. Checkboxes track progress.

**Goal:** 用 `aiwiki.corpus` 只读共享层断开 `content ↔ memory` 环，使 `content` **零** import `memory`。  
**Spec / 分析:** `docs/plans/2026-08-05-structural-debt-resolution.md` §4 方案 A  
**Architecture:** `corpus` 只依赖 `utils` / `state` / `protocol`；禁止 import `content` / `memory` / `execution` / `runner`。首波只迁「环上交叉的纯函数 + path 常量」，并把 `content` 对 `load_machine_memory` 的依赖改为调用方注入。`memory → content` 窄只读依赖本波允许保留（环已单向）。  
**Tech stack:** Python 3.10+ stdlib；验证 `bash scripts/verify.sh`。  
**Out of scope（另开计划）:** facade 删除、hub 拆分、`memory→content` 全迁入 corpus、Commercial 三阻断。

---

## Files touched

| File | Action | Responsibility |
|------|--------|----------------|
| `src/aiwiki/corpus/__init__.py` | create | 包文档 + 所有权规则 |
| `src/aiwiki/corpus/paths.py` | create | 共享 state path（从 memory.paths 迁入环相关项） |
| `src/aiwiki/corpus/scoring.py` | create | 纯评分/时间 helper（整文件自 memory.scoring 迁入） |
| `src/aiwiki/corpus/ranks.py` | create | `action_priority_rank` / `action_status_rank`（自 memory.action_rank） |
| `src/aiwiki/memory/paths.py` | modify | re-export 自 corpus（过渡；Task 4 可删冗余） |
| `src/aiwiki/memory/scoring.py` | modify | re-export 自 corpus |
| `src/aiwiki/memory/action_rank.py` | modify | re-export 自 corpus |
| `src/aiwiki/content/{material,archive,rewrite,concept_quality}.py` | modify | 改引 corpus；去掉 memory import |
| `src/aiwiki/compile/{runtime_step,ranking}.py` | modify | scoring→corpus；material 注入 memory |
| `src/aiwiki/execution/ask.py` / `app_linting/nightly.py` | modify | `refresh_material_state` 传入 memory |
| `src/aiwiki/memory/action_core.py` 等 | modify | ranks 可改引 corpus（或继续经 memory.action_rank re-export） |
| `tests/test_library_surfaces.py` | modify | 加分层 import 契约测 |
| `scripts/docs_consistency_check.sh` | modify | `content ↛ memory` 硬钉 |
| `docs/DEVELOPER.md` | modify | owner map 加 `corpus/` |
| `PROGRESS.md` | modify | 头条记录 |

---

## Task 1: 建包并迁入 paths / scoring / ranks

**Depends on:** none

**Files:**
- Create: `src/aiwiki/corpus/__init__.py`
- Create: `src/aiwiki/corpus/paths.py`
- Create: `src/aiwiki/corpus/scoring.py`
- Create: `src/aiwiki/corpus/ranks.py`
- Modify: `src/aiwiki/memory/paths.py`, `scoring.py`, `action_rank.py`（改为 re-export，行为不变）

- [ ] **Step 1:** 创建包文档，写明禁止依赖：

```python
"""Read-only shared corpus helpers (paths, scoring, ranks).

Owned symbols used by both ``content`` and ``memory``.
MUST NOT import ``content``, ``memory``, ``execution``, or ``runner``.
"""
```

- [ ] **Step 2:** 将下列 path 函数迁入 `corpus/paths.py`（实现原样剪切）：
  - `manual_link_state_path`
  - `concept_rewrite_state_path`
  - `concept_rewrite_proposal_page_path`
  - （可选同迁）`machine_memory_action_state_path` / `machine_memory_history_path` / `execution_*` — **仅当本波有 content 调用方**；否则留 `memory.paths`，避免 scope 膨胀。本波最低集：前三个。
- [ ] **Step 3:** 将 `memory/scoring.py` 全文迁入 `corpus/scoring.py`；`memory/scoring.py` 变为：

```python
"""Compat re-export — prefer ``aiwiki.corpus.scoring``."""
from aiwiki.corpus.scoring import *  # noqa: F403
```

- [ ] **Step 4:** 将 `action_priority_rank` / `action_status_rank` 迁入 `corpus/ranks.py`；`memory/action_rank.py` 同样 re-export。
- [ ] **Step 5:** `memory/paths.py` 对已迁符号 re-export；未迁符号保留本地实现。
- [ ] **Verify:** `bash scripts/verify.sh python-static` — expect PASS；`PYTHONPATH=src python3 -c "from aiwiki.corpus import scoring, paths, ranks; from aiwiki.memory import scoring as ms"` — expect no ImportError。

---

## Task 2: content / compile 改引 corpus（断 paths/scoring/ranks 边）

**Depends on:** Task 1（corpus 符号存在）

**Files:**
- Modify: `src/aiwiki/content/archive.py` — `from ..corpus.scoring import ...`
- Modify: `src/aiwiki/content/rewrite.py` — `from ..corpus.paths import concept_rewrite_state_path`
- Modify: `src/aiwiki/content/material.py` — paths/scoring → corpus（`load_machine_memory` 留到 Task 3）
- Modify: `src/aiwiki/content/concept_quality.py` — `from ..corpus.ranks import action_priority_rank`
- Modify: `src/aiwiki/compile/ranking.py` — `from ..corpus.scoring import recency_score_for_timestamp`

- [ ] **Step 1:** 按上表改 import；不改函数体。
- [ ] **Step 2:** 确认 content 内不再出现 `from ..memory.scoring` / `from ..memory.paths` / `from ..memory.action_rank`：

```bash
rg 'from \.\.memory\.(paths|scoring|action_rank)' src/aiwiki/content
# expect: no matches
```

- [ ] **Verify:** `bash scripts/verify.sh python-static` + `bash scripts/verify.sh unit` — expect PASS。

---

## Task 3: 去掉 content → `load_machine_memory`（调用方注入）

**Depends on:** Task 2（material 已用 corpus paths/scoring）

**Files:**
- Modify: `src/aiwiki/content/material.py` — `build_material_state_documents` / `refresh_material_state` 增加 `machine_memory: dict[str, Any] | None = None`
- Modify: `src/aiwiki/compile/runtime_step.py` — 传入 `machine_memory=context.memory`
- Modify: `src/aiwiki/execution/ask.py` — `refresh_material_state(..., machine_memory=load_machine_memory(root))`（ask 已 import memory，合法）
- Modify: `src/aiwiki/app_linting/nightly.py` — 同上（nightly 已有 memory）

- [ ] **Step 1:** 改签名与默认行为：

```python
def build_material_state_documents(
    root: Path,
    *,
    generated_at: str,
    entries: list[dict[str, Any]] | None = None,
    active_protocol: str | None = None,
    machine_memory: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    ...
    memory = machine_memory if isinstance(machine_memory, dict) else {}
    graph_context = material_graph_context(memory)
```

- [ ] **Step 2:** 删除 `material.py` 顶层 `from ..memory.state import load_machine_memory`。
- [ ] **Step 3:** 调用方传入真实 memory（compile 用 `context.memory`；ask/nightly 本地 load 后传入）。
- [ ] **Step 4:** 硬门禁：

```bash
rg 'from \.\.memory|from aiwiki\.memory' src/aiwiki/content
# expect: no matches
```

- [ ] **Verify:** `bash scripts/verify.sh unit` + `bash scripts/verify.sh acceptance` — expect PASS（acceptance 24）。

---

## Task 4: 分层契约测 + docs_consistency 钉 + SoT

**Depends on:** Task 3（content↛memory 已成立）

**Files:**
- Modify: `tests/test_library_surfaces.py` — 新增分层测试
- Modify: `scripts/docs_consistency_check.sh` — rg 钉
- Modify: `docs/DEVELOPER.md` — owner map 行
- Modify: `PROGRESS.md` — 头条 1–2 行
- Modify: `docs/plans/2026-08-05-structural-debt-resolution.md` — 标注环断开状态（可选一行）

- [ ] **Step 1:** 测试（示意）：

```python
def test_content_package_does_not_import_memory() -> None:
    import ast
    from pathlib import Path
    root = Path("src/aiwiki/content")
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("aiwiki.memory")
                assert not node.module.startswith("..memory")
                # relative: module may be "memory" with level>=1 — reject level>=1 and module=="memory" or startswith "memory."
```

（实现时用 AST 覆盖 relative `from ..memory...`；也可用子进程 `rg` 断言。）

- [ ] **Step 2:** `docs_consistency_check.sh` 增加：

```bash
if rg -n 'from \.\.memory|from aiwiki\.memory' src/aiwiki/content --glob '*.py' >/dev/null; then
  echo "[FAIL] content must not import memory" >&2
  FAIL=1
else
  echo "[OK] content ↛ memory"
fi
if rg -n 'from \.\.content|from \.\.memory|from aiwiki\.(content|memory)' src/aiwiki/corpus --glob '*.py' >/dev/null; then
  echo "[FAIL] corpus must not import content/memory" >&2
  FAIL=1
else
  echo "[OK] corpus ↛ content/memory"
fi
```

- [ ] **Step 3:** DEVELOPER owner map 增加：`corpus/` = 只读共享 paths/scoring/ranks。
- [ ] **Verify:** `bash scripts/docs_consistency_check.sh` + `bash scripts/verify.sh unit` — expect PASS。

---

## Task 5: Final verify + 收口记录

**Depends on:** Task 4

**Files:**
- Modify: `PROGRESS.md`（若 Task 4 未写全）
- Modify: Scorecard / Post-Cleanup 仅当计数变化时（本波预期 unit +1 分层测）

- [ ] **Step 1:** 跑全量：`bash scripts/verify.sh all` — expect EXIT 0；记录 acceptance/llm/unit/Jest 计数。
- [ ] **Step 2:** 更新计数钉（若 unit 因新测增加）；`docs_consistency` 绿。
- [ ] **Step 3:** PROGRESS 头条：`content↛memory` 经 corpus 落地；链到本计划。
- [ ] **Verify:** `bash scripts/verify.sh all` + `bash scripts/docs_consistency_check.sh`。

---

## Final verify

```bash
bash scripts/verify.sh all
bash scripts/docs_consistency_check.sh
rg 'from \.\.memory|from aiwiki\.memory' src/aiwiki/content   # empty
rg 'from \.\.(content|memory)|from aiwiki\.(content|memory)' src/aiwiki/corpus  # empty
```

**Done 判据（本计划）：**
1. `content` 包 AST/`rg` 零 `memory` import  
2. `corpus` 零 `content`/`memory` import  
3. `verify.sh all` EXIT 0  
4. DEVELOPER 有 `corpus/` owner 行  

**非本计划 Done：** facade 清零、hub &lt;800、memory↛content。

---

## 风险与回滚

| 风险 | 缓解 |
|---|---|
| `refresh_material_state` 未传 memory → graph_context 空 | ask/nightly 必须显式传入；单测可补「缺省 {} 不崩」 |
| re-export 双路径混淆 | Task 4 后门禁只钉 content/corpus；memory re-export 允许过渡 |
| material 仍 lazy import `compile.ranking` / `execution.history` | 已知；不属 content↔memory 环；另记 follow-up |
