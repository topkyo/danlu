# Ask 联网调研 + 默认 flash

**Date:** 2026-08-12  
**Status:** Approved  
**Owner:** runtime ask + LLM client + Product Shell settings  
**Supersedes framing in:** `docs/plans/2026-08-12-dogfood-operations-analysis.md` §2 / §6（「只能答喂过的」不再是产品终局；该报告 P0 信任缺陷仍并入本规格）

## Goal

炼丹炉 Ask 在保留 local-first、fail-closed、可审计的前提下，**可以联网调研后回答**：不再因 vault 无原料就只能生硬拒答。默认模型改为 `deepseek-v4-flash`（支持 DeepSeek Responses `web_search`）；`deepseek-v4-pro` 仅用户手动选择。网页证据默认只服务本次报告，不自动写入 `raw/`；拒答不得再被盖成 `deliverable` 或 file-back 进 judgment。

## Decisions（已锁定）

1. **空炉可答**：本地证据不足时通过联网调研直接回答，而不是只引导去 `drop`。
2. **联网优先提供商能力**：`deepseek-api` + 支持 `web_search` 的模型走 DeepSeek Responses API 服务端搜索。
3. **默认模型**：产品默认 `deepseek-v4-flash`；`deepseek-v4-pro` 仅 Shell/设置手动选。
4. **触发**：每次 `run-ask` 都允许模型自行决定是否调用 `web_search`（本地有料也可补网）。
5. **沉淀**：联网材料默认不写 `raw/`；报告 + receipt 保留 URL/摘要；答后提供可选「沉淀」入口（显式 `drop url`）。
6. **信任 P0 并入**：无证据/拒答 → `artifact_quality: no-evidence`；`file-back` 拒绝非 `deliverable`；Today/recent_outputs 区分展示。

## Constraints

- 技术栈保持 stdlib-first；HTTP 客户端沿用现有 urllib/`safe_fetch` 模式，不引入新重依赖。
- 不自动跨 backend fallback；不写 deterministic 占位成功答案。
- fail-closed：没有 vault 路径或可审计 web URL 证据时，不得把综合结论写成事实。
- `web_search` 仅在 **backend=deepseek-api 且模型声明支持** 时启用（V1：`deepseek-v4-flash`）。用户手选 `deepseek-v4-pro` 时 **不** 启用提供商 `web_search`（官方尚未支持），Ask 退回 vault-only；若无证据则诚实 `no-evidence` + 可操作引导（含切换 flash / 投喂）。
- 联网是 Ask/LLM 显式路径的一部分；隐私文档须声明「Ask 可能触发提供商侧 web_search」。
- 不把本轮做成通用搜索引擎产品；不做独立 research CLI；不自动 file-back 网页。

## Design

### Architecture

```
用户提问 (Shell/CLI run-ask)
  → 本地 rank（sources / concepts / judgments）照旧
  → LLM 调用：
       flash + deepseek-api → Responses API + tools:[web_search]，tool_choice=auto
       其他（pro / 非 deepseek-api）→ 现有 chat/completions，无 web_search
  → 模型可调用 web_search；结果由服务端回注，写入报告正文与引用
  → 盖章：有可引用证据（vault 或 web URL）→ deliverable；否则 no-evidence
  → 可选：报告/Shell 提供「沉淀这些网页」→ 用户确认后 drop url（另一步，不默认执行）
```

不变：五层分层、single writer、citations fail-closed、无隐式 backend fallback。  
变：默认模型；Ask 可带提供商联网；拒答语义与 file-back 门禁。

### Components

| 组件 | 职责 |
|---|---|
| `config.py` + Shell `llm_settings.js` / `constants.js` / vault 模板 | 默认模型 → `deepseek-v4-flash`；文档与测试钉住；pro 仍可选 |
| `llm.py` | 新增 DeepSeek Responses 路径（或等价 client）：支持 `tools`/`web_search`；解析 `message` + `web_search_call`；receipt 记录搜索摘要（query、URL 列表、response id） |
| `runner` ask 工作流 / `execution/ask.py` | flash+deepseek 时走 Responses；把 vault 上下文与「允许搜网」写入 prompt；回写 `used_web_refs`（或扩展 `used_refs`） |
| `schema/citations.md` + ask prompt | 允许引用：`wiki/sources|judgments|...` **或** 带完整 URL 的网页来源；无二者则不得写事实 |
| `workflows_ask_status.py` | 完成盖章：检测无证据/拒答信号 → `artifact_quality: no-evidence`（非 deliverable） |
| `execution/file_back.py`（及 CLI/Shell 入口） | `artifact_quality != deliverable` → 拒绝回流（明确错误） |
| Product Shell | 设置里模型可选 flash（默认）/ pro；报告完成若有 web refs，展示「沉淀」CTA（文案 + 触发 drop url；V1 可用 Notice/命令，不必大改 UI） |
| 文档 | Runtime Ops / DEVELOPER / AGENTS / USER_GUIDE / PRIVACY / CHANGELOG：默认 flash、Ask 可联网、沉淀可选 |

### Data flow

1. Shell/CLI 发起 `advanced run-ask`（同步，行为不变）。
2. Runtime 组装 vault 召回上下文（现有 ranking / compound）。
3. 若 `backend==deepseek-api` 且 `model` 支持 web_search：  
   - `POST /responses`（DeepSeek Responses），`tools: [{type: web_search}]`，`tool_choice: auto`；  
   - system/user prompt 说明：优先用 vault；不足或需要时效信息时可搜网；引用必须给出 vault 路径或 URL。
4. 否则：现有 `/chat/completions`，无 tools。
5. 校验契约（frontmatter/结构）后写报告；frontmatter 增加：  
   - `artifact_quality`: `deliverable` \| `no-evidence`  
   - `web_search_used`: bool  
   - `used_web_refs`: URL 列表（可空）  
   - 保留既有 `used_refs`（vault）
6. llm-receipt 追加：backend/model、是否 Responses、`web_search_call` 摘要（不含把整页 HTML 永久写入 vault）。
7. Today / shell-summary：`deliverable` 与 `no-evidence` 分桶或分标记，避免拒答进「成功产出」。
8. 用户可选沉淀：对 `used_web_refs` 逐条或批量 `drop url`（显式），再 compile；**不**在 ask 成功路径自动 drop。

### Error handling

| 情况 | 行为 |
|---|---|
| Responses / web_search HTTP 失败 | 记 receipt；若仍有 vault 证据可仅用 vault 完成；若无 vault 证据 → 失败或 `no-evidence` 报告（不编造），不标 deliverable |
| 模型返回拒答话术且无 vault/web 引用 | `artifact_quality: no-evidence`；正文给覆盖范围 + 建议（投喂 / 确认模型为 flash） |
| 用户手选 pro 且零召回 | vault-only；`no-evidence` + 说明 pro 无提供商联网，可改 flash 或 drop |
| file-back 非 deliverable | 硬拒绝，退出码非 0，错误信息可操作 |
| 契约校验失败 | 现有 `validation_failed` / degraded 路径，不变 |

### Testing

- **单元**：Responses payload 构造；`web_search_call` → `used_web_refs` 解析；盖章：有/无证据；file-back 门禁。
- **llm-integration / acceptance**：fixture 模拟 Responses（含/不含 web_search）；零召回 + 搜网成功 → deliverable + URL refs；零召回 + 无搜网 → no-evidence 且不进 file-back。
- **Product Shell Jest**：默认模型常量 = flash；provider default 集合含 flash；设置项仍可选 pro。
- **文档一致性**：`docs_consistency_check` 钉默认 `deepseek-v4-flash`（替换原 pro 产品默认叙述）。
- 验证入口：`bash scripts/verify.sh` 按改动跑 `python-static` / `unit` / `llm-integration` / `product-shell-static` / 必要时 `all`。

## Success criteria

1. 新产品默认（无显式 model 覆盖）为 `deepseek-api` + `deepseek-v4-flash`。
2. 在 flash + deepseek-api 下，对「今天 A股行情」类无 vault 证据问题：可产出带 URL 引用的调研回答，或明确的 `no-evidence`（搜网失败时），**不得**再出现「成功 deliverable 的拒答」。
3. `no-evidence` 报告不能被 file-back 进 judgment。
4. 联网材料默认不出现在 `raw/`；仅用户显式沉淀后才有。
5. PRIVACY / USER_GUIDE 写明 Ask 可能触发提供商 web_search。
6. `bash scripts/verify.sh` 相关 target 全绿。

## Out of scope

- watcher 停滞、治理队列空转、alchemy 双注册、默认值单源生成脚本、vault 目录按需创建（分析报告 P1/P2，另立项）。
- 独立 Search API / 本机 `safe_fetch` 调研降级作为 V1 主路径（pro 无 web_search 时不做自动 URL 抓取循环；仅诚实 no-evidence）。
- 自动把网页写入 raw/wiki；自动 file-back。
- 非 deepseek-api backend 的提供商联网（OpenAI/Anthropic/OpenCode browsing）— 后续可加，本规格不承诺。
- iPad/iOS；hosted 服务。

## Migration / dogfood

- 改 Python/JS/模板默认常量；测试与 SoT 文档同步。
- 已有 vault `data.json` 若显式写着 `deepseek-v4-pro`：保留用户显式选择（不静默改写）。若字段为空或等于「提供商默认模型」集合中的旧默认，解析时落到新默认 flash（沿用现有 Shell profile-default 归一逻辑，把 flash 设为 deepseek 的 `defaultModel`）。
- dogfood 验证：sync Product Shell 后，用 flash 问一条时效性问题，检查报告 refs + receipt；再确认拒答/失败路径不进 deliverable/file-back。

## Open questions

（无 — 已在对话锁定）

## Design narrative（一次性写全，供实现对照）

### §2 组件与接口（摘要）

- LLM 抽象：保留 `complete(system, user) -> CompletionResult` 给非 Responses 路径；Responses 路径可扩展为返回 `CompletionResult` + 可选 `web_meta`（refs、search calls），或在 ask 层专用函数，避免污染 Anthropic/OpenAI 客户端。
- 引用：报告正文应出现可点击/可复制的 URL；frontmatter `used_web_refs` 为机器列表。
- 沉淀 CTA：报告末固定小节「可选沉淀」列出 URL；Shell 可用 Notice「复制 drop 命令」或后续一键；V1 不要求完整批量 UI。

### §3 与分析报告 P0 的关系

| 分析项 | 本规格 |
|---|---|
| A 拒答盖 deliverable | 修：无证据 → `no-evidence` |
| B file-back 污染 | 修：非 deliverable 拒绝 |
| C 零召回无早停 | **不**再早停拒答；改为允许 web_search。零召回 + 无 web 支持/失败 → `no-evidence` 引导 |
| D–L watcher/复杂度等 | 不在本规格 |

### §4 非目标再强调

炼丹炉仍是「投喂 → 沉淀 → 复利」+ **按需联网调研**；不是永远在线的通用聊天机器人。联网结果要进复利，必须经过用户显式沉淀。
