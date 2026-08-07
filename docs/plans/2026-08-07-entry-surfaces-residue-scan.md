---
title: "Entry Surfaces Residue Scan 2026-08-07"
kind: "report"
status: "executed"
created_at: "2026-08-07"
---

# 入口面清理后 · 同类残留全量扫描

> **性质**：4 路只读扫描交叉裁决。对照 `docs/plans/2026-08-06-entry-surfaces-cleanup.md` 已落地范围，找「还有没有同类没清干净」。  
> **HEAD**：入口面清理已合入 main。  
> **原始报告**：`tmp/scan-{writers,links,docs-cli,shell-dead}.md`

## 结论先行

**主体已闭合**：Live 14 索引页 writer 链路完整；退役页无复活；compile / Shell Outputs Hub / Active 主文档（README/HOME/Runtime Ops/Evolution/Architecture/USER_GUIDE）无现役坏入口；dogfood `wiki/indexes/` 15 页均为在生/策略页，HOME/README 与模板一致。

**仍未清干净的，集中在四类「漏网」**——不是又一批无 writer 索引页，而是：

1. **Obsidian workspace 用户状态**未随模板同步（repo + dogfood）  
2. **少量 Active/商业文档**死链与裸 CLI 名  
3. **Shell thin-summary 契约半截**（构造了但不落盘 / JS 读不到）  
4. **代码侧兼容 seam**（零调用 path helper、no-op log、纯 façade）——与入口面同型死代码

---

## 已确认干净

| 面 | 状态 |
|---|---|
| Live 14 页 writer | compile 12 + nightly repair-backlog；managed review-center/graph-view |
| git `wiki/indexes/` | 仅策略 `README.md`；无退役页文件 |
| dogfood indexes | 无退役页文件；HOME/README 与模板逐字一致 |
| furnace_center / Shell Outputs Hub | 三节首屏；fallback furnace-center |
| `DEFAULT_DASHBOARD_FILES` / nightly / meta 路径列表 | 无退役页 |
| CLI 顶层文档 | 仅 drop/today/advanced（主 Active 文档） |
| docs_consistency | 53× OK（主链 25/84/176/204） |

---

## 交叉债清单（按优先级）

### P0 — 用户/开发者会直接碰到

| ID | 项 | 证据 | 建议 |
|---|---|---|---|
| W-1 | repo `.obsidian/workspace.json` 仍含 `Outputs.md`、`execution-center.md` | 三路扫描一致；`vault/templates.py` 新模板已对齐 | 删 lastOpenFiles 死项；加「repo workspace ≠ 仅测模板」断言 |
| W-2 | dogfood workspace 仍含 `Outputs.md`、`output-packs.md`、`domain-pilots.md` | shell-dead vault 实证 | 清 dogfood `lastOpenFiles` |
| D-1 | `docs/Furnace Elixir.md` → 不存在的 `docs/Outputs.md`；金丹裸 `alchemy-*`；nightly aging 旧叙事 | docs-cli + links | 改 related_docs；CLI 加 `advanced`；改 aging 口径 |
| D-2 | `PROGRESS.md` 头条 Jest **203** / 一条 llm **85** | docs-cli | 改 **204** / **84** |
| S-1 | `curated_page_roots`：meta 构造、JS 依赖，但 thin persist **不落盘** | shell-dead | 要么纳入 thin schema + 契约测，要么删 JS reader（禁半截） |

### P1 — 同型死代码 / SoT 漂移

| ID | 项 | 建议 |
|---|---|---|
| C-1 | `render/paths.py` 9 个零调用 helper（pack/memo/sop/receipt…） | 整簇删除 |
| C-2 | `append_wiki_log` no-op 仍被 15 处调用；`ensure_wiki_log` 指向退役 log.md | 删调用链后删函数 |
| C-3 | `runner/__init__.py` 零调用 re-export façade | 清空为包 init |
| C-4 | `content/rewrite.py`、`execution_surfaces` re-export | 调用方直引 owner 后删 |
| C-5 | `shell_links` / `shell_capabilities.views` 整簇构造后被 thin 丢弃 | 收窄到真实 consumer |
| C-6 | `schema/review.md` 仍提 `aging-report.md` | 与 protocol template 对齐 |
| C-7 | Post-Cleanup §8 / D5/D14 Jest 203；CHANGELOG Removed「现行见 24/85/203」 | 改 204 / 标 historical |
| C-8 | commercial BOUNDARIES/PRICING、INSTALL 多处裸 operator 名 | 统一 `advanced …` |
| C-9 | compile 侧 output-pack / domain-pilot **空状态** telemetry 簇 | 另开数据契约审计，勿与死页混删 |

### P2 — 卫生

| ID | 项 |
|---|---|
| P2-1 | `docs_consistency` regex 仍白名单 `execution-center`；可扩钉 PROGRESS/Post-Cleanup Jest |
| P2-2 | Shell i18n 未用键（Execution queue / Open outputs hub）；`apply-rewrite` 文案 |
| P2-3 | wiki/indexes/README `aiwiki compile` → `advanced compile` |
| P2-4 | plugin `src/README.md` apply/revert 措辞补「已删」 |

---

## 与入口面清理的关系

| 入口面已做 | 本轮漏网形态 |
|---|---|
| 无 writer 索引页连代码退役 | **无**第二批同类死索引页 |
| 修 Outputs.md 死链（渲染/Shell/模板） | **workspace 用户状态**未清 |
| Active 主文档叙事 | **Elixir / commercial / PROGRESS 计数**边角 |
| 删死渲染器 | **path helper / no-op log / façade / thin-summary 死键** 仍在 |

**一句话**：不是「还有一大批炉心同款脏面板」，而是「状态文件 + 边角文档 + Shell 契约半截 + 编译路径死符号」四类尾巴。

---

## 建议下一刀（若继续清）

1. **快刀（<1h）**：W-1/W-2 workspace、D-1 Elixir、D-2 PROGRESS、C-6 schema、C-7 计数、P2-1 regex。  
2. **契约刀**：S-1 `curated_page_roots` 二选一做干净。  
3. **代码刀（入口面同型）**：C-1–C-5 死 helper / no-op log / façade / shell 死键一轮做完，不留半迁移。  
4. **另案**：C-9 empty telemetry；不并入本刀。
