# Report Provenance Scrub + Explicit GC（KISS）

**Date:** 2026-07-20  
**Status:** Implemented 2026-07-21（compile scrub + `gc-orphans` + ①′；dogfood 清炉已跑）

## Goal（只做三件事）

1. **Compile scrub**：剥离已不存在的 `output/reports/...` 引用；页标 `provenance_status`: `ok` | `degraded` | `broken`。  
2. **一个显式 GC 命令**：dry-run 默认；`--apply` + receipt；清 broken file-backs，以及可选的噪音概念 / 误投。  
3. **①′ 展示收口**：停写机器记忆 HTML；用户文案用「证据链」，不把图谱当主路径。

不做第四件「卫生平台」、不做双 CLI、不做 health 产品面翻新。

## Non-goals（刻意砍掉）

| 曾写入、现移出本 spec | 理由 |
|----------------------|------|
| 独立 `gc-graph-hygiene` + 大量 flag | 与 report GC 合并；dogfood 清炉一次跑完 |
| 恢复/精修 `graph-health.md` 遥测页（原 Slice D） | W5 已停写；本轮只把 **计数写入 `shell-summary.json`**（或 graph JSON 旁路字段），不复活 markdown SoT 争论 |
| Shell Today 提示文案 / 路径标签大改（原 Naming 主交付） | 只改 `graph-view.md` 模板一句；Shell 标签另题或顺手一行 |
| Slice E「标 legacy repair 提案」代码注释运动 | 文档一句即可；不改 repair 代码 |
| 噪音启发式三套（词表 + 短 slug + watch 列表） | **仅**：词表命中 ∪ health 已标 singleton；白名单保护 hub |
| `--list-orphan-sources` / `--slugs` / `--source-ids` 完整运维面 | 误投用指纹；其余 `rm` 即可 |
| 度量门禁框架、方案③④长文 | 留在决策记录一段，不进实现清单 |

## Strategic note（一段够用）

- **采用 ①′**：保留 `machine-memory-graph.json`（ask/compile）；**停写** `machine-memory.html`；人读靠 Obsidian 证据链。  
- **禁止**默认删报告级联删 wiki。  
- 图谱 viz **不打磨**；本轮只修「删报告后撒谎」+ dogfood 可清噪音/误投。

## Design

### Compile scrub

- 扫：`wiki/judgments/`、`wiki/derived/`、`wiki/elixirs/`。  
- 字段：`source_files`、`derived_from`（有则处理）；`citations` 仅当元素是 `output/reports/` 路径字符串时剥离。  
- 分类：剥离后仍有现存锚点 → `degraded`；否则 → `broken`；无死 report 引用 → `ok`。  
- 副作用：`shell-summary.json` 增加 `provenance_degraded` / `provenance_broken` 计数（整数即可）。  
- **不**为 scrub 单独写/恢复 `graph-health.md`。

### CLI（合并为一个）

```
aiwiki advanced gc-orphans
  [--dry-run | --apply]           # 默认 --dry-run
  [--judgments] [--derived] [--elixirs]   # file-back 类；至少一个或下面的概念/误投
  [--force-degraded]              # 默认只删 broken；清炉时打开
  [--noise-concepts]              # 词表∪singleton，且非白名单
  [--misdrops]                    # 指纹匹配的 raw + wiki/sources
  [--force]                       # misdrop 仍被 judgment 引用时仍删 source
```

**默认候选**

- judgments/derived/elixirs：`broken`；`--force-degraded` 时含 `degraded`。  
- elixir：仅自身 broken，或锚点已不存在 / 指向本次将删页。  
- noise：slug ∈ `{because,aio,api,brain,autonomous,environment,history-ethos-garden}` **或** 图健康 singleton；且 ∉ `{llm,knowledge,memory,obsidian,agent,judgment,evidence,concept}`。  
- misdrops：路径/url/title 含 `vphone-aio` 或 `34306/vphone`。

`--apply`：删文件 + receipt；不隐式 compile。

### ①′ HTML

- compile **停写** `output/graph/machine-memory.html`（或写 10 行占位指向 JSON）。  
- `graph-view.md` 模板：改称证据链 / 机器记忆邻接；写明 HTML 非主路径。  
- 不改 ask；不恢复 Shell open-graph。

### Dogfood 清炉（实现后）

```
compile
gc-orphans --judgments --derived --elixirs --force-degraded --noise-concepts --misdrops --dry-run
gc-orphans … --apply
compile
```

孤立 PARA 等：人工 `rm`，不进 CLI。

## Testing

1. judgment 仅死 report → compile → `broken` + shell-summary 计数。  
2. 死 report + 现存 source → `degraded`。  
3. GC 默认不删 degraded；`--force-degraded` 删。  
4. `--noise-concepts` 列 `because` 不列 `llm`；`--misdrops` 列 vphone。  
5. compile 后无增强 HTML 产物依赖（acceptance 不打开 HTML）。

## Success

- 删报告后 FM 不残留死 `output/reports` 路径。  
- 一个命令能完成 dogfood 清炉（judgment/derived/elixir + 噪音 + vphone）。  
- HTML 不再作为交付物增强；JSON 图仍在。  
- 无新 Shell GC/图谱 UI。

## Deferred（真要再做再开 spec）

- Shell 文案/标签、orphan 列表 UX、薄 graph-health.md、repair legacy 标注、概念 harden、typed 边。
