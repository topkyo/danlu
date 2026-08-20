# OSS 公共契约求真（B 层）

**Date:** 2026-08-13  
**Status:** Approved  
**Owner:** CLI / Active docs / Product Shell copy  
**Evidence:** 四路只读扫描（public contract / dual names / dead-looking-live / private residue）

## Goal

陌生人 clone 之后，**文档说的、开关名叫的、UI 暗示的，必须和代码实际做的是同一件事**。看起来还活、其实已死的入口，比缺功能更糟。

本规格只修这一类谎言。不把「删未用模块」「补开源三件套」「去维护者本机路径」捆进同一 diff。

## First principles（后面做 vs 一起做）

一起做**不是**更彻底的第一性原理。第一性原理是「公开含义为真」，不是「一天删光所有未用代码」。不同性质的工作分开验、分开审。

| 项 | 本轮 | 原因 |
|---|---|---|
| 文档/开关/命令撒谎 | **做** | 贡献者按文档操作会失败或以为开了 LLM |
| 死功能用户文案（apply / rewrite / 可执行） | **做** | 产品面仍在教一条已删的 apply 路 |
| `rewrite_state.js` 整文件 | **下一刀** | 读源码会以为 rewrite apply 还在；删除会炸 Jest + `main.js`，是子系统拆除不是改假话 |
| `repair-plan` 引擎 / `apply_ready` JSON | **下一刀** | compile 仍产出「可 apply」结构，比文案深；需单独决定 diagnostic-only vs 删除 |
| `alchemy-start` action id | **永不做** | Obsidian 产品契约，CLI 已拒绝平铺别名；改 id 是 churn 不是求真 |
| `AGENTS.md` 本机 / iCloud 路径 | **开源发布前** | 对维护者是真的，当作通用贡献者协议则是假的；与「命令撒谎」不是一类 |
| `CONTRIBUTING` / `SECURITY` / `.env.example` | **开源发布前** | 缺文件是不完整，不是撒谎 |
| `docs/archive/**` 改写成现行产品 | **永不做** | 史料必须保持当时日期；抹平历史反第一性原理 |

## Constraints

- 不改产品 CLI argv 形状：仍是 `drop` / `today` / `advanced`；`drop markdown` 不变。
- 不删 `rewrite_state.js`；不拆 `execution/repair_plan.py`；不改 `alchemy-start` / `file-back-judgment` action id。
- 不改 archive；不改历史 plan 的已勾选叙述（只改 Active SoT + CHANGELOG Unreleased）。
- 改 Product Shell JS 文案后必须 `bash .obsidian/plugins/furnace-product-shell/build.sh`。
- `mm_actions` **不**加兼容别名（一个桶一个名字）。`command_hint` 变更会漂 acceptance stdout fixture，必须同步刷新。
- `drop note` **不**做成工作别名；失败要响、错误要指向 `drop markdown`。
- ingest JSON 里的 `material: note` / `kind: note` 是原料类型，不是 CLI 子命令，保持不动。

## Design

### Architecture

公开契约只有一层：

```
用户/贡献者看到的名字
  = argparse 子命令 / 真实 env 读取 / 仍存在的写入入口
```

内部函数名（`drop_note()`）、插件 action id（`alchemy-start`）、compile 诊断 JSON（`apply_ready`）可以暂时落后，只要**不出现在用户该敲的命令和 Active 文档里**。

### Components

| 面 | 谎言 | 改为 |
|---|---|---|
| `AIWIKI_L3_AUTO_ADOPT_MIN_EVIDENCE` | CHANGELOG / 旧 plan 写「仍生效」；全仓库零调用 | 删除 `config.py` 常量与 `l3_auto_adopt_min_evidence_from_env`；Unreleased 改为「已删除死开关」 |
| `AIWIKI_DISABLE_AUTOMATION` | Runtime Ops + `autonomy_policy` docstring 写「停所有自动化」 | 只阻断 LLM client（`disable_external_llm`）；watcher/nightly 不停。文档与 docstring 写清。停服务仍用 `systemctl`/`launchctl` |
| `AIWIKI_AUTONOMY_PROFILE` | Runtime Ops 写影响 nightly receipt 记账；`runner/` 不读 | 文档改为「写入 policy 文件的 profile 字段，无行为分叉」；installer 可继续写，不删 env |
| `AIWIKI_LLM_BACKEND` | Architecture / AGENTS 写「必须显式设置」；`config.py` 默认 `deepseek-api` | Active 文档：可省略，默认 `deepseek-api`；其他 backend 必须显式；无 cross-backend fallback |
| INSTALL | 「systemd/launchd 安装脚本均以此为准」 | Shell/CLI/`llm-check` 默认路由以此为准；installer **不写** backend，沿用 runtime 默认 |
| Runtime Ops 示例 | `AIWIKI_VAULT=$AIWIKI_DOGFOOD_VAULT` | `AIWIKI_VAULT=/path/to/vault` |
| Runtime Ops §9 | 自主权红线指向 Architecture **§8**（实为已删 AgentOS 面） | 指向 §4 不变量；说明 `DISABLE_AUTOMATION` 只停 LLM |
| Runtime Ops retention | planner-log 像仍有 operator 面 | 注「只读历史 artifact，无 CLI（Architecture §8）」 |
| USER_GUIDE | `file-back --kind judgment` | 删除 `--kind`；只写 `advanced file-back <path>` |
| CHANGELOG Unreleased | 同节既写默认 flash 又写「模型不变 pro」；L3 env 仍生效 | 与 `config.py` SoT 对齐 |
| `drop note` | `_DROP_TYPED_SUBCOMMANDS` 含 `note`，像有子命令 | 从集合去掉；`drop note` 显式退出：用 `drop markdown` |
| `--bucket mm_actions` | help / `command_hint` / machine-memory 索引教这个名；真实桶是 `machine_memory_actions` | 用户可见字符串全部改成真名；acceptance stdout 同步 |
| README / vault HOME | 管线词 `ask` / `compile` / `nightly` 像顶层命令 | 管线 shorthand 加注，或写 `advanced run-ask` / `advanced compile` / `advanced run-nightly` |
| `llm-check_render.py` | docstring ``aiwiki llm-check`` | ``aiwiki advanced llm-check`` |
| 炉心 | 「先处理 N 个低风险 machine-memory 动作」 | 删这条 next-step；review-queue 仍可查看 |
| repair-backlog 文案 | 「按动作队列处理 / 先执行已接受动作」；「概念重写优先级」 | 改为查看/分流；删除「概念重写优先级」渲染段（内部 `rewrite_candidates` 数据可留） |
| 协议 nightly | 「关注 … concept rewrite」 | 「weak concepts / concept quality」；`schema/protocols/general/nightly.md` 与 `protocol/library.py` 同步；`test_repair.py` 断言同步 |
| vault 树标签 | `wiki/rewrite-proposals` 标成「改写提案」正式层 | 从 `VAULT_TREE` 标签移除；ignore/hide 可留（藏历史目录） |
| Shell 单写者警告 | 把 `apply / revert` 与 compile/nightly 并列 | 改为仍有入口的写入：compile / nightly / alchemy / file-back |

### Data flow

不变：compile 仍可写空 `concept_rewrite.proposals`、仍可生成 repair-plan JSON。Shell `rewrite_state.js` 继续 normalize 空列表。用户从炉心/repair 文案/协议/CLI help **走不到** apply。

变：用户按 README/USER_GUIDE/Runtime Ops/help 敲的命令，要么存在，要么明确报「请用 X」。

### Error handling

| 情况 | 行为 |
|---|---|
| `aiwiki drop note …` | stderr 说明不是命令，指向 `drop markdown`；exit 2。不把 `note` 当万能 payload 送进 planner |
| `advanced review-queue --bucket mm_actions` | 空桶（无别名）。help 只举 `machine_memory_actions` |
| `AIWIKI_DISABLE_AUTOMATION=1` | 显式 LLM 入口失败；watch/nightly 照常 |

### Testing

- `PYTHONPATH=src python3 -m pytest tests/test_cli_surfaces.py tests/test_library_surfaces.py tests/test_repair.py tests/test_vault_plugin.py -q`
- 若 `command_hint` 变更：刷新 `tests/fixtures/acceptance/**/expected/stdout/*run-ask*.json` 中的 `mm_actions` 字符串；必要时 `bash scripts/verify.sh acceptance`
- JS 文案：`cd .obsidian/plugins/furnace-product-shell && npm test`（或 `verify.sh product-shell-static`）
- 收口：`bash scripts/verify.sh all`；计数钉不变则不动 AGENTS/Scorecard

## Out of scope

- 删除 `rewrite_state.js` / 改 Jest rewrite fixtures
- 删除或重命名 `repair_plan.py`、`can_apply` JSON 字段、`safe_apply_preview`
- 重命名 `drop_note()` / JS `buildDropNoteCommandSpec`
- 去 AGENTS.md / sync 脚本 / Runtime Ops systemd 示例中的 `/Users/ht`（发布切片）
- 新增 CONTRIBUTING / SECURITY / CODE_OF_CONDUCT
- 改写 `docs/archive/**`
- 给 `docs_consistency_check.sh` 加 `/Users/ht` 门禁（属发布切片）

## Open questions

(none)
