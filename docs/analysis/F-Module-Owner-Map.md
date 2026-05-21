# F — 模块 Owner 映射

> 合并 AGOS-005 seam map 与 runtime 模块归属。**勿向 facade 文件新增逻辑。**

## Owner 子包（在此编写）

| 包 | 职责 |
|----|------|
| `compile/` | 确定性编译流水线 |
| `content/` | Source/concept IO 与记录 |
| `execution/` | Receipts、review、L3、alchemy 执行 |
| `memory/` | Machine memory 图、execution surfaces |
| `runner/` | LLM 工作流、prompt、自动化 |
| `planner/` | Planner log、dry-run、schema |
| `signals/` | 信号采集与适配器 |
| `protocol/` | 静态协议库 |
| `render/` | HTML/packs/paths |
| `cli/` | 解析与分发 |

## Facade（仅兼容）

| 模块 | 状态 |
|------|------|
| `app.py` | 对外 shim — 不可删除 |
| `app_content.py` | Re-export — import 迁移至 `content.*` |
| `app_memory_surfaces.py` | Re-export — 测试 patch seam |
| `app_compile.py` | Re-export compile 符号 |
| `runner/workflows.py` | 薄编排；本地统计 → `runner/local_stats.py` |

## Hub 文件（仅 targeted slim）

| 文件 | LOC | 下一 seam |
|------|-----|-----------|
| `runner/workflows.py` | ~1246 | compile/lint/nightly；ask → `workflows_ask.py` |
| `runner/alchemy.py` | 2589 | 延后（高风险） |
| `app_protocol.py` | ~1750 | library 已抽出 |
| `app_lifecycle.py` | 1835 | lifecycle → execution/* |
| `memory/execution_surfaces.py` | ~1280 | 更多 helper |

## 新模块（Post-AGOS）

- `runner/local_stats.py` — 本地确定性 ask intent
- `runner/workflows_ask.py` — run-ask / background / direct ask
- `runner/workflow_shared.py` — shared receipt/raw-response helpers
- `protocol/library.py` — PROTOCOL_LIBRARY
- `llm_telemetry.py` — LLM + execution receipt 聚合
- `memory/execution_surface_helpers.py` — 渲染行构建器

## Product Shell

- 源码：`.obsidian/plugins/furnace-product-shell/src/`
- Drift gate：`scripts/check_product_shell_bundle.sh`
- Feed 契约：`schema/today-feed.json`
