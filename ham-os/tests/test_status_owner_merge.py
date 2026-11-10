"""Regression tests for owner-facing 9998 execution-chain grouping."""
from __future__ import annotations

import importlib.util
from pathlib import Path


SERVER = Path.home() / ".hindsight/releases/ham-os-status-1.0.0-phase6-interim-gate-20260829T2300/control/hindsight_rebuild_status_server.py"
spec = importlib.util.spec_from_file_location("hindsight_status_server", SERVER)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def test_background_continuation_merges_into_its_owner_turn() -> None:
    fingerprint = "same-user-prompt"
    owner = {
        "at": "2026-08-30T18:00:00Z", "event": "recall", "query_id": "owner",
        "execution_id": "owner", "query_preview": "请完整梳理 Hindsight 的更新履历",
        "query_fingerprint": fingerprint, "user_prompt_fingerprint": fingerprint,
        "client": "codex-hook", "role": "codex", "bank_id": "bank",
        "execution_complete": True, "memory_action": "deep_recall", "result_count": 5,
        "memory_effectiveness": {"injected_count": 5, "retrieved_count": 5},
    }
    helper = {
        "at": "2026-08-30T18:00:01Z", "event": "recall", "query_id": "helper",
        "execution_id": "helper", "query_preview": owner["query_preview"],
        "query_fingerprint": fingerprint, "user_prompt_fingerprint": fingerprint,
        "client": "codex-hook", "role": "codex", "bank_id": "bank",
        "execution_complete": True, "continuation_mode": True,
        "memory_action": "deep_recall", "result_count": 0,
        "memory_effectiveness": {"injected_count": 0, "retrieved_count": 0},
    }
    merged = module.merge_owner_turns([owner, helper])
    assert len(merged) == 1
    assert merged[0]["memory_effectiveness"]["injected_count"] == 5
    assert merged[0]["owner_turn_receipt"]["execution_count"] == 2
    assert merged[0]["owner_turn_receipt"]["helper_execution_count"] == 1


def test_foreground_completion_merges_and_exposes_the_packet_that_hook_received() -> None:
    """A synchronous deep pass must replace the focused delivery projection."""
    fingerprint = "foreground-complete"
    owner = {
        "at": "2026-09-03T01:00:00Z", "event": "recall", "query_id": "owner",
        "execution_id": "owner", "query_preview": "解释系统之间的因果链",
        "query_fingerprint": fingerprint, "user_prompt_fingerprint": fingerprint,
        "client": "codex-hook", "role": "codex", "bank_id": "bank",
        "execution_complete": True, "coverage_complete": False,
        "memory_action": "system_map", "result_count": 6,
        "memory_effectiveness": {
            "injected_count": 5, "retrieved_count": 6,
            "packet_delivery": {"state": "hook_context_prepared", "transport_record_ids": ["o-1"]},
        },
    }
    deep = {
        "at": "2026-09-03T01:00:05Z", "event": "recall", "query_id": "deep",
        "execution_id": "deep", "query_preview": owner["query_preview"],
        "query_fingerprint": fingerprint, "user_prompt_fingerprint": fingerprint,
        "client": "codex-hook", "role": "codex", "bank_id": "bank",
        "execution_complete": True, "coverage_complete": True,
        "continuation_mode": True, "foreground_continuation": True,
        "foreground_parent_execution_id": "owner", "memory_action": "system_map",
        "result_count": 8,
        "memory_effectiveness": {
            "injected_count": 7, "retrieved_count": 8,
            "packet_delivery": {"state": "hook_packet_delivered", "transport_record_ids": [f"d-{i}" for i in range(7)]},
        },
    }
    merged = module.merge_owner_turns([owner, deep])
    assert len(merged) == 1
    trace = merged[0]
    assert trace["memory_effectiveness"]["injected_count"] == 7
    receipt = trace["owner_turn_receipt"]
    assert receipt["execution_count"] == 2
    assert receipt["foreground_continuation_count"] == 1
    assert receipt["foreground_continuations"][0]["parent_execution_id"] == "owner"
    assert receipt["actual_injected_count"] == 7


def test_owner_trace_keeps_clean_user_wording_and_exposes_helper_provenance() -> None:
    fingerprint = "prompt-provenance"
    owner = {
        "at": "2026-08-31T12:00:00Z", "event": "recall", "query_id": "owner",
        "execution_id": "owner", "query_preview": "修复状态页的真实链路显示",
        "raw_user_prompt": (
            "当前任务需要补齐相关历史事实、已做决策、实施进度、未完成项和回退条件。\n"
            "当前问题：修复状态页的真实链路显示"
        ),
        "query_fingerprint": fingerprint, "user_prompt_fingerprint": fingerprint,
        "client": "codex-hook", "role": "codex", "bank_id": "bank",
        "execution_complete": True, "result_count": 2,
        "memory_effectiveness": {"injected_count": 2, "retrieved_count": 2},
    }
    helper = {
        "at": "2026-08-31T12:00:01Z", "event": "background_continuation", "query_id": "helper",
        "execution_id": "helper", "query_preview": "当前任务需要补齐相关历史事实、已做决策、实施进度、未完成项和回退条件。",
        "query_fingerprint": fingerprint, "user_prompt_fingerprint": fingerprint,
        "client": "codex-hook", "role": "codex", "bank_id": "bank",
        "execution_complete": True, "continuation_mode": True, "result_count": 7,
        "memory_effectiveness": {"injected_count": 0, "retrieved_count": 7},
    }
    merged = module.merge_owner_turns([owner, helper])
    trace = merged[0]
    assert trace["raw_user_prompt"] == "修复状态页的真实链路显示"
    assert trace["prompt_provenance"]["kind"] == "user_direct"
    assert trace["owner_turn_receipt"]["helper_executions"] == [{
        "execution_id": "helper", "at": "2026-08-31T12:00:01Z", "kind": "controller_internal_helper",
        "result_count": 7, "feedback_sample_count": 7, "injected_count": 0,
        "outcome": "completed",
    }]


def test_late_helper_results_do_not_overwrite_actual_owner_delivery_chain() -> None:
    """A timed-out supplement is audit evidence, not retroactive injection."""
    fingerprint = "late-helper"
    owner = {
        "at": "2026-08-31T14:09:43Z", "event": "recall",
        "query_id": "owner", "execution_id": "owner",
        "query_preview": "状态页中我在哪查 full prompt 啊？",
        "query_fingerprint": fingerprint, "user_prompt_fingerprint": fingerprint,
        "client": "codex-hook", "role": "codex", "bank_id": "bank",
        "execution_complete": True, "result_count": 0,
        "selected_results": [],
        "claim_receipt": {"admitted_claim_count": 0, "candidate_record_count": 0, "claims": []},
        "memory_effectiveness": {"injected_count": 0, "retrieved_count": 0},
    }
    helper = {
        "at": "2026-08-31T14:09:53Z", "event": "recall",
        "query_id": "helper", "execution_id": "helper",
        "query_preview": (
            "当前任务需要补齐相关历史事实、已做决策、实施进度、未完成项和回退条件。"
            "\n当前问题：状态页中我在哪查 full prompt 啊？"
        ),
        "query_fingerprint": fingerprint, "user_prompt_fingerprint": fingerprint,
        "client": "codex-hook", "role": "codex", "bank_id": "bank",
        "execution_complete": True, "result_count": 10,
        "selected_results": [{"id": "late"}],
        "claim_receipt": {"admitted_claim_count": 10, "candidate_record_count": 10, "claims": [{"claim_id": "late"}]},
        "memory_effectiveness": {"injected_count": 0, "retrieved_count": 10},
    }
    trace = module.merge_owner_turns([owner, helper])[0]
    assert trace["result_count"] == 0
    assert trace["selected_results"] == []
    assert trace["claim_receipt"]["admitted_claim_count"] == 0
    assert trace["memory_effectiveness"]["injected_count"] == 0
    assert trace["owner_turn_receipt"]["helper_executions"][0]["result_count"] == 10


def test_status_page_names_all_four_actual_pipeline_stages() -> None:
    page = (Path.home() / ".hindsight" / "control-plane" / "recall-observability.html").read_text(encoding="utf-8")
    for label in ("检索原始候选", "Controller 准入", "Hook 后处理", "Memory Packet 实际投递"):
        assert label in page


def test_full_prompt_modal_labels_deterministic_and_failed_qwen_fallbacks_truthfully() -> None:
    page = (Path.home() / ".hindsight" / "control-plane" / "recall-observability.html").read_text(encoding="utf-8")
    assert "deterministic_context_hint_only:'本地结构信封（未使用会话上下文）'" in page
    assert "Qwen 消解未采用；回退" in page


def test_status_page_distinguishes_mcp_tool_reads_from_hook_zero_injection() -> None:
    page = (Path.home() / ".hindsight" / "control-plane" / "recall-observability.html").read_text(encoding="utf-8")
    assert "MCP 按需读取" in page
    assert "不计入 Hook 实际注入" in page
    assert "Agent 工具读取" in page


def test_count_only_injection_receipt_is_not_projected_as_zero() -> None:
    trace = {
        "at": "2026-08-31T12:00:00Z", "query_preview": "Hermes 测试", "query_id": "h",
        "execution_id": "h", "client": "hermes-hindsight-full-prompt-adapter", "role": "hermes",
        "memory_effectiveness": {"actual_injected_count": 3, "injected_count": 0, "injected_ids": []},
    }
    normalized = module.normalize_trace_for_status(trace)
    effect = normalized["memory_effectiveness"]
    assert effect["injected_count"] == 3
    assert effect["injection_receipt_state"] == "count_only_historical"
    assert effect["candidate_record_count"] == 0


def test_candidate_metric_prefers_the_hook_candidate_ledger_over_controller_claim_input() -> None:
    normalized = module.normalize_trace_for_status({
        "query_id": "candidate-units",
        "claim_receipt": {"candidate_record_count": 1},
        "memory_effectiveness": {
            "candidate_count": 34,
            "claim_delivery": {
                "candidate_record_count": 34,
                "candidate_record_ids": [f"c-{i}" for i in range(34)],
                "controller_claim_input_count": 1,
            },
        },
    })
    assert normalized["memory_effectiveness"]["candidate_record_count"] == 34


def test_exact_stage_accounting_overrides_stale_compact_effectiveness_counts() -> None:
    """The owner page must not show a compact sample as the full candidate total."""
    normalized = module.normalize_trace_for_status({
        "query_id": "exact-stage-accounting",
        "result_count": 30,
        "pipeline_stages": {
            "retrieval": {"raw_result_count": 122, "fused_candidate_count": 100,
                           "controller_input_count": 101},
            "controller_admission": {"input_count": 101, "qualified_count": 30,
                                      "rejected_count": 71, "deferred_count": 0},
            "hook_postprocessing": {"input_count": 31, "admitted_count": 16,
                                     "rejected_count": 15, "deferred_count": 0},
            "packet_delivery": {"input_count": 16, "delivered_count": 16,
                                 "not_delivered_count": 0},
        },
        "memory_effectiveness": {
            # This is the stale bounded feedback sample seen in a real trace.
            "candidate_count": 12,
            "candidate_record_count": 12,
            "rejected_before_injection_count": 12,
            "retrieved_count": 7,
            "injected_count": 16,
        },
    })
    effect = normalized["memory_effectiveness"]
    assert effect["candidate_record_count"] == 101
    assert effect["candidate_count"] == 101
    assert effect["rejected_before_injection_count"] == 71
    assert effect["qualified_count"] == 30
    assert effect["controller_input_count"] == 101
    assert effect["hook_input_count"] == 31
    assert effect["packet_delivered_count"] == 16
    assert effect["feedback_sample_count"] == 7
    assert effect["stage_accounting_source"] == "pipeline_stages"


def test_status_exposes_controller_and_hook_sidecar_candidate_boundaries() -> None:
    """A Hook-only governance sidecar must not look like a Controller mismatch."""
    normalized = module.normalize_trace_for_status({
        "query_id": "candidate-boundary",
        "pipeline_stages": {
            "candidate_ledger": {
                "controller_candidate_count": 83,
                "hook_candidate_count": 84,
                "hook_only_candidate_count": 1,
            },
            "controller_admission": {"input_count": 83, "qualified_count": 7,
                                      "rejected_count": 76, "deferred_count": 0},
        },
        "memory_effectiveness": {
            "candidate_count": 84,
            "claim_delivery": {"candidate_record_count": 84},
        },
    })
    effect = normalized["memory_effectiveness"]
    assert effect["candidate_record_count"] == 83
    assert effect["controller_candidate_count"] == 83
    assert effect["hook_candidate_count"] == 84
    assert effect["hook_only_candidate_count"] == 1
    assert effect["candidate_boundary_scope"] == "controller_admission_plus_hook_sidecars"


def test_status_uses_actual_facet_rows_for_completion_fraction() -> None:
    """Planned lanes and appended sidecars must not render an impossible 5/3."""
    normalized = module.normalize_trace_for_status({
        "query_id": "facet-boundary",
        "queries_requested": 3,
        "queries_completed": 5,
        "facets": [
            {"label": "base", "status": "completed"},
            {"label": "definition", "status": "completed"},
            {"label": "graph", "status": "completed"},
            {"label": "observations", "status": "completed"},
            {"label": "fallback", "status": "completed"},
            {"label": "guidance", "status": "completed"},
        ],
        "memory_effectiveness": {},
    })
    assert normalized["queries_requested"] == 3
    assert normalized["queries_completed"] == 5
    assert normalized["facet_queries_requested"] == 6
    assert normalized["facet_queries_completed"] == 6
    effect = normalized["memory_effectiveness"]
    assert effect["facet_requested_count"] == 6
    assert effect["facet_completed_count"] == 6


def test_raw_prompt_never_includes_the_private_context_search_hint() -> None:
    trace = module.normalize_trace_for_status({
        "client": "codex-hook", "role": "codex", "query_preview": "老板的实际问题",
        "raw_user_prompt": "老板的实际问题\n\n[受控上下文检索提示] 这里是系统摘录，不是用户输入。",
        "memory_effectiveness": {},
    })
    assert trace["raw_user_prompt"] == "老板的实际问题"


def test_explicit_agent_or_test_prompt_origin_is_never_mislabeled_as_user() -> None:
    assert module._prompt_provenance({
        "client": "codex-hook", "query_preview": "diagnostic", "prompt_origin": "test_probe",
    })["kind"] == "test_probe"
    assert module._prompt_provenance({
        "client": "codex-hook", "query_preview": "diagnostic", "prompt_origin": "agent_generated",
    })["kind"] == "agent_generated"
    assert module._prompt_provenance({
        "client": "codex-agent-mcp", "query_preview": "deep recall", "prompt_origin": "agent_tool_call",
    })["kind"] == "agent_tool_call"
    assert module._prompt_provenance({
        "client": "codex-hook", "query_preview": "diagnostic", "full_prompt_source": "live_regression_full_prompt",
    })["kind"] == "test_probe"


def test_synthetic_test_session_cannot_mask_the_latest_real_user_trace() -> None:
    """Shared audit streams must not let FakeClient rows reach 9998 latest."""
    assert module.diagnostic_trace({
        "client": "codex-hook", "prompt_origin": "user_direct",
        "session_id": "test-session", "query_preview": "单测输入",
    }) is True
    assert module.diagnostic_trace({
        "client": "codex-hook", "prompt_origin": "user_direct",
        "session_id": "01a05ca5-c19b-7f62-8ce0-0833fadbbfe8",
        "hook_invocation_id": "hook-real", "query_preview": "真实用户输入",
    }) is False
    assert module.diagnostic_trace({
        "client": "codex-hook", "session_source": "diagnostic",
        "session_id": "real-looking", "query_preview": "诊断输入",
    }) is True


def test_agent_mcp_read_is_kept_for_history_but_cannot_be_latest_owner_turn() -> None:
    """A later MCP oracle must not replace the last visible user Hook turn."""
    user = {
        "at": "2026-09-01T11:47:12Z", "bank_id": "bank",
        "client": "codex-hook", "prompt_origin": "user_direct",
        "session_source": "vscode", "session_id": "real-session",
        "hook_invocation_id": "hook-real", "query_preview": "真实用户问题",
    }
    mcp = {
        "at": "2026-09-01T12:32:27Z", "bank_id": "bank",
        "client": "codex-agent-mcp", "prompt_origin": "agent_tool_call",
        "query_preview": "诊断型只读检索",
    }
    assert module.latest_owner_trace([mcp, user], "bank") is user
    # The MCP read remains inspectable in history; this only affects the
    # representative selected for the top-of-page latest card.
    assert module._prompt_provenance(mcp)["kind"] == "agent_tool_call"


def test_status_projection_bounds_non_delivered_candidate_details() -> None:
    """9998 keeps counts/all deliveries but not megabytes of duplicate rows."""
    rejected = [
        {"id": f"r-{i}", "text_preview": f"rejected {i}", "admission": {"reason": "unrelated"}}
        for i in range(60)
    ]
    delivered = [{"id": f"d-{i}", "text_preview": f"delivered {i}"} for i in range(25)]
    trace = {
        "pipeline_stages": {
            "retrieval": {"candidate_items": rejected, "raw_result_count": 60},
            "controller_admission": {"rejected_items": rejected, "rejected_count": 60},
            "packet_delivery": {"delivered_items": delivered, "delivered_count": 25},
        },
        "relevance_admission": {"rejected_items": rejected, "rejected_count": 60},
        "memory_effectiveness": {
            "pipeline_stages": {"duplicate": "must be removed"},
            "relevance_admission": {"duplicate": "must be removed"},
            "items": [dict(x, injected=False) for x in rejected]
                     + [dict(x, injected=True) for x in delivered],
        },
    }
    projected = module.compact_trace_for_status(trace)
    assert len(projected["pipeline_stages"]["retrieval"]["candidate_items"]) == 12
    assert len(projected["pipeline_stages"]["controller_admission"]["rejected_items"]) == 12
    # Every actual delivery remains inspectable; only non-delivered samples are bounded.
    assert len(projected["pipeline_stages"]["packet_delivery"]["delivered_items"]) == 25
    effect = projected["memory_effectiveness"]
    assert "pipeline_stages" not in effect
    assert "relevance_admission" not in effect
    assert sum(bool(x.get("injected")) for x in effect["items"]) == 25
    assert len(effect["items"]) == 37
    assert effect["items_projection_omitted_count"] == 48
