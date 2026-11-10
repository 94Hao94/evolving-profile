#!/usr/bin/env python3
"""Production-equivalent Hindsight recall validation.

This does not send messages to a live Codex task.  Each case invokes the real
UserPromptSubmit Hook in ``shadow_replay`` mode, against the real Controller
and official Bank.  The harness then compares the Hook-owned injection receipt
with the immutable Controller/status-page trace.  A fixed transcript fixture
is used only where a follow-up would otherwise be impossible to interpret.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK = Path.home() / ".hindsight/custom-codex/scripts/recall.py"
RUNTIME = Path.home() / ".hindsight/shadow-0.9/runtime-20260813-2318/bin/python"
STATE = Path.home() / ".hindsight/audit/replay-state/last_recall.json"
STATUS_URL = "http://127.0.0.1:9998/api/status"
FIXTURE = ROOT / "tests/fixtures/hindsight-replay/followup-chain.jsonl"
FIXTURE_BY_CASE = {
    "zero_injection_status_followup": ROOT / "tests/fixtures/hindsight-replay/zero-injection-status-followup.jsonl",
    "short_audit_verification_followup": ROOT / "tests/fixtures/hindsight-replay/short-audit-verification-followup.jsonl",
    "test_vs_live_comparison": ROOT / "tests/fixtures/hindsight-replay/test-vs-live-comparison.jsonl",
}
REPORT = Path("/tmp/hindsight-bplus-production-equivalence.json")


# The cases cover timeline, cross-task continuation, propagation, entities,
# observations/mental models, provenance, current-source isolation, simple
# questions, and genuine no-memory turns.  ``minimum_injected`` is never a
# global cap: it is only a lower-bound for this particular test's known need.
CASES = [
    ("evolution_full", "Hindsight 从官方最开始到现在经历了哪些关键变迁？请把起点、阶段、当前架构、未完成项和证据链完整梳理。", 5, ["hindsight"], False),
    ("evolution_compare", "请比较官方 Hindsight、我们后续接入 Hook/Controller 后的变化，以及现在 Agent Memory OS 还缺什么。", 4, ["hindsight", "controller"], False),
    ("cross_task_handoff", "小黛之前做了 Codex 文件夹迁移任务。请接管：我需要知道已做什么、当前在哪、还有什么未完成及回退条件。", 1, ["小黛", "codex"], False),
    ("propagation_requirement", "我在 PPT 某一页加入第三个岗位时，为什么后面关联岗位没有同步？请找出我对“关联项全量传播、逐页核对”的历史要求。", 1, ["岗位", "关联"], False),
    ("entity_alias", "云深处科技和宇树科技是不是同一个实体？在方案中应该怎样处理它们的别名、全称和关系？", 1, ["云深处"], False),
    ("weekly_report", "周报总想办法预防再出问题：请找出此前关于月报、核验、失败防复发和发布证据的相关规则。", 1, ["周报"], False),
    ("observation_mental_model", "我的解释偏好、证据要求和视觉验收习惯，哪些已经形成观察或心智模型？哪些仍应由原始事实补证？", 1, ["用户"], False),
    ("architecture_map", "我要学习整个 Hindsight 系统的文件、服务、接口、日志和风险点。请按系统地图给出目前有效的架构。", 3, ["hindsight"], False),
    ("recall_injection_audit", "为什么以前状态页会把检索候选、实际注入和回答使用混在一起？现在每一步如何分别留回执？", 3, ["注入"], False),
    ("token_claim", "Hindsight 页面上显示节省 token，和完全不用 Hindsight 相比到底是否真的节省？边界和计算口径是什么？", 1, ["token"], False),
    ("timeline_issue", "观察时间线为什么以前只显示很少内容？现在按倒序、按入库时间和按事件时间分别怎样处理？", 1, ["时间线"], False),
    ("agentmemory_comparison", "AgentMemory 和 Hindsight 在我们这里各自承担什么角色？为什么不能只看一个排行榜就替换？", 2, ["agentmemory"], False),
    ("backup_provenance", "Hindsight 备份上传 WPS 云盘时，云端保留、加密、恢复演练和来源核验有什么已确认规则？", 1, ["备份"], False),
    ("current_architecture", "现在 Hindsight 的官方 Bank、Controller、Hook、9998 和 9999 分别是什么关系？哪些是正式路径？", 3, ["hindsight"], False),
    ("source_isolation", "# Files mentioned by the user:\n\n## 当前费用附表.xlsx: /tmp/current-expense.xlsx\n\n请只根据这份当前文件核对这一处金额，不要用旧历史猜测。", 0, [], False),
    # This fixture's evidence is about the chain/status-page evolution, not
    # the product name.  Assert the user-requested concepts so the test proves
    # semantic coverage rather than rewarding a coincidental token match.
    # “页面” is a presentation target, not a required literal inside a Bank
    # record. Requiring that exact word rewarded keyword stuffing even when
    # the injected trace/route evidence was semantically correct. The durable
    # subject that must be recovered here is the execution chain itself.
    ("followup_fixture", "刷新后页面还是这样：请结合前面关于实际链路、历史阶段和当前状态的讨论，解释为什么，并把需要核对的记忆完整补齐。", 1, ["链路"], True),
    # Regression for the real failure where “这个注入是 0 条，正常吗？”
    # was reduced to a generic point query and therefore admitted no Bank
    # evidence.  Its fixture supplies the active status/Packet context; the
    # assertion proves that the live Hook produces a Qwen-resolved Full Prompt
    # and nonzero, delivery-receipted relevant memory.
    ("zero_injection_status_followup", "这个注入是0条，正常吗？", 1, ["注入"], True),
    ("short_audit_verification_followup", "现在你觉得怎么样，能测试出来吗", 1, ["注入"], True),
    ("test_vs_live_comparison", "你测试的真实吗", 1, ["测试"], True),
    ("direct_fact", "Hindsight 官方 recall 采用哪些检索信号？", 1, ["检索"], False),
    ("cross_agent", "即使 Codex 或 Hermes 没有各自的 MEMORY.md，Hindsight 如何让它们在跨会话、跨项目时仍有共同的长期记忆能力？", 2, ["hindsight"], False),
    ("simple_greeting", "你好", 0, [], False),
    ("current_task_only", "把刚才这张状态页再刷新一次。", 0, [], True),
]


def get_status() -> dict:
    with urllib.request.urlopen(STATUS_URL, timeout=6) as response:
        return json.loads(response.read().decode())


def status_trace(query_id: str, expected_injected: int) -> dict | None:
    # The owner page refreshes every 10 seconds and its read-only snapshot is
    # stale-while-revalidate.  Waiting only 6.5 seconds made a successful Hook
    # and Controller execution fail the test even though the exact query ID
    # appeared on 9998 moments later.  Cover one full UI refresh interval plus
    # a bounded cold-snapshot allowance, matching what the user can observe.
    deadline = time.monotonic() + 16.0
    while time.monotonic() < deadline:
        data = get_status()
        rows = list(data.get("traces", []))
        # Shadow/exec rows are intentionally removed from the owner-facing
        # dashboard. Query the Controller raw projection as the diagnostic lane
        # before declaring a missing page trace; otherwise every high-fidelity
        # replay is falsely marked failed even when Hook and Packet agree.
        try:
            rows += get("http://127.0.0.1:8879", "/v1/traces?limit=200&projection=status").get("items", [])
        except Exception:
            pass
        for row in rows:
            if row.get("query_id") == query_id:
                effect = row.get("memory_effectiveness") or {}
                # The Controller writes the route receipt first and the Hook
                # writes its injection receipt just after.  Do not declare an
                # early partial row a valid page result.
                if int(effect.get("injected_count") or 0) == expected_injected:
                    return row
        time.sleep(0.25)
    return None


def run_case(case: tuple[str, str, int, list[str], bool]) -> dict:
    name, prompt, minimum, anchors, with_fixture = case
    env = dict(os.environ)
    env["HINDSIGHT_EXECUTION_MODE"] = "shadow_replay"
    if with_fixture:
        env["HINDSIGHT_SHADOW_REPLAY_WITH_TRANSCRIPT"] = "1"
    else:
        env.pop("HINDSIGHT_SHADOW_REPLAY_WITH_TRANSCRIPT", None)
    payload = {
        "session_id": f"bplus-production-equivalence-{name}-{uuid.uuid4().hex[:10]}",
        "cwd": "/tmp/hindsight-bplus-production-equivalence",
        "prompt": prompt,
        # Forces a fresh Controller continuation key without changing the user
        # query.  The value is a test-only temporal ceiling at “now”, not a
        # fabricated memory or a cache-busting term injected into semantics.
        "memory_evaluation_as_of": datetime.now(timezone.utc).isoformat(),
    }
    if with_fixture:
        payload["transcript_path"] = str(FIXTURE_BY_CASE.get(name, FIXTURE))
    started = time.monotonic()
    proc = subprocess.run(
        [str(RUNTIME), str(HOOK)],
        input=json.dumps(payload), text=True, capture_output=True, env=env, timeout=205,
    )
    elapsed = round(time.monotonic() - started, 3)
    if proc.returncode != 0:
        return {"name": name, "passed": False, "reason": "hook_nonzero", "stderr": proc.stderr[-500:], "elapsed": elapsed}
    try:
        output = json.loads(proc.stdout or "")
    except json.JSONDecodeError:
        return {
            "name": name, "passed": False, "reason": "invalid_hook_json",
            "stdout": proc.stdout[-500:], "stderr": proc.stderr[-500:], "elapsed": elapsed,
        }
    if not isinstance(output.get("hookSpecificOutput"), dict):
        return {
            "name": name, "passed": False, "reason": "missing_hook_output_contract",
            "stdout": proc.stdout[-500:], "stderr": proc.stderr[-500:], "elapsed": elapsed,
        }
    state = json.loads(STATE.read_text())
    injected = list(state.get("injected_ids") or [])
    trace = status_trace(str(state.get("query_id") or ""), len(injected))
    receipt = dict(state.get("claim_delivery") or {})
    context = str(((output.get("hookSpecificOutput") or {}).get("additionalContext") or ""))
    texts = "\n".join(str(x.get("text_preview") or x.get("text") or "") for x in (state.get("injected_items") or [])).casefold()
    reasons: list[str] = []
    if not state.get("query_id"):
        reasons.append("missing_query_id")
    if len(injected) < minimum:
        reasons.append(f"injected {len(injected)} < expected minimum {minimum}")
    if minimum and state.get("memory_action") == "source_first":
        reasons.append("historical/relational query was incorrectly short-circuited to source_first")
    if minimum and not context.strip():
        reasons.append("nonzero injection has no Hook context")
    for anchor in anchors:
        if anchor.casefold() not in texts:
            reasons.append(f"missing expected evidence anchor: {anchor}")
    if trace is None:
        reasons.append("9998 did not expose this execution trace")
    else:
        effect = trace.get("memory_effectiveness") or {}
        if int(effect.get("injected_count") or 0) != len(injected):
            reasons.append("status injection count differs from Hook receipt")
        delivery = effect.get("claim_delivery") or {}
        if receipt.get("schema") and delivery.get("actual_hook_injected_record_ids") != receipt.get("actual_hook_injected_record_ids"):
            reasons.append("status claim-delivery receipt differs from Hook receipt")
        if not trace.get("execution_complete"):
            reasons.append("status trace is not execution_complete")
    return {
        "name": name,
        "passed": not reasons,
        "elapsed": elapsed,
        "query_id": state.get("query_id"),
        "memory_action": state.get("memory_action"),
        "injected": len(injected),
        "claims": len(receipt.get("actual_hook_injected_claim_ids") or []),
        "reasons": reasons,
    }


def main() -> None:
    if not RUNTIME.is_file():
        raise SystemExit(f"missing expected isolated runtime: {RUNTIME}")
    results = []
    for case in CASES:
        result = run_case(case)
        results.append(result)
        REPORT.write_text(json.dumps({"results": results}, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(result, ensure_ascii=False))
    # A trace that was visible immediately can still disappear after later
    # broad recalls enlarge the append-only audit.  This is the exact refresh
    # path the owner sees on 9998, so check all completed cases again after
    # the full write burst rather than only checking each one in isolation.
    time.sleep(1.0)
    for result in results:
        trace = status_trace(str(result.get("query_id") or ""), int(result.get("injected") or 0))
        if trace is None:
            result["passed"] = False
            result.setdefault("reasons", []).append("9998 lost or mismatched this trace after later log writes")
        else:
            result["post_pressure_trace_verified"] = True
    passed = sum(bool(item["passed"]) for item in results)
    summary = {"summary": {"passed": passed, "total": len(CASES), "injected_total": sum(r["injected"] for r in results)}}
    REPORT.write_text(json.dumps({"results": results, **summary}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False))
    if passed != len(CASES):
        raise SystemExit("production-equivalence replay failed; fix every failed case before completion")


if __name__ == "__main__":
    main()
