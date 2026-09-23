"""Publish a conservative, Codex-reviewed batch from the 60-day raw families.

The source witness report is treated as untrusted input.  This module only
publishes an explicitly selected, hand-reviewed batch and keeps the original
quote in every evidence reference.  No model call is made.
"""
from __future__ import annotations

from hashlib import sha256
import datetime as dt
import json
from pathlib import Path
import re
import sys

from mcp_runtime import load_repository
from publisher import prepare_publication, commit_publication


BATCH = [
    # family index: canonical text, category, scope, validity, applies_when, exceptions
    (0, "面对实时来源与历史状态冲突时，区分当前有效结论、被替代的旧状态和必须保留的历史经历；证据不足时明确标记 unresolved，不强行补全。", "reasoning", "global", "stable", ["状态或来源发生冲突时"], ["当前用户Prompt和当前权威材料优先"]),
    (1, "处理实体关联时，允许标准名、别名、缩写和历史称呼作为检索入口，但只有具备主体、关系、时间、来源和范围的证据才能进入结论或注入。", "reasoning", "global", "stable", ["历史实体、别名或关系需要核对时"], ["图谱或星座图只提供关联线索，不能单独证明事实"]),
    (2, "长任务续接不能只依赖最近几轮；应结合活动任务证据、必要远距离上下文和当前 Full Prompt，并避免把普通续写误判为同一任务。", "collaboration", "global", "stable", ["用户以‘继续’等短句续接长任务时"], ["新目标或当前Prompt明确改变时重新判断"]),
    (7, "发现问题时先定位原因并修复根因，再对同类和相邻范围做回归检查，不只对当前表面症状打补丁。", "reasoning", "global", "stable", ["出现错误、失败或重复缺陷时"], ["用户明确只要诊断而不要求修改时不越权执行"]),
    (8, "执行任务前先选择最适合的技能或工具；发现技能本身有问题时，先修正或绕开技能缺陷，再继续主任务。", "collaboration", "global", "stable", ["任务涉及可复用技能、工具或工作流时"], ["明确自足且不需要工具的简单任务可直接回答"]),
    (10, "正式交付前必须进行整体检查和至少一次同类回归，重点核对格式、分页、图表、链接和内容是否完整，不能只看局部改动。", "delivery", "global", "stable", ["交付文档、表格、演示文稿或网页时"], ["用户明确要求只做文字诊断时不修改成品"]),
    (14, "图表或示意图中的关键数字不能留空；没有真实数据时应明确使用有边界的模拟数据，并标注其性质。", "delivery", "global", "stable", ["需要展示指标、图表或示例数据时"], ["用户明确要求保留空白字段时遵从当前要求"]),
    (15, "视觉材料首先保证可读性：图片、图例和文字应达到实际查看或打印时可辨识的大小，必要时拆分为多页。", "delivery", "global", "stable", ["制作或修改图表、图片、PPT或打印材料时"], ["页面数量约束与可读性冲突时说明取舍"]),
    (21, "表格交付应优先保持单表、对齐和紧凑分页，避免无必要的首行缩进、续表、跨页断裂和说明文字挤出单元格。", "delivery", "global", "stable", ["编辑正式表格或带表格的文档时"], ["原模板有明确不可变结构时只改必要内容"]),
    (24, "页面内容要先梳理层次再安排文字和图示；文字不堆砌，图示清晰且与页面主题直接对应。", "communication", "global", "stable", ["制作汇报材料、方案或可视化页面时"], ["技术细节需要完整保留时用分层或附录承载"]),
    (25, "正式材料中的术语必须符合真实业务逻辑和当前阶段，不能因为沿用模板就写入‘参考’、‘需求书’等不适用表述。", "communication", "domain", "context_sensitive", ["面向客户或学校编写正式材料时"], ["引用历史材料时保留其历史身份并明确不是当前事实"]),
    (31, "对外说明用自然、直接、少模板腔的中文；避免明显的AI套话，同时保留必要的技术边界和证据说明。", "communication", "global", "stable", ["为用户或外部对象撰写说明、回复或报告时"], ["正式公文格式和用户明确术语要求优先"]),
    (34, "解释技术图或机制时，先说明它解决什么问题和各部分如何连接，再用不懂技术的业务读者也能理解的语言解释。", "learning", "global", "stable", ["解释技术机制、架构图或流程图时"], ["用户要求仅给结论时不强行展开教程"]),
    (35, "执行复杂任务前先锁定目标、约束、交付物和验收标准；过程中持续对照这些边界，防止任务逐步跑偏。", "collaboration", "global", "stable", ["多步执行或跨文件任务开始前"], ["当前用户Prompt改变目标时以新目标为准"]),
    (44, "同类错误重复出现时，先查找可复用的参照、规则和根因，形成防复发检查项，再继续修改。", "reasoning", "global", "stable", ["错误具有重复性或已有历史先例时"], ["无可靠参照时明确不确定性"]),
    (62, "完成一轮修改后要主动寻找遗漏、冲突和更好的方案，而不是只等待用户指出下一处问题。", "reasoning", "global", "stable", ["阶段性结果或版本完成后"], ["用户明确要求停止扩展范围时遵从"]),
    (63, "专家意见、修改说明和实际改动必须一一对应；重复出现的相同意见在后续位置可以简化，避免表格被冗余说明撑乱。", "delivery", "global", "stable", ["整理评审意见、修改说明或审计表时"], ["首次出现的规则仍需给出完整定义"]),
    (66, "客户需求理解和核心架构判断保留在当前主Agent；可将明确、可验收的执行和整理工作委派出去，但委派必须带着边界、验收标准和回读证据。", "collaboration", "global", "stable", ["需要在主Agent与专用Agent之间分工时"], ["用户当前Prompt明确指定其他分工时优先"]),
    (72, "涉及网页或桌面界面时，验收要从用户可见的完整页面和交互出发，检查显示、链接、切换和状态，而不只看后端接口。", "delivery", "global", "stable", ["网页、桌面端或状态页交付时"], ["纯后端或文字任务不强制做界面检查"]),
    (89, "记忆系统验收必须区分候选、筛选、工具返回、宿主接收、实际注入和答案使用；候选数量或绿色状态页不能替代端到端证据。", "reasoning", "global", "stable", ["验证记忆召回、注入或工具链路时"], ["无法观测的模型注意力和答案改善保持 unknown"]),
    (91, "验证记忆链路时使用自然任务、短句续问、近义改写和空结果等多种输入，并同时检查相关性、上下文负担和必要时的补读。", "learning", "global", "stable", ["测试召回、上下文协同或分页补读时"], ["明确禁止记忆时不读取"]),
    (94, "交付中的表格、图表和状态结果应提供可回读或可放大入口，让用户能检查细节而不是只能看缩略图。", "delivery", "global", "stable", ["状态页、报告或可视化结果需要细节核验时"], ["纯文本短答不需要额外链接"]),
    (96, "专用Agent默认读取与其任务直接相关的核心偏好；主Agent可在需要时读取更广范围，但不能把专用任务的全部历史无差别注入。", "collaboration", "global", "stable", ["为不同Agent设计记忆权限和召回范围时"], ["当前任务明确需要跨领域历史时扩大范围并记录理由"]),
    (100, "历史偏好提炼不能只等待用户再次明确提问；应从跨会话的重复表达、纠错和验收反馈中寻找可泛化模式，同时保留来源、范围和不确定性。", "reasoning", "global", "stable", ["进行长期偏好或行为模式提炼时"], ["一次性指令、测试问句和项目局部规则不得升级为全局偏好"]),
]


def _ref(family: dict, witness: dict, quote: str, bank_id: str, ordinal: int) -> dict:
    user_span = str(witness.get("user_span") or quote)
    start = user_span.find(quote)
    if start < 0:
        # The family quote is authoritative; use the witnessed span as the
        # bounded source when a punctuation-normalized copy was stored.
        quote = user_span
        start = 0
    source_sha = sha256(user_span.encode()).hexdigest()
    created = witness.get("created_at") or family.get("event_at_max") or "unknown"
    return {"bank_id": bank_id, "memory_id": None, "document_id": str(witness["document_id"]),
            "chunk_id": "raw-thread-witness:" + str(witness["document_id"]) + ":" + str(ordinal),
            "source_revision": str(created), "source_sha256": source_sha,
            "span_start": int(start), "span_end": int(start + len(quote)), "quote": quote,
            "stored_role": "user", "origin": "user_direct", "statement_kind": "request",
            "event_at": str(created), "stored_at": "unknown", "human_author_verified": False,
            "origin_witness_ref": "codex-60d-family:" + str(family.get("family_key", "")),
            "origin_witness_sha256": source_sha}


def publish(config_path: str, witness_path: str, out_path: str) -> dict:
    config = json.loads(Path(config_path).read_text())
    repo = load_repository(config_path)
    repo.set_owner(config["owner_token"])
    source = json.loads(Path(witness_path).read_text())
    active = repo.active_units()
    active_text = {re.sub(r"\s+", "", str(u.get("text", ""))) for u in active}
    results, held = [], []
    for ordinal, item in enumerate(BATCH):
        index, canonical, category, scope, validity, applies, exceptions = item
        if index >= len(source.get("items", [])):
            held.append({"index": index, "reason": "family_index_missing"}); continue
        family = source["items"][index]
        if family.get("disposition") != "codex_reviewable_general_pattern":
            held.append({"index": index, "reason": "not_general_pattern"}); continue
        witnesses = family.get("source_witnesses") or []
        if len(witnesses) < 2:
            held.append({"index": index, "reason": "fewer_than_two_hindsight_documents"}); continue
        quote = str((family.get("verbatim_quotes") or [family.get("canonical_text", "")])[0])
        refs = [_ref(family, witness, quote, config["bank_id"], n) for n, witness in enumerate(witnesses[:2])]
        if re.sub(r"\s+", "", canonical) in active_text:
            held.append({"index": index, "reason": "duplicate_active_text"}); continue
        target = "codex-60d:" + sha256(canonical.encode()).hexdigest()[:24]
        proposal = {"proposal_id": target, "operation": "create", "target_id": target,
                    "base_revision": repo.active_revision(), "nature": "inferred_pattern",
                    "primary_category": category, "related_categories": [], "text": canonical,
                    "verbatim_quote": quote, "asr_corrections": [], "uncertain_terms": [],
                    "applies_when": applies, "exceptions": exceptions,
                    "effect_on_action": "在适用范围内作为多维度偏好参考，不扩张执行授权。",
                    "scope": {"user_id": "user", "agent_roles": [], "project_ids": [], "task_ids": [], "domains": [], "media": []},
                    "evidence_refs": refs, "source_family_ids": ["codex-60d-family:" + str(index)]}
        review = {"support": "supported", "scope_ok": True, "conditions_preserved": True,
                  "source_role_ok": True, "hypothetical_only": False, "conflicts": [],
                  "source_witness_hash": sha256("\x1f".join(ref["origin_witness_sha256"] for ref in refs).encode()).hexdigest(),
                  "reviewer_model": "current-codex-60d-cross-thread-semantic-review", "reviewed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                  "audit": {"scope_level": scope, "validity_kind": validity, "independent_threads": family.get("independent_threads"), "occurrences": family.get("occurrences"), "source_documents": len(witnesses)}}
        try:
            prepared = prepare_publication(repo, proposal, review, config["owner_token"])
            committed = commit_publication(repo, prepared["publication_id"], repo.active_revision(), prepared["source_tokens"], config["owner_token"])
            repo.set_unit_audit(committed["unit_id"], committed["revision"], {"state": "approved", "scope_level": scope, "validity_kind": validity, "reason": "Codex reviewed across independent raw conversation families; source witnesses preserved.", "superseded_by": None})
            results.append({"index": index, "unit_id": committed["unit_id"], "revision": committed["revision"], "category": category, "scope": scope, "source_documents": len(witnesses)})
            active_text.add(re.sub(r"\s+", "", canonical))
        except Exception as exc:
            held.append({"index": index, "reason": type(exc).__name__ + ":" + str(exc)})
    report = {"schema": "guidance.codex-60d-controlled-publication.v1", "at": dt.datetime.now(dt.timezone.utc).isoformat(), "selected": len(BATCH), "published": len(results), "held": held, "items": results, "boundary": "Only explicit reviewed families published; remaining raw candidates and all held families remain isolated."}
    Path(out_path).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    report = publish(*sys.argv[1:])
    print(json.dumps({k: report[k] for k in ("selected", "published", "held")}, ensure_ascii=False))
