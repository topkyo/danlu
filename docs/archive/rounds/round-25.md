# Round 25 — M-UX.4 Advanced 与运行状态文案收敛

status: 完成
commit:

Round 25 / M-UX.4 Advanced 与运行状态文案收敛 — 完成
- Product Shell Advanced 抽屉中文标题由“高级”改为“更多工具”，摘要改为“待审 / 待执行 / 运行记录”，降低工程入口感。
- 运行状态面板中文文案从 `single writer / command / compile-nightly-apply-revert` 口吻改为用户任务状态：当前无任务、已有写入任务运行、等结束后再开始新的写入任务。
- LLM 与 metrics 文案产品化：`LLM 后端` 改为 `LLM 服务`，`LLM 健康态` 改为 `LLM 状态`，`deterministic 回退` 改为 `本地兜底`，Advanced metrics 补齐“知识复利指标”等中文翻译，并隐藏 `aiwiki metrics --json` 的直读提示。
- Verification：Product Shell focused tests pass；`bash scripts/verify.sh` pass（1505 unit + 13 acceptance，coverage 92%）。
- QA review：fresh-session reviewer 仍被 Codex usage limit 阻塞；已记录 same-context fallback，无发现。
