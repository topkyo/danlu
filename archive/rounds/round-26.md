# Round 26 — M-UX.5 Vault User View + Chinese Graph

status: 完成
commit: 

Round 26 — M-UX.5 Vault User View + Chinese Graph — 完成
- **目的**: 按真机截图继续从普通用户角度收敛 dogfood vault：左侧文件树不再把 `raw/wiki/schema/output` 运行时分层作为日常入口，`output/` 用户默认只看报告；关系图谱继续中文化
- **设计核心**:
  - `src/aiwiki/app_vault.py` 的 new-vault CSS snippet 增加用户视图隐藏规则：隐藏 `raw/wiki/schema/scripts/prompts`，以及 `output/` 下除 `reports/` 外的候选、控制面、图谱导出、审阅、packs、slides 等 operator folders
  - 可见文件树文案从 `输出 output` / `报告 reports` 收敛为 `报告` / `全部报告`，保留真实 runtime 路径不变
  - 当前 dogfood `/home/tim/danlu/炼丹炉/.obsidian/workspace.json` 改为主区 Product Shell + README，左右侧栏默认折叠，左侧只保留文件列表/书签，右侧只保留 Outline/Backlinks
  - dogfood `HOME.md` / `README.md` 改成“用户只关心报告；runtime 层默认隐藏但仍存在”的说明
  - `output/graph/machine-memory.html` 由 compile 重新生成，图谱 UI 从 `component/slug/wiki/rewrite` 口吻改为“关系组、关键词或来源编号、详情页、核心概念、核心来源、改写提案”等中文
- **验证**:
  - `python3 -m py_compile src/aiwiki/memory/graph.py src/aiwiki/app_vault.py`
  - focused unittest: `tests.test_vault tests.test_obsidian_workspace` + 3 个 machine-memory graph HTML tests，13/13
  - dogfood `source .envrc.dogfood && ./scripts/aiwiki-launcher.sh compile` exit 0，更新 `output/graph/machine-memory.html` 等 3 个 dirty artifacts
  - `bash scripts/verify.sh` exit 0；1505 unit + 13 acceptance；coverage 92%
- **QA gate**:
  - `qa-review`: fresh-session reviewer 仍受 Codex usage limit 阻塞；same-context fallback pass，无发现
  - `qa-runtime`: scripted pass；覆盖 focused checks、dogfood compile 与 full verify
- **当前评估**: 当前 dogfood vault 默认已经更接近“Product Shell + 报告”产品壳；runtime 分层仍可通过更多工具、链接或 CLI 到达，但不再占据普通用户文件树心智
