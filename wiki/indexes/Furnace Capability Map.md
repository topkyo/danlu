---
title: "炼丹炉能力地图"
kind: "roadmap"
status: "snapshot"
---

# 炼丹炉能力地图

这份文档现在主要回答一件事：

1. **截至 2026-04-13，炼丹炉当前已经做到了什么**

它不是终局愿景稿，也不是当前 active sprint contract。

它是：

- 当前能力分布图
- 当前成熟度判断
- 截至 `2026-04-13` 的能力快照

对应关系：

- 基线架构：[[wiki/indexes/Alchemy Furnace|炼丹炉架构]]
- 终局架构：[[wiki/indexes/Furnace Ultimate Architecture|炼丹炉最终极形态]]
- Product Shell 设计稿：[[wiki/indexes/Furnace Product Shell Plugin|炼丹炉 Product Shell Plugin]]
- 当前工程状态：[PROGRESS.md](<../../PROGRESS.md>)
- 当前这份：`现在做到哪了`

## 当前角色

- 这份文档保留为能力快照 / 参考文档
- 它不再承担“下一轮 contract”职责
- 当前 active work 不再由这份文档维护；以 `PROGRESS.md` 和 active contract 为准

## 一句话判断

截至 2026-04-13，炼丹炉已经是一个 **强内核 + 初代可用 Product Shell** 的系统。

- `aiwiki` runtime 已经完成 evidence plane、knowledge lifecycle、governance、execution 的主线闭环
- `aiwiki` runtime 已完成 `app.py` 模块化重构，形成 `protocol / content / memory / compile / utils / state` 的实现骨架
- Obsidian Product Shell 已经从“看板壳”推进到“带 judgment/governance 对象的原生工作台”
- 当前瓶颈已经不在 runtime 主链，而在 **更深的 object workflow、batch orchestration 与 action-specific context**

## 当前能力地图

### 1. Evidence Fabric

当前状态：**稳定**

已经具备：

- `raw/` 作为唯一事实输入层
- `drop-url / drop-pdf / drop-image / drop-repo`
- source page compile
- provenance / source-level back link
- archive apply / revert
- material state、active corpus、routing、archive candidate

这一层已经不是设计稿。它已经有显式运行态和归档/回滚闭环。

### 2. Knowledge Compiler

当前状态：**稳定**

已经具备：

- deterministic compile baseline
- LLM-backed compile / ask 可选执行
- `wiki/sources / wiki/indexes / wiki/derived`
- concepts synthesis
- machine-memory-aware query narrowing
- protocol-aware ranking / routing

这一层的关键价值已经不是“能不能编译”，而是“编译后如何进入后续治理和判断层”。

### 3. Judgment System

当前状态：**可运行**

已经具备：

- `wiki/decisions / wiki/judgments`
- review workflow
- `file-back`
- confidence / invalidation / revisit 语义
- protocol-aware review window
- `judgment-assets / cognitive-history`
- shell-facing judgment asset summary

这一层已经能承载长期判断资产，并把完整度 / 漂移 / 复审历史暴露给 governance 与 Product Shell；判断质量仍然依赖上游 evidence / concept 的精度。

### 4. Machine Memory

当前状态：**可运行**

已经具备：

- machine memory state
- graph / topology / retrieval narrowing
- runtime-aware query routes
- repair action proposal / review / apply / revert
- shell-summary / shell-status 前台摘要 contract

这里已经不只是内部缓存，而是明确为治理、execution 和 Product Shell 提供机读层。

### 5. Schema / Protocol Layer

当前状态：**稳定**

已经具备：

- `schema/`
- `schema/protocols/`
- `general / investing / research / product / ops`
- protocol-aware ask / review / file-back / output / nightly 偏置
- protocol runtime switch

这层现在已经是 runtime 规则平面，不再只是“说明文档”。

### 6. Governance Layer

当前状态：**稳定**

已经具备：

- `review / aging / escalation / lint / repair / nightly`
- lifecycle-driven governance surfaces
- `review-center / review-queue / aging-report / repair-backlog`
- `domain-pilots` 的 protocol-aware relevance / ambiguity summary
- judgment asset focus objects
- decision / judgment split review control objects

当前最强的不是某个单页，而是这些治理视图已经开始消费统一 state，并把 judgment asset 缺口提升成显式治理对象。

### 7. Execution Layer

当前状态：**受限可用**

已经具备：

- machine-memory action review / apply / revert
- archive apply / revert
- concept retire / reactivate
- receipts / audit / revert history
- low-risk safe execution 边界

这里已经形成“显式动作 -> receipt -> revert”的闭环，但仍然是保守执行层，不是通用自动执行器。

### 8. Outputs Layer

当前状态：**稳定**

已经具备：

- `report / slides / figure`
- output packs
- HTML control surfaces
- receipt / audit artifacts
- filed-back derived pages

这层已经不是 ask 的副产品，而是可回流、可治理、可审计的正式产物层。

### 9. Product Shell

当前状态：**初代可用控制台**

已经具备：

- `shell-summary.json`
- `aiwiki shell-status`
- repo-local launcher
- Obsidian desktop-only plugin scaffold
- `Furnace Center`
- `Recent Runs`
- `Review Center`
- `Execution Center`
- `compile / ask / nightly / protocol-set / refresh`
- `file-back / review-page / review-rewrite / apply-rewrite`
- `retire-concept / reactivate-concept`
- `apply-archive / revert-archive`
- `review-action / apply-action / revert-action`
- `Review Center / Execution Center` 的 item-level inline action
- `review-page / review-rewrite / review-action` context picker
- judgment asset summary / governance links
- decision objects / judgment objects split review surface
- context missing 时的 modal fallback

这一层已经从“只读工作台”推进到“上下文感知、带 judgment/governance focus object 的受限动作工作台”。

但它仍然是：

- launcher 驱动
- 一部分 action context 仍然依赖 fallback modal
- 还缺 batch / queue-level orchestration
- 还不是完整 object-specific workflow shell

现在已经进入“identity-aware judgment/governance control surface”的阶段，但还没有到终局文档里的细粒度对象控制台。

## 当前成熟度判断

### 已经站住的部分

- 炉心分层没有被打穿
- `aiwiki` runtime 已完成 `app.py` 解单体，并保留 `aiwiki.app` 兼容 facade
- `aiwiki CLI` 仍然是唯一正式 runtime 接口
- hidden `.aiwiki/state/*` 仍然没有被 Product Shell 直接升级成公共 UI 接口
- `review / archive / apply / revert / audit` 已经能闭环
- Product Shell 已经进入 Obsidian 原生壳，而不是停在 markdown/html 面板

### 当前短板

不是 runtime 主链，而是壳层交互深度：

- 动作入口仍以 modal 为主
- 部分 context 缺失场景仍要手填 `entry_id / action_id / page path`
- judgment/governance object 虽已成为一等对象，但还缺更细的 action-specific context picker
- 还缺 queue-level / batch-level workflow
- `app_content.py` / `app_memory.py` / `app_compile.py` 仍然偏大，后续可以继续细分，但这已经不是当前主 blocker
- `qa-review` 当前仍然是 same-context fallback，不是独立 reviewer

### 当前非目标

现阶段仍然不该优先做：

- hidden state direct read
- daemon / service mode
- 通用安装发现
- auto archive executor
- learned ranker

## 现在最值得做的不是什麽

不是继续补 evidence/runtime 状态文件。

这条线已经够厚了。

接下来最值得做的是：

- 继续把 object identity 做实
- 减少对 fallback modal 的依赖
- 让 execution / review summary 直接服务 item-level action

## 历史草案归档：曾规划的下一轮 Product Shell 方向

下面这段保留为当时对 Product Shell 下一轮的草案归档，用来解释这份能力快照里的“下一步判断”从哪里来。

它不是当前 active contract，也不代表现在正在执行的 sprint。

### 当时的 Goal

推进 `Product Shell Plugin` 的下一轮：把当前“第一轮 item-level action”继续推进成 **identity-aware 的细粒度控制台**，优先减少对 receipt path 推断和 fallback modal 的依赖。

### 当时的问题 / 背景

当前插件已经有：

- `Review Center / Execution Center`
- P1/P2 动作接线
- launcher-based action runner
- active file 默认值
- item-level inline action
- context picker

但当前交互仍然偏粗：

- 一部分 action id 仍然依赖可见 receipt/event 的近似推断
- 一部分动作仍然需要 fallback modal
- runtime summary 对对象身份的暴露还不够细
- 现在是“初代对象控制台”，还不是“细粒度对象控制台”

### 当时的 Success Criteria

- runtime summary 显式暴露更稳定的 object identity，而不是让插件猜
- `Review Center / Execution Center` 的 item-level action 覆盖更多对象类型
- `review-action / apply-action / revert-action` 减少对 receipt path stem 的推断
- `review-page / review-rewrite / review-action` 的 context picker 优先吃对象身份而不是仅吃路径文本
- fallback modal 只保留在真正缺上下文的场景
- 继续保持所有动作通过 repo-local launcher 调 `aiwiki CLI`
- 继续保持插件不直接读写 hidden `.aiwiki/state/*`
- 补测试覆盖 identity-aware wiring 和 fallback path

### 当时的 Constraints

- `aiwiki CLI` 仍然是唯一正式 runtime 接口
- 不引入 daemon / server / hosted backend
- 不为方便 UI 而绕过 receipt / audit / revert 语义
- 第一版仍按 repo-local desktop mode 设计
- 不重写 runtime state ownership

### 当时的 In Scope

- `.obsidian/plugins/furnace-product-shell/main.js`
- `tests/test_app.py`
- `wiki/indexes/Furnace Product Shell Plugin.md`
- 视图内 item-level action binding
- action-specific context picker

### 当时的 Out Of Scope

- TypeScript/build toolchain
- hidden state direct reads
- 全局安装发现
- mobile support
- 新增 daemon

### 当时的 Verification Plan

- 先跑插件静态契约测试
- 跑 `node --check`
- 跑 `bash scripts/verify.sh`
- 做 same-context review 或更高等级 review
- 跑 `closed_loop`

### 当时的 Stop Conditions

- 插件为了做 item-level action 被迫直接读取 hidden `.aiwiki/state/*`
- 插件为了少写表单而绕过 launcher/CLI
- 为了绑定对象而把 runtime 真相搬进插件

## 当时推荐的执行顺序

1. 先做 Review Center 的 item-level inline action
2. 再做 Execution Center 的 item-level inline action
3. 然后再补 action-specific context picker
4. 最后视情况决定是否需要更细的 execution/review summary

## 快照结论

当前炼丹炉的判断可以收敛成一句话：

**炉心已经稳定，Product Shell 已经可用，下一轮真正决定体验上限的不是“再加几个命令”，而是“能不能把对象级上下文和动作真正接起来”。**
