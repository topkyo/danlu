# W1 Single-Protocol Runtime — Implementation Plan

> **For agentic workers:** Load `executing-plans`. One implementer Task per task below; review after each DONE. Then `finishing`. Checkboxes track progress.

**Goal:** Physically collapse 炼丹炉 to a single protocol runtime (`general` only): delete multi-protocol schema/CLI/Shell/learnings/pilots; zero alias for old protocol slugs.  
**Spec:** `docs/specs/2026-07-18-knowledge-compounding-principles.md` (P9, W1: A1 A2 A38 B45 + C52 protocol docs)  
**Architecture:** One canonical runtime from `protocol/library.py` + `schema/protocols/general/`. `shell_protocol_state` and `load_protocol_state` must agree. Old `protocol-set investing|…` and `protocol-learn-*` gone (hard fail / missing command). Non-`general` `protocol.json` **coerces to `general` and rewrites state** (explicit one-time migration, not cross-protocol alias).  
**Tech stack:** Python 3.10+, Product Shell JS, `bash scripts/verify.sh`  
**Out of this plan:** W2 ranking/suggest build; W3–W5 governance cuts (separate plans).

**Worktree:** `.worktrees/feat-w1-single-protocol` on branch `feat/w1-single-protocol`

---

## Files touched (summary)

| Area | Paths |
|------|--------|
| Library | `src/aiwiki/protocol/library.py`, `runtime_config.py`, `templates.py`, `descriptors.py` |
| State | `src/aiwiki/app_protocol.py`, `app_compile_ops.py`, `app_shell/meta.py` |
| Learnings | `src/aiwiki/execution/protocol_learnings.py` (delete), `runner/commands.py`, `runner/workflows.py` |
| CLI | `src/aiwiki/cli/parsers.py`, `dispatch.py`, `legacy_argv.py` |
| Ask/B45 | `src/aiwiki/execution/ask.py`, `app_queries.py` |
| Pilots A38 | `src/aiwiki/render/pilots.py` call sites, `app_vault.py`, lint phases |
| Schema | `schema/protocols/` — keep `general/` + rewrite `index.md`; delete other slug dirs |
| Shell | `.obsidian/plugins/furnace-product-shell/src/*` + `build.sh` → `main.js` |
| Fixtures | `tests/fixtures/acceptance/M6.1/case_idempotency_shell/...`, M6.1b/M6.2 index.md, `tests/test_acceptance_loop.py` |
| Docs | `docs/USER_GUIDE.md`, `DEVELOPER.md`, Evolution/Architecture protocol sections, `PROGRESS.md` |

---

## Task 1: Collapse PROTOCOL_LIBRARY + runtime_config + state loaders

**Depends on:** none

**Files:**
- Modify: `src/aiwiki/protocol/library.py` — only `general` entry
- Modify: `src/aiwiki/protocol/runtime_config.py` — drop per-slug maps or keep only `general` keys
- Modify: `src/aiwiki/app_protocol.py` — `available_protocols()` only general; `load_protocol_state` coerce non-general → general + rewrite `.aiwiki/state/protocol.json`; `ensure_protocol_scaffold` only general; `resolve_protocol` reject non-general with clear error
- Modify: `src/aiwiki/app_shell/meta.py` — `shell_protocol_state` / capabilities: remove `protocol-set` from p0; `available_protocols == ["general"]` only
- Modify: `src/aiwiki/app_compile_ops.py` — `set_active_protocol` only accepts `general` or delete callers later

- [ ] **Step 1:** Shrink `PROTOCOL_LIBRARY` to `{"general": ...}` only.
- [ ] **Step 2:** Coerce logic in `load_protocol_state`: if active not `general`, set active=`general`, write state, do not preserve investing/research behavior.
- [ ] **Step 3:** Align `shell_protocol_state()` with the same single list (fix dual-source bug).
- [ ] **Verify:** `bash scripts/verify.sh python-static`

**Commit:** `feat(protocol): collapse library and state to general-only`

---

## Task 2: Delete protocol-learn (A2) + B45 ask injection

**Depends on:** Task 1

**Files:**
- Delete: `src/aiwiki/execution/protocol_learnings.py` (if only used for learnings)
- Modify: `src/aiwiki/runner/commands.py` — remove learn façades
- Modify: `src/aiwiki/runner/workflows.py` — remove nightly protocol_learnings aging hook
- Modify: `src/aiwiki/cli/parsers.py` — remove all `protocol-learn-*` parsers; remove `--load-learnings`; remove or ignore `--protocol` on ask/run-ask/file-back/alchemy (prefer **remove flags**; if flag remains, only `general` allowed else argparse/runtime error)
- Modify: `src/aiwiki/cli/dispatch.py` — remove learn + protocol override wiring
- Modify: `src/aiwiki/cli/legacy_argv.py` — remove learn/protocol-set rewrites
- Modify: `src/aiwiki/execution/ask.py` — remove `load_learnings_for_protocol` block
- Modify: `src/aiwiki/app_queries.py` / `app_protocol.py` — remove `protocol_output_guidance` injection into report seed if present
- Grep-clean imports/signals referencing `protocol_learning`

- [ ] **Step 1:** Delete learn CLI + module + nightly hook.
- [ ] **Step 2:** Remove B45 guidance/learnings injection from ask path.
- [ ] **Step 3:** Remove `protocol-set` / `protocol-status` parsers and dispatch (A1 CLI).
- [ ] **Verify:** `rg 'protocol-learn|load_learnings_for_protocol|protocol-set' src/aiwiki` → no live commands; `bash scripts/verify.sh python-static cli-smoke`

**Commit:** `feat(protocol): remove learnings CLI and ask protocol guidance`

---

## Task 3: Delete multi-protocol schema templates + pilots (A38)

**Depends on:** Task 1

**Files:**
- Delete dirs: `schema/protocols/investing/`, `research/`, `product/`, `ops/`
- Modify: `schema/protocols/index.md` — single-runtime copy
- Modify: `src/aiwiki/protocol/templates.py` — no multi-protocol scaffold lists; domain-pilots template remove or stub
- Modify: `src/aiwiki/protocol/descriptors.py` — single protocol index text
- Modify: `src/aiwiki/app_vault.py` — bootstrap folder labels only general
- Modify: pilots render/lint call sites (`render/pilots.py` consumers in `app_linting/*`, `app_queries.py`) — stop generating per-protocol pilots; delete or no-op pilot generation
- Delete or gut: `.aiwiki/derived/pilots` layout expectations if only for multi-protocol scorecards

- [ ] **Step 1:** Delete four protocol trees under repo `schema/protocols/`.
- [ ] **Step 2:** Stop pilot scorecard generation for multiple protocols.
- [ ] **Verify:** `test -d schema/protocols/investing` fails; `bash scripts/verify.sh python-static`

**Commit:** `feat(protocol): delete non-general schema trees and pilots`

---

## Task 4: Product Shell — remove protocol picker / set

**Depends on:** Task 1, Task 2

**Files:**
- Modify: `.obsidian/plugins/furnace-product-shell/src/constants.js` — `DEFAULT_PROTOCOLS = ["general"]` or remove multi list
- Modify: `context_state.js`, `plugin.js`, `modals.js`, `modal_specs.js`, `command_specs.js`, `plugin_lifecycle.js`, `render_primitives.js` — remove ProtocolCommandModal / ask protocol `<select>` / `runProtocolSetCommand`; stop passing `--protocol`
- Update Jest that assume five protocols or `research` pickers
- Rebuild: `bash .obsidian/plugins/furnace-product-shell/build.sh` (or repo `build.sh`)

- [ ] **Step 1:** Remove UI + command wiring for protocol set/pick.
- [ ] **Step 2:** Rebuild `main.js`; fix Jest.
- [ ] **Verify:** `bash scripts/verify.sh product-shell-static`

**Commit:** `fix(shell): remove multi-protocol picker and protocol-set`

---

## Task 5: Acceptance fixtures + test_acceptance_loop

**Depends on:** Task 3, Task 4

**Files:**
- Modify/delete: `tests/fixtures/acceptance/M6.1/case_idempotency_shell/root/schema/protocols/{investing,research,product,ops}/`
- Modify: all acceptance `schema/protocols/index.md` still advertising five protocols
- Modify: `tests/fixtures/.../wiki/indexes/domain-pilots.md` if multi-protocol
- Modify: `tests/test_acceptance_loop.py` — replace `--protocol research` with no flag or `general`

- [ ] **Step 1:** Collapse M6.1 idempotency fixture to general-only schema.
- [ ] **Step 2:** Fix acceptance loop protocol flags.
- [ ] **Verify:** `bash scripts/verify.sh acceptance`

**Commit:** `test: single-protocol acceptance fixtures`

---

## Task 6: Active docs + PROGRESS + final verify

**Depends on:** Task 5

**Files:**
- Modify: `docs/USER_GUIDE.md`, `docs/DEVELOPER.md`, `docs/Furnace Evolution Mechanics.md`, `docs/Furnace Agent Architecture.md` (五协议主线 → 单 runtime)
- Modify: `PROGRESS.md` — W1 done note
- Modify: `docs/plans/2026-07-18-w1-single-protocol-runtime.md` checkboxes
- Do **not** rewrite `docs/archive/**`

- [ ] **Step 1:** Active doc sync for single protocol.
- [ ] **Step 2:** `bash scripts/docs_consistency_check.sh`
- [ ] **Step 3:** `bash scripts/verify.sh all`
- [ ] **Verify:** all PASS

**Commit:** `docs: sync active docs for single-protocol runtime`

---

## Final verify

```bash
bash scripts/verify.sh all
rg -n 'protocol-set|protocol-learn|PROTOCOL_LIBRARY\[|investing/research/product/ops' src/aiwiki schema/protocols --glob '!**/general/**' | head
```

Expect: no multi-protocol schema dirs; no learn/set commands; verify all green.

---

## Execution notes

- Zero alias: do not map `investing` → `general` at CLI for success; command absent or error. State file coerce is migration only.
- Preserve `DEFAULT_PROTOCOL = "general"` string unless renaming to `default` is trivial; prefer keep `general` slug to limit churn.
- Dogfood vault schema dirs not deleted by this plan (local vault); runtime ignores non-general after coerce.
