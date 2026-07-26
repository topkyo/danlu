---
title: "炼丹炉运行机制与 LLM 后端操作手册"
kind: "ops-runbook"
status: "active"
owner: "tim"
created_at: 2026-05-01
related_docs:
  - docs/Furnace Agent Architecture.md
  - docs/Furnace Evolution Mechanics.md
  - README.md
---

# 炼丹炉 Runtime Operations

本文档回答三个问题：
1. **炼丹炉是不是"自动一直在跑"？** — 是；机制见 §1
2. **它怎么跑？** — `systemd --user` 或 macOS `launchd` watcher + nightly timer + 显式 LLM-backed worker 入口（§2 / §3）
3. **LLM backend 不可用时应该怎么处理？** — §5 操作手册

---

## 1. 总览：炼丹炉处于哪种"始终运行"模式

炼丹炉不是 hosted service，但在装好 user-service 的机器上是 **"始终保持监听 + 每天炼化 + 显式 LLM 工位"** 的本机自动化模式：

| 进程 | 类型 | 频率 | LLM 调用 | 自愈 |
|---|---|---|---|---|
| `aiwiki-watch.service` | 长驻 daemon | 每 5 秒 inbox 扫描 | **否**（默认 `--deterministic-only`）| `Restart=always` |
| `aiwiki-nightly.timer` → `aiwiki-nightly.service` | 定时 oneshot | 每天 00:00 | **否**（deterministic `compile` + `lint` + nightly health；W8 无 agent-loop / signals）| `Persistent=true` 错过补跑 |
| 用户/agent 显式 `run-ask` | 手动 worker | 按需 | **是**（产品 LLM 主入口） | 无（手动调用） |
| 用户/agent 显式 `run-nightly` | 手动 worker | 按需 | **否**（同 nightly timer：确定性维护链） | 无（手动调用） |

> 2026-07-15 清理：原 `aiwiki-dogfood-maturity.timer` 行已删除（属于历史验证 harness，本轮 scripts + systemd 一并删除 `install_user_service.sh` 的 `AIWIKI_INSTALL_DOGFOOD_MATURITY` 分支）。如升级机器上的旧 unit，自动 cleanup 由 `scripts/install_user_service.sh` / `uninstall_user_service.sh` 兜底。

**含义**：炼丹炉在用户睡觉时也在工作，但工作内容受三条硬约束：

- **deterministic-only watcher**：watcher 默认不主动调 LLM；只跑 deterministic compile / lint，确保 raw → wiki 的最低可用流水线长期 alive
- **nightly 确定性炼化**：timer / `run-nightly` 默认只跑 deterministic `compile` + `lint` + nightly health 写入（W8 已移除 agent-loop / signal pipeline / debt LLM 消化）
- **LLM 隔离到受控入口**：产品 LLM 主路径是 `run-ask`；watcher / nightly / drop-auto **不会**偷跑 LLM `run-compile` / `run-lint`（W6/W8）
- **single writer**：任意时刻只允许一个 writer（watcher / nightly / 手动 CLI / Obsidian Plugin）持有 `runtime.lock`

---

## 2. 服务单元（systemd --user / macOS launchd）

### 2.1 安装位置

```text
~/.config/systemd/user/
├── aiwiki-watch.service           ← 长驻 watcher
├── aiwiki-nightly.service         ← oneshot 巡检
├── aiwiki-nightly.timer           ← daily timer 触发上者
├── default.target.wants/aiwiki-watch.service
└── timers.target.wants/aiwiki-nightly.timer

~/.config/aiwiki/
├── aiwiki-watch.env               ← watcher env vars
└── aiwiki-nightly.env             ← nightly env vars
```

模板源在 `systemd/aiwiki-*.template`，由 `scripts/install_user_service.sh` 渲染落地。本轮清理已删除 `aiwiki-dogfood-maturity.*` 模板；`scripts/install_user_service.sh` 仅渲染 `aiwiki-watch.service` + `aiwiki-nightly.{service,timer}`。升级路径上，对已存在 `aiwiki-dogfood-maturity.*` unit 做清理兜底。

macOS 没有 user-level systemd 时，用 launchd 脚本安装同等产品主线：

```bash
AIWIKI_VAULT=/path/to/vault scripts/install_launchd_service.sh
scripts/uninstall_launchd_service.sh
```

launchd 写入：

```text
~/Library/LaunchAgents/
├── com.aiwiki.watch.plist
└── com.aiwiki.nightly.plist

~/.config/aiwiki/logs/
├── aiwiki-watch.out.log / aiwiki-watch.err.log
└── aiwiki-nightly.out.log / aiwiki-nightly.err.log
```

macOS wrapper 走 vault 内 `scripts/aiwiki-launcher.sh`，所以 Product Shell 写入本机插件 `data.json` 的 LLM backend / key 能被 watcher 和 nightly 读取；plist 只保存 `AIWIKI_VAULT`、调度和非敏感运行参数，不保存 API key。`scripts/install_launchd_service.sh` 也是 Product Shell release 同步入口：它会更新目标 vault 的 `manifest.json` / `main.js` / `styles.css`，但不覆盖 `data.json`。

### 2.2 watcher 服务

```ini
[Service]
Type=simple
WorkingDirectory=/Users/ht/github/danlu
EnvironmentFile=/Users/ht/.config/aiwiki/aiwiki-watch.env
ExecStart=/Users/ht/github/danlu/scripts/run_watch.sh
Restart=always
RestartSec=5
```

`run_watch.sh` 真实命令：

```bash
python3 -m aiwiki.cli --root "$AIWIKI_VAULT" advanced watch \
  --interval 5 --compile-limit 5 --deterministic-only
```

关键 env：
- `AIWIKI_VAULT=$AIWIKI_DOGFOOD_VAULT` —— 监听目标 vault
- `AIWIKI_WATCH_INTERVAL=5` —— 5s 轮询 inbox
- `AIWIKI_WATCH_DETERMINISTIC_ONLY=1` —— 默认禁 LLM；设 `0` 才会 inline 跑 LLM compile（**不推荐**，会持锁太久阻塞投料）
- `AIWIKI_WATCH_NO_SEMANTIC_LINT=0` —— 默认跑 semantic lint
- `AIWIKI_WATCH_SKIP_INITIAL=0` —— 启动时是否跳过首轮 compile

### 2.3 nightly 服务 + timer

```ini
[Timer]
OnCalendar=daily          ← 每天 0:00
Persistent=true            ← 错过的执行会补跑
Unit=aiwiki-nightly.service
```

`run_nightly.sh` 决策路径：

```text
aiwiki advanced run-nightly --compile-limit N    ← deterministic compile + lint + nightly health
```

> **W8 产品路径说明**：`run-nightly` 不再读取 `AIWIKI_NIGHTLY_AUTO_*` 做 agent-loop、signals 或 debt LLM 消化。installer 仍可能写入这些 env 键作历史 compat，但对当前 nightly 路径 **无效果**；需要 LLM 请走显式 `advanced run-ask`；需要治理写回请走 `advanced review-page` / `file-back` / `alchemy-revert` 或 library receipt 路径（L3 apply/revert 等产品 CLI 已删）。

关键 env（仍生效）：
- `AIWIKI_AUTONOMY_PROFILE=agentic` —— runtime profile override；新安装 nightly env 默认写入，保证旧 vault 的 legacy policy 文件不会让 receipt 继续按旧 profile 记账
- `AIWIKI_NIGHTLY_COMPILE_LIMIT=5` —— nightly receipt 元数据（compile 本身为确定性全量）
- `scripts/run_nightly.sh` 不再配置跨 backend fallback；需要换模型或后端时显式设置 `AIWIKI_LLM_BACKEND` / `AIWIKI_LLM_MODEL` 后重跑

**历史 compat env（W8 nightly 忽略，勿当产品能力）**：`AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT`、`AIWIKI_NIGHTLY_AUTO_ADOPT_L1/L2/L3`、`AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS`、`AIWIKI_NIGHTLY_AUTO_APPLY_HEAVY_SEMANTIC`、`AIWIKI_NIGHTLY_AUTO_ADOPT_CORE_L3` —— installer 可能仍写入 `0`，但不再驱动产品 nightly 路径。

### 2.4 （自 2026-07-15 起：dogfood maturity 验证 harness 已废弃）

> 原 `AIWIKI_INSTALL_DOGFOOD_MATURITY=1` 启用 `aiwiki-dogfood-maturity.{service,timer}` 与 `--dogfood-maturity-only` 卸载 flag 已随 `scripts/install_user_service.sh` / `uninstall_user_service.sh` 一并删除。`systemd/aiwiki-dogfood-maturity.{service,timer}.template` 也已删除。本仓库当前不存在「成熟度自动 verdict timer」；成熟度以人盯 `.aiwiki/state/execution-receipts/` 与 `output/control/llm-receipts.jsonl` 异常事件为准。若机器上保留有旧 unit，`scripts/install_user_service.sh` / `scripts/uninstall_user_service.sh` 仍主动清理。

### 2.5 状态查询

```bash
# 当前活动状态
systemctl --user status aiwiki-watch.service
systemctl --user status aiwiki-nightly.timer

# 下次触发时间
systemctl --user list-timers --all | grep aiwiki

# 实时日志
journalctl --user -u aiwiki-watch.service -f
journalctl --user -u aiwiki-nightly.service --since today
```

### 2.6 临时停服与恢复

```bash
# 暂停（dogfood / debug 期间避免抢锁）
systemctl --user stop aiwiki-watch.service aiwiki-nightly.timer

# 恢复
systemctl --user start aiwiki-watch.service aiwiki-nightly.timer

# 永久禁用（不推荐）
systemctl --user disable --now aiwiki-watch.service aiwiki-nightly.timer
```

---

## 3. 受控 LLM-backed worker 入口

watcher 与 nightly timer 默认不调 LLM。LLM 在产品面的默认发生点：

| 入口 | 触发方式 | 持锁 | LLM | 用途 |
|---|---|---|---|---|
| `aiwiki advanced compile` | 手动 / watcher / nightly | 是 | 否 | 确定性 compile：manifest → wiki sources/indexes |
| `aiwiki advanced lint` | 手动 / nightly | 是 | 否 | 确定性 lint + repair backlog |
| `aiwiki advanced run-nightly` | timer / 手动 | 是 | 否 | 确定性 compile + lint + nightly health |
| `aiwiki advanced run-ask "<question>" --format report` | 手动 / agent 调用 | 是 | **是** | LLM-backed reasoning：生成 query report |
| `aiwiki drop …` | 手动 / Shell | 是 | 可选（universal payload 默认 LLM planner；`AIWIKI_LLM_PLANNER=0` 关） | 入 raw 后 **默认** deterministic compile + lint（`--no-auto` 可跳过）。plan/execute：planner 不写 raw，executor 原样落盘。`AIWIKI_LLM_DISTILL` 控制 distill synthesizer（默认开）。 |

`run-ask` 路径会：
- 先做 `preflight_check_backend`（4-state probe），结果记入 receipt 的 `backend_compat` 字段
- 写 LLM receipt（`.aiwiki/logs/llm-receipts.jsonl`）+ runtime history + universal audit
- 失败时：受 P4-2 raw response observability 保护，失败原因和 raw stdout 都可在 receipt 里追到

> W8：产品 nightly / drop-auto / watch 均不调 LLM；历史 `AIWIKI_NIGHTLY_AUTO_*` env 不再驱动 nightly 行为。

---

## 4. LLM Backend 选择策略

**产品默认（B44 product lock）：** 对外产品与 Shell/CLI 主路径只承诺 `opencode-api/deepseek-v4-pro`；其它 backend 为专家 escape hatch，需显式 env 切换，runtime 不做隐式 cross-backend routing。

| Backend | 状态 | 用途 |
|---|---|---|
| **opencode-api/deepseek-v4-pro** | compatible ✓ | **产品默认** primary（systemd env 默认） |
| **deepseek-api/deepseek-v4-pro** | supported | 直接 DeepSeek API key route |
| **openai-api/gpt-4.1-mini** | supported | OpenAI / OpenAI-compatible API route |
| **anthropic-api/claude-sonnet-4-20250514** | supported | Claude API route |

按 9+ feasibility contract，**runtime core 永不做 cross-backend 自动 routing**——普通 CLI 切 backend 必须显式（env 或 CLI flag）。`scripts/run_nightly.sh` 也不再提供跨 backend fallback wrapper。

---

## 5. LLM API 后端操作手册

### 5.1 凭据位置

```text
~/.aiwiki-secrets/<provider>.env   ← mode 600，父目录 700，repo 外，永不入 git
内容（脱敏示例）：
  export AIWIKI_DEEPSEEK_API_KEY="sk-...your-key..."
```

> **凭据安全规范**：见 README §"认证说明" 与 AGENTS.md。本文档不写明文 key。

### 5.2 临时切到 DeepSeek 跑一条命令

```bash
source ~/.aiwiki-secrets/deepseek.env
AIWIKI_LLM_BACKEND=deepseek-api \
AIWIKI_LLM_MODEL=deepseek-v4-pro \
PYTHONPATH=src \
python3 -m aiwiki.cli --root "$AIWIKI_VAULT" advanced run-ask "..."
```

### 5.3 systemd nightly 后端选择

`scripts/install_user_service.sh` 必须以 `AIWIKI_VAULT=/path/to/vault` 运行，不会默认使用项目根目录。它默认写入 `opencode-api/deepseek-v4-pro`。要切换到 DeepSeek / OpenAI / Claude，直接改 `~/.config/aiwiki/aiwiki-nightly.env` 里的 `AIWIKI_LLM_BACKEND`、`AIWIKI_LLM_MODEL` 和对应 API key 环境变量。

验证：

```bash
systemctl --user restart aiwiki-nightly.service   # 立即触发一次
journalctl --user -u aiwiki-nightly.service --since "1 minute ago"
```

> **Watcher 不需要切**：watcher 默认 deterministic-only，不调 LLM。

## 6. Retention 与恢复（AGOS-008）

本地审计证据默认 **archive-first**，不静默删除：

| Artifact | 路径 | 策略 |
|----------|------|------|
| execution receipt | `.aiwiki/state/execution-receipts/*.json` + `.aiwiki/state/execution-receipts.jsonl` | 保留；回滚依赖 |
| planner-log | `.aiwiki/state/planner-log.jsonl` | 保留；rollback marker 追加 |
| LLM receipt | `.aiwiki/logs/llm-receipts.jsonl` | 保留；只读聚合走 `advanced llm-check` / acceptance（CLI `llm-telemetry`/`backend-telemetry` 已删） |
| LLM raw response | receipt 内 `raw_response_path` | 按路径引用；清理需显式 operator 策略 |
| maturity gate | `output/control/maturity-gate/run-*.json` | 保留；自然日去重 summarize |

恢复原则：corrupt JSON/JSONL 由 acceptance fixture 锁定回归；**不**默认删除历史 receipt 解决磁盘膨胀。watcher 仍 deterministic-only。

### 5.5 后端切换

后端切换只通过显式 env 完成，不再有 wrapper fallback。支持值：`deepseek-api`、`opencode-api`、`openai-api`、`anthropic-api`。

### 5.6 Fallback chain（同 backend 内多 model 重试）

同 backend 多 model 重试用 `AIWIKI_MODEL_FALLBACK` 或 `--model-fallback`（**不**做跨 backend）：

```bash
AIWIKI_LLM_BACKEND=deepseek-api \
AIWIKI_LLM_MODEL=deepseek-v4-pro \
AIWIKI_MODEL_FALLBACK="deepseek-chat" \
... advanced run-ask "..."
```

---

## 7. 监听排障速查

| 现象 | 排查 |
|---|---|
| watcher 不响应新投料 | `systemctl --user status aiwiki-watch.service` 看是否 active；`journalctl --user -u aiwiki-watch.service -n 50` |
| nightly 没跑 | `systemctl --user list-timers --all` 看 trigger；`journalctl --user -u aiwiki-nightly.service --since today` |
| dogfood maturity timer 还在跑（2026-07-15 清理前遗留） | `scripts/uninstall_user_service.sh` 会自动清理；保留 vault receipt/data |
| `run-ask` 报 frontmatter / contract 校验失败 | backend 输出有装饰；用 `aiwiki advanced llm-check --probe --format human` 确认；切到 compatible backend |
| LLM 调用 `unavailable / requires_credential` | 跑 `aiwiki advanced llm-check --probe-all`，按 §4 表选 compatible backend；按 §5 切换 |
| 多写者抢锁 | `cat .aiwiki/state/runtime.lock` 看 pid；停 watcher 或确认 Obsidian / CLI 是否同时在写 |
| iCloud 分叉 `.aiwiki/state/execution-policy-decisions N.jsonl` | dogfood vault 的 `.aiwiki/state` 应 symlink 到 `~/Library/Application Support/aiwiki/dogfood-state`（本地，不走 iCloud）；幂等迁移：`bash scripts/relocate_aiwiki_state_out_of_icloud.sh`；原目录保留为 `.aiwiki/state.icloud-backup-*` |
| 想短期暂停所有自动化 | `systemctl --user stop aiwiki-watch.service aiwiki-nightly.timer`；或更激进：`AIWIKI_DISABLE_AUTOMATION=1` 全局 kill switch |

---

## 8. 与"始终运行"哲学的关系

炼丹炉 §3 "deterministic baseline" 不变量保证：**watcher 即使在 LLM 完全不可用的情况下，也能维持 raw → wiki 的最低可用流水线**。这意味着：

- 出门旅行没网 → watcher 仍能 deterministic compile 投料
- LLM provider 全 down → `run-nightly` 仍可跑确定性 compile + lint；watcher 不受影响
- API key 过期 → `run-ask` 等显式 LLM 命令失败，但 watcher / nightly 确定性链路不受影响

默认产品路径可以理解为：**等待投料（watch）→ 确定性炼化（nightly）→ 显式提问（run-ask）→ 产出（wiki/output/receipt）→ 回馈（review/file-back/judgment / 金丹 alchemy）**。`compile` / `lint` 始终是 deterministic baseline，不再通过 watch / nightly / drop-auto 隐式调用 LLM `run-compile` / `run-lint`。

这条性质是炼丹炉与多数 RAG-first PKM（Reor / Khoj 等）的根本差异，详见 [`docs/archive/Furnace Market Scan 2026Q2.md`](<./archive/Furnace Market Scan 2026Q2.md>)（该 doc 已 archive，需以 archive 形式查阅）。

---

## 9. 不在本手册定义

- 安装初始化：见 `scripts/install_user_service.sh`
- LLM provider 详细鉴权：见 README §LLM 后端
- agent loop 内部决策：见 `docs/Furnace Agent Architecture.md` §4
- 受控自主权红线：见 `docs/Furnace Agent Architecture.md` §8 与 `autonomy-status / autonomy-disable / autonomy-enable` CLI
