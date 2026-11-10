"""Guard multi-turn retrieval traces against false "untraced prompt" alarms."""
import importlib.util
from pathlib import Path


HOME = Path.home()
RECALL = HOME / ".hindsight" / "custom-codex" / "scripts" / "recall.py"
CONTROLLER = HOME / ".hindsight" / "query-controller" / "controller.py"
EFFECTIVENESS = HOME / ".hindsight" / "bin" / "hindsight-memory-effectiveness-audit.py"
STATUS_SERVER = Path(__file__).resolve().parents[1] / "control" / "hindsight_rebuild_status_server.py"


def load_status_server():
    spec = importlib.util.spec_from_file_location("hindsight_status_server", STATUS_SERVER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def load_controller():
    spec = importlib.util.spec_from_file_location("hindsight_query_controller", CONTROLLER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_trace_correlation_uses_the_original_user_prompt_fingerprint():
    assert "X-Memory-User-Prompt-Fingerprint" in RECALL.read_text(encoding="utf-8")
    assert "user_prompt_fingerprint" in CONTROLLER.read_text(encoding="utf-8")
    assert "user_prompt_fingerprint" in EFFECTIVENESS.read_text(encoding="utf-8")


def test_controller_plan_keeps_raw_prompt_separate_from_full_prompt():
    controller = load_controller()
    policy = controller.load_json(HOME / ".hindsight" / "memory-access-policy-v3.json")
    contract = controller.load_json(controller.DEFAULT_CONTRACT)
    raw = "那这个 Spark 相比 5090 服务器省电吗？"
    full = "请基于前文 5090 与 DGX Spark 的采购背景，比较 Spark 的功耗、噪音和 24 小时运行条件。"
    plan = controller.build_plan(
        full,
        "codex",
        policy,
        contract.get("queryController") or {},
        client="codex-hook",
        bank_id="ep-default-bank-v2-shadow-20260811",
        runtime_context={
            "raw_user_prompt": raw,
            "full_prompt": full,
            "full_prompt_source": "qwen3.7-plus_context_resolution",
            "prompt_origin": "user_direct",
        },
    )
    assert plan["raw_user_prompt"] == raw
    assert plan["full_prompt"] == full
    assert plan["raw_user_prompt"] != plan["full_prompt"]


def test_cached_hook_reuse_keeps_a_distinct_visible_execution_identity():
    recall = RECALL.read_text(encoding="utf-8")
    controller = CONTROLLER.read_text(encoding="utf-8")
    assert "X-Memory-Invocation-Id" in recall
    assert "def _record_reused_invocation" in controller
    assert "reuse_kind=\"foreground\"" in controller


def test_hook_owned_current_authority_still_has_a_controller_trace():
    recall = RECALL.read_text(encoding="utf-8")
    controller = CONTROLLER.read_text(encoding="utf-8")
    assert 'X-Memory-Authority-Only' in recall
    assert 'hook_deterministic_authority' in controller


def test_source_first_authority_cannot_be_polluted_by_broad_policy_sidecars():
    """A live backup/runtime fact is not a license to inject every Hindsight rule."""
    source = RECALL.read_text(encoding="utf-8")
    # The Hook enforces source-only filtering even if a just-restarted
    # Controller has not yet returned its matching source_guard receipt.
    assert "if live_authority_only:" in source
    assert '"backup-runtime-authority"' in source
    assert "current_authority_sources" in source
    assert "is_identity_query," in source
    assert "strict_source_first = bool(source_guard.get(\"active\"))" in source
    assert "if strict_source_first:" in source


def test_controller_source_first_short_circuits_even_when_guidance_sidecar_is_enabled():
    """Authority safety is stronger than an optional stable-guidance sidecar."""
    source = CONTROLLER.read_text(encoding="utf-8")
    assert 'if plan.get("memory_action") == "noop_long_term" or plan.get("memory_action") == "source_first":' in source
    assert 'or (plan.get("memory_action") == "source_first" and not guidance_enabled)' not in source


def test_attachment_does_not_hide_a_memory_or_trace_diagnosis_behind_source_first():
    """A screenshot is evidence for a diagnosis, not its sole answer source.

    The common real wording below asks why an *execution chain* is incomplete.
    It must be allowed to inspect historic traces and the memory mechanism;
    treating the attached screenshot itself as the whole authority yields a
    misleading zero-recall receipt.
    """
    controller = load_controller()
    query = "好多类似这个的实际链路为什么不全呢？"
    assert controller.attachment_requires_source_first(query) is False
    # This is the user's real short follow-up after refreshing a status page.
    # It has no standalone attachment fact to protect; forcing source-first
    # hides the diagnostic/retry state behind a misleading zero-injection card.
    assert controller.attachment_requires_source_first("刷新了，还是这样啊") is False
    assert controller.attachment_requires_source_first(
        "你之前测试了这么多都成功了，是不是你测试和我实际上输入有区别啊？"
    ) is False
    assert controller.attachment_requires_source_first("请核对这张截图中的当前版本号") is True
    followup = controller.working_set_decision("刷新了，还是这样啊")
    assert followup["sufficient"] is True
    assert followup["decision"] == "inspect_current_observed_state"


def test_real_zero_recall_writes_an_auditable_injection_receipt():
    source = RECALL.read_text(encoding="utf-8")
    assert "A real zero-recall outcome is still a real user-turn outcome." in source
    assert '"feedback_id": hashlib.sha256(f"injection:{query_id}:empty"' in source
    assert "persist_hook_state(session_recall_state_name(session_id), state)" in source


def test_status_page_labels_qwen_full_prompt_resolution_truthfully():
    page = (HOME / ".hindsight" / "control-plane" / "recall-observability.html").read_text(encoding="utf-8")
    assert "qwen3.7-plus_context_resolution" in page
    assert "Qwen 3.7 Plus 基于当前会话消解" in page


def test_cassette_replay_uses_the_live_hook_without_mutating_production_state():
    source = RECALL.read_text(encoding="utf-8")
    controller = CONTROLLER.read_text(encoding="utf-8")
    assert "def capture_hook_cassette" in source
    assert '"X-Memory-Execution-Mode": "shadow_replay" if is_shadow_replay() else "production"' in source
    assert "def persist_hook_state" in source
    assert "execution_mode not in {\"replay\", \"shadow_replay\", \"cassette_replay\"}" in controller
    assert "self.project_states.summary(runtime_context)" in controller


def test_injection_receipt_counts_every_hook_owned_context_item():
    source = RECALL.read_text(encoding="utf-8")
    assert '"injected_count": len(injected_items)' in source
    assert '"candidate_count": len(candidate_items)' in source
    assert "deterministic_identity_alias_authority" in source


def test_policy_authority_is_not_mislabelled_as_an_attachment_source():
    source = RECALL.read_text(encoding="utf-8")
    controller = CONTROLLER.read_text(encoding="utf-8")
    assert '"X-Memory-Authority-Kind"] = "smalltalk_memory_policy"' in source
    assert "hook_policy_authority_only" in controller


def test_backup_question_rejects_a_memory_model_without_backup_topic():
    controller = load_controller()
    query = "Hindsight 备份上传 WPS 云盘时，云端保留几份，是否加密？"
    unrelated = {"type": "mental_model", "text": "Hindsight 的协作与决策边界，说明用户如何做项目判断。", "metadata": {"is_stale": False, "mental_model_section_gate": True}}
    related = {"type": "mental_model", "text": "Hindsight 的 WPS 云盘备份采用加密，并保留最近两套恢复点。", "metadata": {"is_stale": False, "mental_model_section_gate": True}}
    assert controller.qualify_stable_mental_model(query, unrelated)[0] is False
    assert controller.qualify_stable_mental_model(query, related)[0] is True


def test_agentmemory_does_not_accidentally_match_a_generic_memory_policy():
    controller = load_controller()
    policy = {
        "type": "direct_policy",
        "text": "不要过滤密钥、API Key 和 Token。",
        "metadata": {
            "direct_policy_gate": True, "policy_status": "active_provisional",
            "direct_policy_keywords": ["记忆系统", "memory", "密钥", "token"],
        },
    }
    assert controller.qualify_direct_policy(
        "为什么要把 AgentMemory 作为名字保留，但不让它成为实际的独立记忆系统？", policy
    )[0] is False


def test_owner_turn_merges_a_duplicate_hook_receipt_without_hiding_real_injection():
    status = load_status_server()
    prompt_fp = "same-visible-question"
    raw = {
        "at": "2026-08-30T01:00:00+00:00", "client": "codex-hook", "role": "codex",
        "bank_id": "bank", "query_id": "raw", "execution_id": "raw",
        "query_fingerprint": prompt_fp, "user_prompt_fingerprint": prompt_fp,
        "query_preview": "继续处理刚才的跨任务迁移", "result_count": 8,
        "memory_effectiveness": {"injected_count": 0, "retrieved_count": 8},
    }
    hook = {
        "at": "2026-08-30T01:00:08+00:00", "client": "codex-hook", "role": "codex",
        "bank_id": "bank", "query_id": "hook", "execution_id": "hook",
        "query_fingerprint": "helper-query", "user_prompt_fingerprint": prompt_fp,
        "query_preview": "当前任务需要补齐相关历史事实、已做决策、实施进度、未完成项和回退条件。",
        "result_count": 12,
        "memory_effectiveness": {"injected_count": 12, "retrieved_count": 8, "unknown_count": 12},
    }
    merged = status.merge_owner_turns([raw, hook])
    assert len(merged) == 1
    assert merged[0]["query_preview"] == raw["query_preview"]
    assert merged[0]["memory_effectiveness"]["injected_count"] == 12
    assert merged[0]["owner_turn_receipt"]["execution_count"] == 2
    assert merged[0]["owner_turn_receipt"]["helper_execution_count"] == 1


def test_owner_turn_never_merges_two_independent_visible_retries():
    status = load_status_server()
    first = {
        "at": "2026-08-30T01:00:00+00:00", "client": "codex-hook", "role": "codex",
        "bank_id": "bank", "query_id": "first", "execution_id": "first",
        "query_fingerprint": "same-prompt", "user_prompt_fingerprint": "same-prompt",
        "query_preview": "同一句真实用户问题", "memory_effectiveness": {"injected_count": 15},
    }
    retry = {
        **first, "at": "2026-08-30T01:00:12+00:00", "query_id": "retry", "execution_id": "retry",
        "memory_effectiveness": {"injected_count": 5},
    }
    merged = status.merge_owner_turns([first, retry])
    assert len(merged) == 2
    assert merged[-1]["memory_effectiveness"]["injected_count"] == 5


def test_source_first_owner_trace_cannot_borrow_a_helper_memory_receipt():
    """An attachment-first turn must show its own zero-history decision.

    A preceding internal expansion can have a perfectly real injection receipt,
    but that receipt does not describe the later source-first execution.  Mixing
    them creates the exact UI lie this guards against: a graph that says
    “authority only” while its footer claims historical memory was injected.
    """
    status = load_status_server()
    prompt_fp = "attachment-first-owner"
    helper = {
        "at": "2026-08-30T02:00:00+00:00", "client": "codex-hook", "role": "codex",
        "bank_id": "bank", "query_id": "helper", "execution_id": "helper",
        "query_fingerprint": "helper-query", "user_prompt_fingerprint": prompt_fp,
        "query_preview": "当前任务需要补齐相关历史事实、已做决策、实施进度、未完成项和回退条件。\n当前问题：周报为什么是0",
        "execution_complete": True, "result_count": 3,
        "memory_effectiveness": {"injected_count": 3, "retrieved_count": 3},
    }
    source_first = {
        "at": "2026-08-30T02:00:08+00:00", "client": "codex-hook", "role": "codex",
        "bank_id": "bank", "query_id": "owner", "execution_id": "owner",
        "query_fingerprint": prompt_fp, "user_prompt_fingerprint": prompt_fp,
        "query_preview": "周报这个条目怎么0实际记忆注入呢？",
        "execution_complete": True, "memory_action": "source_first", "result_count": 0,
        "source_guard": {"active": True, "kind": "authoritative_source", "source_label": "screen.png"},
        "memory_effectiveness": {"injected_count": 0, "retrieved_count": 0},
    }
    merged = status.merge_owner_turns([helper, source_first])
    assert len(merged) == 1
    assert merged[0]["memory_action"] == "source_first"
    assert merged[0]["memory_effectiveness"]["injected_count"] == 0
    assert merged[0]["owner_turn_receipt"]["historical_injection_is_separate"] is True


def test_coverage_expansion_does_not_repeat_a_coverage_complete_recall():
    source = RECALL.read_text(encoding="utf-8")
    assert "not bool(controller_receipt.get(\"coverage_complete\"))" in source


def test_profile_question_with_fenbie_is_not_misread_as_a_local_edit():
    controller = load_controller()
    decision = controller.working_set_decision(
        "解释复杂技术问题时，我对熟悉术语和特别困难内容分别有什么偏好？"
    )
    assert decision["sufficient"] is False
    assert decision["signals"]["direct_task_instruction"] is False


def test_unknown_personal_attribute_cannot_inject_unrelated_memories_or_models():
    source = RECALL.read_text(encoding="utf-8")
    expected_guard = """if negative_calibration:
        # A point question such as \"我的血型是什么？\" is asking for one
        # directly evidenced attribute, not for a nearby general profile."""
    assert expected_guard in source
    start = source.index(expected_guard)
    guard = source[start:start + 1000]
    assert "results = []" in guard
    assert "mental_model = None" in guard


def test_old_injection_receipt_is_not_lost_when_recent_feedback_tail_overflows(tmp_path):
    """A visible trace must retain its own injection receipt, not show false zero."""
    controller = load_controller()
    receipt = tmp_path / "memory-effectiveness.jsonl"
    target = "cross-task-execution"
    old_event = {
        "event": "memory_effectiveness", "stage": "injection", "query_id": target,
        "execution_id": target, "injected_ids": ["migration-state", "rollback-plan"],
    }
    # Put enough newer feedback after it to push it outside the normal 1 MB tail.
    filler = {"event": "memory_effectiveness", "stage": "answer", "query_id": "new", "blob": "x" * 32000}
    receipt.write_text(
        "\n".join(__import__("json").dumps(row) for row in [old_event] + [filler] * 40) + "\n",
        encoding="utf-8",
    )
    recent = controller.recent_jsonl_events(receipt, limit=200, max_bytes=1_048_576)
    assert target not in {row.get("execution_id") for row in recent}
    matched = controller.events_for_execution_ids(receipt, {target}, recent_events=recent)
    joined = controller.join_effectiveness(
        [{"execution_id": target, "selected_results": [{"id": "migration-state"}, {"id": "rollback-plan"}]}],
        matched,
    )
    assert joined[0]["memory_effectiveness"]["injected_count"] == 2
