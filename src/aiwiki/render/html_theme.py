"""Shared HTML theme tokens for all aiwiki HTML dashboards.

Replaces hardcoded light-only CSS across graph / execution / furnace / review
HTML surfaces with a single source of truth that supports light and dark modes
via ``prefers-color-scheme``.
"""

from __future__ import annotations

HTML_COMMON_CSS: str = """\
  :root {
    color-scheme: light dark;
    --bg: #f8fafc;
    --bg-gradient: linear-gradient(180deg, #f8fafc 0%, #e2e8f0 100%);
    --ink: #0f172a;
    --muted: #475569;
    --faint: #94a3b8;
    --panel: rgba(255, 255, 255, 0.94);
    --line: #cbd5e1;
    --accent: #1d4ed8;
    --accent-hover: #1e40af;
    --accent-bg: #eff6ff;
    --success: #16a34a;
    --success-bg: #f0fdf4;
    --warning: #ea580c;
    --warning-bg: #fff7ed;
    --error: #dc2626;
    --error-bg: #fef2f2;
    --radius-sm: 8px;
    --radius-md: 14px;
    --radius-lg: 18px;
    --shadow-sm: 0 2px 8px rgba(15, 23, 42, 0.06);
    --shadow-md: 0 18px 40px rgba(15, 23, 42, 0.06);
    --font: 'Segoe UI', 'PingFang SC', system-ui, sans-serif;
    --font-mono: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace;
  }

  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0f172a;
      --bg-gradient: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
      --ink: #e2e8f0;
      --muted: #94a3b8;
      --faint: #64748b;
      --panel: rgba(30, 41, 59, 0.94);
      --line: #334155;
      --accent: #3b82f6;
      --accent-hover: #60a5fa;
      --accent-bg: #1e3a5f;
      --success: #22c55e;
      --success-bg: #052e16;
      --warning: #f97316;
      --warning-bg: #431407;
      --error: #ef4444;
      --error-bg: #450a0a;
      --shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.2);
      --shadow-md: 0 18px 40px rgba(0, 0, 0, 0.2);
    }
  }
"""

HTML_SHARED_STYLES: str = """\
    body {{
      margin: 0;
      padding: 24px;
      background: var(--bg-gradient);
      color: var(--ink);
      font: 14px/1.6 var(--font);
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
    }}
    h1, h2, h3 {{
      margin: 0 0 12px;
      color: var(--ink);
    }}
    p {{
      margin: 0 0 12px;
      color: var(--muted);
    }}

    /* Layout helpers */
    .meta, .cards, .lists, .grid {{
      display: grid;
      gap: 16px;
    }}
    .meta {{
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      margin: 18px 0 24px;
    }}
    .grid {{
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    }}
    .lists {{
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    }}

    /* Card */
    .card {{
      padding: 14px 16px;
    }}
    .card, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius-lg);
      box-shadow: var(--shadow-md);
    }}

    /* Panel */
    .panel {{
      padding: 20px;
      margin-bottom: 18px;
    }}

    /* Metric cards */
    .metric {{
      font-size: 24px;
      font-weight: 800;
      color: var(--accent);
    }}
    .metric-label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}

    /* Lists */
    ul {{
      margin: 0;
      padding-left: 18px;
    }}
    li {{
      margin: 6px 0;
      padding: 4px 0;
    }}

    /* Links */
    a {{
      color: var(--accent);
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
      color: var(--accent-hover);
    }}

    /* Metadata text */
    .item-meta {{
      color: var(--muted);
      font-size: 12px;
    }}

    /* Code blocks */
    code {{
      background: var(--accent-bg);
      padding: 2px 8px;
      border-radius: var(--radius-sm);
      font-family: var(--font-mono);
      font-size: 0.9em;
    }}

    /* Empty state */
    .empty {{
      padding: 16px 20px;
      background: var(--warning-bg);
      border: 1px solid var(--warning);
      border-radius: var(--radius-md);
      color: var(--warning);
      font-size: 0.95em;
    }}

    /* Status pills */
    .pill {{
      display: inline-block;
      padding: 2px 10px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 600;
    }}
    .pill-ok {{
      background: var(--success-bg);
      color: var(--success);
    }}
    .pill-warn {{
      background: var(--warning-bg);
      color: var(--warning);
    }}
    .pill-err {{
      background: var(--error-bg);
      color: var(--error);
    }}

    /* Controls (inputs, selects) */
    .controls {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      margin-bottom: 18px;
    }}
    .controls label {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 6px;
    }}
    .controls input,
    .controls select {{
      width: 100%;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      font: inherit;
      background: var(--panel);
      color: var(--ink);
      box-sizing: border-box;
    }}
"""


def html_theme_css() -> str:
    """Return the full CSS block for HTML dashboards."""
    return HTML_COMMON_CSS + "\n" + HTML_SHARED_STYLES


def html_theme_styles() -> str:
    """Return <style>…</style> block ready for HTML embedding."""
    return f"  <style>\n{html_theme_css()}\n  </style>"


def html_meta_theme() -> str:
    """Return <meta> tags for theme support."""
    return (
        '  <meta charset="utf-8" />\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1" />\n'
        '  <meta name="color-scheme" content="light dark" />'
    )
