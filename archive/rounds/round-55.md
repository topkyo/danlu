# Round 55 — D-4 Investing Dogfood Plan (Contract-Only)

status: 完成
commit: 

Round 55 — D-4 Investing Dogfood Plan (Contract-Only) — 完成
- **目的**: 把 D-1 方向文档识别的"投资协议端到端 dogfood 从未跑通"gap 物化为可执行 contract；本 session 不实跑，为外部 LLM backend ready 后的端到端 dogfood 提供可验收 SoT
- **方向 SoT**: `docs/Furnace Next Direction Post-P4.md` §D-4
- **新增文档**: `docs/Furnace Investing Dogfood Plan.md`（contract-only）
- **覆盖**: 7 步 flow（准备 / 投料 / compile / judgment / distill / compounding / L3 proposal）+ 19 条 F-INV-* 摩擦点 + 验收标准 + Stop Lines + 摩擦报告模板
- **状态**: `pending(blocked-on-llm)`；执行依赖外部 LLM backend ready
- **Stop Lines**: 0 src 改动；不引入新 schema；不在 contract 中放松 review/apply/revert 边界；不预设投资建议生成
- **下一步**: 本 session 范围 D 系列已收口；后续按 backend availability 触发 D-4 实跑
