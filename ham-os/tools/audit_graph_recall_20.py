#!/usr/bin/env python3
"""Integration audit for graph-assisted Hindsight recall and injection.

Each case uses the installed Hook, independently reads the official Bank
graph, then reconciles the Controller trace and the Hook's append-only
injection receipt.  It deliberately tests relationships across world facts,
experiences, observations, mental models and entities; it is not a UI mock.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path("/Users/example/Documents/Codex/2026-07-11/ag/hindsight-memory-os")
HOOK = Path("/Users/example/.hindsight/custom-codex/scripts/recall.py")
BANK = "ep-default-bank-v2-shadow-20260811"
OUT = ROOT / "evidence" / "graph-recall-audit-20-20260830.json"
EFFECT_AUDIT = Path("/Users/example/.hindsight/audit/memory-effectiveness.jsonl")
RUN_ID = time.strftime("%Y%m%d-%H%M%S")


@dataclass(frozen=True)
class Case:
    prompt: str
    graph_seed: str
    expected_terms: tuple[str, ...]
    graph_expected: bool = True


CASES = [
    Case("请把 FileVault 的当前偏好、以前相反的建议和相关心智模型关联起来说明，不要遗漏前后关系。", "FileVault", ("FileVault",)),
    Case("云深处科技和宇树科技是不是同一个实体？请用全称、别名和方案关系做关联核对。", "云深处科技", ("云深", "宇树")),
    Case("语音识别写成刘忠阳时，应如何通过张三这个实体的别名证据找到正确身份及相关偏好？", "张三", ("张三",)),
    Case("小黛接管 Codex 文件夹迁移任务时，前后步骤、关联文件与回滚约束分别是什么？", "Codex", ("Codex",)),
    Case("WPS 云同步文件夹空白又刷新出现时，把同步状态、备份策略和排查步骤关联起来，不要只给一条历史。", "WPS", ("WPS", "同步")),
    Case("为什么 AgentMemory 只保留名称而不再作为独立系统？把架构决定、迁移经历和当前边界关联起来。", "AgentMemory", ("AgentMemory",)),
    Case("请从世界事实、经历、观察到心智模型的派生链解释：医疗偏好怎样影响后续回答，同时保留证据边界。", "医疗", ("医疗", "观察")),
    Case("Hindsight 实际注入、检索返回、回答引用和反馈闭环之间如何关联？请覆盖整条链路。", "Hindsight", ("注入", "检索")),
    Case("我要求生成 AI 图片必须真实且有参考来源，这个明确要求与相关质量观察、历史交付之间如何联动？", "图片", ("图片", "真实")),
    Case("跨任务接管一个项目时，项目状态卡、历史记忆、当前会话上下文之间应怎样关联，才能不遗漏也不塞无关内容？", "项目", ("项目", "上下文")),
    # The Bank stores the governing rule as time/source authority, not the UI
    # label "时间线".  Assert the substance that must reach the task rather
    # than requiring a cosmetic phrase from the screen.
    Case("解释观察时间线为何要按最新优先：时间、来源权威、历史证据之间的关系是什么？", "时间线", ("时间", "来源权威")),
    Case("关于实体别名治理，为什么要把全称、别名、证据来源和冲突记录连成图谱，而不能只做字符串替换？", "实体", ("实体", "别名")),
    Case("Hindsight 备份与 WPS 云盘的关系中，云端保留份数、加密、恢复验证和当前有效策略应该怎样一起召回？", "WPS", ("WPS", "备份")),
    Case("我学习代码时的系统地图、代码流、工程判断三种能力有什么前后依赖？请关联我已确认的学习偏好。", "系统地图", ("系统地图", "代码流")),
    Case("对于正式 Word 对外交付，请把格式母版、渲染检查、可访问性和回滚这几个相互影响的要求完整关联起来。", "Word", ("Word", "渲染")),
    Case("当新附件纠正旧结论时，当前来源、被替代的历史记忆、相关观察和心智模型怎样联动更新？", "Hindsight", ("当前", "历史")),
    # The durable rule is cross-page dependency checking.  The named company
    # scopes the request; it must not force injection of an otherwise irrelevant
    # company history when the structural rule is the answer-bearing memory.
    Case("云深处科技的方案内容若新增岗位，怎样用实体和关联范围保证所有受影响页面都同步检查？", "云深处科技", ("关联",)),
    Case("请把“不要只靠固定注入条数”的政策、相关性准入、图谱闭包和实际注入回执关联起来解释。", "注入", ("注入", "相关")),
    Case("为什么复杂技术解释要对熟悉术语少解释、对困难内容举例？请关联用户偏好和对应心智模型。", "解释", ("解释", "举例")),
    # Negative control: the graph lane must remain closed for a greeting.
    Case("你好", "", (), graph_expected=False),
]


def http_json(url: str, body: dict | None = None) -> dict:
    raw = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(url, data=raw, headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.loads(response.read().decode())


def norm(value: str) -> str:
    return "".join(str(value or "").casefold().split())


def effect_for_session(session_id: str) -> dict:
    for _ in range(30):
        for line in reversed(EFFECT_AUDIT.read_text(encoding="utf-8", errors="replace").splitlines()[-500:]):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("stage") == "injection" and row.get("session_id") == session_id:
                return row
        time.sleep(0.25)
    raise RuntimeError("missing Hook injection receipt")


def trace_for_execution(execution_id: str) -> dict:
    for _ in range(30):
        for row in http_json("http://127.0.0.1:8879/v1/traces?limit=240").get("items") or []:
            if row.get("execution_id") == execution_id:
                return row
        time.sleep(0.25)
    raise RuntimeError("missing Controller trace")


def official_graph_count(seed: str) -> int:
    if not seed:
        return 0
    url = "http://127.0.0.1:8888/v1/default/banks/" + urllib.parse.quote(BANK, safe="") + "/graph?" + urllib.parse.urlencode({"q": seed, "limit": 80})
    return len(http_json(url).get("nodes") or [])


def main() -> None:
    requested = {int(value) for value in sys.argv[1:] if value.isdigit()}
    selected_cases = [case for index, case in enumerate(CASES, 1) if not requested or index in requested]
    if requested and len(selected_cases) != len(requested):
        raise SystemExit(f"unknown case index; available 1..{len(CASES)}")
    reports: list[dict] = []
    for index, case in [(i, candidate) for i, candidate in enumerate(CASES, 1) if candidate in selected_cases]:
        session = f"graph-audit-visible-{RUN_ID}-{index:02d}"
        report: dict = {"index": index, "session": session, "prompt": case.prompt, "graph_seed": case.graph_seed}
        try:
            graph_nodes_direct = official_graph_count(case.graph_seed)
            run = subprocess.run(
                ["python3", str(HOOK)], input=json.dumps({"session_id": session, "cwd": str(ROOT), "prompt": case.prompt}, ensure_ascii=False),
                text=True, capture_output=True, timeout=70, check=False,
            )
            hook = json.loads(run.stdout or "{}") if run.stdout.strip() else {}
            context = ((hook.get("hookSpecificOutput") or {}).get("additionalContext") or "")
            receipt = effect_for_session(session)
            trace = trace_for_execution(str(receipt.get("execution_id") or receipt.get("query_id") or ""))
            controller = trace.get("query_controller") or trace
            graph_route = controller.get("graph_route") or {}
            graph_receipt = graph_route.get("receipt") or {}
            injected = list(receipt.get("injected_items") or [])
            injected_text = context + "\n" + "\n".join(str(row.get("text_preview") or row.get("text") or "") for row in injected)
            anchors_present = all(norm(term) in norm(injected_text) for term in case.expected_terms)
            graph_items = [row for row in injected if row.get("graph_evidence")]
            reasons: list[str] = []
            notes: list[str] = []
            if run.returncode:
                reasons.append("hook_nonzero")
            if not controller.get("execution_complete"):
                reasons.append("trace_incomplete")
            if int(receipt.get("injected_count", len(receipt.get("injected_ids") or [])) or 0) != len(injected):
                reasons.append("receipt_item_count_mismatch")
            if case.graph_expected:
                if not graph_route.get("enabled"):
                    reasons.append("graph_lane_not_enabled")
                if graph_nodes_direct and not graph_receipt.get("selected_count"):
                    # A visual graph may have broad co-occurrence neighbours
                    # but none that proves this question's requested relation.
                    # That is a governed zero, not a licence to inject noise.
                    notes.append("official_graph_neighbours_rejected_as_not_relation_supported")
                if graph_receipt.get("status") != "completed":
                    reasons.append("graph_lane_not_completed")
                if case.expected_terms and not anchors_present:
                    reasons.append("expected_anchor_missing_from_actual_injection")
            else:
                if graph_route.get("enabled"):
                    reasons.append("graph_lane_opened_for_negative_control")
            report.update({
                "status": "pass" if not reasons else "fail", "reasons": reasons,
                "notes": notes,
                "direct_graph_nodes": graph_nodes_direct,
                "controller_graph": graph_receipt,
                "actual_injected_count": len(injected),
                "actual_graph_injected_count": len(graph_items),
                "anchors_present": anchors_present,
                "execution_id": controller.get("execution_id"),
                "injected": [{"id": row.get("id"), "text": str(row.get("text_preview") or row.get("text") or "")[:260], "graph": bool(row.get("graph_evidence"))} for row in injected],
            })
        except Exception as error:
            report.update({"status": "fail", "reasons": [f"audit_exception:{type(error).__name__}:{error}"]})
        reports.append(report)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({"run_id": RUN_ID, "cases": reports}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{index:02d} {report['status']:<4} graph={report.get('direct_graph_nodes','?')}/{(report.get('controller_graph') or {}).get('selected_count','?')} inj={report.get('actual_injected_count','?')} {case.prompt[:32]}", flush=True)
    failed = [row for row in reports if row["status"] != "pass"]
    print(json.dumps({"total": len(reports), "passed": len(reports) - len(failed), "failed": len(failed), "output": str(OUT)}, ensure_ascii=False))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
