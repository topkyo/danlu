"""Vault templates and constants for Obsidian vault bootstrapping."""
from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

PLUGIN_ID = "furnace-product-shell"

DEFAULT_OBSIDIAN_APP = {
    "alwaysUpdateLinks": True,
    "attachmentFolderPath": "raw/assets",
    "defaultViewMode": "preview",
    "newFileFolderPath": "raw/inbox",
    "newFileLocation": "folder",
    "promptDelete": False,
    # Raw/inbox notes always start with `# {title}`; inline title would duplicate that heading.
    "showInlineTitle": False,
    "showUnsupportedFiles": True,
    "useMarkdownLinks": False,
    "userIgnoreFilters": [
        "docs/",
        "raw/normalized/",
        "wiki/derived/",
        "wiki/decisions/",
        "wiki/judgments/",
        "wiki/elixirs/",
        "wiki/sources/",
        "wiki/concepts/",
        "wiki/indexes/",
        "schema/",
        "output/control/",
        "output/graph/",
        ".aiwiki/derived/packs/",
        "output/review/",
        "output/slides/",
        "output/figures/",
        # Never ignore output/reports/ — Product Shell "Open report" needs Obsidian indexing.
        ".aiwiki/",
    ],
}

DEFAULT_OBSIDIAN_CORE_PLUGINS = {
    "audio-recorder": False,
    "backlink": True,
    "bases": True,
    "bookmarks": True,
    "canvas": True,
    "command-palette": True,
    "daily-notes": False,
    "editor-status": False,
    "file-explorer": True,
    "file-recovery": False,
    "footnotes": False,
    "global-search": True,
    "graph": True,
    "markdown-importer": False,
    "note-composer": False,
    "outline": True,
    "outgoing-link": True,
    "page-preview": True,
    "properties": True,
    "publish": False,
    "random-note": False,
    "slash-command": False,
    "slides": False,
    "switcher": True,
    "sync": False,
    "tag-pane": False,
    "templates": False,
    "webviewer": False,
    "word-count": False,
    "workspaces": True,
    "zk-prefixer": False,
}

DEFAULT_PLUGIN_DATA = {
    "settings": {
        "defaultAskFormat": "report",
        "launcherPath": "scripts/aiwiki-launcher.sh",
        "locale": "zh",
        "llmBackend": "opencode-api",
        "llmModel": "deepseek-v4-pro",
        "recentRunsLimit": 8,
    },
    "recentRuns": [],
}

FOLDER_LABEL_SNIPPET_NAME = "danlu-zh-folders"

DEFAULT_OBSIDIAN_APPEARANCE = {
    "enabledCssSnippets": [FOLDER_LABEL_SNIPPET_NAME],
}

FOLDER_LABEL_OVERRIDES: tuple[tuple[str, str], ...] = (
    ("raw", "原料"),
    ("output", "产出"),
    ("schema", "规则 schema"),
    ("scripts", "脚本 scripts"),
    ("prompts", "提示词 prompts"),
    ("raw/inbox", "收件箱"),
    ("raw/assets", "附件"),
    ("raw/normalized", "标准化 normalized"),
    ("wiki/sources", "来源 sources"),
    ("wiki/concepts", "概念 concepts"),
    ("wiki/derived", "派生 derived"),
    ("wiki/decisions", "决策 decisions"),
    ("wiki/judgments", "判断 judgments"),
    ("wiki/indexes", "索引 indexes"),
    ("wiki/execution-proposals", "执行提案 execution-proposals"),
    ("wiki/rewrite-proposals", "改写提案 rewrite-proposals"),
    (".aiwiki/derived/agents", "智能体 agents"),
    ("output/control", "控制面板 control"),
    (".aiwiki/state/execution-receipts", "执行回执 execution-receipts"),
    ("output/graph", "图谱 graph"),
    (".aiwiki/derived/packs", "输出包 packs"),
    (".aiwiki/derived/packs/review", "审阅包 review"),
    (".aiwiki/derived/packs/decision-memos", "决策备忘 decision-memos"),
    (".aiwiki/derived/packs/sop-drafts", "SOP 草稿 sop-drafts"),
    ("output/reports", "报告"),
    ("output/review", "审阅 review"),
    ("output/figures", "图表 figures"),
    ("output/slides", "幻灯片 slides"),
    ("schema/protocols", "协议 protocols"),
    ("schema/policies", "策略 policies"),
    ("schema/protocols/general", "通用协议 general"),
)

USER_HIDDEN_FOLDER_PATHS: tuple[str, ...] = (
    "raw/normalized",
    "docs",
    "wiki",
    "schema",
    "scripts",
    "prompts",
    ".aiwiki/derived/agents",
    "output/control",
    "output/figures",
    "output/graph",
    ".aiwiki/derived/packs",
    "output/review",
    "output/slides",
)

def _folder_label_selectors(path: str) -> tuple[str, ...]:
    return (
        f'.nav-folder[data-path="{path}"] > .nav-folder-title > .nav-folder-title-content',
        f'.nav-folder[data-path="{path}"] .nav-folder-title-content',
        f'.nav-folder-title[data-path="{path}"] > .nav-folder-title-content',
        f'.tree-item[data-path="{path}"] > .tree-item-self > .tree-item-inner',
        f'.tree-item[data-path="{path}"] .tree-item-inner',
        f'.tree-item-self[data-path="{path}"] > .tree-item-inner',
        f'.tree-item[data-path="{path}"] .tree-item-title',
        f'.tree-item-self[data-path="{path}"] .tree-item-title',
    )

def _folder_container_selectors(path: str) -> tuple[str, ...]:
    return (
        f'.nav-folder[data-path="{path}"]',
        f'.tree-item[data-path="{path}"]',
        f'.nav-folder-title[data-path="{path}"]',
        f'.tree-item-self[data-path="{path}"]',
    )

def _render_folder_label_snippet() -> str:
    lines = [
        "/*",
        " * 炼丹炉 vault — 文件浏览器用户视图",
        " * 保留运行时英文路径不变；普通用户默认只看投料收件箱和报告，其余运行时分层从文件树隐藏。",
        " * 同时兼容旧结构（data-path 在父级）和新结构（data-path 在 title/self）两种 DOM。",
        " */",
        "",
    ]
    lines.extend(
        [
            "/* 默认隐藏 runtime / operator folders；Product Shell 和更多工具仍可打开对应页面。 */",
        ]
    )
    for path in USER_HIDDEN_FOLDER_PATHS:
        lines.extend(
            [
                f"/* hide {path} from the daily file tree */",
                ",\n".join(_folder_container_selectors(path)) + " {",
                "  display: none !important;",
                "}",
                "",
            ]
        )
    for path, label in FOLDER_LABEL_OVERRIDES:
        selectors = _folder_label_selectors(path)
        pseudo_selectors = tuple(f"{selector}::after" for selector in selectors)
        lines.extend(
            [
                f"/* {path} -> {label} */",
                ",\n".join(selectors) + " {",
                "  font-size: 0 !important;",
                "  line-height: 0 !important;",
                "  color: transparent !important;",
                "}",
                ",\n".join(pseudo_selectors) + " {",
                f'  content: "{label}";',
                "  display: inline-block !important;",
                "  font-size: var(--nav-item-size, 13px) !important;",
                "  line-height: var(--line-height-normal, 1.4) !important;",
                "  color: var(--nav-item-color, var(--text-normal)) !important;",
                "  vertical-align: middle;",
                "}",
                "",
            ]
        )
    return "\n".join(lines)

def _default_workspace_document() -> dict[str, Any]:
    return {
        "active": "main-furnace-center",
        "lastOpenFiles": [
            "wiki/indexes/furnace-center.md",
            "HOME.md",
            "README.md",
            "wiki/indexes/Outputs.md",
            "wiki/indexes/judgment-assets.md",
            "wiki/indexes/review-center.md",
            "output/control/shell-summary.json",
        ],
        "left": {
            "collapsed": True,
            "children": [
                {
                    "children": [
                        {
                            "id": "left-files",
                            "state": {
                                "icon": "lucide-folder-closed",
                                "state": {"autoReveal": False, "sortOrder": "alphabetical"},
                                "title": "文件列表",
                                "type": "file-explorer",
                            },
                            "type": "leaf",
                        },
                        {
                            "id": "left-bookmarks",
                            "state": {
                                "icon": "lucide-bookmark",
                                "state": {},
                                "title": "书签",
                                "type": "bookmarks",
                            },
                            "type": "leaf",
                        },
                    ],
                    "id": "left-tabs",
                    "type": "tabs",
                }
            ],
            "direction": "horizontal",
            "id": "left-root",
            "type": "split",
            "width": 260,
        },
        "left-ribbon": {
            "hiddenItems": {
                "bases:新建数据库": False,
                "canvas:新建白板": False,
                "command-palette:打开命令面板": False,
                "furnace-product-shell:Open Furnace Center": False,
                "furnace-product-shell:打开炉心面板": False,
                "furnace-product-shell:Refresh Furnace Shell": False,
                "furnace-product-shell:刷新炼丹炉 Shell": False,
                "graph:查看关系图谱": False,
                "switcher:打开快速切换": False,
                "workspaces:管理工作区布局": False,
            }
        },
        "main": {
            "children": [
                {
                    "children": [
                        {
                            "id": "main-furnace-center",
                            "state": {
                                "icon": "flask-conical",
                                "state": {},
                                "title": "炼丹炉",
                                "type": "furnace-product-shell-furnace-center",
                            },
                            "type": "leaf",
                        },
                        {
                            "id": "home-leaf",
                            "state": {
                                "icon": "lucide-file",
                                "state": {"file": "HOME.md", "mode": "preview", "source": False},
                                "title": "HOME",
                                "type": "markdown",
                            },
                            "type": "leaf",
                        },
                    ],
                    "currentTab": 0,
                    "id": "main-tabs",
                    "type": "tabs",
                }
            ],
            "direction": "vertical",
            "id": "main-root",
            "type": "split",
        },
        "right": {
            "collapsed": True,
            "children": [
                {
                    "children": [
                        {
                            "id": "right-outline",
                            "state": {
                                "icon": "lucide-list",
                                "state": {
                                    "file": "HOME.md",
                                    "followCursor": False,
                                    "searchQuery": "",
                                    "showSearch": False,
                                },
                                "title": "HOME 的大纲",
                                "type": "outline",
                            },
                            "type": "leaf",
                        },
                        {
                            "id": "right-backlinks",
                            "state": {
                                "icon": "links-coming-in",
                                "state": {
                                    "backlinkCollapsed": False,
                                    "collapseAll": False,
                                    "extraContext": False,
                                    "searchQuery": "",
                                    "showSearch": False,
                                    "sortOrder": "alphabetical",
                                    "unlinkedCollapsed": True,
                                },
                                "title": "反向链接",
                                "type": "backlink",
                            },
                            "type": "leaf",
                        },
                    ],
                    "currentTab": 0,
                    "id": "right-tabs",
                    "type": "tabs",
                }
            ],
            "direction": "horizontal",
            "id": "right-root",
            "type": "split",
            "width": 280,
        },
    }

def _render_vault_readme(runtime_root: Path) -> str:
    runtime = str(runtime_root.resolve())
    return (
        "\n".join(
            [
                "# 炼丹炉 Vault",
                "",
                "这是一个新的炼丹炉工作区（Obsidian vault）。",
                "",
                f"- 当前绑定的 runtime root：`{runtime}`",
                "- 当前 vault root：本目录",
                "- 日常入口：打开 Obsidian -> 主区 Product Shell（`HOME.md` 只保留说明和关键链接；CLI 作为备用/脚本入口）",
                "- 左侧文件树是用户视图：默认只保留投料收件箱和报告入口；`raw/wiki/schema/output` 的完整分层仍由 runtime 管理。",
                "- Obsidian 与 CLI 共用同一个 runtime / state，遵守 `single writer, many readers`。",
                "- Product Shell 默认界面语言为中文，可在插件设置里切到 English。",
                "- Product Shell 默认 LLM route 是 `opencode-api/deepseek-v4-pro`；可以在设置里显式切换已配置 backend，但不会自动跨 backend fallback。",
                "- 当前 dogfood 主路由以 OpenCode API 为准；旧 CLI、NVIDIA NIM 和 OpenRouter 后端不再作为 Shell/runtime 自动 fallback 后端。",
                "- API key 只应放在本机未跟踪的 Product Shell `data.json` 或 repo 外 secret env 文件；不要写入 README、测试 fixture 或 git-tracked 文件。",
                "",
                "## 备用 CLI / 脚本入口",
                "",
                "```bash",
                "./scripts/aiwiki-launcher.sh shell-status",
                "./scripts/aiwiki-launcher.sh compile",
                './scripts/aiwiki-launcher.sh drop markdown --title "晨间观察" --text "记录今天的新线索"',
                './scripts/aiwiki-launcher.sh run-ask-submit "今天最重要的变化是什么？" --format report',
                "./scripts/aiwiki-launcher.sh nightly",
                "```",
                "",
                "## 工作流",
                "",
                "1. 默认在 Obsidian 中工作：主区 Product Shell 是日常入口，`HOME.md` 只做说明和关键链接。",
                "2. 投料从 Product Shell 输入框或 CLI / agent 的 `drop url / drop pdf / drop image / drop repo / drop markdown` 开始；Markdown / 文本材料可直接投，不要从文件树理解 runtime 分层。",
                "3. 提问也有两个入口：Obsidian Product Shell 的 `Ask`，以及 `./scripts/aiwiki-launcher.sh run-ask-submit ... --format report`；默认生成 `output/reports/*.md` 报告。",
                "4. `compile / nightly / apply / revert` 这类写操作不要双开；同一时刻只保留一个写入口。",
                "",
                "## Runtime 目录职责",
                "",
                "- `raw/`：原料",
                "- `wiki/`：来源、概念、判断、决策、索引",
                "- `output/`：报告、图表、HTML 控制面、审计产物",
                "- `schema/`：运行时规则和协议",
                "- `.aiwiki/`：状态、缓存、日志",
                "- 普通用户文件树默认只露出 `raw/inbox` 投料收件箱和 `output/` 报告入口，具体报告文件直接集中在报告入口下；其余运行时分层由 Product Shell、更多工具和 CLI 间接打开。",
                "- `.aiwiki/staging/`：候选金丹与 L3/judge 提案（Obsidian 默认隐藏，由 runtime 管理）。",
                "- `.aiwiki/lint/` 是 nightly / operator 质量检查产物，不是用户报告证据；位于 Obsidian 不可见的 runtime 分层。",
                "- `raw / wiki / output / schema` 这些英文目录名是 runtime contract；中文化通过工作台导航和说明完成，不建议直接重命名路径。",
                "",
                "## 备注",
                "",
                "- 这个 vault 通过 `scripts/aiwiki-launcher.sh` 回到 runtime 执行，不要求 vault 自己包含 `src/aiwiki/`。",
                "- 图谱与审阅优先在 Obsidian 打开 `wiki/indexes/`；机器记忆 JSON 见 `.aiwiki/cache/machine-memory-graph.json`。**HTML 控制面（如 `output/graph/machine-memory.html`）已停写**，勿再当主入口。",
                "- 如果 runtime root 迁移了，重新创建 launcher 或更新脚本里的 `RUNTIME_ROOT` 即可。",
                "",
            ]
        )
        + "\n"
    )

def _render_vault_home() -> str:
    return (
        "\n".join(
            [
                "---",
                'title: "炼丹炉工作台"',
                'kind: "dashboard"',
                "---",
                "",
                "# 炼丹炉",
                "",
                "这是炼丹炉在 Obsidian 里的产品入口。默认从主区的 Product Shell 开始：投料、提问、看 Today、打开报告；其他治理和调试入口收在更多工具。",
                "",
                "## 日常路径",
                "",
                "1. 在 Product Shell 输入框里投 URL / 文件 / 图片，或直接问一个问题。",
                "2. 看 Today：报告点 `Open`，审阅点 `Open Review`，命令先 `Copy command`。",
                "3. 把有价值的报告回流为判断、决策或金丹。",
                "4. 需要排障时再展开更多工具；不要先从目录结构开始工作。",
                "",
                "左侧文件树是用户视图：日常只需要投料收件箱和报告。`raw/wiki/schema` 和 `output/` 的其他产物仍存在，但默认不作为用户入口。",
                "`.aiwiki/lint/` 属于 operator 质量检查和排障产物，不是用户报告证据，不会进入 Obsidian 文件树。",
                "",
                "## 首屏模型",
                "",
                "- 输入端：Ask / Drop / 投文字材料",
                "- 输出端：Today / Today's Reports / Previous Reports",
                "- 更多工具：审阅、执行、运行记录、指标、LLM 状态",
                "",
                "## 关键入口",
                "",
                "- [[README|使用说明]]",
                "- [[wiki/indexes/README|索引策略（compile 后生成面板页）]]",
                "",
                "`wiki/indexes/` 下的炉心 / 审阅 / 判断资产等面板页由 `compile` 生成；先跑 compile 再打开。",
                "",
                "## 备用命令",
                "",
                "```bash",
                "./scripts/aiwiki-launcher.sh shell-status",
                "./scripts/aiwiki-launcher.sh compile",
                './scripts/aiwiki-launcher.sh run-ask-submit "总结今天的关键变化" --format report',
                "./scripts/aiwiki-launcher.sh nightly",
                "```",
                "",
                "写操作遵守单写约束：不要同时在 Obsidian 和终端里各跑一个 `compile / nightly / apply / revert`。",
                "",
            ]
        )
        + "\n"
    )

def _render_launcher_script(runtime_root: Path) -> str:
    """Vault-local launcher: prefer runtime-repo picker (Python ≥3.10), then PATH aiwiki."""
    quoted_runtime = shlex.quote(str(runtime_root.resolve()))
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            'SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
            'VAULT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"',
            f"RUNTIME_ROOT={quoted_runtime}",
            "",
            # Prefer the runtime-repo launcher so Obsidian GUI PATH (often Apple
            # Python 3.9) still gets an explicit ≥3.10 interpreter.
            'if [ -x "$RUNTIME_ROOT/scripts/aiwiki-launcher.sh" ]; then',
            '  export AIWIKI_VAULT="$VAULT_ROOT"',
            '  exec "$RUNTIME_ROOT/scripts/aiwiki-launcher.sh" "$@"',
            "fi",
            "",
            'if command -v aiwiki >/dev/null 2>&1; then',
            '  exec aiwiki --root "$VAULT_ROOT" "$@"',
            "fi",
            "",
            'if [ ! -f "$RUNTIME_ROOT/src/aiwiki/cli/__main__.py" ]; then',
            '  echo "error: runtime root is not an aiwiki checkout and no `aiwiki` console script is on PATH: $RUNTIME_ROOT" >&2',
            "  exit 1",
            "fi",
            'export PYTHONPATH="$RUNTIME_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"',
            'exec python3 -m aiwiki.cli --root "$VAULT_ROOT" "$@"',
            "",
        ]
    )


def _render_indexes_readme() -> str:
    return (
        "\n".join(
            [
                "# wiki/indexes 策略",
                "",
                "`wiki/indexes/` 保存由 `aiwiki compile` 生成的派生索引页和看板页。",
                "",
                "- 这些文件不是 SoT。事实来源仍是 `raw/`、`wiki/sources/`、受控回流的 `wiki/derived/`、schema 文件，以及 runtime state / receipts。",
                "- 不要靠手改生成索引正文来修数据；应重新运行 compile，让索引从底层状态再生成。",
                "- 如果生成索引持续产出破链或 stale 页面，应修正发出该链接的 compile 输入或规则。",
                "- 如果生成索引对仓库太吵，应明确把生成输出移出版本控制；不要临时删除整个目录。",
                "",
                "本 README 是该目录的人读策略说明，可以手写维护。",
                "",
            ]
        )
        + "\n"
    )
