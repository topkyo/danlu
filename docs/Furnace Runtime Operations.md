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
| `aiwiki-nightly.timer` → `aiwiki-nightly.service` | 定时 oneshot | 每天 00:00 | **是**（默认 full local furnace profile）| `Persistent=true` 错过补跑 |
| 用户/agent 显式 `run-compile` / `run-ask` / `run-lint` | 手动 worker | 按需 | 是 | 无（手动调用） |
| `aiwiki-dogfood-maturity.timer` | 验证 harness（opt-in） | 验证期定时 | 条件 LLM / deterministic | 验证结束应移除 |

**含义**：炼丹炉在用户睡觉时也在工作，但工作内容受三条硬约束：

- **deterministic-only watcher**：watcher 默认不主动调 LLM；只跑 deterministic compile / lint，确保 raw → wiki 的最低可用流水线长期 alive
- **nightly 五层炼化**：runtime policy 缺省 `autonomy_profile=agentic`，nightly 默认执行 L0/L1/L2/L3/Judgment 和 heavy semantic 非核心自动化；env / policy 可按层缩窄，但所有变更必须 receipt/audit/revert；核心 prompt/policy/schema 写回仍 proposal-only；fallback 仍默认关闭
- **LLM 隔离到受控入口**：要让 LLM 介入，必须走 `run-*` 命令或 nightly 的 `run-nightly` 路径；watcher 不会偷跑
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

模板源在 `systemd/aiwiki-*.template`，由 `scripts/install_user_service.sh` 渲染落地。`aiwiki-dogfood-maturity.*` 模板仍保留，但默认不安装；仅在 `AIWIKI_INSTALL_DOGFOOD_MATURITY=1` 的验证运行中渲染。

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

macOS wrapper 走 vault 内 `scripts/aiwiki-launcher.sh`，所以 Product Shell 写入本机插件 `data.json` 的 LLM backend / key 能被 watcher 和 nightly 读取；plist 只保存 `AIWIKI_VAULT`、调度和非敏感运行参数，不保存 API key。

### 2.2 watcher 服务

```ini
[Service]
Type=simple
WorkingDirectory=/home/tim/ai-wiki
EnvironmentFile=/home/tim/.config/aiwiki/aiwiki-watch.env
ExecStart=/home/tim/ai-wiki/scripts/run_watch.sh
Restart=always
RestartSec=5
```

`run_watch.sh` 真实命令：

```bash
python3 -m aiwiki.cli --root "$AIWIKI_VAULT" watch \
  --interval 5 --compile-limit 5 --deterministic-only
```

关键 env：
- `AIWIKI_VAULT=/home/tim/danlu/炼丹炉` —— 监听目标 vault
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
if AIWIKI_NIGHTLY_DETERMINISTIC_ONLY == 1:
    aiwiki nightly                          ← deterministic only
elif LLM 已 configured:
    aiwiki run-nightly --compile-limit 5    ← primary LLM-backed full path
    if configured LLM run-nightly failed:
        fail closed; do not convert to deterministic success
else:
    if no LLM path and AIWIKI_NIGHTLY_REQUIRE_LLM == 1:
        fail without deterministic fallback
    else:
        aiwiki nightly
```

关键 env：
- `AIWIKI_AUTONOMY_PROFILE=agentic` —— runtime profile override；新安装 nightly env 默认写入，保证旧 vault 的 legacy policy 文件不会让 receipt 继续按旧 profile 记账
- `AIWIKI_NIGHTLY_DETERMINISTIC_ONLY=0` —— 默认跑 LLM；设 `1` 强制不调 LLM
- `AIWIKI_NIGHTLY_REQUIRE_LLM=0` —— 当没有任何 configured LLM path 可尝试时，默认允许 wrapper 跑 deterministic nightly；一旦 configured `run-nightly` 已失败，wrapper 会 fail closed，不把 deterministic nightly 当作本次 success proof
- `AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT=1` —— **L0 维护层自动 apply**；agent_loop preview 完成后立即执行 receipted light primitives（compile/lint/nightly），写 receipt + audit。systemd installer 默认写 `0`，必须显式 opt-in。
- `AIWIKI_NIGHTLY_AUTO_ADOPT_L1=1` —— **L1 语义层自动采纳**：concept backlog → active、revisit → deferred、source-concept link 自动 accept + apply。systemd installer 默认写 `0`。
- `AIWIKI_NIGHTLY_AUTO_ADOPT_L2=1` —— **L2 结构层自动采纳**：overloaded-concept split 自动 accept + apply。systemd installer 默认写 `0`。
- `AIWIKI_NIGHTLY_AUTO_ADOPT_L3=1` —— **L3 策略层自动采纳**：自动登记 `metadata_only` candidate，核心 prompt/policy/schema 写回仍必须显式 human accept + 手动 `apply` + hash gate。systemd installer 默认写 `0`。
- `AIWIKI_NIGHTLY_AUTO_ADOPT_JUDGMENTS=1` —— **判断层自动复核**：LLM-powered counter-evidence review，读取反证来源页生成 upheld/weakened/refuted 结论，并写标准 execution receipt、history、audit。systemd installer 默认写 `0`。
- `AIWIKI_NIGHTLY_AUTO_APPLY_HEAVY_SEMANTIC=1` —— **heavy semantic phase 自动 apply**：signal pipeline 会执行 heavy `review/distill/propose` 的 receipt-backed 非核心 apply，核心写回继续走 proposal/human gate。systemd installer 默认写 `0`。
- `AIWIKI_NIGHTLY_AUTO_ADOPT_CORE_L3=1` —— **核心 L3 写回授权**：默认关闭；当前仍不允许无人值守改核心 prompt/policy/schema，仅作为未来显式 contract flag

这些 env 是显式覆盖层；缺省值来自 `.aiwiki/state/autonomy-policy.json`，文件缺失或 `AIWIKI_AUTONOMY_PROFILE=agentic` 覆盖时 runtime profile 允许维护、治理、judgment review、metadata-only L3 和 heavy semantic 非核心自动化，但核心 L3 写回默认关闭。systemd installer 为防止安装即写入，把上述写入型 auto env 默认落为 `0`；operator 要无人值守写入时必须在 env 文件中显式改成 `1`。`AIWIKI_DISABLE_AUTOMATION=1` 是全局 kill switch；policy 损坏时 fail-closed。预算字段 `max_l3_apply_per_run` 与 `judgment_review_limit` 分别限制单次 nightly 的 L3 apply 数和 judgment review 数。
- `AIWIKI_NIGHTLY_COMPILE_LIMIT=5` —— LLM enrichment 单批上限
- `AIWIKI_NIGHTLY_NO_SEMANTIC_LINT=0` —— 是否跑 semantic lint
- `scripts/run_nightly.sh` 不再配置跨 backend fallback；需要换模型或后端时显式设置 `AIWIKI_LLM_BACKEND` / `AIWIKI_LLM_MODEL` 后重跑

### 2.4 dogfood maturity 验证 harness（opt-in）

`aiwiki-dogfood-maturity.service/timer` 只用于成熟度 proof / dogfood 验证，不属于默认产品服务链。安装验证 timer：

```bash
AIWIKI_INSTALL_DOGFOOD_MATURITY=1 scripts/install_user_service.sh
```

验证结束后移除 unit，但保留 vault 数据、receipt 与 env 文件：

```bash
scripts/uninstall_user_service.sh --dogfood-maturity-only
```

这条验证 harness 会写 maturity receipt，并默认要求 LLM nightly path 可用（禁用 deterministic nightly fallback），用来证明“人只看异常”的成熟度；它不应长期混在默认 watcher/nightly 服务状态里。

### 2.5 状态查询

```bash
# 当前活动状态
systemctl --user status aiwiki-watch.service
systemctl --user status aiwiki-nightly.timer
systemctl --user status aiwiki-dogfood-maturity.timer  # 仅验证期应存在

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

# 只移除 dogfood maturity 验证 timer
scripts/uninstall_user_service.sh --dogfood-maturity-only
```

---

## 3. 受控 LLM-backed worker 入口

watcher 不调 LLM，那 LLM 在哪发生？三条路径：

| 入口 | 触发方式 | 持锁 | 用途 |
|---|---|---|---|
| `aiwiki run-compile [--paths] [--limit]` | 手动 / agent 调用 | 是 | LLM enrichment：补 source frontmatter / concept summary |
| `aiwiki run-ask "<question>" --format report [--protocol P]` | 手动 / agent 调用 | 是 | LLM-backed reasoning：生成 query report |
| `aiwiki run-nightly --compile-limit N` | nightly timer 触发 | 是 | 一次跑 nightly 全套 + LLM compile |
| `aiwiki run-lint` | 手动 | 是 | LLM 辅助 lint（少用） |

所有 `run-*` 路径都：
- 先做 `preflight_check_backend`（4-state probe），结果记入 receipt 的 `backend_compat` 字段
- 写 LLM receipt（`.aiwiki/logs/llm-receipts.jsonl`）+ runtime history + universal audit
- 失败时：受 P4-2 raw response observability 保护，失败原因和 raw stdout 都可在 receipt 里追到

---

## 4. LLM Backend 选择策略

| Backend | 状态 | 用途 |
|---|---|---|
| **opencode-api/deepseek-v4-pro** | compatible ✓ | 默认 primary（systemd env 默认） |
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
python3 -m aiwiki.cli --root "$AIWIKI_VAULT" run-ask "..."
```

### 5.3 临时切到 DeepSeek 跑 run-compile（推荐 + paths 显式过滤）

```bash
source ~/.aiwiki-secrets/deepseek.env
AIWIKI_LLM_BACKEND=deepseek-api \
AIWIKI_LLM_MODEL=deepseek-v4-pro \
PYTHONPATH=src \
python3 -m aiwiki.cli --root "$AIWIKI_VAULT" run-compile \
  --paths "discovered-20260501001505-http-v20250903-1" \
  --limit 1
```

### 5.4 systemd nightly 后端选择

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
| execution receipt | `output/control/execution-receipts/*.json` + `.aiwiki/state/execution-receipts.jsonl` | 保留；回滚依赖 |
| planner-log | `.aiwiki/state/planner-log.jsonl` | 保留；rollback marker 追加 |
| LLM receipt | `.aiwiki/logs/llm-receipts.jsonl` | 保留；`llm-telemetry` 只读聚合 |
| LLM raw response | receipt 内 `raw_response_path` | 按路径引用；清理需显式 operator 策略 |
| maturity gate | `output/control/maturity-gate/run-*.json` | 保留；自然日去重 summarize |

恢复原则：corrupt JSON/JSONL 用 fault-injection tests 锁定；**不**默认删除历史 receipt 解决磁盘膨胀。watcher 仍 deterministic-only。

### 5.5 后端切换

后端切换只通过显式 env 完成，不再有 wrapper fallback。支持值：`deepseek-api`、`opencode-api`、`openai-api`、`anthropic-api`。

### 5.6 Fallback chain（同 backend 内多 model 重试）

同 backend 多 model 重试用 `AIWIKI_MODEL_FALLBACK` 或 `--model-fallback`（**不**做跨 backend）：

```bash
AIWIKI_LLM_BACKEND=deepseek-api \
AIWIKI_LLM_MODEL=deepseek-v4-pro \
AIWIKI_MODEL_FALLBACK="deepseek-chat" \
... run-ask "..."
```

---

## 6. 监听排障速查

| 现象 | 排查 |
|---|---|
| watcher 不响应新投料 | `systemctl --user status aiwiki-watch.service` 看是否 active；`journalctl --user -u aiwiki-watch.service -n 50` |
| nightly 没跑 | `systemctl --user list-timers --all` 看 trigger；`journalctl --user -u aiwiki-nightly.service --since today` |
| dogfood maturity timer 还在跑 | `scripts/uninstall_user_service.sh --dogfood-maturity-only`；不要删除 vault receipt/data |
| run-compile 报 `Compile response is missing frontmatter` | backend 输出有装饰；用 `aiwiki llm-check --probe --format human` 确认；切到 compatible backend |
| LLM 调用 `unavailable / requires_credential` | 跑 `aiwiki llm-check --probe-all`，按 §4 表选 compatible backend；按 §5 切换 |
| 多写者抢锁 | `cat .aiwiki/state/runtime.lock` 看 pid；停 watcher 或确认 Obsidian / CLI 是否同时在写 |
| 想短期暂停所有自动化 | `systemctl --user stop aiwiki-watch.service aiwiki-nightly.timer`；或更激进：`AIWIKI_DISABLE_AUTOMATION=1` 全局 kill switch |

---

## 7. 与"始终运行"哲学的关系

炼丹炉 §3 "deterministic baseline" 不变量保证：**watcher 即使在 LLM 完全不可用的情况下，也能维持 raw → wiki 的最低可用流水线**。这意味着：

- 出门旅行没网 → watcher 仍能 deterministic compile 投料
- LLM provider 全 down 且未实际尝试 configured `run-nightly` → nightly wrapper 可跑 deterministic `nightly` 维持维护层；如果 configured `run-nightly` 已失败，则失败显式暴露，不降级为 success proof
- API key 过期 → run-* 命令显式失败，但 watcher 不受影响

默认产品路径可以理解为：**等待投料（watch）→ 炼丹（nightly / run-*）→ 产出（wiki/output/receipt）→ 回馈（review/file-back/judgment）→ 受控学习（L0-L3/Judgment，receipt-gated）**。dogfood maturity timer 只是证明这条路径成熟度的仪表，不是路径本身。

这条性质是炼丹炉与多数 RAG-first PKM（Reor / Khoj 等）的根本差异，详见 `docs/Furnace Market Scan 2026Q2.md`。

---

## 8. 不在本手册定义

- 安装初始化：见 `scripts/install_user_service.sh`
- LLM provider 详细鉴权：见 README §LLM 后端
- agent loop 内部决策：见 `docs/Furnace Agent Architecture.md` §4
- 受控自主权红线：见 `docs/Furnace Agent Architecture.md` §8 与 `autonomy-status / autonomy-disable / autonomy-enable` CLI
