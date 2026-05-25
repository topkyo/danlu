from __future__ import annotations

from aiwiki import app_protocol
from aiwiki.protocol import descriptors, runtime_config, templates


def test_app_protocol_reexports_static_templates_from_protocol_templates():
    names = [
        "LAYOUT_DIRS",
        "DEFAULT_SCHEMA_FILES",
        "DEFAULT_DASHBOARD_FILES",
        "MANAGED_DASHBOARD_TEMPLATE_FILES",
        "CURATED_ASSET_SECTION_ORDER",
        "PROTOCOL_SECTION_FILES",
        "PROTOCOL_SECTION_TITLES",
    ]

    for name in names:
        assert getattr(app_protocol, name) is getattr(templates, name)


def test_app_protocol_reexports_protocol_descriptors():
    assert app_protocol.AGENT_PACK_LIBRARY is descriptors.AGENT_PACK_LIBRARY
    for name in [
        "protocol_title",
        "protocol_summary",
        "render_protocol_library_index",
        "render_protocol_overview",
        "render_protocol_section",
    ]:
        assert getattr(app_protocol, name) is getattr(descriptors, name)


def test_app_protocol_reexports_protocol_runtime_config():
    names = [
        "PROTOCOL_ELIXIR_REVIEW_DAYS",
        "PROTOCOL_REVIEW_WINDOWS",
        "PROTOCOL_CLASSIFICATION_MARKERS",
        "PROTOCOL_PROMOTION_PREFIXES",
        "PROTOCOL_FOCUS_KEYWORDS",
        "PROTOCOL_ACTION_KIND_WEIGHTS",
        "PROTOCOL_OUTPUT_GUIDANCE",
        "PROTOCOL_EXECUTION_POLICY_RULES",
        "PROTOCOL_QUERY_ROUTE_CONFIG",
        "CONFLICT_SIGNAL_PAIRS",
        "EVIDENCE_GAP_MARKERS",
        "DECISION_STATUSES",
        "JUDGMENT_STATUSES",
        "ACTION_STATUSES",
        "REWRITE_PROPOSAL_STATUSES",
        "ACTIVE_CORPUS_STATUSES",
        "ARCHIVE_CANDIDATE_STATUSES",
        "PENDING_DECISION_REVIEW_STATUSES",
        "PENDING_JUDGMENT_REVIEW_STATUSES",
        "PENDING_ACTION_STATUSES",
        "PENDING_REWRITE_PROPOSAL_STATUSES",
        "CONCEPT_HARDNESS_LEVELS",
        "CAUSAL_RELATION_TYPES",
        "LOW_RISK_APPLYABLE_ACTION_KINDS",
        "RESOLVABLE_MONITOR_ACTION_KINDS",
        "ACTIVE_CORPUS_TTL",
        "ARCHIVE_QUERY_STALE_AFTER",
        "EXECUTION_BAND_LABELS",
        "AGING_WINDOWS_DAYS",
        "AUTO_PROMOTION_MIN_OCCURRENCES",
        "AUTO_PROMOTION_FORMATS",
        "DECISION_QUERY_MARKERS",
        "JUDGMENT_QUERY_MARKERS",
    ]

    for name in names:
        assert getattr(app_protocol, name) is getattr(runtime_config, name)


def test_protocol_templates_keep_runtime_scaffold_contract():
    assert "raw/inbox" in templates.LAYOUT_DIRS
    assert "schema/protocols" in templates.LAYOUT_DIRS
    assert "schema/index.md" in templates.DEFAULT_SCHEMA_FILES
    assert "wiki/indexes/review-center.md" in templates.DEFAULT_DASHBOARD_FILES
    assert templates.MANAGED_DASHBOARD_TEMPLATE_FILES == (
        "wiki/indexes/review-center.md",
        "wiki/indexes/graph-view.md",
    )
    assert templates.PROTOCOL_SECTION_FILES == ("taxonomy", "decision", "judgment", "review", "nightly", "query")


def test_protocol_descriptors_render_protocol_scaffold_pages():
    assert descriptors.protocol_title("product") == "产品协议"
    assert descriptors.protocol_summary("missing") == ""
    index = descriptors.render_protocol_library_index()
    overview = descriptors.render_protocol_overview("product")
    section = descriptors.render_protocol_section("product", "query")

    assert "# 协议规则索引" in index
    assert "[产品协议](./product/index.md)" in index
    assert "# 产品协议" in overview
    assert "[查询提示](./query.md)" in overview
    assert "# 产品协议 · 查询提示" in section
    assert "这页属于 `product` 协议。" in section
