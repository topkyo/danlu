# ask / io hub 单 seam ×2

> **For agentic workers:** `executing-plans` inline（2 tasks）。禁止 broad rewrite；views ask_report 已在同分支落地时一并保留。

**Goal:** 各外提一条自然 seam，使 `execution/ask.py` 与 `content/io.py` 明显瘦身。  
**Out:** 不拆 `ask_question` 巨函数本体；不改 file-back / output 扫描语义；不留 re-export facade。

## Seams

| Hub | Seam | New owner | Approx LOC out |
|-----|------|-----------|----------------|
| ask | `file_back` 写出面 | `execution/file_back.py` | ~210（含 stem/hints） |
| io | output 扫描 + recurring promotion | `content/output_artifacts.py` | ~200（L479–677） |

## Files touched

| File | Action |
|------|--------|
| `src/aiwiki/execution/file_back.py` | create |
| `src/aiwiki/execution/ask.py` | modify — 删除 file_back 簇；`_output_artifact_seed` 用 shared stem |
| `src/aiwiki/cli/dispatch.py` | modify — import file_back owner |
| `tests/test_acceptance_loop.py` | modify — import file_back owner |
| `src/aiwiki/content/output_artifacts.py` | create |
| `src/aiwiki/content/io.py` | modify — 删除 output 簇 |
| callers of collect_*/find_promoted/annotate_* | retarget `content.output_artifacts` |
| `PROGRESS.md` / Post-Cleanup / DEVELOPER | hub 行数刷新 |

---

## Task 1: ask → file_back

**Depends on:** none

- [x] 剪切 `NEXT_STEP_HINTS` / stem / `file_back` → `execution/file_back.py`（244）
- [x] `ask.py` 665；dispatch + acceptance 直引 owner
- [x] Verify python-static / unit / acceptance 绿

**Done：** `ask.py` **665**（< 720）。

---

## Task 2: io → output_artifacts

**Depends on:** none（同 checkout 串行）

- [x] 剪切 collect_* … `annotate_recurring_promotion` → `content/output_artifacts.py`（226）
- [x] Callers retarget；`io.py` **677**
- [x] Verify python-static / unit **153** / acceptance **24** / llm **85** / scripts 绿

**Done：** `io.py` **677**（< 700）。
