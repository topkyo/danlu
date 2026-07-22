# Less-is-More 推荐收口包

> **For agentic workers:** Load `executing-plans`.

**Goal:** 完成复评剩余里**真对 Less** 的几项：僵尸 Shell 面、SoT 单枚举、PROGRESS 瘦身、alchemy 轻归组。  
**Out:** hub LOC 大拆、`app_*` 目录 rename、全量 advanced 21 叶重排。

**Source:** 用户批准的「推荐收口包」（P1-6 + P2-9 + P2-10 + P1-4 缩小版）

---

## Task 1: Shell 僵尸 i18n + render_runs 出默认 bundle

**Depends on:** none  
**Files:** Product Shell `build.sh` / bundle order, `constants.js` or i18n, `render_runs.js` importers, Jest

- [ ] 确认 `render_runs.js` 是否仍被默认 Furnace Center 路径引用；若仅死面，移出默认 `build.sh` 拼接（或删未用 export）
- [ ] 清理明显已退役 Review/Execution 中心的 i18n 死键（只删确认无引用的）
- [ ] rebuild `main.js`；`bash scripts/verify.sh product-shell-static`
- [ ] Commit: `chore: Shell 去掉 runs 死面与僵尸 i18n`

## Task 2: SoT 枚举并成一处

**Depends on:** none  
**Files:** `docs/README.md`, `docs/AGOS-9-Scorecard.md` Active SoT 段, `AGENTS.md` Source of Truth（轻触）

- [x] 以 `docs/README.md` Active 表为**唯一枚举**；Scorecard / AGENTS 改为指针 + 「engineering 子集」一句，删重复长列表或对齐同一份
- [x] 把已完成 Ask/Less plans 标 Delivered 或链到 archive 复评
- [x] `docs_consistency_check.sh` PASS
- [x] Commit: `docs: SoT Active 枚举收敛到 docs/README`

## Task 3: PROGRESS 砍 Round 长尾

**Depends on:** none  
**Files:** `PROGRESS.md`

- [ ] 保留：SoT 引用 + 当前动态（近几条）+ 改进方向段
- [ ] Round-by-round 超长历史：移到 `docs/archive/rounds/` 新快照文件，或折叠为「详见 archive」指针（不丢 git 历史）
- [ ] Commit: `docs: PROGRESS 瘦身为 head + 改进方向`

## Task 4: alchemy CLI 轻归组（P1-4 缩小版）

**Depends on:** none  
**Files:** `cli/parsers.py`, `cli/dispatch.py`, 文档/help 若提及

- [ ] 在 `advanced` 下增加 `alchemy` 父命令，子命令 start/distill/finalize/promote/revert/demote
- [ ] **保留**旧 `alchemy-start` 等为 compat alias（argv rewrite 或双注册），避免砸脚本
- [ ] help 默认展示新树；verify python-static + acceptance（若有 alchemy fixture）
- [ ] Commit: `feat: advanced alchemy 子树（保留旧命令 compat）`

## Task 5: 收口

- [ ] 更新 `docs/plans/2026-07-22-less-is-more-cuts.md` Deferred 注明收口包已做
- [ ] PROGRESS 记一笔；vault 同步 `main.js`（若 Shell 有改）
- [ ] `bash scripts/verify.sh all`
