#!/usr/bin/env python3
"""Run a repeatable, real-hook recall audit against Hindsight.

This is deliberately an integration audit, not a mocked unit test.  Each case
goes through the installed Codex UserPromptSubmit hook, then independently
queries the Bank API directly (without Controller/Hook) and compares the
receipt, selected candidates and injected items.  The first ten use a visible
session prefix so their corresponding traces can be inspected in 9998.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path("/Users/example/Documents/Codex/2026-07-11/ag/hindsight-memory-os")
HOOK = Path("/Users/example/.hindsight/custom-codex/scripts/recall.py")
BANK = "ep-default-bank-v2-shadow-20260811"
OUT = ROOT / "evidence" / "recall-audit-40-20260830.json"
EFFECT_AUDIT = Path("/Users/example/.hindsight/audit/memory-effectiveness.jsonl")
# A receipt is append-only.  Every audit run needs an isolated session prefix:
# otherwise a just-started rerun can see an older receipt with the same ID
# before the new Hook process has appended its own final injection event.
RUN_ID = time.strftime("%Y%m%d-%H%M%S")


@dataclass(frozen=True)
class Case:
    prompt: str
    expected_terms: tuple[str, ...] = ()
    expect_memory: bool = True


# These are intentionally different request shapes, not 40 paraphrases.  The
# anchors are only used to make an evidence-backed assertion when the direct
# Bank read finds that proposition; they never force an arbitrary item limit.
CASES = [
    Case("语音识别可能写成刘忠阳，我真正的姓名是什么？", ("张三",)),
    Case("小黛之前做过 Codex 文件夹迁移，你接管时应该优先知道哪项迁移和回滚信息？", ("ROLLBACK", "Codex")),
    Case("云深科技和宇树科技是不是同一个实体？在方案里应该怎样写两者关系？", ("云深", "宇树")),
    Case("我不希望你再建议我开启 FileVault，这个偏好是否应当遵守？", ("FileVault",)),
    Case("解释复杂技术问题时，我对熟悉术语和特别困难内容分别有什么偏好？", ("举例", "解释")),
    Case("我要求生成 AI 图片时，对真实性和参考来源有什么明确要求？", ("真实", "图片")),
    # Use the actual cryptographic evidence token rather than the generic word
    # “加密”: the live authority states AES-256-CBC, which is more precise and
    # avoids reporting a false coverage failure for a correct answer.
    Case("Hindsight 备份上传 WPS 云盘时，云端保留几份，是否加密？", ("WPS", "AES")),
    Case("请回顾 Hindsight 的观察为何不能把所有原始事实都直接升级为观察。", ("观察", "证据")),
    Case("为什么要把 AgentMemory 作为名字保留，但不让它成为实际的独立记忆系统？", ("AgentMemory",)),
    Case("跨任务继续处理历史项目时，Hindsight 应怎样补充当前会话上下文，而不重复无关历史？", ("当前", "项目")),
    Case("我学习代码时最想先掌握什么能力：系统地图、代码流还是工程判断？", ("系统地图",)),
    Case("正式 Word 对外发出前，我要求做哪些格式和交付核验？", ("Word", "渲染")),
    Case("WPS 同步文件夹偶尔空白但刷新后出现，这种问题之前如何判断？", ("WPS", "同步")),
    Case("我的 Hindsight 页面里，观察时间线默认排序应该是什么方向？", ("倒序", "时间线")),
    Case("长对话里一条新消息和逐步形成的经历、观察、心智模型之间是什么关系？", ("经历", "观察")),
    Case("有明确来源和时间变化的事实发生冲突时，Hindsight 应怎样决定采用哪一个？", ("来源", "时间")),
    Case("如果我说“都、全部、分类”并问某个月的事项，应该走哪种召回形态？", ("盘点", "月")),
    Case("我说只改图中的一处时，长期记忆应否把整个历史项目都塞进来？", (), False),
    Case("如果当前任务上下文已经覆盖同一事实，Hindsight 的额外注入原则是什么？", ("上下文", "补充")),
    Case("询问一个从未记录过的个人属性时，系统应当注入无关偏好吗？", (), False),
    Case("我希望用 Hindsight 替代跨任务的 MEMORY.md，它至少要达到什么效果？", ("MEMORY", "跨任务")),
    Case("一个实体有多个别名时，实体治理为什么要保留证据和全称？", ("别名", "实体")),
    Case("回顾本月 Hindsight 改进的过程，应该把哪些相互关联的决策和结果一起找出？", ("Hindsight", "改进")),
    Case("为什么在回答“当前状态”时不应该从旧历史里直接取代最新事实？", ("当前", "旧")),
    Case("你在我的健康建议上，应当如何处理高风险、时效性强的信息？", ("健康",)),
    Case("我要求你做视觉检查时，页面链路的哪些方面必须核对？", ("视觉", "链路")),
    Case("解释 Hindsight 实际注入、检索返回、回答引用三者的区别。", ("注入", "检索")),
    Case("如果召回候选很多，但只有一部分与问题有关，筛选的首要原则是什么？", ("相关", "注入")),
    Case("当我指出前面的结论错了并提供新附件，历史记忆应该怎样处理旧口径？", ("附件", "纠正")),
    Case("对于项目持续推进、移交和回滚，应该怎样建立关联闭包而不是只取一条？", ("回滚", "项目")),
    Case("我提出一个单词是什么意思，这类对话通常是否应写成长期记忆？", ("单词", "记忆")),
    Case("为什么观察和心智模型的写入门槛不能仅按条数，而要看证据结构？", ("观察", "心智模型")),
    Case("给我总结 Hindsight 中世界事实、经历、观察、心智模型和实体各自作用。", ("世界事实", "实体")),
    Case("如果一个问题需要大量相关记忆，系统能否因为固定上限而截断？", ("上限", "相关")),
    Case("我问的是当前 WPS 云同步状态，而不是历史教程；应该以什么来源为准？", ("WPS", "当前")),
    Case("在近期对话里，哪些用户偏好应该更适合形成稳定的心智模型？", ("偏好", "心智模型")),
    Case("Hindsight 与 Codex 当前会话上下文如何配合，才能减少重复而不漏掉跨任务事实？", ("上下文", "跨任务")),
    Case("我说‘继续’而没有给新主题时，什么时候应激活项目状态与长期记忆？", ("继续", "项目")),
    Case("请判断“刘忠阳”这个名字能否作为我的身份实体建立关联。", ("张三", "错字")),
    Case("普通闲聊‘你好’是否需要为了凑数量注入长期记忆？", (), False),
]


def http_json(url: str, body: dict | None = None) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def normalize(value: str) -> str:
    return "".join(str(value or "").lower().split())


def trace_for(prompt: str) -> dict:
    fingerprint = hashlib.sha256(" ".join(prompt.split()).encode()).hexdigest()[:16]
    for _ in range(15):
        traces = http_json("http://127.0.0.1:8879/v1/traces?limit=120").get("items") or []
        # Coverage-expansion helpers deliberately carry the same owner prompt
        # fingerprint.  They are not the user turn and often have zero direct
        # injection because their candidates are merged back into the owner's
        # receipt.  Prefer the real user query before using the fingerprint.
        for trace in traces:
            if trace.get("query_preview") == prompt:
                return trace
        for trace in traces:
            if trace.get("user_prompt_fingerprint") == fingerprint and "当前任务需要补齐相关历史事实" not in str(trace.get("query_preview") or ""):
                return trace
        time.sleep(0.2)
    raise RuntimeError(f"controller trace was not recorded: {prompt}")


def effect_for_session(session: str) -> dict:
    """Read the exact Hook injection receipt, independent of UI aggregation."""
    for _ in range(15):
        # Receipts are append-only and recent audit runs are at the tail.
        rows = EFFECT_AUDIT.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in reversed(rows[-300:]):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("stage") == "injection" and row.get("session_id") == session:
                return row
        time.sleep(0.2)
    raise RuntimeError(f"missing injection receipt for {session}")


def trace_for_execution(execution_id: str, prompt: str) -> dict:
    for _ in range(15):
        traces = http_json("http://127.0.0.1:8879/v1/traces?limit=180").get("items") or []
        for trace in traces:
            if trace.get("execution_id") == execution_id:
                return trace
        time.sleep(0.2)
    raise RuntimeError(f"trace missing for execution {execution_id} ({prompt})")


def main() -> None:
    reports = []
    requested = {int(value) for value in sys.argv[1:] if value.isdigit()}
    selected = [(index, case) for index, case in enumerate(CASES, start=1) if not requested or index in requested]
    if requested and len(selected) != len(requested):
        raise SystemExit(f"unknown case index; available 1..{len(CASES)}")
    for index, case in selected:
        session = ("audit40-visible" if index <= 10 else "benchmark-audit40") + f"-{RUN_ID}-{index:02d}"
        try:
            payload = {"session_id": session, "cwd": str(ROOT), "prompt": case.prompt}
            completed = subprocess.run(["python3", str(HOOK)], input=json.dumps(payload, ensure_ascii=False), text=True, capture_output=True, timeout=45, check=False)
            hook = json.loads(completed.stdout or "{}") if completed.stdout.strip() else {}
            context = ((hook.get("hookSpecificOutput") or {}).get("additionalContext") or "")
            # The Hook has returned, but the bounded audit receipt is appended
            # on the same event loop shortly afterwards.  A first read of
            # /v1/traces can therefore show a false transient 0 injection.
            # Wait for the receipt window before judging a real execution.
            time.sleep(1.1)
            effect_receipt = effect_for_session(session)
            trace = trace_for_execution(str(effect_receipt.get("execution_id") or effect_receipt.get("query_id") or ""), case.prompt)
            direct = http_json(
                f"http://127.0.0.1:8888/v1/default/banks/{BANK}/memories/recall",
                {"query": case.prompt, "budget": "high", "max_tokens": 3000, "types": ["world", "experience", "observation"], "trace": True},
            )
        except Exception as error:
            reports.append({"index": index, "session": session, "prompt": case.prompt, "status": "fail", "reasons": [f"audit_exception:{type(error).__name__}:{error}"], "actual_injected_count": None})
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(json.dumps({"cases": reports}, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{index:02d} fail audit_exception={type(error).__name__}: {error}", flush=True)
            continue
        direct_rows = direct.get("results") or []
        effect = trace.get("memory_effectiveness") or {}
        injected_rows = list(effect_receipt.get("injected_items") or [])
        selected = trace.get("selected_results") or []
        direct_text = "\n".join(str(row.get("text") or "") for row in direct_rows)
        injection_text = context + "\n" + "\n".join(str(row.get("text_preview") or "") for row in injected_rows)
        terms_in_bank = all(normalize(term) in normalize(direct_text) for term in case.expected_terms)
        terms_injected = all(normalize(term) in normalize(injection_text) for term in case.expected_terms)
        # A direct Bank answer makes the proposition discoverable.  When it is
        # also an expected anchor, a zero/anchor-missing injection is a real
        # discrepancy, not a low-count cosmetic alert.
        status = "pass"
        reasons = []
        if completed.returncode:
            status = "fail"; reasons.append("hook_nonzero")
        if not trace.get("execution_complete"):
            status = "fail"; reasons.append("trace_incomplete")
        if int(effect_receipt.get("injected_count", len(effect_receipt.get("injected_ids") or [])) or 0) != len(injected_rows):
            status = "fail"; reasons.append("receipt_item_count_mismatch")
        if case.expect_memory and terms_in_bank and not terms_injected:
            status = "fail"; reasons.append("bank_anchor_missing_from_injection")
        if not case.expect_memory and effect.get("injected_count", 0) and not case.expected_terms:
            # No generic no-memory case is considered an error merely for a
            # local contract; this flags it for human audit without hiding it.
            reasons.append("review_nonempty_for_no_memory_case")
        reports.append({
            "index": index, "session": session, "prompt": case.prompt,
            "status": status, "reasons": reasons,
            "direct_bank_count": len(direct_rows), "controller_selected_count": len(selected),
            "actual_injected_count": int(effect_receipt.get("injected_count", len(effect_receipt.get("injected_ids") or [])) or 0),
            "injected_item_count": len(injected_rows),
            "direct_anchor_found": terms_in_bank, "injection_anchor_found": terms_injected,
            "execution_id": trace.get("execution_id"), "trace_id": trace.get("trace_id"),
            "direct_top": [{"id": r.get("id"), "text": str(r.get("text") or "")[:220]} for r in direct_rows[:5]],
            "injected": [{"id": r.get("id"), "text": str(r.get("text_preview") or "")[:240]} for r in injected_rows],
        })
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({"cases": reports}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{index:02d} {status:<4} inj={int(effect_receipt.get('injected_count', len(effect_receipt.get('injected_ids') or [])) or 0):<2} bank={len(direct_rows):<2} {case.prompt[:38]}", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"cases": reports}, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [report for report in reports if report["status"] != "pass"]
    print(json.dumps({"total": len(reports), "passed": len(reports)-len(failed), "failed": len(failed), "output": str(OUT)}, ensure_ascii=False))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
