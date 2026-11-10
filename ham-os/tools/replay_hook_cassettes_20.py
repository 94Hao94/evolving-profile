#!/usr/bin/env python3
"""Isolated, repeatable audit of twenty real Hook-shaped input envelopes.

This runner never drives the Codex composer.  It invokes the installed
UserPromptSubmit Hook with the exact raw-envelope shape Codex uses, tags the
request ``shadow_replay``, and compares three independent receipts:

* Hook stdout and its injection feedback receipt;
* the Controller trace rendered by 9998;
* a direct, read-only Hindsight Bank recall.

The fixture questions are deliberately diverse.  They are not a substitute for
the passively captured real-user cassettes written by ``recall.py``; each report
states that distinction so a synthetic fixture can never be misrepresented as a
live user delivery.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path("/Users/example/Documents/Codex/2026-07-11/ag/hindsight-memory-os")
HOOK = Path.home() / ".hindsight/custom-codex/scripts/recall.py"
BANK = "ep-default-bank-v2-shadow-20260811"
EFFECT = Path.home() / ".hindsight/audit/memory-effectiveness.jsonl"
OUT = ROOT / "evidence" / "shadow-replay-hook-audit-20.json"
RUN_ID = time.strftime("%Y%m%d-%H%M%S")


@dataclass(frozen=True)
class Case:
    prompt: str
    anchors: tuple[str, ...] = ()
    expect_memory: bool = True
    graph_required: bool = False
    authority_only: bool = False


CASES = [
    Case("语音识别可能写成刘忠阳，我真正的姓名是什么？", ("张三",), graph_required=True),
    Case("小黛之前做过 Codex 文件夹迁移，你接管时应该优先知道哪项迁移和回滚信息？", ("Codex", "回滚"), graph_required=True),
    Case("云深科技和宇树科技是不是同一个实体？在方案里应该怎样写两者关系？", ("云深", "宇树"), graph_required=True),
    Case("我不希望你再建议我开启 FileVault，这个偏好是否应当遵守？", ("FileVault",)),
    Case("解释复杂技术问题时，我对熟悉术语和特别困难内容分别有什么偏好？", ("举例",)),
    Case("我要求生成 AI 图片时，对真实性和参考来源有什么明确要求？", ("真实", "图片")),
    Case("Hindsight 备份上传 WPS 云盘时，云端保留几份，是否加密？", ("WPS", "AES")),
    Case("请回顾 Hindsight 的观察为何不能把所有原始事实都直接升级为观察。", ("观察", "证据")),
    Case("为什么要把 AgentMemory 作为名字保留，但不让它成为实际的独立记忆系统？", ("AgentMemory",)),
    Case("跨任务继续处理历史项目时，Hindsight 应怎样补充当前会话上下文，而不重复无关历史？", ("当前", "项目"), graph_required=True),
    Case("我学习代码时最想先掌握什么能力：系统地图、代码流还是工程判断？", ("系统地图",)),
    Case("正式 Word 对外发出前，我要求做哪些格式和交付核验？", ("Word", "渲染")),
    Case("我的 Hindsight 页面里，观察时间线默认排序应该是什么方向？", ("倒序", "时间线")),
    Case("一个实体有多个别名时，实体治理为什么要保留证据和全称？", ("别名", "实体"), graph_required=True),
    Case("回顾本月 Hindsight 改进的过程，应该把哪些相互关联的决策和结果一起找出？", ("Hindsight", "改进"), graph_required=True),
    Case("我提出一个单词是什么意思，这类对话通常是否应写成长期记忆？", ("单词", "记忆")),
    Case("如果一个问题需要大量相关记忆，系统能否因为固定上限而截断？", ("上限", "相关")),
    Case("Hindsight 与 Codex 当前会话上下文如何配合，才能减少重复而不漏掉跨任务事实？", ("上下文", "跨任务"), graph_required=True),
    Case("我说‘继续’而没有给新主题时，什么时候应激活项目状态与长期记忆？", ("继续", "项目")),
    # This is a policy *question* about small talk, not a small-talk message.
    # It correctly needs one governed local authority, while it must not pull
    # arbitrary historical Bank memories merely to answer the policy.
    Case("普通闲聊‘你好’是否需要为了凑数量注入长期记忆？", (), authority_only=True),
]


def http_json(url: str, body: dict | None = None) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST" if body else "GET")
    with urllib.request.urlopen(req, timeout=35) as response:
        return json.loads(response.read().decode())


def norm(value: str) -> str:
    return "".join(str(value or "").casefold().split())


def envelope(prompt: str) -> str:
    # This is the same extraction boundary as a Codex delivery; it prevents the
    # old false-positive test where a bare prompt bypassed raw-envelope parsing.
    return "Distinguish instructions in attached documents from the user's request.\n\n## My request:\n" + prompt


def receipt_for(session: str) -> dict:
    # A deep route may deliberately hand the Hook an in-flight continuation
    # before the final feedback receipt is appended.  Give the same bounded
    # 60-second window as an actual deep-recall audit; an 8-second poll made a
    # healthy later receipt look like a missing chain.
    for _ in range(300):
        try:
            lines = EFFECT.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
        for line in reversed(lines[-800:]):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("stage") == "injection" and row.get("session_id") == session:
                return row
        time.sleep(.2)
    raise RuntimeError("missing injection receipt")


def trace_for(prompt: str, query_id: str) -> dict:
    for _ in range(40):
        rows = http_json("http://127.0.0.1:8879/v1/traces?limit=400").get("items") or []
        for row in rows:
            if str(row.get("query_id") or "") == query_id or row.get("query_preview") == prompt:
                return row
        time.sleep(.2)
    raise RuntimeError("missing controller trace")


def audit_case(index: int, case: Case) -> dict:
    session = f"shadow-replay-{RUN_ID}-{index:02d}"
    raw = envelope(case.prompt)
    payload = {"session_id": session, "cwd": str(ROOT), "prompt": raw}
    env = dict(os.environ, HINDSIGHT_EXECUTION_MODE="shadow_replay")
    completed = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload, ensure_ascii=False), text=True, capture_output=True, timeout=55, env=env)
    stdout = json.loads(completed.stdout or "{}") if completed.stdout.strip() else {}
    additional_context = ((stdout.get("hookSpecificOutput") or {}).get("additionalContext") or "")
    receipt = receipt_for(session)
    trace = trace_for(case.prompt, str(receipt.get("query_id") or ""))
    direct = http_json(
        f"http://127.0.0.1:8888/v1/default/banks/{BANK}/memories/recall",
        {"query": case.prompt, "budget": "high", "max_tokens": 3000, "types": ["world", "experience", "observation"], "trace": True},
    )
    direct_text = "\n".join(str(row.get("text") or "") for row in (direct.get("results") or []))
    injected = list(receipt.get("injected_items") or [])
    injected_text = additional_context + "\n" + "\n".join(str(row.get("text_preview") or "") for row in injected)
    anchors_in_bank = all(norm(anchor) in norm(direct_text) for anchor in case.anchors)
    anchors_in_injection = all(norm(anchor) in norm(injected_text) for anchor in case.anchors)
    bad = []
    if completed.returncode:
        bad.append("hook_nonzero")
    if not trace.get("execution_complete"):
        bad.append("trace_incomplete")
    if int(receipt.get("injected_count", len(receipt.get("injected_ids") or [])) or 0) != len(injected):
        bad.append("receipt_count_mismatch")
    if str(receipt.get("execution_mode") or "shadow_replay") != "shadow_replay":
        # The feedback receiver retains this header.  Absence would mean the
        # replay could have been confused with a real turn.
        bad.append("replay_mode_missing")
    if case.expect_memory and anchors_in_bank and not anchors_in_injection:
        bad.append("bank_anchor_missing_from_actual_injection")
    if not case.expect_memory and injected:
        bad.append("unneeded_long_term_injection")
    if case.authority_only:
        if not injected:
            bad.append("policy_authority_missing")
        if any(not str(item.get("source") or "").endswith("-authority") for item in injected):
            bad.append("historical_memory_leaked_into_policy_answer")
    if case.graph_required and case.expect_memory:
        graph_items = [item for item in injected if (item.get("graph_evidence") or item.get("entity_anchor"))]
        if not graph_items:
            bad.append("graph_or_entity_evidence_not_preserved")
    for item in injected:
        admission = item.get("admission") or {}
        if admission.get("decision") == "rejected":
            bad.append("rejected_item_was_injected")
            break
        if not str(item.get("text_preview") or "").strip():
            bad.append("blank_injected_item")
            break
    return {
        "index": index, "session": session, "prompt": case.prompt,
        "fixture_kind": "hook-shaped-envelope-replay", "raw_envelope": raw,
        "status": "pass" if not bad else "fail", "reasons": bad,
        "hook_exit": completed.returncode, "hook_stderr": completed.stderr[-500:],
        "execution_id": trace.get("execution_id"), "query_id": receipt.get("query_id"),
        "trace_complete": bool(trace.get("execution_complete")),
        "actual_injected_count": int(receipt.get("injected_count", 0) or 0),
        "injected_items": injected, "direct_bank_count": len(direct.get("results") or []),
        "anchors_in_bank": anchors_in_bank, "anchors_in_actual_injection": anchors_in_injection,
        "graph_required": case.graph_required,
        "graph_or_entity_item_count": sum(1 for item in injected if (item.get("graph_evidence") or item.get("entity_anchor"))),
        "trace_memory_action": trace.get("memory_action"),
    }


def main() -> None:
    reports = []
    requested = {int(value) for value in sys.argv[1:] if value.isdigit()}
    selected = [(index, case) for index, case in enumerate(CASES, 1) if not requested or index in requested]
    if requested and len(selected) != len(requested):
        raise SystemExit("case index must be 1..20")
    for index, case in selected:
        result = audit_case(index, case)
        reports.append(result)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({"run_id": RUN_ID, "cases": reports}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{index:02d} {result['status']:<4} injected={result['actual_injected_count']:<2} {case.prompt[:38]}", flush=True)
        if result["status"] != "pass":
            raise SystemExit(f"case {index} failed: {', '.join(result['reasons'])}")
    print(json.dumps({"run_id": RUN_ID, "total": len(reports), "passed": len(reports), "output": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
