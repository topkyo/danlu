from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_compile import compile_wiki
from aiwiki.app_content import ingest_source, sync_manifest_with_raw
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import append_runtime_history, load_machine_memory, load_output_candidates_state
from aiwiki.app_utils import parse_frontmatter, relative_path
from aiwiki.config import LLMConfig
from aiwiki.drop import drop_note
from aiwiki.execution.ask import ask_question
from aiwiki.llm import CompletionResult, LLMError
from aiwiki.runner import (
    _append_jsonl_log,
    _append_llm_receipt,
    _append_log,
    _build_ask_prompt,
    _build_compile_prompt,
    _build_concept_compile_prompt,
    _build_lint_prompt,
    _client_model_name,
    _context_budget,
    _dedupe_report_citations,
    _extract_related_concept_slugs,
    _fit_log_prompt_section,
    _fit_prompt_section,
    _load_prompt,
    _normalize_markdown,
    _pending_summary_count,
    _protocol_context,
    _read_context,
    _reinject_candidate_frontmatter,
    _render_machine_query,
    _rewrite_candidate_record,
    _rewrite_candidate_slugs,
    _schema_context,
    _system_prompt,
    _validate_concept_page,
    _validate_output_markdown,
    _validate_source_page,
    _write_automation_state,
    create_client,
    llm_probe,
    llm_status,
    promote_recurring_outputs,
    run_ask,
    run_compile,
    run_lint,
    run_nightly,
)
from aiwiki.runner.workflows import _safe_quoted_report_reference_paths, run_ask_resume, run_ask_submit

_VALID_REPORT_BODY = (
    "---\nid: query-stub\nkind: output\nformat: report\n---\n\n"
    "# Stub answer\n\n"
    "## 结论\nStubbed conclusion.\n\n"
    "## 关键证据\n"
    "- See wiki/sources/source-1.md\n"
    "- Secondary evidence point.\n"
    "- Tertiary evidence point.\n\n"
    "## 反证与不确定性\n- None observed in stub.\n\n"
    "## 行动建议\n- Stub follow-up.\n\n"
    "## 下次观察信号\n- Stub revisit signal.\n\n"
    "## 引用\n- wiki/sources/source-1.md\n"
)


def _load_jsonl_records(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class _DummyClient:
    def __init__(self) -> None:
        self.config = type("Config", (), {"model": "dummy-model"})()

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        del system_prompt
        del user_prompt
        raise AssertionError("complete should not be called in this test")


class _BackendFailoverAskClient:
    def __init__(self, response_text: str | None = None) -> None:
        self.response_text = response_text or _VALID_REPORT_BODY
        self.config = type(
            "Config",
            (),
            {"model": "deepseek-v4-pro", "backend": "opencode-api", "backend_requested": "opencode-api", "timeout_seconds": 120},
        )()

    def advance_model(self) -> bool:
        if self.config.backend == "codex-cli":
            return False
        self.config = type(
            "Config",
            (),
            {"model": "gpt-5.5", "backend": "codex-cli", "backend_requested": "opencode-api", "timeout_seconds": 120},
        )()
        return True

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        del system_prompt, user_prompt
        if self.config.backend == "opencode-api":
            raise LLMError("LLM endpoint timed out after 120 seconds.")
        return CompletionResult(text=self.response_text, response_id="resp_failover", usage={"total_tokens": 6})


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)
        for name in ("compile.md", "ask.md", "lint.md"):
            (self.root / "prompts" / name).write_text(f"{name} fixture\n", encoding="utf-8")
        for name in ("index.md", "citations.md", "conflicts.md", "writeback.md", "taxonomy.md"):
            (self.root / "schema" / name).write_text(f"# {name}\n\nschema fixture\n", encoding="utf-8")
        for name in ("index.md", "taxonomy.md", "query.md", "review.md", "nightly.md", "decision.md", "judgment.md"):
            path = self.root / "schema" / "protocols" / "general" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {name}\n\nprotocol fixture\n", encoding="utf-8")
        self.sample = self.root / "sample.md"
        self.sample.write_text(
            "# Transformer Scaling\n\nTransformers benefit from scale.\nInference costs also rise.\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_llm_status_and_create_client_delegate_to_backend_layers(self) -> None:
        fake_status = {"configured": True, "max_context_chars": 12345}
        fake_client = object()
        with patch("aiwiki.runner.clients.LLMConfig.status_from_env", return_value=fake_status):
            self.assertEqual(llm_status(), fake_status)
        fake_config = LLMConfig(backend="codex-cli", timeout_seconds=120)
        with patch("aiwiki.runner.clients.LLMConfig.from_env", return_value=fake_config):
            with patch("aiwiki.runner.clients.create_backend_client", return_value=fake_client) as create_backend_client:
                self.assertIs(create_client(self.root), fake_client)
                self.assertIs(create_client(self.root, timeout_seconds=45), fake_client)
        calls = create_backend_client.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].args[0].timeout_seconds, 120)
        self.assertEqual(calls[1].args[0].timeout_seconds, 45)
        self.assertEqual(calls[0].args[1], self.root)
        self.assertEqual(calls[1].args[1], self.root)

    def test_append_llm_receipt_writes_universal_audit(self) -> None:
        event = {
            "event": "run-ask",
            "status": "failed",
            "protocol": "research",
            "run_id": "run-1",
            "trace_id": "trace-llm",
            "model_selected": "stub-model",
        }

        _append_llm_receipt(self.root, event)
        _append_llm_receipt(self.root, event)

        receipt_lines = (self.root / ".aiwiki/logs/llm-receipts.jsonl").read_text(encoding="utf-8").splitlines()
        audit_records = [
            json.loads(line)
            for line in (self.root / ".aiwiki/state/audit.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        receipt_records = [json.loads(line) for line in receipt_lines if line.strip()]
        self.assertEqual(len(receipt_records), 2)
        self.assertTrue(all(record["event"] == "run-ask" for record in receipt_records))
        self.assertTrue(all(record["created_at"] for record in receipt_records))
        self.assertEqual(len(audit_records), 2)
        self.assertEqual(audit_records[0]["source_stream"], "llm_receipts")
        self.assertEqual(audit_records[0]["source_ref"], ".aiwiki/logs/llm-receipts.jsonl#L1")
        self.assertEqual(audit_records[0]["event_type"], "failed")
        self.assertEqual(audit_records[0]["occurred_at"], receipt_records[0]["created_at"])
        self.assertEqual(audit_records[0]["trace_id"], "trace-llm")
        self.assertEqual(audit_records[0]["subject"], {"kind": "failed", "id": "run-1"})
        self.assertFalse(audit_records[0]["revert_supported"])
        self.assertEqual(audit_records[1]["source_ref"], ".aiwiki/logs/llm-receipts.jsonl#L2")
        self.assertNotEqual(audit_records[0]["audit_event_id"], audit_records[1]["audit_event_id"])

    def test_append_jsonl_log_propagates_fsync_failure(self) -> None:
        with patch.object(os, "fsync", side_effect=OSError("fsync failed")):
            with self.assertRaises(OSError):
                _append_jsonl_log(self.root, ".aiwiki/logs/runs.jsonl", {"event": "run-ask"})

    def test_run_ask_direct_note_uses_lightweight_llm_without_ranking_context(self) -> None:
        class _DirectClient:
            def __init__(self) -> None:
                self.config = type("Config", (), {"model": "gpt-5.5", "backend": "opencode-api", "timeout_seconds": 45})()
                self.prompts: list[str] = []

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                self.prompts.append(user_prompt)
                self.assert_direct_prompt(system_prompt)
                return CompletionResult(text="我是当前配置的 LLM。", response_id="resp_direct", usage={"total_tokens": 8})

            def assert_direct_prompt(self, system_prompt: str) -> None:
                self.prompts.append(f"system:{system_prompt}")

        client = _DirectClient()
        with patch("aiwiki.runner.workflows_ask.ask_question") as deterministic_ask:
            result = run_ask(self.root, "你是什么大模型？", "note", client=client, direct=True)

        deterministic_ask.assert_not_called()
        self.assertEqual(result["delivery_mode"], "llm-direct")
        self.assertEqual(result["format"], "note")
        self.assertEqual(result["model_final"], "gpt-5.5")
        self.assertEqual(client.prompts[0], "你是什么大模型？")
        artifact = self.root / result["path"]
        content = artifact.read_text(encoding="utf-8")
        self.assertIn('delivery_mode: "llm-direct"', content)
        self.assertIn("# 你是什么大模型？", content)
        self.assertIn("我是当前配置的 LLM。", content)
        receipt = json.loads((self.root / ".aiwiki/logs/llm-receipts.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(receipt["event"], "run-ask-direct")
        self.assertEqual(receipt["status"], "success")

    def test_run_ask_quoted_report_note_uses_report_as_llm_material_context(self) -> None:
        report = self.root / "output" / "reports" / "炼丹炉-md-files-note.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            "---\n"
            'id: "quoted-report"\n'
            'kind: "output"\n'
            'format: "note"\n'
            'query: "炼丹炉有多少 md 文件"\n'
            "---\n\n"
            "# 炼丹炉 Markdown 文件统计\n\n"
            "当前仓库有 42 个 Markdown 文件。\n"
            "授权方式：把文件放入当前 vault，或通过引用报告路径提供上下文。\n",
            encoding="utf-8",
        )

        class _QuotedReportClient:
            def __init__(self) -> None:
                self.config = type("Config", (), {"model": "deepseek-v4-pro", "backend": "opencode-api", "timeout_seconds": 45})()
                self.system_prompts: list[str] = []
                self.user_prompts: list[str] = []

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                self.system_prompts.append(system_prompt)
                self.user_prompts.append(user_prompt)
                return CompletionResult(
                    text="根据引用报告，当前有 42 个 Markdown 文件；授权方式是把材料放进 vault 或用引用报告提供上下文。",
                    response_id="resp_quoted_report",
                    usage={"total_tokens": 18},
                )

        question = "引用报告：output/reports/炼丹炉-md-files-note.md\n如何给于你权限去访问呢？"
        client = _QuotedReportClient()
        with patch("aiwiki.runner.workflows_ask.ask_question") as deterministic_ask:
            result = run_ask(self.root, question, "note", client=client, direct=True)

        deterministic_ask.assert_not_called()
        self.assertEqual(result["delivery_mode"], "llm-direct")
        self.assertEqual(result["format"], "note")
        self.assertEqual(result["material_refs"], ["output/reports/炼丹炉-md-files-note.md"])
        self.assertIn("材料问答助手", client.system_prompts[0])
        self.assertIn("用户问题：如何给于你权限去访问呢？", client.user_prompts[0])
        self.assertIn("材料摘录：", client.user_prompts[0])
        self.assertIn("当前仓库有 42 个 Markdown 文件", client.user_prompts[0])
        self.assertIn("授权方式：把文件放入当前 vault", client.user_prompts[0])
        self.assertNotIn("引用报告：output/reports", client.user_prompts[0])
        artifact = self.root / result["path"]
        self.assertEqual(artifact.name, "如何给于你权限去访问呢-note.md")
        content = artifact.read_text(encoding="utf-8")
        self.assertIn("# 如何给于你权限去访问呢？", content)
        self.assertIn("根据引用报告，当前有 42 个 Markdown 文件", content)
        self.assertNotIn("引用报告：output/reports", content)
        receipt = json.loads((self.root / ".aiwiki/logs/llm-receipts.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(receipt["event"], "run-ask-direct")
        self.assertEqual(receipt["status"], "success")
        self.assertEqual(receipt["material_refs"], ["output/reports/炼丹炉-md-files-note.md"])

    def test_run_ask_quoted_report_report_uses_clean_question_and_material_context(self) -> None:
        report = self.root / "output" / "reports" / "base-note.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            "---\nformat: note\n---\n\n# Base Note\n\n特朗普访华预期是不翻车即双赢，需要关注关税法律工具和随行企业信号。\n",
            encoding="utf-8",
        )

        class _ReportClient:
            def __init__(self) -> None:
                self.config = type("Config", (), {"model": "deepseek-v4-pro", "backend": "opencode-api", "timeout_seconds": 120})()
                self.user_prompt = ""

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                self.user_prompt = user_prompt
                return CompletionResult(text=_VALID_REPORT_BODY, response_id="resp_report", usage={"total_tokens": 20})

        question = "引用报告：output/reports/base-note.md\n基于原投料，做个分析评估生成一份详细报告"
        client = _ReportClient()
        result = run_ask(self.root, question, "report", client=client, lean=True)

        self.assertEqual(result["format"], "report")
        self.assertEqual(result["material_refs"], ["output/reports/base-note.md"])
        self.assertIn("## Quoted Report / Material Context", client.user_prompt)
        self.assertIn("特朗普访华预期是不翻车即双赢", client.user_prompt)
        self.assertNotIn("引用报告：output/reports", client.user_prompt)
        artifact = self.root / result["path"]
        self.assertEqual(artifact.name, "基于原投料-做个分析评估生成一份详细报告.md")
        content = artifact.read_text(encoding="utf-8")
        self.assertIn("# Stub answer", content)
        self.assertNotIn("引用报告：output/reports", content)

    def test_quoted_report_reference_paths_must_stay_under_output_reports(self) -> None:
        reports_dir = self.root / "output" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "safe.md").write_text("# Safe report\n", encoding="utf-8")
        secret = self.root / "raw" / "inbox" / "secret.md"
        secret.parent.mkdir(parents=True, exist_ok=True)
        secret.write_text("# Secret\n", encoding="utf-8")
        refs = [
            "output/reports/safe.md",
            "output/reports/../../raw/inbox/secret.md",
            r"output/reports/..\\..\\raw\\inbox\\secret.md",
        ]
        symlink_path = reports_dir / "linked-secret.md"
        try:
            symlink_path.symlink_to(secret)
        except OSError:
            pass
        else:
            refs.append("output/reports/linked-secret.md")

        self.assertEqual(_safe_quoted_report_reference_paths(self.root, refs), ["output/reports/safe.md"])

    def test_run_ask_elixir_count_uses_local_stats_before_direct_llm(self) -> None:
        elixir_dir = self.root / "wiki" / "elixirs"
        elixir_dir.mkdir(parents=True, exist_ok=True)
        (elixir_dir / "elixir-a.md").write_text(
            '---\nid: "elixir-a"\nkind: "elixir"\nelixir_state: "settled"\ntopic: "第一个金丹"\n---\n\n# Elixir\n',
            encoding="utf-8",
        )
        (elixir_dir / "elixir-b.md").write_text(
            '---\nid: "elixir-b"\nkind: "elixir"\nelixir_state: "settled"\ntopic: "第二个金丹"\n---\n\n# Elixir\n',
            encoding="utf-8",
        )
        candidate_dir = self.root / "output" / "_candidates" / "elixirs"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        (candidate_dir / "candidate.md").write_text("# Candidate\n", encoding="utf-8")

        question = "# 引用报告：output/reports/目前炼丹炉有几个金丹-note.md 当前炼丹炉valut这个仓库有几个金丹？"
        with patch("aiwiki.runner.workflows_ask.ask_question") as deterministic_ask, patch(
            "aiwiki.runner.preflight.preflight_check_backend",
            side_effect=AssertionError("local elixir stats must not probe backend"),
        ):
            result = run_ask(self.root, question, "note", direct=True)

        deterministic_ask.assert_not_called()
        self.assertEqual(result["delivery_mode"], "local-deterministic")
        self.assertEqual(result["settled_elixir_count"], 2)
        self.assertEqual(result["candidate_elixir_count"], 1)
        self.assertIn("当前炼丹炉vault这个仓库有几个金丹？", result["clean_question"])
        artifact = self.root / result["path"]
        content = artifact.read_text(encoding="utf-8")
        self.assertIn("generated_by: \"aiwiki-local-elixir-stats\"", content)
        self.assertIn("cssclasses:", content)
        self.assertIn('  - "aiwiki-output"', content)
        self.assertIn("当前 vault 已沉淀金丹 **2 个**", content)
        self.assertIn("候选金丹 **1 个**", content)
        self.assertIn("[第一个金丹](wiki/elixirs/elixir-a.md)", content)
        receipt = json.loads((self.root / ".aiwiki/logs/llm-receipts.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(receipt["event"], "run-ask-local-elixir-stats")
        self.assertEqual(receipt["status"], "success")

    def test_run_ask_direct_note_marks_backend_failover_stage(self) -> None:
        with patch("aiwiki.runner.workflows_ask.ask_question") as deterministic_ask:
            result = run_ask(
                self.root,
                "你是什么大模型？",
                "note",
                client=_BackendFailoverAskClient(response_text="我是备用 Codex。"),
                direct=True,
            )

        deterministic_ask.assert_not_called()
        self.assertEqual(result["delivery_mode"], "llm-direct")
        self.assertEqual(result["backend_requested"], "opencode-api")
        self.assertEqual(result["backend_effective"], "codex-cli")
        self.assertEqual(result["model_selected"], "deepseek-v4-pro")
        self.assertEqual(result["model_final"], "gpt-5.5")
        self.assertEqual(result["fallback_stage"], "backend-failover")
        receipt = json.loads((self.root / ".aiwiki/logs/llm-receipts.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(receipt["event"], "run-ask-direct")
        self.assertEqual(receipt["fallback_stage"], "backend-failover")
        self.assertEqual(receipt["backend_effective"], "codex-cli")

    def test_run_ask_direct_note_rejects_template_answer_before_success(self) -> None:
        class _TemplateThenValidClient:
            def __init__(self) -> None:
                self.config = type(
                    "Config",
                    (),
                    {"model": "deepseek-v4-pro", "backend": "opencode-api", "backend_requested": "opencode-api", "timeout_seconds": 45},
                )()
                self.calls = 0

            def advance_model(self) -> bool:
                if self.config.backend == "codex-cli":
                    return False
                self.config = type(
                    "Config",
                    (),
                    {"model": "gpt-5.5", "backend": "codex-cli", "backend_requested": "opencode-api", "timeout_seconds": 45},
                )()
                return True

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt, user_prompt
                self.calls += 1
                if self.calls == 1:
                    return CompletionResult(text="_LLM: 请用 2–5 段自然语言直接回答。", response_id="resp_template", usage={})
                return CompletionResult(text="当前配置的备用模型是 gpt-5.5。", response_id="resp_valid", usage={"total_tokens": 7})

        with patch("aiwiki.runner.workflows_ask.ask_question") as deterministic_ask:
            result = run_ask(
                self.root,
                "你是什么模型？",
                "note",
                client=_TemplateThenValidClient(),
                direct=True,
            )

        deterministic_ask.assert_not_called()
        self.assertEqual(result["delivery_mode"], "llm-direct")
        self.assertEqual(result["backend_effective"], "codex-cli")
        self.assertEqual(result["fallback_stage"], "backend-failover")
        content = (self.root / result["path"]).read_text(encoding="utf-8")
        self.assertIn("当前配置的备用模型是 gpt-5.5。", content)
        self.assertNotIn("_LLM:", content)

    def test_run_ask_material_note_uses_extracted_material_context_without_ranking_context(self) -> None:
        raw_note = self.root / "raw" / "inbox" / "image-note.md"
        raw_note.parent.mkdir(parents=True, exist_ok=True)
        raw_note.write_text("---\ntitle: image\n---\n\n## Extracted Text\nMass to Orbit: SpaceX 841.0t. Rest of World 128.6t.\n", encoding="utf-8")

        class _MaterialClient:
            def __init__(self) -> None:
                self.config = type("Config", (), {"model": "deepseek-v4-pro", "backend": "opencode-api", "timeout_seconds": 45})()
                self.user_prompts: list[str] = []

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                self.user_prompts.append(user_prompt)
                self.assert_system_prompt(system_prompt)
                return CompletionResult(text="图片显示 SpaceX 2026 YTD 入轨质量显著高于其他地区。", response_id="resp_material", usage={"total_tokens": 12})

            def assert_system_prompt(self, system_prompt: str) -> None:
                self.user_prompts.append(f"system:{system_prompt}")

        question = "图片内容？\n\n请优先使用本次投喂材料回答；材料路径供系统路由使用：raw/inbox/image-note.md、raw/assets/image.jpeg"
        client = _MaterialClient()
        with patch("aiwiki.runner.workflows_ask.ask_question") as deterministic_ask:
            result = run_ask(self.root, question, "note", client=client)

        deterministic_ask.assert_not_called()
        self.assertEqual(result["delivery_mode"], "llm-direct")
        self.assertEqual(result["format"], "note")
        self.assertEqual(result["material_refs"], ["raw/inbox/image-note.md", "raw/assets/image.jpeg"])
        self.assertIn("用户问题：图片内容？", client.user_prompts[0])
        self.assertIn("Mass to Orbit", client.user_prompts[0])
        artifact = self.root / result["path"]
        content = artifact.read_text(encoding="utf-8")
        self.assertIn("# 图片内容？", content)
        self.assertIn("SpaceX 2026 YTD", content)

    def test_run_ask_markdown_count_uses_local_stats_before_direct_llm(self) -> None:
        (self.root / "raw" / "inbox").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "sources").mkdir(parents=True, exist_ok=True)
        (self.root / "raw" / "inbox" / "a.md").write_text("# A\n", encoding="utf-8")
        (self.root / "wiki" / "sources" / "b.md").write_text("# B\n", encoding="utf-8")

        class _UnexpectedClient:
            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt, user_prompt
                raise AssertionError("local markdown stats must not call LLM")

        result = run_ask(self.root, "炼丹炉有多少md文件？", "note", client=_UnexpectedClient(), direct=True)

        self.assertEqual(result["delivery_mode"], "local-deterministic")
        self.assertGreaterEqual(result["markdown_file_count"], 2)
        content = (self.root / result["path"]).read_text(encoding="utf-8")
        self.assertIn(f"当前 vault 中可见 Markdown 文件共 **{result['markdown_file_count']} 个**", content)
        self.assertIn("`raw/`：1 个", content)
        self.assertIn("`wiki/`：", content)
        self.assertIn("raw/inbox/a.md", content)
        self.assertIn('generated_by: "aiwiki-local-markdown-stats"', content)

    def test_run_ask_direct_note_supplies_relevant_vault_context_to_llm(self) -> None:
        source = self.root / "wiki" / "sources" / "source-vla.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            "---\ntitle: VLA 技术路线\n---\n\n# VLA 技术路线\n\n机器人技术路线包括 VLA、端到端和模块化控制。投资判断关注数据闭环与部署安全。\n",
            encoding="utf-8",
        )

        class _VaultContextClient:
            def __init__(self) -> None:
                self.config = type("Config", (), {"model": "deepseek-v4-pro", "backend": "opencode-api", "timeout_seconds": 45})()
                self.user_prompt = ""

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                self.user_prompt = user_prompt
                if "材料问答助手" not in system_prompt:
                    raise AssertionError("system prompt should use the material QA profile")
                return CompletionResult(text="本地材料显示，机器人路线至少包括 VLA、端到端和模块化控制。", response_id="resp_vault", usage={})

        client = _VaultContextClient()
        result = run_ask(self.root, "当前机器人路线总共有几条技术路线？", "note", client=client, direct=True)

        self.assertEqual(result["delivery_mode"], "llm-direct")
        self.assertIn("## wiki/sources/source-vla.md", client.user_prompt)
        self.assertIn("机器人技术路线包括 VLA", client.user_prompt)
        content = (self.root / result["path"]).read_text(encoding="utf-8")
        self.assertIn("VLA、端到端和模块化控制", content)

    def test_run_ask_material_note_fails_without_deterministic_fallback_when_llm_times_out(self) -> None:
        raw_note = self.root / "raw" / "inbox" / "pdf-note.md"
        raw_note.parent.mkdir(parents=True, exist_ok=True)
        raw_note.write_text(
            "---\ntitle: pdf\n---\n\n## Extracted Text\n特朗普访华成果预期：不翻车即双赢。\n",
            encoding="utf-8",
        )

        class _TimeoutClient:
            def __init__(self) -> None:
                self.config = type("Config", (), {"model": "deepseek-v4-pro", "backend": "opencode-api", "timeout_seconds": 45})()

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt, user_prompt
                raise LLMError("LLM endpoint timed out after 45 seconds.")

        question = "分析下内容\n\n请优先使用本次投喂材料回答；材料路径供系统路由使用：raw/inbox/pdf-note.md、raw/assets/pdf.pdf"
        with patch("aiwiki.runner.workflows_ask.ask_question") as deterministic_ask:
            with self.assertRaisesRegex(LLMError, "timed out"):
                run_ask(self.root, question, "note", client=_TimeoutClient())

        deterministic_ask.assert_not_called()
        receipt = json.loads((self.root / ".aiwiki/logs/llm-receipts.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(receipt["event"], "run-ask-direct")
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["delivery_mode"], "llm-failed")

    def test_run_ask_uses_lean_prompt_immediately_when_requested(self) -> None:
        artifact_path = self.root / "output" / "reports" / "query-lean.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("---\nid: query-lean\nkind: report\n---\n\n# Placeholder\n", encoding="utf-8")
        artifact = {
            "path": "output/reports/query-lean.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": [],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
            "graph_anchor_node_ids": ["source:source-1"],
        }

        class _LeanClient:
            def __init__(self) -> None:
                self.config = type("Config", (), {"model": "gpt-5.4", "timeout_seconds": 120})()
                self.prompts: list[str] = []

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                self.prompts.append(user_prompt)
                return CompletionResult(
                    text=_VALID_REPORT_BODY,
                    response_id="resp_lean",
                    usage={},
                )

        client = _LeanClient()
        with patch("aiwiki.runner.workflows_ask.ask_question", return_value=artifact):
            with patch("aiwiki.runner.workflows_ask._build_ask_prompt", return_value="lean prompt") as build_prompt:
                result = run_ask(self.root, "测试", "report", client=client, lean=True)

        self.assertEqual(result["prompt_profile"], "lean")
        self.assertEqual(result["retry_prompt_profile"], "")
        self.assertEqual(client.prompts, ["lean prompt"])
        build_prompt.assert_called_once()
        self.assertEqual(build_prompt.call_args.kwargs["prompt_profile"], "lean")
        self.assertEqual(result["timeout_seconds"], 120)
        self.assertTrue(result["run_id"])
        self.assertTrue(result["run_notes_path"].startswith("output/control/runs/"))
        notes = (self.root / result["run_notes_path"]).read_text(encoding="utf-8")
        self.assertIn('status: "llm-complete"', notes)
        self.assertIn("Visible Run Progress", notes)
        self.assertIn("Safety Boundary", notes)
        self.assertNotIn("<thought>", notes)
        self.assertNotIn(str(self.root), notes)
        output_frontmatter = parse_frontmatter(artifact_path.read_text(encoding="utf-8"))
        self.assertEqual(output_frontmatter["run_id"], result["run_id"])
        self.assertEqual(output_frontmatter["run_notes_path"], result["run_notes_path"])

    def test_run_ask_marks_backend_failover_stage_in_report_receipts(self) -> None:
        artifact_path = self.root / "output" / "reports" / "query-backend-failover.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("---\nid: query-backend-failover\nkind: report\n---\n\n# Placeholder\n", encoding="utf-8")
        artifact = {
            "path": "output/reports/query-backend-failover.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": ["source-1"],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
        }

        with patch("aiwiki.runner.workflows_ask.ask_question", return_value=artifact):
            with patch("aiwiki.runner.workflows_ask._build_ask_prompt", return_value="report prompt"):
                result = run_ask(self.root, "测试", "report", client=_BackendFailoverAskClient(), lean=True)

        self.assertEqual(result["backend_requested"], "opencode-api")
        self.assertEqual(result["backend_effective"], "codex-cli")
        self.assertEqual(result["model_selected"], "deepseek-v4-pro")
        self.assertEqual(result["model_final"], "gpt-5.5")
        self.assertEqual(result["fallback_stage"], "backend-failover")
        receipt = json.loads((self.root / ".aiwiki/logs/llm-receipts.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(receipt["event"], "run-ask")
        self.assertEqual(receipt["fallback_stage"], "backend-failover")
        self.assertEqual(receipt["backend_effective"], "codex-cli")
        self.assertEqual(receipt["model_final"], "gpt-5.5")

    def test_run_ask_success_preserves_deterministic_source_files_and_writes_execution_receipts(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        judgment_path = self.root / "wiki" / "judgments" / "j1.md"
        judgment_path.parent.mkdir(parents=True, exist_ok=True)
        judgment_path.write_text("---\nid: j1\nkind: judgment\n---\n\n# Judgment\n", encoding="utf-8")

        artifact_path = self.root / "output" / "reports" / "query-receipt-proof.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            "---\n"
            "id: query-receipt-proof\n"
            "kind: output\n"
            "format: report\n"
            "source_files:\n"
            '  - "wiki/judgments/j1.md"\n'
            "---\n\n"
            "# Placeholder\n",
            encoding="utf-8",
        )
        artifact = {
            "path": "output/reports/query-receipt-proof.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": [entry["id"]],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
        }
        llm_report = (
            "---\n"
            "id: query-receipt-proof\n"
            "kind: output\n"
            "format: report\n"
            "---\n\n"
            "# Stub answer\n\n"
            "## 结论\nStubbed conclusion.\n\n"
            "## 关键证据\n"
            f"- See wiki/sources/{entry['id']}.md\n"
            "- Secondary evidence point.\n"
            "- Tertiary evidence point.\n\n"
            "## 反证与不确定性\n- None observed in stub.\n\n"
            "## 行动建议\n- Stub follow-up.\n\n"
            "## 下次观察信号\n- Stub revisit signal.\n\n"
            "## 引用\n"
            f"- wiki/sources/{entry['id']}.md\n"
        )

        class _SuccessClient:
            def __init__(self) -> None:
                self.config = type(
                    "Config",
                    (),
                    {"model": "gpt-5.5", "backend": "codex-cli", "backend_requested": "codex-cli", "timeout_seconds": 45},
                )()

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt, user_prompt
                return CompletionResult(text=llm_report, response_id="resp_receipt_proof", usage={"total_tokens": 9})

        with patch("aiwiki.runner.workflows_ask.ask_question", return_value=artifact):
            result = run_ask(self.root, "Compare transformer scaling tradeoffs", "report", client=_SuccessClient())

        final_frontmatter = parse_frontmatter(artifact_path.read_text(encoding="utf-8"))
        self.assertEqual(final_frontmatter["source_files"], ["wiki/judgments/j1.md"])
        self.assertEqual(result["path"], "output/reports/query-receipt-proof.md")

        receipt_history = _load_jsonl_records(self.root / ".aiwiki" / "state" / "execution-receipts.jsonl")
        matching_history = [
            record
            for record in receipt_history
            if record.get("operation") == "run-ask"
            and record.get("status") == "success"
            and record.get("target_file") == result["path"]
            and record.get("primary_path") == result["path"]
        ]
        self.assertTrue(matching_history, receipt_history)

        receipt_files = []
        receipt_dir = self.root / "output" / "control" / "execution-receipts"
        if receipt_dir.exists():
            receipt_files = [
                (path, json.loads(path.read_text(encoding="utf-8")))
                for path in receipt_dir.rglob("*.json")
            ]
        matching_receipts = [
            (path, payload)
            for path, payload in receipt_files
            if payload.get("operation") == "run-ask"
            and payload.get("status") == "success"
            and payload.get("target_file") == result["path"]
            and payload.get("primary_path") == result["path"]
        ]
        self.assertTrue(matching_receipts, receipt_files)
        receipt_path, receipt_payload = matching_receipts[-1]
        self.assertEqual(receipt_payload["receipt_path"], relative_path(self.root, receipt_path))

    def test_run_ask_drops_llm_injected_provenance(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        artifact_path = self.root / "output" / "reports" / "query-forged-proof.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            "---\n"
            "id: query-forged-proof\n"
            "kind: output\n"
            "format: report\n"
            "source_files:\n"
            f'  - "wiki/sources/{entry["id"]}.md"\n'
            "---\n\n"
            "# Placeholder\n",
            encoding="utf-8",
        )
        artifact = {
            "path": "output/reports/query-forged-proof.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": [entry["id"]],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
        }
        llm_report = (
            "---\n"
            "id: query-forged-proof\n"
            "kind: output\n"
            "format: report\n"
            "source_files:\n"
            '  - "wiki/judgments/forged.md"\n'
            "derived_from:\n"
            '  - "wiki/elixirs/forged.md"\n'
            "---\n\n"
            "# Stub answer\n\n"
            "## 结论\nStubbed conclusion.\n\n"
            "## 关键证据\n"
            f"- See wiki/sources/{entry['id']}.md\n"
            "- Secondary evidence point.\n"
            "- Tertiary evidence point.\n\n"
            "## 反证与不确定性\n- None observed in stub.\n\n"
            "## 行动建议\n- Stub follow-up.\n\n"
            "## 下次观察信号\n- Stub revisit signal.\n\n"
            "## 引用\n"
            f"- wiki/sources/{entry['id']}.md\n"
        )

        class _ForgeryClient:
            def __init__(self) -> None:
                self.config = type(
                    "Config",
                    (),
                    {"model": "gpt-5.5", "backend": "codex-cli", "backend_requested": "codex-cli", "timeout_seconds": 45},
                )()

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt, user_prompt
                return CompletionResult(text=llm_report, response_id="resp_forged", usage={"total_tokens": 9})

        with patch("aiwiki.runner.workflows_ask.ask_question", return_value=artifact):
            run_ask(self.root, "Compare transformer scaling tradeoffs", "report", client=_ForgeryClient())

        final_frontmatter = parse_frontmatter(artifact_path.read_text(encoding="utf-8"))
        self.assertEqual(final_frontmatter["source_files"], [f"wiki/sources/{entry['id']}.md"])
        self.assertNotIn("derived_from", final_frontmatter)

    def test_run_ask_preserves_runtime_curated_provenance_when_llm_adds_forged_refs(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        judgment_path = self.root / "wiki" / "judgments" / "j-runtime.md"
        judgment_path.parent.mkdir(parents=True, exist_ok=True)
        judgment_path.write_text("---\nid: j-runtime\nkind: judgment\n---\n\n# Runtime Judgment\n", encoding="utf-8")

        artifact_path = self.root / "output" / "reports" / "query-runtime-proof.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            "---\n"
            "id: query-runtime-proof\n"
            "kind: output\n"
            "format: report\n"
            "source_files:\n"
            f'  - "wiki/sources/{entry["id"]}.md"\n'
            '  - "wiki/judgments/j-runtime.md"\n'
            "---\n\n"
            "# Placeholder\n",
            encoding="utf-8",
        )
        artifact = {
            "path": "output/reports/query-runtime-proof.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": [entry["id"]],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
        }
        llm_report = (
            "---\n"
            "id: query-runtime-proof\n"
            "kind: output\n"
            "format: report\n"
            "source_files:\n"
            '  - "wiki/judgments/forged.md"\n'
            "derived_from:\n"
            '  - "wiki/elixirs/forged.md"\n'
            "---\n\n"
            "# Stub answer\n\n"
            "## 结论\nStubbed conclusion.\n\n"
            "## 关键证据\n"
            f"- See wiki/sources/{entry['id']}.md\n"
            "- Secondary evidence point.\n"
            "- Tertiary evidence point.\n\n"
            "## 反证与不确定性\n- None observed in stub.\n\n"
            "## 行动建议\n- Stub follow-up.\n\n"
            "## 下次观察信号\n- Stub revisit signal.\n\n"
            "## 引用\n"
            f"- wiki/sources/{entry['id']}.md\n"
        )

        class _ForgeryClient:
            def __init__(self) -> None:
                self.config = type(
                    "Config",
                    (),
                    {"model": "gpt-5.5", "backend": "codex-cli", "backend_requested": "codex-cli", "timeout_seconds": 45},
                )()

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt, user_prompt
                return CompletionResult(text=llm_report, response_id="resp_runtime_proof", usage={"total_tokens": 9})

        with patch("aiwiki.runner.workflows_ask.ask_question", return_value=artifact):
            run_ask(self.root, "Compare transformer scaling tradeoffs", "report", client=_ForgeryClient())

        final_frontmatter = parse_frontmatter(artifact_path.read_text(encoding="utf-8"))
        self.assertEqual(
            final_frontmatter["source_files"],
            [f"wiki/sources/{entry['id']}.md", "wiki/judgments/j-runtime.md"],
        )
        self.assertNotIn("derived_from", final_frontmatter)

    def test_run_ask_execution_receipt_failure_rolls_back_artifact(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        artifact_path = self.root / "output" / "reports" / "query-receipt-fails.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        original = "---\nid: query-receipt-fails\nkind: output\nformat: report\n---\n\n# Original\n"
        artifact_path.write_text(original, encoding="utf-8")
        artifact = {
            "path": "output/reports/query-receipt-fails.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": [entry["id"]],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
        }

        class _SuccessClient:
            def __init__(self) -> None:
                self.config = type(
                    "Config",
                    (),
                    {"model": "gpt-5.5", "backend": "codex-cli", "backend_requested": "codex-cli", "timeout_seconds": 45},
                )()

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt, user_prompt
                return CompletionResult(text=_VALID_REPORT_BODY, response_id="resp_receipt_fail", usage={"total_tokens": 9})

        with patch("aiwiki.runner.workflows_ask.ask_question", return_value=artifact):
            with patch("aiwiki.runner.workflows_ask.write_execution_receipt", side_effect=RuntimeError("receipt failed")):
                with self.assertRaises(RuntimeError):
                    run_ask(self.root, "Compare transformer scaling tradeoffs", "report", client=_SuccessClient())

        self.assertEqual(artifact_path.read_text(encoding="utf-8"), original)

    def test_run_ask_submit_and_resume_reuse_existing_background_manifest_artifact(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        backend_preflight = {
            "backend_requested": "codex-cli",
            "backend": "codex-cli",
            "model_requested": "gpt-5.5",
            "model": "gpt-5.5",
            "compatibility": "compatible",
        }

        with patch("aiwiki.runner.preflight.preflight_check_backend_chain", return_value=backend_preflight):
            submitted = run_ask_submit(
                self.root,
                "Compare transformer scaling tradeoffs",
                "report",
                lean=True,
                timeout_seconds=45,
                spawn=False,
            )

        self.assertEqual(submitted["kind"], "run-ask-background-job")
        self.assertEqual(submitted["status"], "submitted")
        self.assertTrue(submitted["job_id"])
        self.assertTrue(submitted["path"].startswith("output/reports/"))
        self.assertTrue(submitted["run_id"])
        self.assertTrue(submitted["run_notes_path"].startswith("output/control/runs/"))
        self.assertEqual(submitted["backend_preflight"], backend_preflight)
        manifest_path = self.root / submitted["job_manifest_path"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "submitted")
        self.assertEqual(manifest["path"], submitted["path"])
        self.assertEqual(manifest["run_id"], submitted["run_id"])
        self.assertEqual(manifest["run_notes_path"], submitted["run_notes_path"])
        self.assertEqual(manifest["artifact"]["path"], submitted["path"])
        self.assertEqual(manifest["artifact"]["run_id"], submitted["run_id"])
        self.assertEqual(manifest["artifact"]["run_notes_path"], submitted["run_notes_path"])
        self.assertEqual(manifest["artifact"]["background_job_id"], submitted["job_id"])
        self.assertEqual(manifest["artifact"]["background_status"], "submitted")
        self.assertEqual(manifest["backend_preflight"], backend_preflight)
        submitted_frontmatter = parse_frontmatter((self.root / submitted["path"]).read_text(encoding="utf-8"))
        self.assertEqual(submitted_frontmatter["background_job_id"], submitted["job_id"])
        self.assertEqual(submitted_frontmatter["background_status"], "submitted")
        self.assertEqual(submitted_frontmatter["delivery_mode"], "background-pending")
        self.assertEqual(submitted_frontmatter["llm_status"], "pending")
        submitted_receipts = _load_jsonl_records(self.root / ".aiwiki" / "state" / "execution-receipts.jsonl")
        submitted_success_receipts = [
            record
            for record in submitted_receipts
            if record.get("operation") == "run-ask"
            and record.get("status") == "success"
            and record.get("target_file") == submitted["path"]
        ]
        self.assertEqual(submitted_success_receipts, [])

        class _ResumeClient:
            def __init__(self) -> None:
                self.config = type(
                    "Config",
                    (),
                    {"model": "gpt-5.5", "backend": "codex-cli", "backend_requested": "codex-cli", "timeout_seconds": 45},
                )()

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt, user_prompt
                return CompletionResult(text=_VALID_REPORT_BODY, response_id="resp_background", usage={"total_tokens": 7})

        with patch("aiwiki.runner.workflows_ask.ask_question", side_effect=AssertionError("resume should reuse the submitted manifest artifact")):
            resumed = run_ask_resume(self.root, submitted["job_id"], client=_ResumeClient())

        self.assertEqual(resumed["job_id"], submitted["job_id"])
        self.assertEqual(resumed["path"], submitted["path"])
        self.assertEqual(resumed["run_id"], submitted["run_id"])
        self.assertEqual(resumed["run_notes_path"], submitted["run_notes_path"])
        self.assertEqual(sorted(path.name for path in (self.root / "output" / "reports").glob("*.md")), [Path(submitted["path"]).name])
        artifact_path = self.root / submitted["path"]
        self.assertIn("# Stub answer", artifact_path.read_text(encoding="utf-8"))
        output_frontmatter = parse_frontmatter(artifact_path.read_text(encoding="utf-8"))
        self.assertEqual(output_frontmatter["run_id"], submitted["run_id"])
        self.assertEqual(output_frontmatter["run_notes_path"], submitted["run_notes_path"])
        self.assertEqual(output_frontmatter["background_job_id"], submitted["job_id"])
        self.assertEqual(output_frontmatter["background_status"], "completed")
        self.assertNotEqual(output_frontmatter.get("delivery_mode"), "background-pending")
        updated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(updated_manifest["status"], "completed")
        self.assertEqual(updated_manifest["path"], submitted["path"])
        self.assertEqual(updated_manifest["run_id"], submitted["run_id"])
        self.assertEqual(updated_manifest["run_notes_path"], submitted["run_notes_path"])
        self.assertEqual(updated_manifest["result"]["path"], submitted["path"])
        resumed_receipts = _load_jsonl_records(self.root / ".aiwiki" / "state" / "execution-receipts.jsonl")
        resumed_success_receipts = [
            record
            for record in resumed_receipts
            if record.get("operation") == "run-ask"
            and record.get("status") == "success"
            and record.get("target_file") == submitted["path"]
            and record.get("primary_path") == submitted["path"]
        ]
        self.assertTrue(resumed_success_receipts, resumed_receipts)
        receipt_path = self.root / str(resumed_success_receipts[-1]["receipt_path"])
        receipt_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt_payload["operation"], "run-ask")
        self.assertEqual(receipt_payload["status"], "success")
        self.assertEqual(receipt_payload["target_file"], submitted["path"])
        self.assertEqual(receipt_payload["primary_path"], submitted["path"])
        self.assertEqual(receipt_payload["receipt_path"], relative_path(self.root, receipt_path))

    def test_run_ask_timeout_override_is_scoped_to_single_client_creation(self) -> None:
        artifact_path = self.root / "output" / "reports" / "query-timeout-override.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("---\nid: query-timeout-override\nkind: report\n---\n\n# Placeholder\n", encoding="utf-8")
        artifact = {
            "path": "output/reports/query-timeout-override.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": [],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
            "graph_anchor_node_ids": ["source:source-1"],
        }

        class _TimeoutClient:
            def __init__(self) -> None:
                self.config = type("Config", (), {"model": "gpt-5.4", "timeout_seconds": 33})()

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                del user_prompt
                return CompletionResult(
                    text=_VALID_REPORT_BODY,
                    response_id="resp",
                    usage={},
                )

        with patch("aiwiki.runner.workflows_ask.ask_question", return_value=artifact):
            with patch("aiwiki.runner.workflows_ask.create_client", return_value=_TimeoutClient()) as create_client_mock:
                result = run_ask(
                    self.root,
                    "测试",
                    "report",
                    timeout_seconds=33,
                )

        create_client_mock.assert_called_once_with(self.root, timeout_seconds=33)
        self.assertEqual(result["timeout_seconds"], 33)

    def test_run_ask_stamps_backend_compat_when_preflight_runs(self) -> None:
        snapshot = {
            "backend_requested": "codex-cli",
            "backend": "codex-cli",
            "model_requested": "gpt-5.5",
            "model": "gpt-5.5",
            "compatibility": "compatible",
            "compatibility_hint": "strict frontmatter ok",
            "raw_response_path": ".aiwiki/llm-responses/preflight.txt",
            "error_class": "",
        }
        artifact_path = self.root / "output" / "reports" / "query-compat.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("---\nid: query-compat\nkind: report\n---\n\n# Placeholder\n", encoding="utf-8")
        artifact = {
            "path": "output/reports/query-compat.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": [],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
        }

        class _AskClient:
            config = type("Config", (), {"model": "gpt-5.5", "backend": "codex-cli", "backend_requested": "codex-cli", "timeout_seconds": 120})()

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                del user_prompt
                return CompletionResult(
                    text=_VALID_REPORT_BODY,
                    response_id="resp-ask-compat",
                    usage={},
                )

        with patch("aiwiki.runner.preflight.preflight_check_backend", return_value=snapshot):
            with patch("aiwiki.runner.workflows_ask.ask_question", return_value=artifact):
                with patch("aiwiki.runner.workflows_ask.create_client", return_value=_AskClient()):
                    run_ask(self.root, "测试", "report")

        receipt = json.loads((self.root / ".aiwiki/logs/llm-receipts.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(receipt["event"], "run-ask")
        self.assertEqual(receipt["backend_compat"], snapshot)

    def test_run_ask_passes_no_cache_to_ask_question(self) -> None:
        artifact_path = self.root / "output" / "reports" / "query-no-cache.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("---\nid: query-no-cache\nkind: report\n---\n\n# Placeholder\n", encoding="utf-8")
        artifact = {
            "path": "output/reports/query-no-cache.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": [],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
            "no_cache": True,
        }

        class _NoCacheClient:
            def __init__(self) -> None:
                self.config = type("Config", (), {"model": "gpt-5.4", "timeout_seconds": 120})()

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                del user_prompt
                return CompletionResult(
                    text=_VALID_REPORT_BODY,
                    response_id="resp_no_cache",
                    usage={},
                )

        with patch("aiwiki.runner.workflows_ask.ask_question", return_value=artifact) as ask_mock:
            with patch("aiwiki.runner.workflows_ask._build_ask_prompt", return_value="prompt"):
                result = run_ask(self.root, "测试", "report", client=_NoCacheClient(), no_cache=True)

        ask_mock.assert_called_once_with(
            self.root,
            "测试",
            "report",
            protocol=None,
            no_cache=True,
            write_graph_anchors=False,
        )
        self.assertTrue(result["no_cache"])

    def test_run_ask_frontdoor_marks_artifact_failed_without_deterministic_fallback(self) -> None:
        artifact_path = self.root / "output" / "reports" / "query-frontdoor-fallback.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("---\nid: query-frontdoor-fallback\nkind: report\n---\n\n# Placeholder\n", encoding="utf-8")
        artifact = {
            "path": "output/reports/query-frontdoor-fallback.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": ["source-1"],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
            "graph_anchor_node_ids": ["source:source-1"],
        }

        class _UnavailableAskClient:
            def __init__(self) -> None:
                self.config = type(
                    "Config",
                    (),
                    {"model": "gpt-5.4", "backend": "codex-cli", "backend_requested": "codex-cli", "timeout_seconds": 120},
                )()

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                del user_prompt
                raise LLMError("usage limit exceeded")

        with patch("aiwiki.runner.workflows_ask.ask_question", return_value=artifact):
            with patch("aiwiki.runner.workflows_ask._build_ask_prompt", return_value="prompt"):
                with self.assertRaisesRegex(LLMError, "usage limit"):
                    run_ask(self.root, "测试", "report", client=_UnavailableAskClient())

        content = artifact_path.read_text(encoding="utf-8")
        self.assertIn("LLM 没有返回可用内容", content)
        self.assertIn("llm_status: \"timeout_or_unavailable\"", content)
        self.assertIn("delivery_mode: \"llm-failed\"", content)
        self.assertIn("graph_anchor_node_ids:", content)
        self.assertIn('  - "source:source-1"', content)
        self.assertIn("## 关系图谱锚点", content)
        self.assertIn("`source:source-1`", content)

        llm_receipts = [
            json.loads(line)
            for line in (self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(llm_receipts[-1]["event"], "run-ask")
        self.assertEqual(llm_receipts[-1]["status"], "failed")
        self.assertEqual(llm_receipts[-1]["delivery_mode"], "llm-failed")

    def test_run_ask_frontdoor_hard_fail_still_raises(self) -> None:
        artifact_path = self.root / "output" / "reports" / "query-frontdoor-hard-fail.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("---\nid: query-frontdoor-hard-fail\nkind: report\n---\n\n# Placeholder\n", encoding="utf-8")
        artifact = {
            "path": "output/reports/query-frontdoor-hard-fail.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": ["source-1"],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
        }

        class _HardFailAskClient:
            def __init__(self) -> None:
                self.config = type(
                    "Config",
                    (),
                    {"model": "gpt-5.4", "backend": "codex-cli", "backend_requested": "codex-cli", "timeout_seconds": 120},
                )()

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                del user_prompt
                raise LLMError("unexpected schema mismatch")

        with patch("aiwiki.runner.workflows_ask.ask_question", return_value=artifact):
            with patch("aiwiki.runner.workflows_ask._build_ask_prompt", return_value="prompt"):
                with self.assertRaisesRegex(LLMError, "schema mismatch"):
                    run_ask(self.root, "测试", "report", client=_HardFailAskClient())

        llm_receipts = [
            json.loads(line)
            for line in (self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(llm_receipts[-1]["event"], "run-ask")
        self.assertEqual(llm_receipts[-1]["status"], "failed")
        self.assertEqual(llm_receipts[-1]["delivery_mode"], "llm-failed")

    def test_llm_probe_returns_static_status_when_unconfigured(self) -> None:
        fake_status = {"configured": False, "message": "missing backend"}
        with patch("aiwiki.runner.clients.LLMConfig.status_from_env", return_value=fake_status):
            result = llm_probe(self.root, probe_all=False, timeout_seconds=17)

        self.assertFalse(result["configured"])
        self.assertEqual(result["probe_timeout_seconds"], 17)
        self.assertIsNone(result["probe"])
        self.assertEqual(result["probes"], [])

    def test_llm_probe_delegates_to_single_or_all_backend_probes(self) -> None:
        fake_status = {"configured": True, "backend": "codex-cli"}
        fake_config = type("Config", (), {"backend": "codex-cli"})()
        with patch("aiwiki.runner.clients.LLMConfig.status_from_env", return_value=fake_status):
            with patch("aiwiki.runner.clients.LLMConfig.from_env", return_value=fake_config):
                with patch("aiwiki.runner.clients.probe_backend", return_value={"backend": "codex-cli", "ok": True}) as probe_one:
                    single = llm_probe(self.root, probe_all=False, timeout_seconds=13)
                with patch(
                    "aiwiki.runner.clients.probe_available_backends",
                    return_value=[{"backend": "codex-cli", "ok": True}, {"backend": "copilot-cli", "ok": False}],
                ) as probe_all:
                    all_backends = llm_probe(self.root, probe_all=True, timeout_seconds=19)

        probe_one.assert_called_once_with(fake_config, self.root, timeout_seconds=13)
        probe_all.assert_called_once_with(fake_config, self.root, timeout_seconds=19)
        self.assertEqual(single["probe"], {"backend": "codex-cli", "ok": True})
        self.assertEqual(single["probes"], [])
        self.assertEqual(all_backends["probe"], {"backend": "codex-cli", "ok": True})
        self.assertEqual(len(all_backends["probes"]), 2)

    def test_build_ask_prompt_trims_indexes_and_protocol_pages_for_report_profile(self) -> None:
        target = self.root / "output" / "reports" / "query-test.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("---\nid: query-test\nkind: report\n---\n\n# Query\n", encoding="utf-8")

        prompt = _build_ask_prompt(
            self.root,
            target,
            "测试",
            "report",
            target.read_text(encoding="utf-8"),
            source_pages=[],
            concept_pages=[],
            protocol_pages=[
                ("schema/protocols/general/index.md", "protocol index"),
                ("schema/protocols/general/query.md", "protocol query"),
                ("schema/protocols/general/review.md", "protocol review"),
            ],
            index_pages=[
                ("wiki/indexes/index.md", "index home"),
                ("wiki/indexes/sources.md", "sources index"),
                ("wiki/indexes/review-center.md", "review center should be omitted"),
                ("wiki/indexes/machine-memory.md", "machine memory"),
                ("wiki/indexes/log.md", "## old\n\nold log\n" * 100),
                ("schema/index.md", "schema index"),
            ],
            machine_memory_query={},
            prompt_profile="lean",
        )

        self.assertIn("### wiki/indexes/index.md", prompt)
        self.assertIn("### wiki/indexes/sources.md", prompt)
        self.assertNotIn("### wiki/indexes/machine-memory.md", prompt)
        index_section = prompt.split("## Index Pages", 1)[1].split("## Protocol Pages", 1)[0]
        self.assertNotIn("### schema/index.md", index_section)
        self.assertIn("Omitted `3` additional index page", prompt)
        self.assertNotIn("review-center.md", prompt)
        self.assertIn("### schema/protocols/general/index.md", prompt)
        protocol_section = prompt.split("## Protocol Pages", 1)[1].split("## Concept Pages", 1)[0]
        self.assertNotIn("### schema/protocols/general/query.md", protocol_section)
        self.assertIn("Omitted `1` additional protocol page", prompt)
        self.assertNotIn("protocol review", prompt)
        self.assertLess(len(prompt), 30000)

    def test_run_ask_retries_with_lean_prompt_on_timeout(self) -> None:
        artifact_path = self.root / "output" / "reports" / "query-timeout.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("---\nid: query-timeout\nkind: report\n---\n\n# Placeholder\n", encoding="utf-8")
        artifact = {
            "path": "output/reports/query-timeout.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": [],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
        }

        class _RetryClient:
            def __init__(self) -> None:
                self.config = type("Config", (), {"model": "gpt-5.4"})()
                self.prompts: list[str] = []

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                self.prompts.append(user_prompt)
                if len(self.prompts) == 1:
                    raise LLMError("Codex CLI timed out after 120 seconds.")
                return CompletionResult(
                    text=_VALID_REPORT_BODY,
                    response_id="resp_retry",
                    usage={},
                )

        client = _RetryClient()
        with patch("aiwiki.runner.workflows_ask.ask_question", return_value=artifact):
            with patch("aiwiki.runner.workflows_ask._build_ask_prompt", side_effect=["balanced prompt", "lean prompt"]):
                result = run_ask(self.root, "测试", "report", client=client)

        self.assertEqual(result["path"], "output/reports/query-timeout.md")
        self.assertEqual(result["prompt_profile"], "lean")
        self.assertEqual(result["retry_prompt_profile"], "lean")
        self.assertEqual(result["fallback_stage"], "prompt-profile")
        self.assertEqual(result["model_selected"], "gpt-5.4")
        self.assertEqual(result["model_final"], "gpt-5.4")
        self.assertTrue(result["contract_validated"])
        self.assertEqual(client.prompts, ["balanced prompt", "lean prompt"])
        self.assertIn("# Stub answer", artifact_path.read_text(encoding="utf-8"))

    def test_run_ask_advances_to_next_model_when_first_model_returns_invalid_frontmatter(self) -> None:
        artifact_path = self.root / "output" / "reports" / "query-nim-fallback.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("---\nid: query-nim-fallback\nkind: output\n---\n\n# Placeholder\n", encoding="utf-8")
        artifact = {
            "path": "output/reports/query-nim-fallback.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": ["source-1"],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
        }

        class _ModelFallbackAskClient:
            def __init__(self) -> None:
                self.models = ["moonshotai/kimi-k2.5", "z-ai/glm-5.1"]
                self.index = 0
                self.config = type(
                    "Config",
                    (),
                    {"model": self.models[self.index], "backend": "nvidia-nim-api", "timeout_seconds": 120},
                )()

            def advance_model(self) -> bool:
                if self.index >= len(self.models) - 1:
                    return False
                self.index += 1
                self.config = type(
                    "Config",
                    (),
                    {"model": self.models[self.index], "backend": "nvidia-nim-api", "timeout_seconds": 120},
                )()
                return True

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                del user_prompt
                if self.config.model == "moonshotai/kimi-k2.5":
                    return CompletionResult(
                        text='--- id: "query-nim-fallback" kind: "output" format: "report" ---\n\nMissing real frontmatter.\nwiki/sources/source-1.md\n',
                        response_id="resp_glm",
                        usage={},
                    )
                return CompletionResult(
                    text=_VALID_REPORT_BODY,
                    response_id="resp_kimi",
                    usage={},
                )

        client = _ModelFallbackAskClient()
        with patch("aiwiki.runner.workflows_ask.ask_question", return_value=artifact):
            with patch("aiwiki.runner.workflows_ask._build_ask_prompt", return_value="nim prompt"):
                result = run_ask(self.root, "测试", "report", client=client)

        self.assertEqual(result["prompt_profile"], "balanced")
        self.assertEqual(result["retry_prompt_profile"], "")
        self.assertEqual(result["backend_requested"], "nvidia-nim-api")
        self.assertEqual(result["backend_effective"], "nvidia-nim-api")
        self.assertEqual(result["model_selected"], "moonshotai/kimi-k2.5")
        self.assertEqual(result["model_final"], "z-ai/glm-5.1")
        self.assertEqual(result["fallback_stage"], "model-chain")
        self.assertTrue(result["contract_validated"])
        self.assertEqual(client.config.model, "z-ai/glm-5.1")
        self.assertIn("# Stub answer", artifact_path.read_text(encoding="utf-8"))

        llm_receipts_path = self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl"
        self.assertTrue(llm_receipts_path.exists())
        receipt = json.loads(llm_receipts_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(receipt["model_selected"], "moonshotai/kimi-k2.5")
        self.assertEqual(receipt["model_final"], "z-ai/glm-5.1")
        self.assertEqual(receipt["fallback_stage"], "model-chain")
        self.assertTrue(receipt["contract_validated"])

    def test_run_ask_failed_attempt_is_written_to_runs_log_and_llm_receipts(self) -> None:
        artifact_path = self.root / "output" / "reports" / "query-failed-log.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("---\nid: query-failed-log\nkind: output\n---\n\n# Placeholder\n", encoding="utf-8")
        artifact = {
            "path": "output/reports/query-failed-log.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": ["source-1"],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
        }

        class _FailingAskClient:
            def __init__(self) -> None:
                self.config = type(
                    "Config",
                    (),
                    {"model": "moonshotai/kimi-k2.5", "backend": "nvidia-nim-api", "timeout_seconds": 120},
                )()

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                del user_prompt
                return CompletionResult(
                    text='--- id: "query-failed-log" kind: "output" format: "report" ---\n\nMissing real frontmatter.\nwiki/sources/source-1.md\n',
                    response_id="resp_failed",
                    usage={"prompt_tokens": 1},
                )

        with patch("aiwiki.runner.workflows_ask.ask_question", return_value=artifact):
            with patch("aiwiki.runner.workflows_ask._build_ask_prompt", return_value="failing prompt"):
                with self.assertRaises(RuntimeError) as ctx:
                    run_ask(self.root, "测试", "report", client=_FailingAskClient())

        self.assertIn("frontmatter", str(ctx.exception))

        llm_receipts_path = self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl"
        self.assertTrue(llm_receipts_path.exists())
        receipt = json.loads(llm_receipts_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["backend_requested"], "nvidia-nim-api")
        self.assertEqual(receipt["backend_effective"], "nvidia-nim-api")
        self.assertEqual(receipt["model_selected"], "moonshotai/kimi-k2.5")
        self.assertEqual(receipt["model_final"], "moonshotai/kimi-k2.5")
        self.assertEqual(receipt["fallback_reason"], "Ask response is missing frontmatter.")
        self.assertFalse(receipt["no_cache"])
        self.assertFalse(receipt["contract_validated"])

        runs_log_path = self.root / ".aiwiki" / "logs" / "runs.jsonl"
        self.assertTrue(runs_log_path.exists())
        run_log = json.loads(runs_log_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(run_log["status"], "failed")
        self.assertEqual(run_log["event"], "run-ask")
        self.assertEqual(run_log["backend_requested"], "nvidia-nim-api")
        self.assertEqual(run_log["backend_effective"], "nvidia-nim-api")
        self.assertEqual(run_log["model_selected"], "moonshotai/kimi-k2.5")
        self.assertEqual(run_log["model_final"], "moonshotai/kimi-k2.5")
        self.assertEqual(run_log["fallback_reason"], "Ask response is missing frontmatter.")
        self.assertFalse(run_log["contract_validated"])

    def test_run_ask_failed_attempt_records_no_cache_flag(self) -> None:
        artifact_path = self.root / "output" / "reports" / "query-failed-no-cache.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("---\nid: query-failed-no-cache\nkind: output\n---\n\n# Placeholder\n", encoding="utf-8")
        artifact = {
            "path": "output/reports/query-failed-no-cache.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": ["source-1"],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
            "no_cache": True,
        }

        class _FailingNoCacheAskClient:
            def __init__(self) -> None:
                self.config = type(
                    "Config",
                    (),
                    {"model": "moonshotai/kimi-k2.5", "backend": "nvidia-nim-api", "timeout_seconds": 120},
                )()

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                del user_prompt
                return CompletionResult(
                    text='--- id: "query-failed-no-cache" kind: "output" format: "report" ---\n\nMissing real frontmatter.\nwiki/sources/source-1.md\n',
                    response_id="resp_failed_no_cache",
                    usage={"prompt_tokens": 1},
                )

        with patch("aiwiki.runner.workflows_ask.ask_question", return_value=artifact):
            with patch("aiwiki.runner.workflows_ask._build_ask_prompt", return_value="failing prompt"):
                with self.assertRaises(RuntimeError):
                    run_ask(self.root, "测试", "report", client=_FailingNoCacheAskClient(), no_cache=True)

        llm_receipts_path = self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl"
        receipt = json.loads(llm_receipts_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertTrue(receipt["no_cache"])

        runs_log_path = self.root / ".aiwiki" / "logs" / "runs.jsonl"
        run_log = json.loads(runs_log_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertTrue(run_log["no_cache"])

    def test_run_compile_limit_zero_reports_pending_source_and_concept_pages(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        concept_page = self.root / "wiki" / "concepts" / "transformer-scaling.md"
        text = concept_page.read_text(encoding="utf-8")
        before, marker, after = text.partition("## Summary\n")
        _, related_marker, remainder = after.partition("\n## Related Sources\n")
        concept_page.write_text(
            before
            + marker
            + "- Existing synthesis for transformer-scaling appears\n"
            + "- Keep the current synthesis grounded in the linked sources.\n"
            + related_marker
            + remainder,
            encoding="utf-8",
        )
        compile_wiki(self.root)

        result = run_compile(self.root, client=_DummyClient(), limit=0)

        self.assertEqual(result["pending_pages"], 1)
        self.assertEqual(result["pending_concept_pages"], 0)
        self.assertGreaterEqual(result["pending_rewrite_concept_pages"], 1)
        self.assertEqual(result["updated_pages"], [])
        self.assertEqual(result["updated_concept_pages"], [])
        self.assertIn(entry["id"], result["compile"]["clean_source_ids"] + result["compile"]["dirty_source_ids"])
        self.assertEqual(result["backend_requested"], "")
        self.assertEqual(result["model_selected"], "")
        self.assertFalse(result["contract_validated"])

        llm_receipts_path = self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl"
        self.assertTrue(llm_receipts_path.exists())
        summary_receipt = json.loads(llm_receipts_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(summary_receipt["event"], "run-compile-summary")
        self.assertEqual(summary_receipt["status"], "success")
        self.assertEqual(summary_receipt["delivery_mode"], "skipped")
        self.assertFalse(summary_receipt["fallback_used"])
        self.assertEqual(summary_receipt["prompt_profile"], "")
        self.assertEqual(summary_receipt["retry_prompt_profile"], "")

        runs_log = json.loads((self.root / ".aiwiki" / "logs" / "runs.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(runs_log["event"], "run-compile-summary")
        self.assertEqual(runs_log["delivery_mode"], "skipped")
        self.assertFalse(runs_log["fallback_used"])

    def test_adaptive_compile_timeout_floor_for_empty_pending(self) -> None:
        """F-INV-NEW-1: helper returns None when nothing is pending, so the
        legacy LLMConfig.from_env value flows through unchanged."""

        from aiwiki.runner.workflows import _compute_adaptive_compile_timeout

        self.assertIsNone(_compute_adaptive_compile_timeout(self.root, []))

    def test_run_ask_report_timeout_defaults_to_240_without_env(self) -> None:
        from aiwiki.runner.workflows import _effective_run_ask_timeout

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AIWIKI_LLM_TIMEOUT", None)
            self.assertEqual(_effective_run_ask_timeout("report", None), 240)
            self.assertIsNone(_effective_run_ask_timeout("note", None))
            self.assertEqual(_effective_run_ask_timeout("report", 33), 33)

    def test_run_ask_report_timeout_respects_env_override(self) -> None:
        from aiwiki.runner.workflows import _effective_run_ask_timeout

        with patch.dict(os.environ, {"AIWIKI_LLM_TIMEOUT": "300"}, clear=False):
            self.assertIsNone(_effective_run_ask_timeout("report", None))

    def test_adaptive_compile_timeout_scales_with_largest_pending_raw(self) -> None:
        """F-INV-NEW-1: a single ~270 page raw (≈ 270 * 30KB) lands in the
        adaptive window (floor 240s, ceil 1800s, 60s per page)."""

        from aiwiki.runner.workflows import _compute_adaptive_compile_timeout

        raw = self.root / "raw" / "inbox" / "big.md"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(b"x" * (270 * 30_000))
        pending = [{"id": "src-big", "stored_path": "raw/inbox/big.md"}]
        # No env override: helper should compute adaptive timeout.
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AIWIKI_LLM_TIMEOUT", None)
            timeout = _compute_adaptive_compile_timeout(self.root, pending)
        self.assertIsNotNone(timeout)
        # 270 pages * 60s = 16_200, capped at 1800.
        self.assertEqual(timeout, 1800)

    def test_adaptive_compile_timeout_returns_floor_for_small_raw(self) -> None:
        """F-INV-NEW-1: even tiny inputs get the 240s floor (still better than
        the historical 120s default)."""

        from aiwiki.runner.workflows import _compute_adaptive_compile_timeout

        raw = self.root / "raw" / "inbox" / "tiny.md"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(b"hello")
        pending = [{"id": "src-tiny", "stored_path": "raw/inbox/tiny.md"}]
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AIWIKI_LLM_TIMEOUT", None)
            timeout = _compute_adaptive_compile_timeout(self.root, pending)
        self.assertEqual(timeout, 240)

    def test_adaptive_compile_timeout_respects_env_override(self) -> None:
        """F-INV-NEW-1: explicit AIWIKI_LLM_TIMEOUT always wins; helper returns
        None so create_client falls back to the env-derived LLMConfig value."""

        from aiwiki.runner.workflows import _compute_adaptive_compile_timeout

        raw = self.root / "raw" / "inbox" / "any.md"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(b"x" * 100_000)
        pending = [{"id": "src-any", "stored_path": "raw/inbox/any.md"}]
        with patch.dict(os.environ, {"AIWIKI_LLM_TIMEOUT": "300"}, clear=False):
            self.assertIsNone(_compute_adaptive_compile_timeout(self.root, pending))

    def test_adaptive_compile_timeout_falls_back_to_floor_when_raw_missing(
        self,
    ) -> None:
        """F-INV-NEW-1: pending non-empty but every stored_path is missing /
        absolute / escapes the vault root → fall back to the 240s floor instead
        of silently shrinking back to the 120s default."""

        from aiwiki.runner.workflows import _compute_adaptive_compile_timeout

        pending = [
            {"id": "src-missing", "stored_path": "raw/inbox/does-not-exist.md"},
            {"id": "src-absolute", "stored_path": "/etc/passwd"},
            {"id": "src-escape", "stored_path": "../../../etc/hosts"},
            {"id": "src-no-path", "stored_path": ""},
            {"id": "src-not-dict"},  # malformed entry — should be skipped
        ]
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AIWIKI_LLM_TIMEOUT", None)
            timeout = _compute_adaptive_compile_timeout(self.root, pending)
        self.assertEqual(timeout, 240)

    def test_adaptive_compile_timeout_picks_largest_entry(self) -> None:
        """F-INV-NEW-1: with mixed sizes, the helper must size the timeout off
        the *largest* raw in the filtered queue, not the first or the average."""

        from aiwiki.runner.workflows import _compute_adaptive_compile_timeout

        inbox = self.root / "raw" / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / "small.md").write_bytes(b"x" * 5_000)  # < floor pages
        (inbox / "medium.md").write_bytes(b"x" * 90_000)  # 3 pages → 180s → floor
        (inbox / "large.md").write_bytes(b"x" * (10 * 30_000))  # 10 pages → 600s
        pending = [
            {"id": "src-small", "stored_path": "raw/inbox/small.md"},
            {"id": "src-large", "stored_path": "raw/inbox/large.md"},
            {"id": "src-medium", "stored_path": "raw/inbox/medium.md"},
        ]
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AIWIKI_LLM_TIMEOUT", None)
            timeout = _compute_adaptive_compile_timeout(self.root, pending)
        # Largest is 10 pages * 60s = 600s, well inside [240, 1800].
        self.assertEqual(timeout, 600)

    def test_run_compile_paths_filter_restricts_pending_queue(self) -> None:
        """P4-INV-1 (Round 59): when --paths is supplied, only matching sources
        enter the LLM enrichment queue. Use limit=0 so we just inspect what
        would have been queued without launching the LLM.
        """
        sample_a = self.root / "sample-a.md"
        sample_a.write_text(
            "# Source A\n\nThis is the targeted dogfood note.\n", encoding="utf-8"
        )
        sample_b = self.root / "sample-b.md"
        sample_b.write_text(
            "# Source B\n\nThis is a sibling note that should be filtered out.\n",
            encoding="utf-8",
        )
        entry_a = ingest_source(self.root, str(sample_a), title="A")
        ingest_source(self.root, str(sample_b), title="B")
        compile_wiki(self.root)

        # Without --paths, backlog has 2 pending pages.
        baseline = run_compile(self.root, client=_DummyClient(), limit=0)
        self.assertEqual(baseline["pending_pages"], 2)

        # With --paths pointing only at A, queue must shrink to 1.
        filtered = run_compile(
            self.root, client=_DummyClient(), limit=0, paths=[entry_a["id"]]
        )
        self.assertEqual(filtered["pending_pages"], 1)

        # Empty list / None must keep legacy full-backlog behavior.
        as_full = run_compile(self.root, client=_DummyClient(), limit=0, paths=None)
        self.assertEqual(as_full["pending_pages"], 2)
        as_empty = run_compile(self.root, client=_DummyClient(), limit=0, paths=[])
        self.assertEqual(as_empty["pending_pages"], 2)

        # Filter accepts both wiki/sources/<id>.md form and bare id.
        path_form = run_compile(
            self.root,
            client=_DummyClient(),
            limit=0,
            paths=[f"wiki/sources/{entry_a['id']}.md"],
        )
        self.assertEqual(path_form["pending_pages"], 1)

        # Mismatching token filters everything out.
        none_match = run_compile(
            self.root, client=_DummyClient(), limit=0, paths=["nonexistent-source"]
        )
        self.assertEqual(none_match["pending_pages"], 0)

    def test_run_compile_records_audit_fields_for_success_and_summary(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        updated = source_page.read_text(encoding="utf-8").replace(
            "- Pending LLM summary.",
            "- Transformers benefit from scale, but cost rises with inference demand.",
        )

        class _CompileFallbackClient:
            def __init__(self) -> None:
                self.models = ["moonshotai/kimi-k2.5", "z-ai/glm-5.1"]
                self.index = 0
                self.config = type("Config", (), {"model": self.models[self.index], "backend": "nvidia-nim-api"})()

            def advance_model(self) -> bool:
                if self.index >= len(self.models) - 1:
                    return False
                self.index += 1
                self.config = type("Config", (), {"model": self.models[self.index], "backend": "nvidia-nim-api"})()
                return True

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                del user_prompt
                if self.config.model == "moonshotai/kimi-k2.5":
                    return CompletionResult(text="# not a source page\n", response_id="resp-bad", usage={"prompt_tokens": 1})
                return CompletionResult(text=updated, response_id="resp-good", usage={"prompt_tokens": 2})

        result = run_compile(self.root, client=_CompileFallbackClient(), limit=1)

        self.assertEqual(result["backend_requested"], "nvidia-nim-api")
        self.assertEqual(result["backend_effective"], "nvidia-nim-api")
        self.assertEqual(result["model_selected"], "moonshotai/kimi-k2.5")
        self.assertEqual(result["model_final"], "z-ai/glm-5.1")
        self.assertEqual(result["fallback_stage"], "model-chain")
        self.assertTrue(result["contract_validated"])

        llm_receipts_path = self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl"
        receipts = [json.loads(line) for line in llm_receipts_path.read_text(encoding="utf-8").splitlines()]
        item_receipt = next(receipt for receipt in receipts if receipt["event"] == "run-compile")
        summary_receipt = receipts[-1]
        self.assertEqual(item_receipt["status"], "success")
        self.assertEqual(item_receipt["model_selected"], "moonshotai/kimi-k2.5")
        self.assertEqual(item_receipt["model_final"], "z-ai/glm-5.1")
        self.assertEqual(item_receipt["fallback_stage"], "model-chain")
        self.assertTrue(item_receipt["contract_validated"])
        self.assertEqual(summary_receipt["event"], "run-compile-summary")
        self.assertEqual(summary_receipt["model_selected"], "moonshotai/kimi-k2.5")
        self.assertEqual(summary_receipt["model_final"], "z-ai/glm-5.1")
        self.assertEqual(summary_receipt["fallback_stage"], "model-chain")
        self.assertTrue(summary_receipt["contract_validated"])
        self.assertEqual(summary_receipt["delivery_mode"], "llm-fallback-chain")
        self.assertTrue(summary_receipt["fallback_used"])

    def test_run_compile_stamps_backend_compat_when_preflight_runs(self) -> None:
        snapshot = {
            "backend_requested": "codex-cli",
            "backend": "codex-cli",
            "model_requested": "gpt-5.5",
            "model": "gpt-5.5",
            "compatibility": "compatible",
            "compatibility_hint": "strict frontmatter ok",
            "raw_response_path": ".aiwiki/llm-responses/preflight.txt",
            "error_class": "",
        }
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        updated = source_page.read_text(encoding="utf-8").replace(
            "- Pending LLM summary.",
            "- Transformers benefit from scale, with inference costs rising alongside demand.",
        )

        class _CompileClient:
            config = type("Config", (), {"model": "gpt-5.5", "backend": "codex-cli", "backend_requested": "codex-cli"})()

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                del user_prompt
                return CompletionResult(text=updated, response_id="resp-compat", usage={})

        with patch("aiwiki.runner.preflight.preflight_check_backend", return_value=snapshot):
            with patch("aiwiki.runner.workflows.create_client", return_value=_CompileClient()):
                run_compile(self.root, limit=1)

        receipts = [
            json.loads(line)
            for line in (self.root / ".aiwiki/logs/llm-receipts.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        stamped = [receipt for receipt in receipts if receipt["event"] in {"run-compile", "run-compile-summary"}]
        self.assertTrue(stamped)
        self.assertTrue(all(receipt["backend_compat"] == snapshot for receipt in stamped))

    def test_run_compile_returns_runtime_owned_rewrite_recovery_objects(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        source_page.write_text(
            source_page.read_text(encoding="utf-8").replace(
                "- Pending LLM summary.",
                "- Transformer scale improves capability and raises compute demand.",
            ),
            encoding="utf-8",
        )
        compile_wiki(self.root)
        for concept_page in sorted((self.root / "wiki" / "concepts").glob("*.md")):
            text = concept_page.read_text(encoding="utf-8")
            before, marker, after = text.partition("## Summary\n")
            _, related_marker, remainder = after.partition("\n## Related Sources\n")
            concept_page.write_text(
                before
                + marker
                + f"- Existing synthesis for {concept_page.stem} appears\n"
                + "- Keep the current synthesis grounded in the linked sources.\n"
                + related_marker
                + remainder,
                encoding="utf-8",
            )
        text = concept_page.read_text(encoding="utf-8")
        compile_wiki(self.root)

        memory = load_machine_memory(self.root)
        candidate = memory["health"]["concept_quality"]["rewrite_candidates"][0]
        concept_page = self.root / candidate["path"]
        slug = concept_page.stem

        rewritten = concept_page.read_text(encoding="utf-8").replace("Existing synthesis", "Rewritten synthesis")
        result = run_compile(
            self.root,
            client=type(
                "_RewriteClient",
                (),
                {
                    "config": type("Config", (), {"model": "gpt-5.4", "backend": "codex-cli", "backend_requested": "codex-cli"})(),
                    "complete": lambda self, system_prompt, user_prompt: CompletionResult(
                        text=rewritten,
                        response_id="resp-rewrite",
                        usage={},
                    ),
                },
            )(),
            limit=1,
        )

        self.assertEqual(len(result["updated_rewrite_proposals"]), 1)
        proposal = result["updated_rewrite_proposals"][0]
        self.assertEqual(proposal["slug"], slug)
        self.assertEqual(proposal["proposal_path"], f"wiki/rewrite-proposals/{slug}.md")
        self.assertTrue(proposal["can_review"])
        self.assertEqual(result["rewrite_recovery_actions"][0]["kind"], "review-rewrite")
        self.assertEqual(result["rewrite_recovery_actions"][0]["slug"], slug)
        self.assertIn(f"review-rewrite {slug} --status accepted", result["rewrite_recovery_actions"][0]["command"])

    def test_run_compile_failed_attempt_is_written_to_runs_log_and_llm_receipts(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        current = source_page.read_text(encoding="utf-8")

        class _FailingCompileClient:
            def __init__(self) -> None:
                self.config = type("Config", (), {"model": "moonshotai/kimi-k2.5", "backend": "nvidia-nim-api"})()

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                del user_prompt
                return CompletionResult(text=current, response_id="resp-failed", usage={"prompt_tokens": 1})

        with self.assertRaisesRegex(RuntimeError, "placeholder state"):
            run_compile(self.root, client=_FailingCompileClient(), limit=1)

        llm_receipts_path = self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl"
        receipts = [json.loads(line) for line in llm_receipts_path.read_text(encoding="utf-8").splitlines()]
        item_receipt = next(receipt for receipt in receipts if receipt["event"] == "run-compile")
        summary_receipt = receipts[-1]
        self.assertEqual(item_receipt["status"], "failed")
        self.assertEqual(item_receipt["backend_requested"], "nvidia-nim-api")
        self.assertEqual(item_receipt["model_selected"], "moonshotai/kimi-k2.5")
        self.assertEqual(item_receipt["model_final"], "moonshotai/kimi-k2.5")
        self.assertFalse(item_receipt["contract_validated"])
        self.assertEqual(summary_receipt["event"], "run-compile-summary")
        self.assertEqual(summary_receipt["status"], "failed")
        self.assertFalse(summary_receipt["contract_validated"])
        self.assertEqual(summary_receipt["delivery_mode"], "llm-failed")
        self.assertFalse(summary_receipt["fallback_used"])

        runs_log_path = self.root / ".aiwiki" / "logs" / "runs.jsonl"
        run_log = json.loads(runs_log_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(run_log["event"], "run-compile-summary")
        self.assertEqual(run_log["status"], "failed")
        self.assertEqual(run_log["backend_requested"], "nvidia-nim-api")
        self.assertEqual(run_log["model_selected"], "moonshotai/kimi-k2.5")
        self.assertFalse(run_log["contract_validated"])
        self.assertEqual(run_log["delivery_mode"], "llm-failed")
        self.assertFalse(run_log["fallback_used"])

    def test_run_compile_parse_failure_receipt_links_raw_response(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        raw_text = "not a frontmatter just text"

        class _InvalidFrontmatterClient:
            config = type("Config", (), {"model": "stub-model", "backend": "codex-cli", "backend_requested": "codex-cli"})()

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                del user_prompt
                return CompletionResult(text=raw_text, response_id="resp-invalid", usage={})

        with self.assertRaisesRegex(RuntimeError, "frontmatter"):
            run_compile(self.root, client=_InvalidFrontmatterClient(), limit=1)

        receipts = [
            json.loads(line)
            for line in (self.root / ".aiwiki/logs/llm-receipts.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        receipt = next(record for record in receipts if record["event"] == "run-compile")
        raw_response_path = receipt["raw_response_path"]
        self.assertTrue(raw_response_path)
        self.assertEqual(receipt["error_class"], "parse_error")
        self.assertEqual(receipt["error_message"], receipt["error"])
        self.assertEqual((self.root / raw_response_path).read_text(encoding="utf-8"), raw_text)
        self.assertEqual(entry["title"], "Transformer Scaling")

    def test_cache_benchmark_script_outputs_status_and_timings(self) -> None:
        script = Path(__file__).resolve().parent.parent / "scripts" / "cache_benchmark.py"

        completed = subprocess.run(
            [
                "python3",
                str(script),
                "--fixture-count",
                "6",
                "--question",
                "Compare cache rebuild observability",
            ],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str((Path(__file__).resolve().parent.parent / "src").resolve())},
        )

        payload = json.loads(completed.stdout)
        self.assertEqual(payload["fixture_count"], 6)
        self.assertIn("cold_cache", payload["timings_ms"])
        self.assertIn("warm_cache", payload["timings_ms"])
        self.assertIn("no_cache", payload["timings_ms"])
        self.assertIn("query_shapes", payload)
        self.assertIn("cold_cache_sources", payload["query_shapes"])
        self.assertTrue(payload["cache_status"]["enabled"])
        self.assertGreaterEqual(payload["cache_status"]["schema_version"], 1)
        self.assertIn("stats", payload["cache_status"])
        self.assertIn("last_query", payload["cache_status"])

    def test_run_lint_records_audit_fields_and_summary(self) -> None:
        class _LintFallbackClient:
            def __init__(self) -> None:
                self.models = ["moonshotai/kimi-k2.5", "z-ai/glm-5.1"]
                self.index = 0
                self.config = type("Config", (), {"model": self.models[self.index], "backend": "nvidia-nim-api"})()

            def advance_model(self) -> bool:
                if self.index >= len(self.models) - 1:
                    return False
                self.index += 1
                self.config = type("Config", (), {"model": self.models[self.index], "backend": "nvidia-nim-api"})()
                return True

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                del user_prompt
                if self.config.model == "moonshotai/kimi-k2.5":
                    return CompletionResult(text="not markdown enough", response_id="resp-bad", usage={})
                return CompletionResult(text="# Semantic Lint Report\n\n- No semantic contradictions detected.\n", response_id="resp-good", usage={})

        result = run_lint(self.root, client=_LintFallbackClient())

        self.assertEqual(result["backend_requested"], "nvidia-nim-api")
        self.assertEqual(result["backend_effective"], "nvidia-nim-api")
        self.assertEqual(result["model_selected"], "moonshotai/kimi-k2.5")
        self.assertEqual(result["model_final"], "z-ai/glm-5.1")
        self.assertEqual(result["fallback_stage"], "model-chain")
        self.assertTrue(result["contract_validated"])
        self.assertEqual(result["delivery_mode"], "llm-fallback-chain")
        self.assertTrue(result["fallback_used"])

        llm_receipts_path = self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl"
        receipt = json.loads(llm_receipts_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(receipt["event"], "run-lint")
        self.assertEqual(receipt["model_selected"], "moonshotai/kimi-k2.5")
        self.assertEqual(receipt["model_final"], "z-ai/glm-5.1")
        self.assertEqual(receipt["fallback_stage"], "model-chain")
        runs_log = json.loads((self.root / ".aiwiki" / "logs" / "runs.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(runs_log["event"], "run-lint")
        self.assertEqual(runs_log["delivery_mode"], "llm-fallback-chain")
        self.assertTrue(runs_log["fallback_used"])

    def test_run_nightly_returns_top_level_audit_summary(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        updated_source = source_page.read_text(encoding="utf-8").replace(
            "- Pending LLM summary.",
            "- Transformer scale improves capability and raises compute demand.",
        )
        semantic_lint = "# Semantic Lint Report\n\n- Review placeholder concept summaries next.\n"

        result = run_nightly(self.root, client=type(
            "NightlyClient",
            (),
            {
                "__init__": lambda self: setattr(self, "config", type("Config", (), {"model": "stub-model", "backend": "codex-cli"})()),
                "complete": lambda self, system_prompt, user_prompt: CompletionResult(
                    text=updated_source if "Replace file:" in user_prompt else semantic_lint,
                    response_id="resp-nightly",
                    usage={},
                ),
            },
        )(), compile_limit=1)

        self.assertEqual(result["backend_requested"], "codex-cli")
        self.assertEqual(result["backend_effective"], "codex-cli")
        self.assertEqual(result["model_selected"], "stub-model")
        self.assertEqual(result["model_final"], "stub-model")
        self.assertTrue(result["llm_used"])
        self.assertTrue(result["contract_validated"])
        self.assertEqual(result["delivery_mode"], "llm-success")
        self.assertFalse(result["fallback_used"])
        self.assertEqual(result["agent_loop"]["status"], "ok")
        self.assertTrue(result["agent_loop"]["dry_run"])
        self.assertFalse(result["agent_loop"]["side_effects_allowed"])
        self.assertEqual(result["agent_loop"]["auto_preview"]["mode"], "dry_run")

        llm_receipts_path = self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl"
        receipt = json.loads(llm_receipts_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(receipt["event"], "run-nightly")
        self.assertTrue(receipt["llm_used"])
        self.assertEqual(receipt["compile_prompt_profile"], "balanced")
        self.assertEqual(result["promotions"]["count"], 0)
        runs_log = json.loads((self.root / ".aiwiki" / "logs" / "runs.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(runs_log["event"], "run-nightly")
        self.assertEqual(runs_log["delivery_mode"], "llm-success")
        self.assertFalse(runs_log["fallback_used"])
        runtime_history = [
            json.loads(line)
            for line in (self.root / ".aiwiki" / "state" / "runtime-history.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        nightly_events = [event for event in runtime_history if event.get("event_type") == "nightly"]
        self.assertEqual(len(nightly_events), 1)
        self.assertEqual(nightly_events[0]["protocol"], "general")
        self.assertEqual(nightly_events[0]["compile_limit"], 1)
        self.assertTrue(nightly_events[0]["semantic_lint"])
        self.assertTrue(nightly_events[0]["llm_used"])
        self.assertEqual(nightly_events[0]["state_path"], ".aiwiki/state/nightly-health.json")
        self.assertEqual(nightly_events[0]["repair_backlog"], result["repair_backlog"])
        nightly_state = json.loads((self.root / ".aiwiki" / "state" / "nightly-health.json").read_text(encoding="utf-8"))
        self.assertEqual(nightly_state["agent_loop"]["status"], "ok")
        self.assertTrue(nightly_state["agent_loop"]["dry_run"])
        self.assertFalse(nightly_state["agent_loop"]["side_effects_allowed"])
        # EP-029 Step 3 AC #13: nightly integrates protocol_learnings_age stage.
        self.assertIn("protocol_learnings_age", result)
        self.assertTrue(result["protocol_learnings_age"].get("apply"))

    def test_run_nightly_auto_applies_light_lane_when_env_enabled(self) -> None:
        append_runtime_history(
            self.root,
            {
                "event_type": "raw-added",
                "occurred_at": "2026-04-30T00:00:00+00:00",
                "protocol": "general",
                "stored_path": "raw/inbox/example.md",
            },
        )

        with patch.dict(os.environ, {"AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT": "1"}):
            result = run_nightly(self.root, client=_DummyClient(), compile_limit=0, semantic_lint=False)

        self.assertEqual(result["agent_loop"]["status"], "ok")
        self.assertFalse(result["agent_loop"]["dry_run"])
        self.assertTrue(result["agent_loop"]["side_effects_allowed"])
        self.assertEqual(result["agent_loop"]["auto_apply"]["status"], "applied")
        self.assertEqual(result["agent_loop"]["auto_apply"]["applied_count"], 1)
        light = result["agent_loop"]["auto_apply"]["lane_results"][0]
        self.assertEqual(light["selected_primitives"], ["compile", "lint", "nightly"])
        self.assertEqual(len(light["primitive_receipts"]), 3)
        runs_log = json.loads((self.root / ".aiwiki" / "logs" / "runs.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertTrue(runs_log["agent_loop_auto_apply_light"])

    def test_run_nightly_applies_protocol_learnings_aging(self) -> None:
        from datetime import datetime, timedelta
        from datetime import timezone as _tz

        from aiwiki.execution.protocol_learnings import (
            AUDIT_STATE_PATH,
            LEARNINGS_DIR,
            _atomic_write_text,
            _render_inserted_frontmatter,
            add_learning,
        )

        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / "transformer-scaling.md"
        # Fallback: find any existing source page so we can serve a compile response.
        if not source_page.is_file():
            source_page = next((self.root / "wiki" / "sources").glob("*.md"))
        updated_source = source_page.read_text(encoding="utf-8").replace(
            "- Pending LLM summary.",
            "- Transformer scale improves capability.",
        )
        # Seed one derived page under wiki/derived so learning source_ref is valid.
        derived_dir = self.root / "wiki" / "derived"
        derived_dir.mkdir(parents=True, exist_ok=True)
        derived_page = derived_dir / "nightly-aging-fixture.md"
        derived_page.write_text("# fixture\n", encoding="utf-8")
        learning = add_learning(
            self.root,
            "general",
            title="Nightly aging fixture",
            source_refs=[f"wiki/derived/{derived_page.name}"],
        )
        # Backdate last_verified_at to > 90 days so aging marks it stale.
        learning_path = self.root / learning["path"]
        text = learning_path.read_text(encoding="utf-8")
        old = (datetime.now(_tz.utc) - timedelta(days=100)).replace(microsecond=0).isoformat()
        from aiwiki.app_utils import parse_frontmatter as _pfm

        fm = _pfm(text)
        fm["last_verified_at"] = old
        parts = text.split("---", 2)
        body = parts[-1].lstrip("\n") if len(parts) >= 3 else text
        _atomic_write_text(learning_path, _render_inserted_frontmatter(fm) + body)

        semantic_lint = "# Semantic Lint Report\n\n- Nothing to review.\n"
        run_nightly(
            self.root,
            client=type(
                "NightlyClient2",
                (),
                {
                    "__init__": lambda self: setattr(self, "config", type("Config", (), {"model": "stub-model", "backend": "codex-cli"})()),
                    "complete": lambda self, system_prompt, user_prompt: CompletionResult(
                        text=updated_source if "Replace file:" in user_prompt else semantic_lint,
                        response_id="resp-nightly-aging",
                        usage={},
                    ),
                },
            )(),
            compile_limit=1,
        )

        # Aged: learning should be marked stale and audit dropped.
        audit_path = self.root / AUDIT_STATE_PATH
        self.assertTrue(audit_path.is_file())
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        self.assertTrue(audit["apply"])
        self.assertGreaterEqual(len(audit["aged"]), 1)
        aged_ids = [e["learning_id"] for e in audit["aged"]]
        self.assertIn(learning["learning_id"], aged_ids)
        final_fm = _pfm(learning_path.read_text(encoding="utf-8"))
        self.assertEqual(final_fm.get("state"), "stale")
        self.assertTrue(learning["path"].startswith(LEARNINGS_DIR))

    def test_run_nightly_reports_dirty_protocol_learning_graph_in_audit(self) -> None:
        from aiwiki.execution.protocol_learnings import AUDIT_STATE_PATH, _atomic_write_text

        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        learning_dir = self.root / "wiki" / "protocol-learnings" / "general"
        learning_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(
            learning_dir / "replacement.md",
            "\n".join([
                "---",
                'learning_id: "replacement"',
                'protocol: "general"',
                'title: "replacement"',
                "source_refs:",
                '  - "wiki/derived/source.md"',
                'state: "active"',
                f'created_at: {json.dumps("2026-01-01T00:00:00+00:00")}',
                f'updated_at: {json.dumps("2026-01-01T00:00:00+00:00")}',
                f'last_verified_at: {json.dumps("2026-01-01T00:00:00+00:00")}',
                "supersedes:",
                '  - "old-one"',
                "---",
                "# Protocol Learning",
                "",
            ]),
        )
        _atomic_write_text(
            learning_dir / "old-one.md",
            "\n".join([
                "---",
                'learning_id: "old-one"',
                'protocol: "general"',
                'title: "old-one"',
                "source_refs:",
                '  - "wiki/derived/source.md"',
                'state: "active"',
                f'created_at: {json.dumps("2026-01-01T00:00:00+00:00")}',
                f'updated_at: {json.dumps("2026-01-01T00:00:00+00:00")}',
                f'last_verified_at: {json.dumps("2026-01-01T00:00:00+00:00")}',
                "---",
                "# Protocol Learning",
                "",
            ]),
        )
        semantic_lint = "# Semantic Lint Report\n\n- Nothing to review.\n"

        result = run_nightly(
            self.root,
            client=type(
                "NightlyClient3",
                (),
                {
                    "__init__": lambda self: setattr(self, "config", type("Config", (), {"model": "stub-model", "backend": "codex-cli"})()),
                    "complete": lambda self, system_prompt, user_prompt: CompletionResult(
                        text=semantic_lint,
                        response_id="resp-nightly-dirty-graph",
                        usage={},
                    ),
                },
            )(),
            compile_limit=0,
        )

        self.assertIn("protocol_learnings_age", result)
        self.assertTrue(result["protocol_learnings_age"]["errors"])
        self.assertIn("learning graph inconsistent", result["protocol_learnings_age"]["errors"][0]["reason"])
        audit = json.loads((self.root / AUDIT_STATE_PATH).read_text(encoding="utf-8"))
        self.assertIn("learning graph inconsistent", audit["errors"][0]["reason"])

    def test_promote_recurring_outputs_enqueues_candidates_instead_of_filing_back(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        question = "Should we adopt transformer caching for inference?"
        ask_question(self.root, question, "report")
        ask_question(self.root, question, "report")

        result = promote_recurring_outputs(self.root)

        self.assertEqual(result["count"], 1)
        self.assertFalse((self.root / "wiki" / "decisions").exists())
        self.assertFalse((self.root / "wiki" / "judgments").exists())
        state = load_output_candidates_state(self.root)
        self.assertTrue(state["candidates"])
        promoted_ref = result["pages"][0]["candidate_ref"]
        candidate = next(c for c in state["candidates"] if c["artifact_ref"] == promoted_ref)
        self.assertEqual(candidate["candidate_state"], "pending")
        self.assertEqual(candidate["promotion_origin"], "nightly-recurring")
        self.assertIn("recurring_kind", candidate)

    def test_ask_question_writes_safe_run_notes_and_frontmatter(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        result = ask_question(self.root, f"Compare scaling from {self.root}/private/raw.md and /srv/private/raw.md", "report")

        self.assertTrue(result["run_id"])
        self.assertTrue(result["run_notes_path"].startswith("output/control/runs/"))
        notes_path = self.root / result["run_notes_path"]
        self.assertTrue(notes_path.exists())
        notes = notes_path.read_text(encoding="utf-8")
        self.assertIn('kind: "run-progress-notes"', notes)
        self.assertIn('status: "deterministic-ready"', notes)
        self.assertIn("Visible Run Progress", notes)
        self.assertIn("Safety Boundary", notes)
        self.assertIn("[vault-root]", notes)
        self.assertIn("[local-path]", notes)
        self.assertNotIn("<thought>", notes)
        self.assertNotIn(str(self.root), notes)
        self.assertNotIn("/srv/private/raw.md", notes)
        self.assertNotIn("system prompt", notes.lower())
        output_frontmatter = parse_frontmatter((self.root / result["path"]).read_text(encoding="utf-8"))
        self.assertEqual(output_frontmatter["run_id"], result["run_id"])
        self.assertEqual(output_frontmatter["run_notes_path"], result["run_notes_path"])

    def test_run_notes_ids_include_output_directory_to_avoid_format_collisions(self) -> None:
        from aiwiki.execution.run_notes import run_id_for_artifact

        report_id = run_id_for_artifact("output/reports/same-topic.md")
        slides_id = run_id_for_artifact("output/slides/same-topic.md")

        self.assertNotEqual(report_id, slides_id)
        self.assertIn("output-reports-same-topic", report_id)
        self.assertIn("output-slides-same-topic", slides_id)

    def test_run_ask_prompt_excludes_run_notes_frontmatter_fields(self) -> None:
        artifact_path = self.root / "output" / "reports" / "query-run-notes-prompt.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            "---\n"
            "id: query-run-notes-prompt\n"
            "kind: report\n"
            "run_id: ask-output-reports-query-run-notes-prompt\n"
            "run_notes_path: output/control/runs/ask-output-reports-query-run-notes-prompt/thinking.md\n"
            "background_job_id: ask-report-123\n"
            "background_status: running\n"
            "delivery_mode: background-pending\n"
            "llm_status: pending\n"
            "llm_backend: opencode-api\n"
            "llm_model: deepseek-v4-pro\n"
            "llm_failure_reason: pending\n"
            "---\n\n# Placeholder\n",
            encoding="utf-8",
        )
        artifact = {
            "path": "output/reports/query-run-notes-prompt.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": [],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
            "run_id": "ask-output-reports-query-run-notes-prompt",
            "run_notes_path": "output/control/runs/ask-output-reports-query-run-notes-prompt/thinking.md",
        }

        class _PromptCaptureClient:
            def __init__(self) -> None:
                self.config = type("Config", (), {"model": "gpt-5.4", "timeout_seconds": 120})()

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                self.prompt = user_prompt
                return CompletionResult(text=_VALID_REPORT_BODY, response_id="resp_prompt", usage={})

        client = _PromptCaptureClient()
        with patch("aiwiki.runner.workflows_ask.ask_question", return_value=artifact):
            run_ask(self.root, "测试", "report", client=client)

        self.assertNotIn("run_id:", client.prompt)
        self.assertNotIn("run_notes_path:", client.prompt)
        self.assertNotIn("background_job_id:", client.prompt)
        self.assertNotIn("background_status:", client.prompt)
        self.assertNotIn("delivery_mode:", client.prompt)
        self.assertNotIn("llm_status:", client.prompt)
        self.assertNotIn("llm_backend:", client.prompt)
        self.assertNotIn("llm_model:", client.prompt)
        self.assertNotIn("llm_failure_reason:", client.prompt)

    def test_reinject_candidate_frontmatter_synthesizes_when_llm_strips_frontmatter(self) -> None:
        target = self.root / "output" / "reports" / "stripped.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Naked body\n\nNo frontmatter at all.\n", encoding="utf-8")

        _reinject_candidate_frontmatter(target, corpus_id="investing-foo-abc12345")

        content = target.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("---\n"))
        self.assertIn('candidate_state: "pending"', content)
        self.assertIn('corpus_id: "investing-foo-abc12345"', content)
        self.assertIn("# Naked body", content)

    def test_reinject_candidate_frontmatter_preserves_slides_marp_literal(self) -> None:
        target = self.root / "output" / "slides" / "deck.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("---\nmarp: true\ntitle: Deck\n---\n\n# Slide 1\n", encoding="utf-8")

        _reinject_candidate_frontmatter(target, corpus_id="research-foo-deadbeef")

        content = target.read_text(encoding="utf-8")
        # marp: true 保留原始字面，不被 YAML round-trip 成 True
        self.assertIn("marp: true", content)
        self.assertIn('candidate_state: "pending"', content)
        self.assertIn('corpus_id: "research-foo-deadbeef"', content)

    def test_prompt_helpers_include_schema_protocol_and_quality_signals(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        concept_page = self.root / "wiki" / "concepts" / "transformer-scaling.md"
        prompt = _build_compile_prompt(self.root, entry, self.root / entry["stored_path"], source_page.read_text(encoding="utf-8"))

        self.assertIn("## Runtime Schema", prompt)
        self.assertIn("## Active Protocol", prompt)
        self.assertIn(entry["stored_path"], prompt)
        self.assertIn("Replace file:", prompt)

        concept_prompt = _build_concept_compile_prompt(
            self.root,
            concept_page,
            concept_page.read_text(encoding="utf-8"),
            [f"wiki/sources/{entry['id']}.md"],
            ["transformer-scaling"],
            quality_record={
                "priority": "high",
                "issues": ["conflict", "gap"],
                "rewrite_strategy": "Make evidence boundaries explicit.",
                "conflict_signals": [{"label": "source-tension", "source_pages": [f"wiki/sources/{entry['id']}.md"]}],
                "gap_signals": [{"kind": "coverage-gap", "path": str(concept_page), "markers": ["missing-benchmark"]}],
            },
        )

        self.assertIn("Rewrite priority: `high`", concept_prompt)
        self.assertIn("Conflict `source-tension`", concept_prompt)
        self.assertIn("Gap `coverage-gap`", concept_prompt)
        self.assertIn("Make evidence boundaries explicit.", concept_prompt)
        self.assertIn("hardness: soft|medium|hard", concept_prompt)

    def test_load_prompt_falls_back_to_runtime_templates_when_vault_prompt_is_missing(self) -> None:
        (self.root / "prompts" / "ask.md").unlink()

        prompt = _load_prompt(self.root, "ask.md")

        self.assertIn("Return the full replacement artifact only", prompt)

    def test_compile_prompt_adds_note_kind_hints_for_transcripts(self) -> None:
        drop_note(
            self.root,
            text="# Standup\n\nAlice: review backlog.\nBob: ship runtime validation.\n",
            kind="transcript",
        )
        manifest = sync_manifest_with_raw(self.root)
        entry = manifest["entries"][0]
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"

        prompt = _build_compile_prompt(self.root, entry, self.root / entry["stored_path"], source_page.read_text(encoding="utf-8"))

        self.assertIn("Material kind: `transcript`", prompt)
        self.assertIn("Preserve chronology, speaker attributions", prompt)

    def test_rewrite_candidate_and_machine_query_helpers_render_expected_details(self) -> None:
        memory = {
            "health": {
                "concept_quality": {
                    "rewrite_candidates": [
                        {"slug": "agent", "priority": "high", "issues": ["gap"]},
                        {"slug": "protocol", "priority": "medium", "issues": []},
                    ],
                    "weak_concepts": [
                        {
                            "slug": "agent",
                            "conflict_signals": [{"label": "conflict", "source_pages": ["wiki/sources/a.md"]}],
                            "gap_signals": [{"kind": "gap", "path": "wiki/concepts/agent.md", "markers": ["missing"]}],
                        }
                    ],
                }
            }
        }
        self.assertEqual(_rewrite_candidate_slugs(memory, exclude={"protocol"}), ["agent"])
        record = _rewrite_candidate_record(memory, "agent")
        self.assertEqual(record["priority"], "high")
        self.assertEqual(record["conflict_signals"][0]["label"], "conflict")
        self.assertEqual(_rewrite_candidate_record(memory, "missing"), {})

        rendered = _render_machine_query(
            {
                "matched_terms": ["agent", "protocol"],
                "selected_strategy": "graph-walk",
                "selection_reason": "graph-markers",
                "matched_source_markers": ["source"],
                "matched_graph_markers": ["why"],
                "direct_source_ids": ["s1"],
                "direct_concept_slugs": ["agent"],
                "ranked_source_ids": ["s1", "s2"],
                "ranked_concept_slugs": ["agent", "protocol"],
                "bridge_concept_slugs": ["memory"],
                "touched_component_ids": ["component-1"],
                "supporting_edges": [{"type": "source_to_concept", "left": "s1", "right": "agent"}],
                "query_subgraph": {"sources": [{"id": "s1"}], "concepts": [{"slug": "agent"}], "edges": [1, 2]},
                "query_routes": [
                    {
                        "start": {"id": "s1", "title": "Source 1"},
                        "goal": {"id": "agent", "title": "Agent"},
                        "length": 2,
                        "strategy": "graph-walk",
                    }
                ],
                "planner_next_action": {"action_id": "repair-1", "title": "Repair concept", "priority_score": 42},
                "relevant_actions": [
                    {
                        "priority": "high",
                        "title": "Repair concept",
                        "status": "open",
                        "execution_policy": "safe-apply",
                        "primary_path": "wiki/concepts/agent.md",
                        "secondary_path": "wiki/indexes/concept-quality.md",
                        "next_step": "review",
                        "proposal_kind": "rewrite",
                        "proposal_targets": ["wiki/concepts/agent.md"],
                        "proposal_summary": "Tighten synthesis",
                    }
                ],
            }
        )

        self.assertIn("Matched terms", rendered)
        self.assertIn("Route summaries", rendered)
        self.assertIn("Repair action summaries", rendered)
        self.assertIn("Planner next action", rendered)

    def test_text_helpers_validation_and_state_writers_cover_edge_cases(self) -> None:
        self.assertIn("local-first research wiki", _system_prompt("compile"))
        self.assertIn("Return only the full replacement artifact", _system_prompt("ask"))
        self.assertIn("semantic issues", _system_prompt("lint"))

        self.assertEqual(_normalize_markdown("```md\n# Title\n```\n"), "# Title\n")
        self.assertTrue(_fit_prompt_section("abcdef", 3).endswith("...[truncated]"))
        self.assertTrue(_fit_prompt_section("abcdef", 3, tail=True).startswith("...[truncated earlier content]"))
        log_text = "## A\none\n## B\ntwo\n## C\nthree\n## D\nfour\n"
        self.assertIn("truncated earlier log entries", _fit_log_prompt_section(log_text, 12))
        self.assertEqual(_extract_related_concept_slugs("[A](./agent.md)\n[B](./agent.md)\n[C](./protocol.md)"), ["agent", "protocol"])

        long_text = "x" * 40
        long_path = self.root / "long.md"
        long_path.write_text(long_text, encoding="utf-8")
        self.assertTrue(_read_context(long_path, 10).endswith("...[truncated]"))

        binary_path = self.root / "tiny.bin"
        binary_path.write_bytes(b"binary-content")
        with patch("aiwiki.runner.prompts.read_text_preview", return_value="preview"):
            self.assertEqual(_read_context(binary_path, 20), "preview")

        self.assertIn("schema/index.md", _schema_context(self.root, ("index.md", "missing.md")))
        self.assertIn("Active protocol: `general`", _protocol_context(self.root, ("index.md", "missing.md")))

        source_markdown = "\n".join(
            [
                "---",
                'id: "source-1"',
                'kind: "source"',
                "source_files:",
                '  - "raw/inbox/source.md"',
                'source_sha256: "sha-1"',
                "---",
                "",
                "# Title",
                "",
                "## Summary",
                "- Grounded summary.",
                "",
            ]
        )
        _validate_source_page(source_markdown, "source-1", "raw/inbox/source.md", "sha-1")
        with self.assertRaises(RuntimeError):
            _validate_source_page("# missing frontmatter\n", "source-1", "raw/inbox/source.md", "sha-1")
        with self.assertRaises(RuntimeError):
            _validate_source_page(source_markdown.replace('id: "source-1"', 'id: "source-2"'), "source-1", "raw/inbox/source.md", "sha-1")
        with self.assertRaises(RuntimeError):
            _validate_source_page(source_markdown.replace("- Grounded summary.", "- Pending LLM summary."), "source-1", "raw/inbox/source.md", "sha-1")
        with self.assertRaisesRegex(RuntimeError, "source_files"):
            _validate_source_page(
                source_markdown.replace(
                    'source_files:\n  - "raw/inbox/source.md"',
                    'source_files: ["raw/inbox/source.md"]',
                ),
                "source-1",
                "raw/inbox/source.md",
                "sha-1",
            )

        concept_markdown = "\n".join(
            [
                "---",
                'id: "concept-agent"',
                'kind: "concept"',
                'source_signature: "sig-1"',
                "source_pages:",
                '  - "wiki/sources/source-1.md"',
                'hardness: "medium"',
                "---",
                "",
                "# Agent",
                "",
                "## Summary",
                "- Grounded synthesis.",
                "",
            ]
        )
        _validate_concept_page(concept_markdown, "agent", "sig-1", ["wiki/sources/source-1.md"])
        with self.assertRaisesRegex(RuntimeError, "source_pages"):
            _validate_concept_page(
                concept_markdown.replace(
                    'source_pages:\n  - "wiki/sources/source-1.md"',
                    'source_pages: ["wiki/sources/source-1.md"]',
                ),
                "agent",
                "sig-1",
                ["wiki/sources/source-1.md"],
            )
        with self.assertRaises(RuntimeError):
            _validate_concept_page("# missing frontmatter\n", "agent", "sig-1", ["wiki/sources/source-1.md"])
        with self.assertRaises(RuntimeError):
            _validate_concept_page(concept_markdown.replace('id: "concept-agent"', 'id: "concept-other"'), "agent", "sig-1", ["wiki/sources/source-1.md"])
        with self.assertRaises(RuntimeError):
            _validate_concept_page(
                concept_markdown.replace("- Grounded synthesis.", "- This concept currently appears in `1` source page(s)."),
                "agent",
                "sig-1",
                ["wiki/sources/source-1.md"],
            )
        with self.assertRaises(RuntimeError):
            _validate_concept_page(
                concept_markdown.replace('hardness: "medium"', 'hardness: "unknown"'),
                "agent",
                "sig-1",
                ["wiki/sources/source-1.md"],
            )

        valid_report = (
            "---\nformat: report\n---\n\n"
            "## 结论\nA\n\n"
            "## 关键证据\n"
            "- See wiki/sources/source-1.md\n"
            "- Second evidence point.\n"
            "- Third evidence point.\n\n"
            "## 反证与不确定性\n- None.\n\n"
            "## 行动建议\n- Follow up.\n\n"
            "## 下次观察信号\n- Revisit signal.\n\n"
            "## 引用\n- wiki/sources/source-1.md\n"
        )
        _validate_output_markdown(valid_report, "report", ["source-1"])
        duplicate_citation_report = valid_report.replace(
            "## 引用\n- wiki/sources/source-1.md\n",
            "## 引用\n- wiki/sources/source-1.md\n- wiki/sources/source-1.md\n",
        )
        with self.assertRaisesRegex(RuntimeError, "duplicate citation"):
            _validate_output_markdown(duplicate_citation_report, "report", ["source-1"])
        deduped_report = _dedupe_report_citations(duplicate_citation_report)
        _validate_output_markdown(deduped_report, "report", ["source-1"])
        self.assertEqual(deduped_report.count("wiki/sources/source-1.md"), 2)
        with self.assertRaises(RuntimeError):
            _validate_output_markdown("# no frontmatter\n", "report", ["source-1"])
        with self.assertRaises(RuntimeError):
            _validate_output_markdown(
                "---\nformat: report\n---\n\n"
                "## 结论\nA\n\n## 关键证据\nB\n\n## 反证与不确定性\nC\n\n"
                "## 行动建议\nD\n\n## 下次观察信号\nE\n\n## 引用\nNo citations here.\n",
                "report",
                ["source-1"],
            )

        _append_log(self.root, {"event": "runner-test"})
        log_path = self.root / ".aiwiki" / "logs" / "runs.jsonl"
        self.assertTrue(log_path.exists())
        llm_receipt_path = self.root / ".aiwiki" / "logs" / "llm-receipts.jsonl"
        self.assertFalse(llm_receipt_path.exists())
        _write_automation_state(self.root, {"status": "ok"})
        state_path = self.root / ".aiwiki" / "state" / "automation.json"
        self.assertEqual(json.loads(state_path.read_text(encoding="utf-8"))["status"], "ok")
        self.assertEqual(_client_model_name(_DummyClient()), "dummy-model")

    def test_pending_summary_count_tracks_placeholder_sources(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        self.assertEqual(_pending_summary_count(self.root), 1)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        source_page.write_text(
            source_page.read_text(encoding="utf-8").replace("- Pending LLM summary.", "- Grounded summary."),
            encoding="utf-8",
        )
        self.assertEqual(_pending_summary_count(self.root), 0)
        with patch("aiwiki.runner.prompts.LLMConfig.status_from_env", return_value={"max_context_chars": 1234}):
            self.assertEqual(_context_budget(), 1234)

    def test_run_compile_skips_preflight_when_client_injected(self) -> None:
        with patch("aiwiki.runner.preflight.probe_backend") as probe_backend:
            result = run_compile(self.root, client=_DummyClient(), limit=0)

        probe_backend.assert_not_called()
        self.assertEqual(result["updated_pages"], [])

    def test_run_ask_skips_preflight_when_client_injected(self) -> None:
        artifact_path = self.root / "output" / "reports" / "query-preflight-skip.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("---\nid: query-preflight-skip\nkind: report\n---\n\n# Placeholder\n", encoding="utf-8")
        artifact = {
            "path": "output/reports/query-preflight-skip.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": [],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
        }

        class _AskClient:
            config = type("Config", (), {"model": "gpt-5.4", "timeout_seconds": 120})()

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                del user_prompt
                return CompletionResult(
                    text=_VALID_REPORT_BODY,
                    response_id="resp-preflight-skip",
                    usage={},
                )

        with patch("aiwiki.runner.preflight.probe_backend") as probe_backend:
            with patch("aiwiki.runner.workflows_ask.ask_question", return_value=artifact):
                with patch("aiwiki.runner.workflows_ask._validate_output_markdown", return_value=None):
                    run_ask(self.root, "测试", "report", client=_AskClient())

        probe_backend.assert_not_called()

    def test_run_compile_calls_preflight_when_client_none(self) -> None:
        with patch(
            "aiwiki.runner.preflight.probe_backend",
            return_value={"compatibility": "compatible", "backend": "codex-cli", "model": "gpt-5.5", "compatibility_hint": ""},
        ) as probe_backend:
            with patch("aiwiki.runner.preflight.LLMConfig.from_env", return_value=LLMConfig(backend="codex-cli")):
                result = run_compile(self.root, client=None, limit=0)

        probe_backend.assert_called_once()
        self.assertEqual(result["updated_pages"], [])

    def test_run_ask_calls_preflight_when_client_none(self) -> None:
        artifact_path = self.root / "output" / "reports" / "query-preflight-call.md"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("---\nid: query-preflight-call\nkind: report\n---\n\n# Placeholder\n", encoding="utf-8")
        artifact = {
            "path": "output/reports/query-preflight-call.md",
            "format": "report",
            "protocol": "general",
            "ranked_sources": [],
            "ranked_concepts": [],
            "protocol_pages": [],
            "index_pages": [],
            "machine_memory_query": {},
        }

        class _AskClient:
            config = type("Config", (), {"model": "gpt-5.4", "timeout_seconds": 120})()

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                del user_prompt
                return CompletionResult(
                    text=_VALID_REPORT_BODY,
                    response_id="resp-preflight-call",
                    usage={},
                )

        with patch(
            "aiwiki.runner.preflight.probe_backend",
            return_value={"compatibility": "compatible", "backend": "codex-cli", "model": "gpt-5.5", "compatibility_hint": ""},
        ) as probe_backend:
            with patch("aiwiki.runner.preflight.LLMConfig.from_env", return_value=LLMConfig(backend="codex-cli")):
                with patch("aiwiki.runner.workflows_ask.create_client", return_value=_AskClient()):
                    with patch("aiwiki.runner.workflows_ask.ask_question", return_value=artifact):
                        with patch("aiwiki.runner.workflows_ask._validate_output_markdown", return_value=None):
                            run_ask(self.root, "测试", "report", client=None)

        probe_backend.assert_called_once()
