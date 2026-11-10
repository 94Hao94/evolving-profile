"""Regression guards for owner-visible recall and zero-result recovery."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys


STATUS_SOURCE = Path(os.environ.get(
    "HAM_STATUS_SERVER",
    "/Users/example/.hindsight/releases/ham-os-status-1.0.0-phase6-interim-gate-20260829T2300/control/hindsight_rebuild_status_server.py",
))
CONTROLLER_SOURCE = Path.home() / ".hindsight" / "query-controller" / "controller.py"


def load_module(path: Path, name: str):
    # The live Hook modules use ``lib.*`` absolute imports.  Keep tests at the
    # public module seam while making the production package directory
    # discoverable when a module is loaded from its absolute path.
    scripts_root = Path.home() / ".hindsight" / "custom-codex" / "scripts"
    if str(scripts_root) not in sys.path:
        sys.path.insert(0, str(scripts_root))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_long_active_task_continuation_uses_assistant_context_for_full_prompt():
    """A real follow-up may only have assistant status rows available.

    The live root turn said “继续呀不要停……补充到对应 md 文档”，but the
    resolver saw only assistant status/heartbeat rows and classified it as an
    independent utterance.  That dropped the active CASE scope before recall.
    An explicit continuation/action cue plus active-task evidence must be
    enough to construct a bounded Full Prompt even without a prior user row.
    """
    context = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "context_coordination.py",
        "context_coordination_long_active_continuation",
    )
    prompt = "继续呀不要停，如果总结出新的有用的东西也可以补充到对应md文档中，便于后面得进一步测试和修复"
    messages = [
        {"role": "assistant", "content": "已经开工，但真实窗口 CASE-01 还没有 UserPromptSubmit 回执；不能把委派回合算作真实通过。"},
        {"role": "assistant", "content": "执行契约要求读取台账，做 Bank Oracle、Hook/Controller、9998 状态页视觉和同题复测。"},
        {"role": "assistant", "content": "当前 RUN_STATE=BLOCKED_BY_REAL_UI_SUBMISSION，等待可见 Codex Desktop 输入。"},
    ]
    envelope = context.build_contextual_intent_envelope(prompt, messages, {})
    assert envelope["used_context"] is True
    assert envelope["intent_mode"] == "contextual_followup"
    assert envelope["full_prompt"]
    assert "CASE-01" in envelope["full_prompt"]
    assert context.build_contextual_recall_query(prompt, envelope).startswith("前一项活动任务")


def test_operational_health_does_not_activate_medical_query_expansion():
    """服务/系统健康 must not add a medical synonym facet to unrelated recall."""
    relevance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "relevance.py",
        "relevance_operational_health_bridge",
    )
    operational = "请结合长期交互归纳记忆质量；当前服务健康，但我要核对实际注入和回答使用。"
    medical = "我最近的健康和用药决策有哪些长期风险？"
    assert "医疗决策" not in relevance._concept_labels(operational)
    assert relevance.semantic_query_expansions(operational) == []
    assert "医疗决策" in relevance._concept_labels(medical)
    assert any("医疗" in bridge for bridge in relevance.semantic_query_expansions(medical))


def test_continuation_cue_without_active_task_evidence_stays_independent():
    """The relaxed rule must not turn an unrelated note into a continuation."""
    context = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "context_coordination.py",
        "context_coordination_independent_continuation_guard",
    )
    prompt = "继续呀不要停，把旅行笔记补充到文档里，方便以后再看"
    messages = [
        {"role": "assistant", "content": "刚才我们聊的是周末旅行路线和酒店选择。"},
        {"role": "assistant", "content": "我可以继续整理那份旅行笔记。"},
    ]
    envelope = context.build_contextual_intent_envelope(prompt, messages, {})
    assert envelope["used_context"] is False
    assert envelope["intent_mode"] == "current_utterance"
    assert envelope["full_prompt"] == ""


def test_active_hindsight_optimization_request_keeps_diagnostic_context():
    """An imperative optimization follow-up must not collapse to a bare short query."""
    context = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "context_coordination.py",
        "context_coordination_hindsight_optimization_followup",
    )
    prompt = "那你赶紧想办法给优化好啊！！"
    messages = [
        {"role": "assistant", "content": "状态页显示候选很多但实际注入0条，正在检查 Hook、Controller、Bank、Packet 和回执。"},
        {"role": "assistant", "content": "目标是修复观察和心智模型被准入误拒，并做真实回归测试。"},
        {"role": "user", "content": "请全面诊断 Hindsight 的零注入问题。"},
    ]
    envelope = context.build_contextual_intent_envelope(prompt, messages, {})
    assert envelope["used_context"] is True
    assert envelope["intent_mode"] == "contextual_followup"
    assert "Hindsight" in envelope["full_prompt"]


def test_recall_query_uses_resolved_full_prompt_when_available():
    """Hindsight search must receive the resolved Full Prompt, not only raw text."""
    context = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "context_coordination.py",
        "context_coordination_resolved_query",
    )
    envelope = {
        "used_context": True,
        "intent_mode": "contextual_followup",
        "full_prompt": "前一项活动任务：迁移任务与验证回退。\n本轮用户续问：继续检查。",
    }
    resolved = "Qwen Full Prompt：继续核对 Codex 文件夹迁移的状态、证据和回退要求。"
    query = context.build_contextual_recall_query(
        "继续检查。", envelope, resolved_full_prompt=resolved
    )
    assert query == resolved


def test_active_validation_task_keeps_chain_evidence_without_explicit_node_list():
    """A validation continuation must retain historical chain evidence.

    The live CASE-01 continuation had a Qwen Full Prompt that named the
    validation task and its execution contract, but not every node in the
    Hook -> Controller -> Bank -> Packet chain.  The old generic gate then
    rejected the exact historical audit rows that explained how to execute
    the task.  The query may be broad; the candidate still has to carry at
    least three delivery nodes and two concrete verification/control facts.
    """
    relevance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "relevance.py",
        "relevance_active_validation_alignment",
    )
    query = (
        "请继续执行 Hindsight 真实窗口验证任务（CASE-01 及后续），不要停止。"
        "严格按执行契约和台账做真实测试、根因分析、修复和复测。"
    )
    candidate = {
        "type": "experience",
        "text": (
            "助手执行记忆注入审计的完整流程为：真实测试触发机制、记录执行证据"
            "（Hook/Controller/Hindsight）、独立检索 Hindsight Bank 建立应注入集合、"
            "对比自动注入结果、检查 9998 状态页实际链路与卡片详情、定位根因并修复，"
            "同题回放验证及换新题测试。"
        ),
    }
    decision = relevance.admission_decision(query, candidate, deep=True)
    assert decision["decision"] == "qualified"
    assert decision["active_validation_alignment"]["qualified"] is True


def test_active_validation_alignment_rejects_unrelated_runtime_note():
    """Node-name overlap without a validation proposition remains noise."""
    relevance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "relevance.py",
        "relevance_active_validation_negative",
    )
    query = (
        "请继续执行 Hindsight 真实窗口验证任务（CASE-01 及后续），不要停止。"
        "严格按执行契约和台账做真实测试、根因分析、修复和复测。"
    )
    candidate = {
        "type": "world",
        "text": (
            "Hook、Controller、Bank、Packet 和状态页属于系统运行组件；"
            "当前配置稳定，用于日常对话，组件部署完成。"
        ),
    }
    decision = relevance.admission_decision(query, candidate, deep=True)
    assert decision["decision"] != "qualified"
    assert decision["active_validation_alignment"]["qualified"] is False


def test_active_validation_alignment_keeps_same_case_evidence_without_all_nodes():
    """An exact active CASE row is useful even when its summary omits nodes."""
    relevance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "relevance.py",
        "relevance_active_validation_case_subject",
    )
    query = (
        "请继续执行 Hindsight 真实窗口验证任务（CASE-01 及后续），不要停止。"
        "按执行契约和台账做真实测试、根因分析、修复和复测。"
    )
    candidate = {
        "type": "experience",
        "text": (
            "助手针对 CASE-01 执行了记忆验证测试，完成同题复测和真实窗口验证，"
            "用于评估长期记忆是否覆盖当前任务及回退要求。"
        ),
    }
    decision = relevance.admission_decision(query, candidate, deep=True)
    assert decision["decision"] == "qualified"
    assert decision["active_validation_alignment"]["case_subject_match"] is True


def test_active_validation_alignment_keeps_concise_incident_evidence():
    """A compact single-node incident with a concrete result is not noise."""
    relevance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "relevance.py",
        "relevance_active_validation_evidence_bridge",
    )
    query = (
        "请继续执行 Hindsight 真实窗口验证任务，不要停止；按执行契约做真实测试、"
        "核对状态页，发现问题就定位根因、修复并复测。"
    )
    candidate = {
        "type": "experience",
        "text": (
            "助手承认此前真实 Hook 测试不真实，原因是附件路径与用户问题混为一段查询，"
            "导致未覆盖真实触发路径；修复后需要按实际输入格式回归验证。"
        ),
    }
    decision = relevance.admission_decision(query, candidate, deep=True)
    assert decision["decision"] == "qualified"
    assert decision["active_validation_alignment"]["evidence_bridge"] is True


def test_owner_dashboard_hides_internal_support_trace():
    server = load_module(STATUS_SOURCE, "status_server_regression")
    internal = {
        "client": "codex-hook",
        "query_preview": "当前任务需要补齐相关历史事实、已做决策、实施进度、未完成项和回退条件。\n当前问题：为什么注入是0",
    }
    user_turn = {"client": "codex-hook", "query_preview": "为什么注入是0"}
    assert server.owner_visible_trace(internal) is False
    assert server.owner_visible_trace(user_turn) is True
    assert server.active_audit_failures([
        "openclaw: retired local adapter is not running",
        "controller: port refused",
    ]) == ["controller: port refused"]


def test_zero_result_semantic_response_still_requires_direct_fallback():
    controller = load_module(CONTROLLER_SOURCE, "controller_regression")
    assert controller.requires_direct_fallback([
        ("facet:0", {"results": []}),
        ("facet:1", {"results": []}),
    ]) is True
    assert controller.requires_direct_fallback([
        ("facet:0", {"results": [{"id": "relevant"}]}),
    ]) is False


def test_controller_does_not_reapply_generic_admission_after_merge():
    """A candidate is admitted once at the merge boundary, not silently twice.

    The production regression that produced a zero Packet had broad recall
    candidates and a completed helper, but the HTTP path ran the generic gate
    again after ``merge_recall_responses`` had already applied its source,
    temporal and sidecar-aware admission.  A second generic pass is neither a
    new evidence check nor an injection safeguard: it can only discard an
    already-qualified candidate.
    """
    source = CONTROLLER_SOURCE.read_text(encoding="utf-8")
    start = source.index("        merged = merge_recall_responses(")
    end = source.index("        rejected_ids = self.project_states.rejected_ids", start)
    post_merge_boundary = source[start:end]
    assert "admit_controller_results(" not in post_merge_boundary


def test_controller_status_projection_keeps_every_delivery_and_bounds_only_audit_samples():
    """The 8879 status transport must stay small without hiding injections."""
    controller = load_module(CONTROLLER_SOURCE, "controller_status_projection")
    rejected = [
        {"id": f"r-{i}", "text_preview": "x" * 2000, "metadata": {"diagnostic": "z" * 5000}}
        for i in range(60)
    ]
    delivered = [
        {"id": f"d-{i}", "text_preview": "delivered", "metadata": {"diagnostic": "z" * 5000}}
        for i in range(25)
    ]
    row = {
        "selected_results": rejected[:8],
        "claim_receipt": {
            "candidate_record_count": 60,
            "claims": [{"claim_id": f"claim-{i}", "summary": "z" * 5000} for i in range(20)],
        },
        "pipeline_stages": {
            "retrieval": {"candidate_items": rejected, "raw_result_count": 60},
            "controller_admission": {"rejected_items": rejected, "rejected_count": 60},
        },
        "relevance_admission": {"rejected_items": rejected, "rejected_count": 60},
        "memory_effectiveness": {
            # The Controller trace is written before the Hook receipt.  The
            # later effectiveness event owns these two actual-delivery stages.
            "pipeline_stages": {
                "hook_postprocessing": {"input_count": 25, "admitted_count": 25},
                "packet_delivery": {"input_count": 25, "delivered_items": delivered, "delivered_count": 25},
            },
            "relevance_admission": {"duplicate": True},
            "claim_delivery": {
                "schema": "ham.claim_delivery_receipt.v1",
                "actual_hook_injected_claim_ids": ["d-0"],
                "claims": [{"claim_id": "d-0", "summary": "x" * 5000}],
            },
            "memory_packet": {
                "schema": "ham.memory_packet.v1",
                "rendered_context": "<packet>" + ("x" * 100000) + "</packet>",
                "bundles": [{"claim_id": "d-0", "evidence_summaries": ["y" * 5000]}],
            },
            "candidate_items": rejected,
            "rejected_items": rejected,
            "injected_items": delivered,
            "items": ([dict(item, injected=False) for item in rejected]
                      + [dict(item, injected=True) for item in delivered]),
        },
    }
    projected = controller.status_trace_projection(row, detail_limit=12)
    assert len(projected["pipeline_stages"]["retrieval"]["candidate_items"]) == 12
    assert len(projected["pipeline_stages"]["controller_admission"]["rejected_items"]) == 12
    assert projected["pipeline_stages"]["hook_postprocessing"]["input_count"] == 25
    assert len(projected["pipeline_stages"]["packet_delivery"]["delivered_items"]) == 25
    assert all("metadata" not in item for item in projected["pipeline_stages"]["packet_delivery"]["delivered_items"])
    assert projected["pipeline_stages"]["retrieval"]["candidate_items_projection_omitted_count"] == 48
    assert all("metadata" not in item for item in projected["selected_results"])
    assert "claims" not in projected["claim_receipt"]
    assert len(projected["claim_receipt"]["claim_ids"]) == 20
    effect = projected["memory_effectiveness"]
    assert "pipeline_stages" not in effect
    assert "relevance_admission" not in effect
    assert sum(bool(item.get("injected")) for item in effect["items"]) == 25
    assert len(effect["items"]) == 37
    assert len(effect["candidate_items"]) == 12
    assert effect["candidate_items_projection_omitted_count"] == 48
    assert len(effect["rejected_items"]) == 12
    assert len(effect["injected_items"]) == 25
    assert all("metadata" not in item for item in effect["injected_items"])
    assert "claims" not in effect["claim_delivery"]
    assert effect["claim_delivery"]["actual_hook_injected_claim_ids"] == ["d-0"]
    assert "rendered_context" not in effect["memory_packet"]
    assert len(effect["memory_packet"]["bundles"][0]["evidence_summaries"][0]) == 800


def test_mental_model_guard_requires_evidence_instead_of_prescribing_topology():
    refresh = (Path.home() / ".hindsight" / "bin" / "hindsight-mental-model-refresh.py").read_text(encoding="utf-8")
    audit = (Path.home() / ".hindsight" / "bin" / "hindsight-operational-audit.py").read_text(encoding="utf-8")
    assert '[EVIDENCE-POLICY v1]' in refresh
    assert '不得沿用旧生成提示指定的答案、运行拓扑' in refresh
    assert '副本与重复导入不算独立支持' in refresh
    assert "Hindsight MCP 当前 enabled=false" not in refresh
    assert '"mcp-governed-readonly"' in audit
    assert '"mcp-disabled"' not in audit


def test_governed_mcp_marks_agent_tool_origin_and_controller_accepts_it():
    adapter = (Path.home() / ".hindsight" / "custom-codex" / "scripts" / "hindsight_controller_mcp.py").read_text(encoding="utf-8")
    controller = CONTROLLER_SOURCE.read_text(encoding="utf-8")
    assert '"X-Memory-Prompt-Origin": "agent_tool_call"' in adapter
    assert '"agent_tool_call"' in controller


def test_multi_slot_current_runtime_query_preserves_live_authority_after_semantic_admission():
    """Executable current state must not be rejected for lacking embeddings.

    A real MCP call asking about Hook, the governed MCP, AgentMemory and Coding
    Plan concurrency produced both live authority rows, then lost them in the
    generic semantic gate.  Deterministic authority is generated only after a
    source-specific query recognizer matches, so it needs a separate admission
    class rather than an embedding-score exemption for arbitrary memories.
    """
    controller = load_module(CONTROLLER_SOURCE, "controller_runtime_authority_partition")
    governance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "governance.py",
        "governance_runtime_authority_partition",
    )
    query = (
        "请读取当前 Hindsight 的正式架构：Hook、Query Controller、只读 MCP、"
        "AgentMemory 状态和 Coding Plan 并发限制；只要当前有效状态，不要旧版本。"
    )
    config = json.loads((Path.home() / ".hindsight" / "codex.json").read_text(encoding="utf-8"))
    stale = {
        "text": (
            "Hindsight MCP 默认包含 retain、reflect、delete 等工具；全部交给 Codex 会绕过"
            "现有批处理和 Coding Plan 严格串行策略。"
        ),
        "type": "world",
        "metadata": {"source": "historical-runtime-note"},
    }
    governed = governance.apply_recall_governance(query, [stale], config)
    authorities, ordinary = controller.partition_deterministic_runtime_authorities(governed)
    sources = {(item.get("metadata") or {}).get("source") for item in authorities}
    assert sources == {"coding-plan-runtime-authority", "local-runtime-authority"}
    assert all(
        ((item.get("metadata") or {}).get("_ccy_admission") or {}).get("decision") == "qualified"
        for item in authorities
    )
    assert all((item.get("metadata") or {}).get("source") not in sources for item in ordinary)
    assert all((item.get("metadata") or {}).get("source") != "historical-runtime-note" for item in ordinary)


def test_ui_navigation_memory_survives_semantic_reranker_degradation():
    """Exact entity plus an operation relation is enough during reranker loss.

    The real 2026-08-31 Hook cassette asked where Full Prompt can be viewed on
    the status page.  Hindsight returned records describing the exact card and
    click path, but the cold cross-encoder missed its deadline and every row
    was rejected solely because ``semantic_relevance_score`` was absent.  The
    deterministic fallback must keep the actual navigation proposition while
    continuing to reject a same-entity record about an unrelated operation.
    """
    relevance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "relevance.py",
        "relevance_ui_navigation_degraded",
    )
    query = (
        "在 9998 状态页（recall-observability.html）中，具体通过哪个界面元素或"
        "操作路径可以查看 Full Prompt 的详细内容？"
    )
    relevant = {
        "id": "full-prompt-card",
        "text": "在状态页点击“Full Prompt 与上下文消解”卡片，可查看原始 Prompt、Full Prompt、来源和消解理由。",
        "metadata": {
            "source": "structured_memory",
            "_ccy_entity_anchor": {
                "matched": True,
                "matched_anchors": ["状态页", "Full Prompt"],
            },
        },
    }
    unrelated = {
        "id": "full-prompt-backup",
        "text": "Full Prompt 会写入离线备份清单，并由定时任务压缩保存。",
        "metadata": {
            "source": "structured_memory",
            "_ccy_entity_anchor": {
                "matched": True,
                "matched_anchors": ["Full Prompt"],
            },
        },
    }
    admitted, rejected = relevance.admit_items(query, [relevant, unrelated], deep=False)
    assert [row["id"] for row in admitted] == ["full-prompt-card"]
    assert [row["id"] for row in rejected] == ["full-prompt-backup"]


def test_feedback_item_preserves_controller_rejection_summary():
    """Hook feedback must not erase Controller text and rejection reasons."""
    recall = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "recall.py",
        "recall_feedback_controller_summary",
    )
    row = {
        "id": "rejected-memory",
        "type": "experience",
        "text_preview": "一条被 Controller 拒绝的真实候选",
        "source": "codex-tail-flush",
        "admission": {
            "decision": "rejected",
            "reason": "命中了实体，但没有回答所需的操作关系。",
            "policy": "v5_coverage_proposition_admission",
        },
        "entity_anchor": {"matched": True, "matched_anchors": ["Full Prompt"]},
    }
    projected = recall.feedback_item(row)
    assert projected["text_preview"] == row["text_preview"]
    assert projected["source"] == row["source"]
    assert projected["admission"]["reason"] == row["admission"]["reason"]
    assert projected["entity_anchor"] == row["entity_anchor"]


def test_four_stage_pipeline_receipt_separates_retrieval_admission_hook_and_delivery():
    """The owner audit must expose where each candidate was lost or delivered."""
    recall = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "recall.py",
        "recall_four_stage_receipt",
    )
    controller_receipt = {
        "pipeline_stages": {
            "retrieval": {
                "raw_result_count": 11,
                "fused_candidate_count": 3,
                "candidate_items": [{"id": "keep"}, {"id": "reject"}, {"id": "defer"}],
            },
        },
        "relevance_admission": {
            "candidate_count": 3,
            "qualified_count": 2,
            "injected_eligible_count": 1,
            "rejected_count": 1,
            "deferred_for_token_budget_count": 1,
            "rejected_items": [{
                "id": "reject", "text_preview": "无关候选",
                "admission": {"decision": "rejected", "reason": "没有回答当前操作关系。"},
            }],
            "deferred_items": [{
                "id": "defer", "text_preview": "相关但延后",
                "admission": {"decision": "deferred_for_token_budget", "reason": "动态预算已满。"},
            }],
        },
    }
    stages = recall.build_memory_pipeline_stages(
        controller_receipt,
        candidate_items=[{"id": "keep"}, {"id": "reject"}, {"id": "defer"}],
        hook_admitted_items=[{"id": "keep"}],
        hook_rejected_items=[{
            "id": "reject", "text_preview": "无关候选",
            "admission": {"decision": "rejected", "reason": "没有回答当前操作关系。"},
        }],
        deferred_items=[{"id": "defer"}],
        injected_items=[{"id": "keep", "text_preview": "真实交付"}],
    )
    assert stages["retrieval"]["raw_result_count"] == 11
    assert stages["controller_admission"]["qualified_count"] == 2
    assert stages["controller_admission"]["rejected_items"][0]["admission"]["reason"]
    assert stages["hook_postprocessing"]["admitted_count"] == 1
    assert stages["packet_delivery"]["delivered_count"] == 1
    assert stages["packet_delivery"]["delivered_items"][0]["id"] == "keep"


def test_claim_delivery_candidate_count_matches_the_candidate_id_ledger():
    """A Controller claim count must not overwrite the Hook candidate count."""
    recall = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "recall.py",
        "recall_claim_delivery_count",
    )
    controller_receipt = {
        "execution_id": "execution",
        "claim_receipt": {
            "execution_id": "execution",
            "candidate_record_count": 1,
            "claims": [{"claim_id": "claim", "evidence_ids": ["keep"]}],
        },
    }
    receipt = recall.build_claim_delivery_receipt(
        controller_receipt,
        injected_items=[{"id": "keep"}],
        candidate_items=[{"id": "keep"}, {"id": "reject-a"}, {"id": "reject-b"}],
    )
    assert receipt["candidate_record_count"] == 3
    assert receipt["candidate_record_count"] == len(receipt["candidate_record_ids"])
    assert receipt["controller_claim_input_count"] == 1


def test_candidate_boundary_separates_controller_main_set_from_hook_sidecar():
    """Hook governance sidecars are counted without inflating Controller input."""
    recall = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "recall.py",
        "recall_candidate_boundary",
    )
    controller_receipt = {
        "pipeline_stages": {
            "retrieval": {
                "fused_candidate_count": 3,
                "candidate_items": [
                    {"id": "bank-a", "text_preview": "a"},
                    {"id": "bank-b", "text_preview": "b"},
                    {"id": "bank-c", "text_preview": "c"},
                ],
                "sidecar_candidate_items": [
                    {"source": "direct-policy", "text_preview": "sidecar"},
                ],
            },
        },
        "relevance_admission": {
            "candidate_count": 4,
            "qualified_count": 1,
            "injected_eligible_count": 1,
            "rejected_count": 3,
        },
    }
    stages = recall.build_memory_pipeline_stages(
        controller_receipt,
        candidate_items=[
            {"id": "bank-a"}, {"id": "bank-b"}, {"id": "bank-c"},
            {"source": "direct-policy", "text_preview": "sidecar"},
            {"source": "local-governance", "text_preview": "hook-only"},
        ],
        hook_admitted_items=[{"id": "bank-a"}],
        hook_rejected_items=[], deferred_items=[], injected_items=[{"id": "bank-a"}],
    )
    ledger = stages["candidate_ledger"]
    assert ledger["controller_candidate_count"] == 4
    assert ledger["hook_candidate_count"] == 5
    assert ledger["hook_only_candidate_count"] == 1
    assert len(ledger["hook_only_candidate_ids"]) == 1

    receipt = recall.build_claim_delivery_receipt(
        controller_receipt,
        injected_items=[{"id": "bank-a"}],
        candidate_items=[
            {"id": "bank-a"}, {"id": "bank-b"}, {"id": "bank-c"},
            {"source": "direct-policy", "text_preview": "sidecar"},
            {"source": "local-governance", "text_preview": "hook-only"},
        ],
        pipeline_stages=stages,
    )
    assert receipt["candidate_record_count"] == 5
    assert receipt["controller_candidate_record_count"] == 4
    assert receipt["hook_only_candidate_count"] == 1


def test_controller_admission_input_includes_explicit_sidecars_once():
    """Controller accounting closes even when policy/model sidecars are added.

    Stable guidance and direct-policy records are intentionally evaluated
    outside the ordinary fused Bank ranking.  They are still real Controller
    inputs and must appear in its denominator; otherwise the status page can
    misleadingly show more qualified+rejected rows than input candidates.
    """
    controller = load_module(CONTROLLER_SOURCE, "controller_sidecar_accounting")
    ranked = [
        {"item": {"id": "bank-keep", "text": "bank keep"}},
        {"item": {"id": "bank-reject", "text": "bank reject"}},
    ]
    admitted = [
        {"id": "bank-keep", "text": "bank keep"},
        {"id": "policy-keep", "text": "qualified direct policy"},
    ]
    rejected = [
        {"id": "bank-reject", "text": "bank reject"},
        {"id": "policy-reject", "text": "unrelated direct policy"},
    ]
    rows, sidecars = controller.controller_admission_inputs(
        ranked, admitted, rejected, deferred=[]
    )
    assert [row["id"] for row in rows] == [
        "bank-keep", "bank-reject", "policy-keep", "policy-reject"
    ]
    assert [row["id"] for row in sidecars] == ["policy-keep", "policy-reject"]


def test_optional_reranker_cannot_consume_the_controller_deadline():
    """The local cross-encoder is an ordering aid, never the critical path."""
    controller = load_module(CONTROLLER_SOURCE, "controller_reranker_budget")
    # A real relation query had ~14 seconds left after Bank/graph retrieval.
    # The old code gave all 14 seconds to a cold reranker and then discarded it.
    assert controller.foreground_reranker_budget(14.0, {}) == 3.0
    # Preserve an explicit receipt-building reserve near the deadline.
    assert controller.foreground_reranker_budget(1.2, {}) == 0.0
    # Operators may lower the cap, but cannot remove the receipt reserve.
    assert controller.foreground_reranker_budget(
        10.0, {"rerankerForegroundMaxSeconds": 1.25}
    ) == 1.25
    # Production is RRF-first.  The CPU cross-encoder remains an explicit,
    # benchmark-gated opt-in rather than silently entering every Hook turn.
    assert controller.foreground_semantic_reranker_enabled({}) is False
    assert controller.foreground_semantic_reranker_enabled(
        {"foregroundSemanticRerankerEnabled": True}
    ) is True


def test_timed_out_reranker_is_singleflight_instead_of_stacking_cpu_work():
    """A timed-out Torch inference may keep running; later turns must skip it."""
    import threading

    controller = load_module(CONTROLLER_SOURCE, "controller_reranker_singleflight")
    release = threading.Event()
    calls = []

    def slow(*args, **kwargs):
        calls.append(1)
        release.wait(2)
        return [0.5], None

    controller.cross_encoder_scores = slow
    first = controller.deadline_cross_encoder_scores(
        "q1", ["a"], model_name="test", batch_size=1, timeout=0.01
    )
    second = controller.deadline_cross_encoder_scores(
        "q2", ["b"], model_name="test", batch_size=1, timeout=0.01
    )
    release.set()
    assert first[0] == [None]
    assert "sub-budget" in first[1]
    assert second[0] == [None]
    assert "already running" in second[1]
    assert len(calls) == 1


def test_explicit_stage_comparison_is_an_evolution_question_without_from_to_wording():
    """Official vs later vs current is a timeline even without “从…到…”."""
    controller = load_module(CONTROLLER_SOURCE, "controller_stage_comparison")
    query = (
        "请比较官方 Hindsight、我们后续接入 Hook/Controller 后的变化，"
        "以及现在 Agent Memory OS 还缺什么。"
    )
    assert controller.evolution_question(query) is True
    assert "timeline" in controller.detect_shapes(query)


def test_deterministic_relation_gates_cover_audit_comparison_and_shared_memory():
    """Critical relation questions stay answerable when the reranker degrades."""
    relevance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "relevance.py",
        "relevance_relation_fallbacks",
    )
    audit_query = "为什么状态页会把检索候选、实际注入和回答使用混在一起？现在每一步如何分别留回执？"
    assert relevance.injection_audit_alignment(
        audit_query,
        "状态页应分开显示 Hook 检索候选、实际注入、最终回答使用数和对应回执。",
    )["qualified"] is True
    assert relevance.injection_audit_alignment(
        audit_query, "某次任务实际注入 12 条。"
    )["qualified"] is False

    compare_query = "AgentMemory 和 Hindsight 各自承担什么角色，为什么不能只看排行榜就替换？"
    assert relevance.system_comparison_alignment(
        compare_query,
        "AgentMemory 作为冷档案，Hindsight 作为主长期记忆；不能仅按排行榜替换。",
    )["qualified"] is True
    assert relevance.system_comparison_alignment(
        compare_query, "Hindsight 当前服务健康。"
    )["qualified"] is False

    shared_query = "即使 Codex 或 Hermes 没有 MEMORY.md，Hindsight 如何提供跨会话、跨项目的共同长期记忆？"
    assert relevance.shared_memory_alignment(
        shared_query,
        "Codex 和 Hermes 通过同一 Controller 读取共享 Hindsight Bank，跨会话和跨项目召回。",
    )["qualified"] is True
    assert relevance.shared_memory_alignment(
        shared_query, "Hermes 已接入一个本地 provider。"
    )["qualified"] is False


def test_association_closure_question_bypasses_narrow_injection_audit_but_keeps_scope():
    """Conceptual graph/constellation questions must retain closure evidence.

    The first real Q8 window exposed a boundary bug: wording such as
    ``Packet 注入`` and ``为什么`` activated the narrow delivery-audit veto,
    even though the user was asking how graph/constellation closure and
    generic-node suppression work.  Explicit architecture evidence about
    Claim Bundle, aliases, time/source and anti-generic thresholds must pass;
    a status-only row must remain rejected.
    """
    relevance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "relevance.py",
        "relevance_association_closure_q8",
    )
    query = (
        "围绕‘Full Prompt → Bank 检索 → 图谱和星座关联 → Claim Bundle → Packet 注入’，"
        "请说明为什么只找词面相似记录不够，还需要哪些关联闭包，以及这些关联怎样避免把泛节点当作相关证据。"
    )
    closure_evidence = {
        "type": "mental_model",
        "text": (
            "关联闭包不是只做词面相似：先以实体别名和同一任务建立图谱/星座关联，"
            "再把来源、时间、版本、冲突和上下游关系合并到 Claim Bundle，"
            "按命题覆盖形成可解释路径；泛节点必须有主体锚点、关系边和准入阈值，"
            "不能因为高频词或向量相似就直接进入 Packet。"
        ),
        "metadata": {"semantic_relevance_score": 0.61},
    }
    status_only = {
        "type": "world",
        "text": "本次状态页显示检索候选很多，但实际注入为 0 条；请查看 Hook 回执。",
        "metadata": {"semantic_relevance_score": 0.95},
    }
    decision = relevance.admission_decision(query, closure_evidence, deep=True)
    assert decision["decision"] == "qualified"
    assert decision["association_closure_alignment"]["qualified"] is True
    assert decision["injection_audit_alignment"]["required"] is False
    rejected = relevance.admission_decision(query, status_only, deep=True)
    assert rejected["decision"] != "qualified"


def test_actual_injection_status_question_keeps_audit_gate():
    """A concrete zero-injection diagnosis must still use the audit lane."""
    relevance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "relevance.py",
        "relevance_association_closure_audit_guard",
    )
    query = "为什么状态页显示候选很多但实际注入为0？请核对候选、投递回执和 Packet。"
    alignment = relevance.injection_audit_alignment(query, "实际注入为 0 条，候选和投递回执需要对账。")
    assert alignment["required"] is True


def test_context_and_controller_agree_on_conceptual_association_route():
    """A graph/constellation method question must not be forced into audit.

    Q8's first real window showed a cross-layer mismatch: the Hook context
    envelope labelled a conceptual closure question as
    ``contextual_mechanism_audit`` and forced ``audit``, while the relevance
    policy correctly treated it as an association question.  The two public
    seams must expose the same structural route, otherwise the actual status
    page describes the wrong chain even when the Packet contains good rows.
    """
    context = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "context_coordination.py",
        "context_coordination_association_route",
    )
    controller = load_module(CONTROLLER_SOURCE, "controller_association_route")
    prompt = (
        "围绕‘Full Prompt → Bank 检索 → 图谱和星座关联 → Claim Bundle → Packet 注入’，"
        "请说明为什么只找词面相似记录不够，还需要哪些关联闭包，以及这些关联怎样避免把泛节点当作相关证据。"
    )
    envelope = context.build_contextual_intent_envelope(prompt, [
        {"role": "user", "content": "前面讨论过 Hindsight 的实体、图谱、星座和实际注入链路。"},
        {"role": "assistant", "content": "需要把关联路径、来源时序和 Claim Bundle 一并核对。"},
    ], {})
    assert envelope["intent_mode"] == "association_closure"
    assert "audit" not in envelope["routing_hints"]["force_shapes"]
    assert "system_map" in envelope["routing_hints"]["force_shapes"]
    policy = {
        "roles": {"codex": {"allowedLevels": ["core", "facts", "events"], "initialLevels": ["core"]}},
        "sharedBank": "test-bank",
    }
    plan = controller.build_plan(
        prompt,
        "codex",
        policy,
        {},
        runtime_context={"contextual_intent": envelope, "raw_user_prompt": prompt},
    )
    assert plan["primary_shape"] == "system_map"
    assert "audit" not in plan["matched_shapes"]
    assert "system_map" in plan["matched_shapes"]
    assert plan["association_closure"]["conceptual"] is True
    active = {row["shape"]: row for row in plan["route_decisions"] if row.get("active")}
    assert active["system_map"]["association_closure"]["route"] == "system_map+synthesis"


def test_navigation_expansion_is_a_natural_relation_question_not_a_keyword_bag():
    """The official Bank embeds natural propositions, not search-engine tags.

    The real Full Prompt cassette proved that a suffix made only of nouns such
    as ``页面入口 / 界面元素 / 操作路径`` retrieved Hook-architecture records,
    while a grammatical relation question retrieved the stored click-path
    evidence.  Keep the bridge generic, but express the missing relation.
    """
    controller = load_module(CONTROLLER_SOURCE, "controller_navigation_query_bridge")
    queries = controller.build_queries("状态页中我在哪查 Full Prompt？", ["point"], 2)
    assert len(queries) == 2
    assert "界面中如何查看目标的详细内容" in queries[1]
    assert "应点击哪一个卡片或节点" in queries[1]


def test_comprehensive_procedure_opens_bounded_high_budget_lifecycle_facets():
    """A multi-stage process question must not use the mid-budget blind spot.

    The live Q5 incident reproduced a real upstream distinction: the same
    wording returned the complete process record under ``budget=high`` but not
    under ``budget=mid``.  Keep the promotion structural and bounded so a
    normal one-step how-to remains cheap while discovery/diagnosis/repair/
    regression/rollback questions receive enough Bank coverage.
    """
    controller = load_module(CONTROLLER_SOURCE, "controller_procedure_depth_lane")
    query = (
        "请总结一次 Hindsight 真实召回/注入问题的完整处理流程：如何发现、如何定位是召回还是准入还是投递、"
        "如何修复、如何做同题复测和相邻变体复测，以及失败时如何回退。"
    )
    assert controller.comprehensive_procedure_requested(query, ["procedure"]) is True
    queries = controller.build_queries(query, ["procedure"], 5)
    assert len(queries) == 5
    assert any("步骤分面" in value for value in queries)
    assert any("处置分面" in value for value in queries)
    assert any("恢复分面" in value for value in queries)
    plan = controller.build_plan(
        query,
        "codex",
        {},
        {},
        client="codex-hook",
        bank_id="ep-default-bank-v2-shadow-20260811",
    )
    assert plan["procedure_depth"] is True
    assert plan["budget"] == "high"
    assert plan["max_tokens"] >= 2800
    # Required-slot coverage facets may add up to three bounded lanes after
    # the five lifecycle facets.  The invariant is a finite high-budget plan,
    # not an exact count that would reject later coverage expansion.
    assert 5 <= plan["planned_query_count"] <= 8
    assert plan["query_count"] == 2
    assert plan["coverage_required"] is True
    assert "steps" in plan["coverage_dimensions"]


def test_small_transcript_tail_reader_rewinds_after_measuring_file_size(tmp_path):
    """A normal small task must not disappear after the tail-size check.

    ``seek(0, SEEK_END)`` was used inside the size comparison.  For files below
    the 8 MiB tail threshold the condition was false and the cursor stayed at
    EOF, so Full Prompt resolution received zero messages.  Large rollouts
    happened to work because their true branch sought backwards again.
    """
    content = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "content.py",
        "content_small_transcript_tail",
    )
    transcript = tmp_path / "small-rollout.jsonl"
    transcript.write_text(
        '{"role":"user","content":"前文里的真实审计对象"}\n'
        '{"role":"assistant","content":"正在核对 Full Prompt 和实际注入"}\n',
        encoding="utf-8",
    )
    messages = content.read_transcript(str(transcript), max_tail_bytes=8 * 1024 * 1024)
    assert [row["content"] for row in messages] == [
        "前文里的真实审计对象",
        "正在核对 Full Prompt 和实际注入",
    ]


def test_stable_observation_sidecar_records_nonqualified_rows_as_rejected():
    """Every fused candidate must end in a named Controller state."""
    controller = load_module(CONTROLLER_SOURCE, "controller_observation_closed_ledger")
    unrelated = {
        "id": "unrelated-observation",
        "type": "observation",
        "text": "用户偏好在课程学习中先看因果模型。",
        "metadata": {"source": "observation-sidecar"},
    }
    admitted, rejected = controller.admit_stable_guidance_sidecar(
        "状态页中在哪查看 Full Prompt？",
        [{"item": unrelated, "sources": ["stable_guidance_observations"]}],
        [],
        [],
    )
    assert admitted == []
    assert [row["id"] for row in rejected] == ["unrelated-observation"]
    assert rejected[0]["metadata"]["_ccy_admission"]["decision"] == "rejected"
    assert rejected[0]["metadata"]["_ccy_admission"]["reason"]


def test_concrete_cross_task_handoff_rejects_generic_agent_state_but_keeps_migration_receipt():
    controller = load_module(CONTROLLER_SOURCE, "controller_handoff_relevance")
    query = "小黛之前做了 Codex 文件夹的迁移任务，你接管一下并说明当前状态、未完成项和回退条件。"
    generic = {
        "id": "generic-agent-state", "text": "当前 Codex 配置为 custom，小黛服务 running/healthy。",
        "metadata": {"source": "codex-tail-flush", "semantic_relevance_score": 0.98},
    }
    unrelated_recovery = {
        "id": "service-recovery", "text": "小黛服务故障后已恢复正常，进程 healthy。",
        "metadata": {"source": "codex-tail-flush", "semantic_relevance_score": 0.98},
    }
    migration = {
        "id": "migration-receipt", "text": "已将 Codex 配置从原目录迁移至项目目录，生成 ROLLBACK.sh 回滚脚本与差异文件。",
        "metadata": {"source": "codex-tail-flush", "semantic_relevance_score": 0.91},
    }
    admitted, rejected = controller.relevance_admit_items(query, [generic, unrelated_recovery, migration])
    assert [item["id"] for item in admitted] == ["migration-receipt"]
    assert all(item["metadata"]["_ccy_admission"]["continuity_task_alignment"]["required"] is True for item in rejected)


def test_subject_lane_cannot_bypass_concrete_handoff_scope():
    """A broad subject hit must not admit a global policy into a folder handoff.

    Before v8, ``subject_evidence_alignment`` ran before the continuity gate.
    A long global writing policy happened to contain ``文件`` plus two generic
    proposition markers (``机制/模型``), so it was injected even though it had
    no Codex migration, path or rollback evidence.  The same guard must reject
    a UI note that merely quotes the task title while keeping a real migration
    receipt.
    """
    relevance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "relevance.py",
        "relevance_handoff_subject_scope_v8",
    )
    query = (
        "请结合长期记忆，还原涉及 Codex 文件夹迁移任务（rollout_id: 01a04cc2-077f-7b53-a40f-40bba7e874b9）"
        "的最终收尾情况。具体包括目录复制、路径重绑、备份生成、验证与回退机制，"
        "并区分历史已完成与当前实时复核。"
    )
    global_policy = {
        "type": "world",
        "text": (
            "直接用户规则（范围=global）：五千字左右不少于五千字，之前生成各级标题并形成PPT文件；"
            "这里说明写作机制、模型、数据和内容结构。"
        ),
    }
    quoted_ui_note = {
        "type": "world",
        "text": (
            "右侧主区最后一条用户消息不以‘小黛之前做过 Codex 文件夹迁移任务’开头，"
            "预览内容是另一段镜头节奏；确认对话历史状态。"
        ),
    }
    migration_receipt = {
        "type": "world",
        "text": (
            "小黛此前执行了 Codex 文件夹迁移任务，将 WPS Cloud Files 的 codex 根目录复制至 "
            "/Users/example/Projects/Codex，保留旧源目录并完成差异校验。"
        ),
    }
    policy_decision = relevance.admission_decision(query, global_policy, deep=True)
    quoted_decision = relevance.admission_decision(query, quoted_ui_note, deep=True)
    migration_decision = relevance.admission_decision(query, migration_receipt, deep=True)
    assert policy_decision["decision"] != "qualified"
    assert policy_decision["continuity_task_alignment"]["passes"] is False
    assert policy_decision["subject_evidence_alignment"]["qualified"] is False
    assert quoted_decision["decision"] != "qualified"
    assert quoted_decision["continuity_task_alignment"]["passes"] is False
    assert migration_decision["decision"] == "qualified"
    assert migration_decision["continuity_task_alignment"]["passes"] is True


def test_takeover_wording_is_a_continuity_signal_even_without_unfinished_wording():
    controller = load_module(CONTROLLER_SOURCE, "controller_takeover_signal")
    plan = controller.analyze_query_dimensions("小黛做过迁移任务，请你接管一下。", ["point"])
    assert plan["continuity"] is True
    assert "接管" in plan["continuity_signals"]


def test_agentmemory_architecture_question_is_not_misclassified_as_live_runtime_state():
    governance = load_module(Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "governance.py", "governance_runtime_gate")
    assert governance.is_current_runtime_query(
        "为什么要把 AgentMemory 作为名字保留，但不让它成为实际的独立记忆系统？"
    ) is False
    assert governance.is_current_runtime_query(
        "当前 AgentMemory 的 MCP 是否启用、端口是否监听？"
    ) is True


def test_multi_component_injection_causal_chain_requires_durable_bank_recall():
    """A causal chain audit must not become a one-row live source check.

    The real Q7 turn named the Hook, Controller, official Bank, Packet and
    9998 page and asked which failure produces many candidates but zero actual
    injection.  It contains no literal ``历史`` cue, so the old recognizer
    classified it as current runtime authority and skipped every Bank facet.
    Component/relation structure is the reusable signal; a plain health check
    with only one or two components must remain source-first.
    """
    governance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "governance.py",
        "governance_architecture_chain_recall",
    )
    query = (
        "请解释 Codex Hook、Query Controller、官方 Hindsight Bank、Memory Packet "
        "和 9998 状态页之间的因果链：每个组件负责什么，哪个组件出问题会造成"
        "‘候选很多但实际注入为 0’？"
    )
    assert governance.is_memory_architecture_chain_query(query) is True
    assert governance.requires_historical_bank_recall(query) is True
    assert governance.is_current_runtime_query(query) is False
    assert governance.is_current_runtime_query("现在 Hindsight 的 Hook 服务是否启用、端口是否监听？") is True
    current_only = (
        "Hindsight 当前 Hook 主链路、只读 MCP 深查通道和并发配置分别是什么？"
        "只给当前有效架构并排除旧版本。"
    )
    assert governance.is_memory_architecture_chain_query(current_only) is False
    assert governance.requires_historical_bank_recall(current_only) is False


def test_source_first_conflict_explanation_does_not_skip_historical_bank():
    """Source-first precedence questions still need old/new evidence from Bank.

    The prompt is intentionally close to a live status query: it says the
    current source was updated and asks about an old contradictory memory. A
    prior regression treated that as ``source_first`` and returned zero
    Controller facets. The durable explanation must instead recall the
    arbitration/supersession rules, while an explicit current-only query stays
    on the authority path.
    """
    governance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "governance.py",
        "governance_source_conflict_explanation",
    )
    query = (
        "当当前来源说‘状态已更新’，但旧记忆仍保留相反结论时，Hindsight 应如何仲裁？"
        "请结合 source-first、时间、supersession 和当前 Prompt 优先级说明正确顺序。"
    )
    assert governance.is_source_conflict_explanation_query(query) is True
    assert governance.requires_historical_bank_recall(query) is True
    assert governance.is_current_runtime_query(query) is False
    current_only = "现在当前来源的状态是什么？只给当前有效结论，不查旧记忆。"
    assert governance.is_source_conflict_explanation_query(current_only) is False
    assert governance.requires_historical_bank_recall(current_only) is False


def test_causal_component_failure_question_routes_to_bounded_system_map():
    """The causal-chain prompt must carry definition and relation coverage."""
    controller = load_module(CONTROLLER_SOURCE, "controller_causal_component_map")
    query = (
        "请解释 Codex Hook、Query Controller、官方 Hindsight Bank、Memory Packet "
        "和 9998 状态页之间的因果链：每个组件负责什么，哪个组件出问题会造成"
        "‘候选很多但实际注入为 0’？"
    )
    assert controller.named_system_taxonomy_question(query) is True
    plan = controller.build_plan(query, "codex", {
        "roles": {"codex": {"allowedLevels": ["core", "facts", "events"], "initialLevels": ["core"]}},
        "sharedBank": "test-bank",
    }, {})
    assert plan["primary_shape"] == "system_map"
    assert "system_definitions" in plan["coverage_dimensions"]
    assert "role_relations" in plan["coverage_dimensions"]
    assert "boundaries" in plan["coverage_dimensions"]
    assert "scope" not in plan["coverage_dimensions"]
    assert plan["relation_closure"]["required"] is True


def test_causal_component_failure_question_admits_architecture_records_at_hook_boundary():
    """The Hook gate must preserve causal-chain evidence, not only audit rows.

    The real Q07 wording contains ``实际注入为 0`` as a failure edge. Before
    the taxonomy predicate was shared with the Hook-side relevance module,
    that phrase activated the narrow injection-audit veto and rejected the
    architecture rows that explain Hook -> Controller -> Bank -> Packet. This
    regression keeps the system-map interpretation consistent end to end.
    """
    relevance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "relevance.py",
        "relevance_causal_component_boundary",
    )
    query = (
        "请解释 Codex Hook、Query Controller、官方 Hindsight Bank、Memory Packet "
        "和 9998 状态页之间的因果链：每个组件负责什么，哪个组件出问题会造成"
        "‘候选很多但实际注入为 0’？"
    )
    architecture = {
        "id": "causal-architecture",
        "type": "world",
        "text": (
            "Codex记忆注入因果链为：用户提交触发Hook召回，经Query Controller"
            "检索与准入筛选后生成Memory Packet，由Hook写入当前回合上下文，"
            "最终通过9998状态页读取回执进行状态投影。"
        ),
    }
    kept, rejected = relevance.admit_items(query, [architecture], deep=True)
    assert [row["id"] for row in kept] == ["causal-architecture"]
    assert not rejected


def test_current_hardware_question_does_not_inject_local_hindsight_runtime_authority():
    """A generic "现在/运行/配置" must not become a Hindsight source guard.

    A real user turn about Kimi-H3, GB10 and RTX 5090 was routed to
    ``source_first`` solely because it contained those generic words.  The
    Hook then injected the unrelated local Hindsight configuration row.  Live
    authority is only appropriate when the prompt contains a Hindsight/
    AgentMemory/Hook/MCP runtime domain anchor as well as a current-state
    request.
    """
    governance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "governance.py",
        "governance_hardware_runtime_false_positive",
    )
    query = (
        "现在啊，像这个 Kimi-H3 做 AI 视频，本地部署需要什么显卡服务器？"
        "Spark GB10 能不能运行、并行几个、每生成 1 秒要多久？"
        "和 RTX 5090 几张卡相比价格和速度哪个合适？"
    )
    assert governance.is_current_runtime_query(query) is False
    config = json.loads((Path.home() / ".hindsight" / "codex.json").read_text(encoding="utf-8"))
    governed = governance.apply_recall_governance(query, [], config)
    assert not any(
        (item.get("metadata") or {}).get("source") == "local-runtime-authority"
        for item in governed
    )


def test_explicit_current_only_architecture_query_uses_runtime_authority_and_drops_stale_snapshots():
    """An explanation word must not defeat an explicit current-only scope."""
    governance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "governance.py",
        "governance_current_architecture_override",
    )
    query = (
        "Hindsight 当前 Hook 主链路、只读 MCP 深查通道和并发配置"
        "分别是什么？只给当前有效架构并排除旧版本。"
    )
    assert governance.is_current_runtime_query(query) is True
    stale = [
        {
            "id": "old-bank",
            "text": "当前 Hindsight 主共享 bank 为 ep-default-bank-v1，MCP 未启用。",
            "metadata": {"source": "codex-tail-flush"},
        },
        {
            "id": "durable-history",
            "text": "Hindsight 升级过程保留了可回滚证据和端到端验收。",
            "metadata": {"source": "codex-tail-flush"},
        },
    ]
    rows = governance.apply_recall_governance(query, stale, {"bankId": "live-bank"})
    assert rows[0]["metadata"]["source"] == "local-runtime-authority"
    assert all(row.get("id") != "old-bank" for row in rows)
    assert any(row.get("id") == "durable-history" for row in rows)


def test_hindsight_concurrency_question_adds_live_limits_authority():
    governance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "governance.py",
        "governance_hindsight_limits",
    )
    rows = governance.apply_recall_governance(
        "Hindsight 当前 retain、reflect 和 consolidation 的并发配置是什么？",
        [],
        {},
    )
    assert any(row["metadata"]["source"] == "coding-plan-runtime-authority" for row in rows)


def test_memory_architecture_mental_model_accepts_hook_and_mcp_as_specific_anchors():
    controller = load_module(CONTROLLER_SOURCE, "controller_mcp_mental_model_anchor")
    item = {
        "type": "mental_model",
        "text": "【心智模型】Hook 是每轮自动主链路；只读 MCP recall 由 Query Controller 治理。",
        "metadata": {"is_stale": False, "mental_model_section_gate": True},
    }
    ok, detail = controller.qualify_stable_mental_model(
        "Hindsight 当前 Hook 和只读 MCP 的架构是什么？", item
    )
    assert ok is True, detail


def test_named_system_taxonomy_routes_to_system_map_not_open_inventory():
    controller = load_module(CONTROLLER_SOURCE, "controller_named_system_taxonomy")
    query = (
        "请说明“Codex、Hindsight、Agent Memory OS、HAM-OS、Query Controller”"
        "这些名称在我们的记忆系统中分别指什么、哪些是别名或上下游组件，"
        "并指出不能混为一谈的边界。"
    )
    assert controller.named_system_taxonomy_question(query) is True
    shapes = controller.detect_shapes(query)
    assert "system_map" in shapes
    assert "inventory" not in shapes
    plan = controller.build_plan(query, "user", {}, {})
    assert plan["primary_shape"] == "system_map"
    assert plan["coverage_required"] is True
    assert {"system_definitions", "role_relations", "alias_relations", "boundaries"}.issubset(
        set(plan["coverage_dimensions"])
    )
    # Taxonomy scope is the explicit named system set; the open-set
    # ``scope`` slot must not be appended by generic relation closure.
    assert "scope" not in plan["coverage_dimensions"]


def test_named_system_taxonomy_admits_role_record_but_rejects_bridge_noise():
    relevance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "relevance.py",
        "relevance_named_system_taxonomy",
    )
    query = (
        "请说明“Codex、Hindsight、Agent Memory OS、HAM-OS、Query Controller”"
        "这些名称在我们的记忆系统中分别指什么、哪些是别名或上下游组件，"
        "并指出不能混为一谈的边界。"
    )
    role_record = {
        "id": "role-record",
        "type": "observation",
        "text": "Hindsight 记忆系统采用分层职责：Hook 触发，Query Controller 编排召回，Bank 持久化，Memory Packet 注入；Agent Memory 是冷档案，不等于主记忆。",
    }
    bridge_noise = {
        "id": "bridge-noise",
        "type": "observation",
        "text": "用户会把 AI 对话工具与外部长期记忆系统打通，客户端不支持时转向自建桥接方案。",
    }
    kept, rejected = relevance.admit_items(query, [role_record, bridge_noise], deep=True)
    assert [row["id"] for row in kept] == ["role-record"]
    assert any(row["id"] == "bridge-noise" for row in rejected)


def test_named_system_taxonomy_keeps_concise_definition_and_state_rows():
    """Short architecture facts are still evidence for a named map.

    The live Q06 packet initially dropped these because it demanded two role
    markers from every row.  A row may be the only durable statement of a
    component's role or a current boundary, so the taxonomy gate must accept
    an explicit one-row definition/flow while continuing to reject an
    experiment plan that merely mentions Codex and Hindsight.
    """
    relevance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "relevance.py",
        "relevance_named_system_taxonomy_concise_rows",
    )
    query = (
        "请说明“Codex、Hindsight、Agent Memory OS、HAM-OS、Query Controller”"
        "这些名称在我们的记忆系统中分别指什么、哪些是别名或上下游组件，"
        "并指出不能混为一谈的边界。"
    )
    concise_definition = "当前个人记忆系统以Hindsight为数据库、Codex Hooks为自动入口、Memory Query Controller为智能检索调度器。"
    current_boundary = "主链路仍是 Codex → Controller → 官方 Hindsight；HAM-OS 仅作为影子验证层，不替代生产路径。"
    experiment_only = "Codex 推荐先做隔离 A/B 测试，创建独立 bank 连接官方 Hindsight，暂不改变生产配置。"
    assert relevance.system_taxonomy_alignment(query, concise_definition)["qualified"] is True
    assert relevance.system_taxonomy_alignment(query, current_boundary)["qualified"] is True
    assert relevance.system_taxonomy_alignment(query, experiment_only)["qualified"] is False


def test_named_system_taxonomy_does_not_admit_single_health_fact():
    """A lone health/status fact is not a definition or relation row."""
    relevance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "relevance.py",
        "relevance_named_system_taxonomy_health_guard",
    )
    query = (
        "请说明“Codex、Hindsight、Agent Memory OS、HAM-OS、Query Controller”"
        "这些名称在我们的记忆系统中分别指什么、哪些是别名或上下游组件，"
        "并指出不能混为一谈的边界。"
    )
    health = "Hindsight API 当前健康，数据库连接正常，延迟 12ms。"
    assert relevance.system_taxonomy_alignment(query, health)["qualified"] is False


def test_named_system_taxonomy_coverage_uses_its_four_receipt_dimensions():
    controller = load_module(CONTROLLER_SOURCE, "controller_named_system_taxonomy_coverage")
    plan = {
        "coverage_dimensions": ["system_definitions", "role_relations", "alias_relations", "boundaries"],
        "relation_closure": {"required": True},
    }
    records = [{
        "type": "world",
        "text": (
            "Codex 是入口，Hindsight 是长期记忆底座；Query Controller 负责编排上下游，"
            "HAM-OS 即 Agent Memory OS 的治理层；Agent Memory 是冷档案，不等于 Hindsight，"
            "这些名称不能混为一谈。"
        ),
    }]
    coverage = controller.evaluate_coverage(records, plan)
    assert coverage["complete"] is True, coverage


def test_visual_quality_question_is_not_misclassified_as_a_local_edit():
    controller = load_module(CONTROLLER_SOURCE, "controller_visual_question")
    query = "我要求你做视觉检查时，页面链路的哪些方面必须核对？"
    decision = controller.working_set_decision(query)
    assert decision["sufficient"] is False
    # This is a bounded quality-criteria question, not a request to inventory
    # every historical record merely because it contains “哪些”.
    assert controller.detect_shapes(query) == ["point"]


def test_current_wps_sync_uses_live_source_authority_not_history():
    governance = load_module(Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "governance.py", "governance_wps_authority")
    query = "我问的是当前 WPS 云同步状态，而不是历史教程；应该以什么来源为准？"
    assert governance.is_wps_sync_current_query(query) is True
    rows = governance.apply_recall_governance(query, [], {})
    assert rows and rows[0]["metadata"]["source"] == "wps-sync-runtime-authority"


def test_meta_memory_pipeline_and_continuation_rules_are_explicit_authorities():
    governance = load_module(Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "governance.py", "governance_meta_authority")
    pipeline = governance.apply_recall_governance("解释 Hindsight 实际注入、检索返回、回答引用三者的区别。", [], {})
    assert any(row["metadata"]["source"] == "memory-pipeline-authority" for row in pipeline)
    continuation = governance.apply_recall_governance("我说‘继续’而没有给新主题时，什么时候应激活项目状态与长期记忆？", [], {})
    assert any(row["metadata"]["source"] == "continuation-policy-authority" for row in continuation)


def test_personal_health_question_rejects_crm_market_record_with_same_industry_word():
    recall = load_module(Path.home() / ".hindsight" / "custom-codex" / "scripts" / "recall.py", "recall_health_domain_boundary")
    health = {"id": "health", "text": "医疗建议应比较副作用、风险、疗效和证据强度。"}
    crm = {"id": "crm", "text": "建立教育/医疗重点对象清单，并将甲方直达率纳入CRM团队指标。"}
    kept, rejected = recall.suppress_domain_collisions("你在我的健康建议上，应当如何处理高风险、时效性强的信息？", [health, crm])
    assert [row["id"] for row in kept] == ["health"]
    assert [row["id"] for row in rejected] == ["crm"]


def test_prevent_recurrence_keeps_same_short_subject_failure_and_fix_not_generic_schedule():
    """A terse task subject must not lose its historical failure/fix chain.

    ``周报`` is only two Chinese characters, so it used to be dropped by the
    generic lexical floor.  The public admission seam must preserve records
    that share that subject *and* prove a failure or its preventative repair;
    a merely related reporting schedule is not enough.
    """
    relevance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "relevance.py",
        "relevance_prevent_recurrence",
    )
    query = "周报也想办法预防再出问题啊"
    failure = {
        "id": "weekly-failure",
        "text": "周报生成流程因图片回读闸门失效出现故障，重试失败并挂起。",
        "metadata": {"source": "structured_memory", "semantic_relevance_score": 0.02},
    }
    repair = {
        "id": "weekly-repair",
        "text": "周报图片回读闸门修正方案：强制校验图片格式与尺寸，重试后回读验收。",
        "metadata": {"source": "structured_memory", "semantic_relevance_score": 0.03},
    }
    schedule = {
        "id": "weekly-schedule",
        "text": "专家Y的周报在周日早晨发送，和当天日报错开以避免时间冲突。",
        # Same report subject alone is not enough; this does not describe the
        # requested failure-prevention chain.
        "metadata": {"source": "structured_memory", "semantic_relevance_score": 0.09},
    }
    admitted, rejected = relevance.admit_items(query, [failure, repair, schedule], deep=False)
    assert [row["id"] for row in admitted] == ["weekly-failure", "weekly-repair"]
    assert [row["id"] for row in rejected] == ["weekly-schedule"]


def test_controller_prevention_guard_excludes_a_different_workflow_even_if_prequalified():
    controller = load_module(CONTROLLER_SOURCE, "controller_prevention_subject_guard")
    query = "周报也想办法预防再出问题啊"
    weekly = {
        "id": "weekly-fix",
        "text": "周报图片回读闸门失效后，修正方案要求下载校验并在重试后回读验收。",
        "metadata": {"source": "structured_memory", "semantic_relevance_score": 0.03},
    }
    daily = {
        "id": "daily-fix",
        "text": "晨报流程修复后不再误判格式错误，并新增投递校验。",
        # Simulate a broad ranker/controller candidate which would otherwise
        # enter as a high-score generic prevention result.
        "metadata": {"source": "structured_memory", "semantic_relevance_score": 0.99},
    }
    admitted, rejected = controller.admit_controller_results(
        query,
        [{"item": weekly}, {"item": daily}],
        {"primary_shape": "procedure", "explicit_deep_recall": False},
    )
    assert [row["id"] for row in admitted] == ["weekly-fix"]
    assert [row["id"] for row in rejected if row["id"] == "daily-fix"] == ["daily-fix"]
    assert rejected[-1]["metadata"]["_ccy_admission"]["decision"] == "rejected_recurrence_subject_mismatch"


def test_named_document_change_rejects_same_project_but_different_workstream():
    """A project name alone cannot pull a procurement record into a PPT edit."""
    relevance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "relevance.py",
        "relevance_document_change_scope",
    )
    query = "河北工业大学廊坊校区的 PPT 中加入第三个岗位时，哪些相关页面、岗位描述和图表都必须同步检查并更新？"
    linked_ppt = {
        "id": "linked-ppt",
        "text": "河北工业大学廊坊校区方案已改为三岗位体系；新增数据采集与训练岗位，并同步课程、师资、实施、验收和成果页面。",
        "metadata": {"source": "structured_memory", "semantic_relevance_score": 0.61},
    }
    same_project_procurement = {
        "id": "same-project-procurement",
        "text": "河北工业大学廊坊分校质疑投诉研究采用视频演示、双盲和异常低价审查的合规防伪路线。",
        "metadata": {"source": "structured_memory", "semantic_relevance_score": 0.98},
    }
    admitted, rejected = relevance.admit_items(query, [linked_ppt, same_project_procurement], deep=True)
    assert [row["id"] for row in admitted] == ["linked-ppt"]
    assert [row["id"] for row in rejected] == ["same-project-procurement"]
    assert rejected[0]["metadata"]["_ccy_admission"]["decision"] == "rejected_document_change_scope_mismatch"


def test_direct_policy_with_print_only_scope_does_not_leak_into_screen_ppt_edit():
    controller = load_module(CONTROLLER_SOURCE, "controller_direct_policy_scope")
    item = {
        "id": "print-chart-policy",
        "type": "direct_policy",
        "text": "图表必须为单色。\n适用范围：所有需要打印输出的文档中的图表。\n边界：不适用于屏幕展示或数字媒体。",
        "metadata": {
            "direct_policy_gate": True,
            "policy_status": "active_provisional",
            "direct_policy_keywords": ["图表", "黑白", "打印"],
        },
    }
    ok, detail = controller.qualify_direct_policy(
        "河北工业大学廊坊校区的 PPT 中加入第三个岗位时，哪些相关页面、岗位描述和图表都必须同步检查并更新？",
        item,
    )
    assert ok is False
    assert "打印" in detail["reason"]


def test_provenance_question_keeps_only_proposition_leads_not_generic_memory_architecture():
    relevance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "relevance.py",
        "relevance_provenance_proposition",
    )
    query = "我之前是怎么强调 Hindsight 不能用固定注入条数、必须避免无关且不能漏掉相关记忆的？请找出对应的原话证据、时间和来源。"
    direct = {
        "id": "direct", "text": "用户原话：不能用固定注入条数；我不担心注入多，只担心完全无关或相关的没有注入。",
        "metadata": {"source": "raw-evidence", "semantic_relevance_score": 0.8},
    }
    proposition_lead = {
        "id": "lead", "text": "注入完整性审计发现高相关记忆漏注入、低相关记忆误注入；固定阈值会误杀相关内容。",
        "metadata": {"source": "structured_memory", "semantic_relevance_score": 0.86},
    }
    generic_architecture = {
        "id": "generic", "text": "Hindsight 采用世界事实、经历、观察和心智模型四层长期记忆架构。",
        "metadata": {"source": "structured_memory", "semantic_relevance_score": 0.99},
    }
    admitted, rejected = relevance.admit_items(query, [direct, proposition_lead, generic_architecture], deep=True)
    assert [row["id"] for row in admitted] == ["direct", "lead"]
    assert [row["id"] for row in rejected] == ["generic"]
    assert rejected[0]["metadata"]["_ccy_admission"]["decision"] == "rejected_provenance_proposition_mismatch"


def test_first_person_memory_system_question_still_opens_provenance_mode():
    relevance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "relevance.py",
        "relevance_first_person_provenance",
    )
    assert relevance.explicit_user_source_request(
        "我之前是怎么强调 Hindsight 不能用固定注入条数的？请找出原话、时间和来源。"
    ) is True


def test_evidence_sources_for_observation_synthesis_do_not_open_raw_provenance_mode():
    relevance = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "relevance.py",
        "relevance_observation_evidence_metadata",
    )
    query = (
        "请结合我的长期交互，归纳我判断记忆是否有用的稳定标准，分别说明哪些是观察、"
        "哪些是心智模型，以及各自的证据和边界；不要只罗列 Hindsight 组件。"
    )
    assert relevance.explicit_user_source_request(query) is False
    observation = {
        "id": "observation",
        "type": "observation",
        "text": "稳定观察：用户以真实交互、实际注入、回答使用和端到端回执判断记忆有效性；适用范围是跨任务验收，仍需标注反例和未知项。",
        "metadata": {"source": "structured_memory", "semantic_relevance_score": 0.80},
    }
    mental_model = {
        "id": "mental-model",
        "type": "mental_model",
        "text": "心智模型：原始证据优先，观察从多条独立证据归纳，心智模型只提供可迁移的解释框架，不能覆盖底层事实；结论附来源、时间、范围和置信度。",
        "metadata": {"source": "structured_memory", "semantic_relevance_score": 0.80},
    }
    generic_components = {
        "id": "generic-components",
        "type": "world",
        "text": "Hindsight 采用 Hook、Controller、Bank 和 Packet 组成架构。",
        "metadata": {"source": "structured_memory", "semantic_relevance_score": 0.99},
    }
    admitted, rejected = relevance.admit_items(
        query, [observation, mental_model, generic_components], deep=True
    )
    assert [row["id"] for row in admitted] == ["observation", "mental-model"]
    assert [row["id"] for row in rejected] == ["generic-components"]
    assert rejected[0]["metadata"]["_ccy_admission"]["decision"] == "rejected"


def test_provenance_question_never_uses_direct_policy_as_original_words():
    controller = load_module(CONTROLLER_SOURCE, "controller_provenance_policy_boundary")
    item = {
        "id": "policy", "type": "direct_policy", "text": "【用户直接政策】不设固定注入条数。",
        "metadata": {"direct_policy_gate": True, "policy_status": "active_provisional", "direct_policy_keywords": ["注入", "条数"]},
    }
    ok, detail = controller.qualify_direct_policy("我之前关于注入条数的原话、时间和来源是什么？", item)
    assert ok is False
    assert "原话" in detail["reason"]


def test_controller_returned_mental_model_keeps_parent_admission_when_split():
    recall = load_module(Path.home() / ".hindsight" / "custom-codex" / "scripts" / "recall.py", "recall_model_section_gate")
    rows = recall.expand_returned_mental_model_sections([{
        "id": "model", "type": "mental_model",
        "text": "## 记忆协同\nHindsight 只补跨任务事实。\n## 投标策略\n预算与评审细节。",
        "metadata": {"source_class": "mental_model", "_ccy_admission": {
            "decision": "qualified", "policy": recall.RELEVANCE_POLICY,
            "source_class": "mental_model", "mental_model_section_gate": True,
            "stable_guidance_sidecar": True, "stable_guidance_anchors": ["记忆"],
        }},
    }])
    assert [row["id"] for row in rows] == ["model:section:1", "model:section:2"]
    assert all(row["metadata"]["_ccy_admission"]["decision"] == "qualified" for row in rows)
    assert all(row["metadata"]["_ccy_admission"]["controller_parent_qualified"] is True for row in rows)


def test_controller_qualified_mental_model_sections_cross_hook_packet_boundary():
    """A Controller-qualified chapter must not become zero at the Hook boundary.

    The historical production bug expanded a qualified Controller model into
    heading-bounded children, deleted the admission receipt, and then ran a
    narrower second gate.  That produced ``qualified_count > 0`` alongside an
    empty Memory Packet.  The child rows must retain the parent's explicit
    section-gate provenance so the Hook can count exactly what it transports.
    """
    recall = load_module(Path.home() / ".hindsight" / "custom-codex" / "scripts" / "recall.py", "recall_model_packet_boundary")
    rows = recall.expand_returned_mental_model_sections([{
        "id": "model", "type": "mental_model",
        "text": "## 记忆协同\nHindsight 只补跨任务事实。\n## 投标策略\n预算与评审细节。",
        "metadata": {"source_class": "mental_model", "_ccy_admission": {
            "decision": "qualified", "policy": recall.RELEVANCE_POLICY,
            "source_class": "mental_model", "mental_model_section_gate": True,
            "stable_guidance_sidecar": True, "stable_guidance_anchors": ["记忆"],
        }},
    }])
    admitted, rejected = recall.admit_recall_results(
        "更新我的记忆协同规则", rows, {"primary_shape": "point"}
    )
    assert [row["id"] for row in admitted] == ["model:section:1", "model:section:2"]
    assert rejected == []
    packet_module = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "lib" / "memory_packet.py",
        "memory_packet_model_packet_boundary",
    )
    packet = packet_module.build_memory_packet(
        full_prompt="更新我的记忆协同规则", items=admitted,
    )
    assert {row["id"] for row in admitted} <= set(packet["transport_confirmed_record_ids"])
    assert all(row["metadata"]["_ccy_admission"]["controller_parent_qualified"] for row in admitted)


def test_current_controller_sidecar_section_is_not_split_again():
    recall = load_module(Path.home() / ".hindsight" / "custom-codex" / "scripts" / "recall.py", "recall_current_model_section")
    row = {
        "id": "mental-model:model:section-hash",
        "type": "mental_model",
        "text": "【心智模型｜记忆协同｜召回与注入】\n## 召回与注入\n### 证据边界\n只把相关内容交给当前任务。",
        "metadata": {
            "source_class": "mental_model",
            "mental_model_id": "model",
            "mental_model_section": "召回与注入",
            "mental_model_section_gate": True,
            "_ccy_admission": {
                "decision": "qualified",
                "policy": recall.RELEVANCE_POLICY,
                "source_class": "mental_model",
                "mental_model_section_gate": True,
            },
        },
    }
    rows = recall.expand_returned_mental_model_sections([row])
    assert rows == [row]


def test_hook_preserves_all_current_controller_qualified_decision_variants_only():
    """Named Controller qualification variants must cross the Hook boundary.

    Evolution/mechanism/entity routes use qualified_* decisions.  The Hook may
    trust those decisions only when they carry the deployed admission policy;
    an arbitrary upstream row with a different policy still goes through the
    ordinary relevance gate.
    """
    recall = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "recall.py",
        "recall_qualified_decision_variants",
    )
    accepted = {
        "id": "stage",
        "type": "world",
        "text": "Hindsight 从官方版本演进到当前架构，并记录了具体变迁和验证边界。",
        "metadata": {"_ccy_admission": {
            "decision": "qualified_evolution_stage",
            "policy": recall.RELEVANCE_POLICY,
            "source_class": "world",
        }},
    }
    admitted, rejected = recall.admit_recall_results(
        "请梳理 Hindsight 从官方到当前的演进履历。",
        [accepted],
        {"primary_shape": "timeline"},
    )
    assert [item["id"] for item in admitted] == ["stage"]
    assert rejected == []

    untrusted = {
        "id": "untrusted",
        "type": "world",
        "text": "另一系统的普通运行说明，没有 Hindsight 的演进证据。",
        "metadata": {"_ccy_admission": {
            "decision": "qualified_evolution_stage",
            "policy": "external_untrusted_policy",
            "source_class": "world",
        }},
    }
    admitted, rejected = recall.admit_recall_results(
        "请梳理 Hindsight 从官方到当前的演进履历。",
        [untrusted],
        {"primary_shape": "timeline"},
    )
    assert admitted == []
    assert rejected and rejected[0]["id"] == "untrusted"


def test_explicit_current_constraint_rejects_old_contrary_recommendation():
    recall = load_module(Path.home() / ".hindsight" / "custom-codex" / "scripts" / "recall.py", "recall_current_constraint")
    current = {"id": "current", "text": "用户明确拒绝启用 FileVault，除非特别提出否则不再主动建议。"}
    old = {"id": "old", "text": "助手建议开启 FileVault 磁盘加密以保护资料。"}
    kept, rejected = recall.prefer_explicit_current_constraint("我不希望你再建议我开启 FileVault，这个偏好是否应当遵守？", [current, old])
    assert [row["id"] for row in kept] == ["current"]
    assert [row["id"] for row in rejected] == ["old"]


def test_controller_complex_plan_cannot_keep_the_short_precise_hook_timeout():
    """The planner's wider shape owns the foreground deadline.

    A long request can contain ``现在`` and therefore look precise to the
    Hook's early lexical classifier, while the Controller correctly identifies
    it as an inventory/timeline query.  Keeping the 15-second precise timeout
    beside an 18-second Controller deadline atomically discarded a valid
    six-item response 0.8 seconds before it returned.
    """
    recall = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "recall.py",
        "recall_plan_timeout_reconciliation",
    )
    initial = {"profile": "precise", "budget": "low", "max_tokens": 700, "timeout": 15}
    plan = {
        "primary_shape": "inventory",
        "matched_shapes": ["current", "timeline", "inventory"],
        "budget": "high",
        "max_tokens": 2400,
        "deadline_ms": 18000,
        "query_count": 4,
        "coverage_required": True,
    }
    reconciled = recall.reconcile_recall_settings_with_plan(initial, plan, {})
    assert reconciled["profile"] == "shape:inventory"
    # The Controller owns 18 seconds of search time; the complete four-stage
    # admission receipt is emitted after that deadline.  Preserve four seconds
    # for its audit/JSON transport while remaining under the foreground cap.
    assert reconciled["timeout"] == 22
    assert reconciled["max_tokens"] == 2400


def test_atomic_point_plan_keeps_the_short_precise_timeout():
    recall = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "recall.py",
        "recall_point_timeout_reconciliation",
    )
    initial = {"profile": "precise", "budget": "low", "max_tokens": 700, "timeout": 15}
    plan = {
        "primary_shape": "point",
        "matched_shapes": ["point"],
        "budget": "mid",
        "max_tokens": 1200,
        "deadline_ms": 2500,
        "query_count": 1,
        "coverage_required": False,
    }
    reconciled = recall.reconcile_recall_settings_with_plan(initial, plan, {})
    assert reconciled["timeout"] == 15


def test_timed_out_plan_probe_fails_safe_to_normal_foreground_timeout():
    """A timed-out plan probe needs the full foreground transport reserve.

    The live propagation cassette hit this path: the 0.8-second plan probe
    timed out, the Controller then finished six qualified memories just after
    its 18-second execution deadline, but serialising the complete admission
    ledger crossed the Hook's ordinary 20-second socket timeout.  Falling back
    to a point-shaped lexical plan must therefore use the configured foreground
    ceiling, not merely the ordinary recall timeout.
    """
    recall = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "recall.py",
        "recall_plan_fallback_timeout",
    )
    initial = {"profile": "precise", "budget": "low", "max_tokens": 700, "timeout": 15}
    fallback = {
        "primary_shape": "point",
        "matched_shapes": ["point"],
        "budget": "mid",
        "max_tokens": 1200,
        "query_count": 1,
        "coverage_required": False,
        "controller_fallback": True,
        "controller_error": "timed out",
    }
    reconciled = recall.reconcile_recall_settings_with_plan(initial, fallback, {})
    assert reconciled["controller_profile"] == "normal"
    assert reconciled["timeout"] == 22


def test_actual_controller_receipt_overrides_a_timed_out_plan_probe():
    recall = load_module(
        Path.home() / ".hindsight" / "custom-codex" / "scripts" / "recall.py",
        "recall_effective_plan_receipt",
    )
    fallback = {
        "primary_shape": "point",
        "strategies": ["semantic_point"],
        "coverage_dimensions": ["semantic"],
        "controller_fallback": True,
        "controller_error": "timed out",
    }
    actual = {
        "primary_shape": "inventory",
        "matched_shapes": ["current", "timeline", "inventory"],
        "strategies": ["current_state", "temporal_sequence", "open_set_inventory"],
        "coverage_dimensions": ["latest_state", "earlier", "transitions", "sources"],
        "scope_claim": "open_set_with_coverage_receipt",
        "deadline_ms": 18000,
    }
    effective = recall.effective_query_plan(fallback, actual)
    assert effective["primary_shape"] == "inventory"
    assert effective["controller_fallback"] is False
    assert effective["planning_probe_fallback"] is True
    assert effective["deadline_ms"] == 18000
