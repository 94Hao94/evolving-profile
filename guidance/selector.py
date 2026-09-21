"""Task-scoped selection. It never publishes and never treats omission as no guidance."""
from __future__ import annotations

from hashlib import sha256
import json
import re

import base64

from repository import GuidanceRepository


def _terms(request: dict) -> set[str]:
    task = request["task"]
    value = " ".join([task.get("objective", ""),task.get("current_user_message",""),task.get("context_summary",""), task.get("phase", ""), *task.get("previous_user_messages",[]), *task.get("current_constraints", []), *task.get("domains", []), *task.get("media", [])]).casefold()
    terms={term for term in value.replace("，", " ").replace("。", " ").split() if term}
    # Chinese prompts have no whitespace boundaries. Add short n-grams so a
    # task such as “内存占用/MCP说明/事实职责” can match applies_when and
    # guidance text without pretending the whole sentence is one token.
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", value):
        for size in (2,3):
            terms.update(chunk[i:i+size] for i in range(0,max(0,len(chunk)-size+1)))
    return terms


def _term_weights(request: dict) -> dict[str, float]:
    """Return weighted query terms; short CJK n-grams are weak evidence.

    The previous selector counted every 2/3-gram like a full keyword. On a
    long Chinese prompt that made unrelated units look highly relevant simply
    because they shared common characters. Keep n-grams for recall, but make
    explicit words and route terms materially stronger.
    """
    task = request["task"]
    value = " ".join([task.get("objective", ""), task.get("current_user_message", ""),
                       task.get("context_summary", ""), task.get("phase", ""),
                       *task.get("previous_user_messages", []),
                       *task.get("current_constraints", []), *task.get("domains", []),
                       *task.get("media", [])]).casefold()
    weights: dict[str, float] = {}
    for term in value.replace("，", " ").replace("。", " ").split():
        if term:
            weights[term] = max(weights.get(term, 0.0), 3.0 if len(term) > 1 else 1.0)
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", value):
        for size in (2, 3):
            for i in range(0, max(0, len(chunk) - size + 1)):
                gram = chunk[i:i + size]
                # Three-character phrases carry a little more signal than
                # isolated bigrams, but neither can dominate a full keyword.
                weights[gram] = max(weights.get(gram, 0.0), 0.55 if size == 3 else 0.25)
    return weights


def _task_categories(request: dict) -> dict[str,int]:
    task=request["task"];text=" ".join([task.get("objective",""),task.get("current_user_message",""),task.get("context_summary",""),*task.get("previous_user_messages",[]),*task.get("current_constraints",[])]).casefold();phase=task.get("phase")
    weights={}
    phase_category={"understand":"learning","analyze":"reasoning","execute":"collaboration","verify":"delivery","deliver":"communication"}.get(phase)
    # Phase is a weak prior only. It must not manufacture a learning
    # preference for every “understand” task.
    if phase_category and phase in {"analyze","execute","verify","deliver"}:
        weights[phase_category]=2
    signals={"learning":("为什么","机制","解释","讲明白","不懂","理解","例子","类比","是什么","什么意思","哪来的","怎么回事","如何","归类","分类","学科","理论"),"reasoning":("分析","判断","决策","权衡","原因","证据","思路","方案","需求","优势","应用","结合"),
             "delivery":("交付","验收","测试","验证","回归","恢复","回退","文件","完成","问题","修正","复查","复测","复盘","缺失","错误","故障"),"collaboration":("执行","继续","修改","推进","授权","协作"),
             "communication":("简短","汇报","表达","领导","怎么说","文字","结论","自然","公文","语气","客户","组织","压成","模板","选项","中文含义")}
    for category,words in signals.items():
        if any(word in text for word in words):weights[category]=weights.get(category,0)+12
    phrase_routes={"reasoning":("反例","替代解释","建模","给推荐"),"collaboration":("恢复目标","未完成项","进度"),"communication":("拍给我","拍到我脸上")}
    for category,phrases in phrase_routes.items():
        if any(phrase in text for phrase in phrases):weights[category]=weights.get(category,0)+20
    topic_routes={
        "reasoning":("架构","内存","MCP","说明书","事实","经历","实体","心智模型","职责","配置","机制","原因","匹配","相关"),
        "collaboration":("服务","进程","关闭","运行","部署","Hook","宿主","适配","继续","推进"),
        "delivery":("验收","测试","修复","页面","界面","溢出","健康","日志","回归"),
        "communication":("汇报","PPT","表达","呈现","文档","文字"),
    }
    for category,words in topic_routes.items():
        if any(word.casefold() in text for word in words): weights[category]=weights.get(category,0)+10
    return weights


# Explicit topic gates prevent a high-frequency observation from becoming a
# universal default.  These are deliberately coarse: they are a veto signal,
# not a second semantic ranker.  A guidance unit with no recognizable topic
# remains eligible when its wording/category matches the task.
_DOMAIN_TERMS = {
    "memory_system": ("mcp", "hindsight", "记忆", "bank", "hook", "recall", "research", "心智模型", "多维度偏好", "内存占用", "记忆系统", "配置文件", "selector", "选择器", "历史知识"),
    "visual_document": ("ppt", "幻灯片", "演示文稿", "演示视频", "视觉", "图片", "截图", "逐页", "投屏", "配图", "logo", "生图", "效果图", "素材", "图像"),
    "word_document": ("word", "docx", "文档", "方案", "材料", "表格", "排版", "段前", "段后", "单元格"),
    "causal_learning": ("因果认知", "五步法", "变量", "反事实", "速度叠加", "时间膨胀"),
    "science_explanation": ("物理", "科学", "svg", "xml文件"),
    "negotiation": ("谈判", "客服", "利益", "沟通心理学"),
    "health": ("药", "用药", "口碑", "副作用", "健康"),
    "software_delivery": ("页面", "界面", "白屏", "空白", "进不去", "出问题", "报错", "故障", "回归", "验收", "测试", "修复", "部署", "进程", "交付"),
}

_DOMAIN_ANCHORS = {
    "memory_system": (("mcp", "bank", "hook", "recall", "research", "记忆", "心智模型", "多维度偏好", "内存"),),
    "visual_document": (("ppt", "幻灯片", "演示文稿", "视觉", "截图", "投屏", "配图", "logo", "生图", "图像"),),
    "word_document": (("word", "docx", "文档", "表格", "段前", "段后", "单元格"),),
    "causal_learning": (("因果", "五步法", "变量", "反事实", "速度叠加", "时间膨胀"),),
    "science_explanation": (("svg", "xml", "物理", "科学"),),
    "negotiation": (("谈判", "客服", "利益", "沟通心理"),),
    "health": (("药", "用药", "口碑", "副作用", "健康"),),
    "software_delivery": (("页面", "界面", "白屏", "回归", "验收", "测试", "修复", "部署", "进程"),),
}

# A topic mentioned only to reject it is not positive evidence for selecting
# that topic's guidance.  Keep these patterns deliberately small and explicit;
# broad negation parsing would turn this selector into a fragile NLU system.
_NEGATED_TOPIC_PATTERNS = {
    "visual_document": (
        "没让你做ppt", "没让你做 ppt", "不是让你做ppt", "不是让你做 ppt",
        "不需要ppt", "不需要 ppt", "不要做ppt", "不要做 ppt",
        "不用做ppt", "不用做 ppt", "无需ppt", "无需 ppt",
        "未要求ppt", "没要求ppt",
    ),
}
_DOCUMENT_SPECIFIC_TERMS = (
    "ppt", "pptx", "word", "docx", "演示文稿", "投屏", "排版", "公文", "幻灯片", "汇报材料", "可视化", "图示",
)
_MEMORY_STRUCTURE_TERMS = ("世界事实", "经历", "观察", "实体", "心智模型", "多维度偏好")
_DELIVERY_INCIDENT_TERMS = ("页面", "界面", "白屏", "进不去", "空白", "报错", "故障", "出问题")
_EXPLANATION_TERM_MARKERS = ("英文", "英语", "缩写", "术语", "音标", "全称")


def explanation_preference_requested(text: str) -> bool:
    """Gate the English-term convention away from generic 'I do not understand' prompts."""
    value = str(text or "")
    if any(marker in value for marker in _EXPLANATION_TERM_MARKERS):
        return True
    return bool(re.search(r"\b(?:svg|xml|api|sdk|mcp|rag|json|yaml|sql|typescript|python)\b", value, re.I))


def _domains(text: str) -> set[str]:
    value = text.casefold()
    return {name for name, words in _DOMAIN_TERMS.items() if any(word.casefold() in value for word in words)}


def _domain_anchors(text: str, domain: str) -> set[str]:
    value = text.casefold()
    return {anchor for group in _DOMAIN_ANCHORS.get(domain, ()) for anchor in group if anchor.casefold() in value}


def _topic_is_negated(text: str, domain: str) -> bool:
    value = re.sub(r"\s+", "", text.casefold())
    return any(pattern.replace(" ", "").casefold() in value for pattern in _NEGATED_TOPIC_PATTERNS.get(domain, ()))


def _document_specific_unit(unit: dict) -> bool:
    corpus = " ".join([unit.get("text", ""), *unit.get("applies_when", []), *unit.get("scope", {}).get("domains", [])]).casefold()
    return any(term in corpus for term in _DOCUMENT_SPECIFIC_TERMS)


def _domain_conflict(request: dict, unit: dict) -> bool:
    if _direct_condition_match(request, unit):
        return False
    task = request.get("task") or {}
    task_text = " ".join([task.get("objective", ""), task.get("current_user_message", ""), task.get("context_summary", ""), *task.get("previous_user_messages", [])])
    unit_text = " ".join([unit.get("text", ""), *unit.get("applies_when", []), *unit.get("scope", {}).get("domains", [])])
    task_domains, unit_domains = _domains(task_text), _domains(unit_text)
    # A prompt may legitimately span multiple domains.  A specialized unit
    # is unsafe when the task has no matching domain at all: otherwise a
    # frequent “causal learning” observation becomes the fallback for short
    # prompts such as “Lark是什么？” or “可以”.
    if not unit_domains:
        return False
    if task_domains.isdisjoint(unit_domains):
        return True
    # A generic UI/page incident is a delivery problem, not a memory-system
    # architecture query. Require an explicit memory anchor before allowing a
    # mixed memory+delivery guidance unit through this gate.
    if "memory_system" in unit_domains and "memory_system" not in task_domains and unit.get("primary_category") != "delivery" and not _direct_condition_match(request, unit):
        return True
    if "software_delivery" in task_domains and unit.get("primary_category") == "delivery" and any(term in task_text for term in _DELIVERY_INCIDENT_TERMS):
        return False
    # A prompt that names several memory layers is an explicit architecture
    # question even when it does not repeat the word “记忆”. Keep the broad
    # memory-routing guidance eligible; finer topic gates still apply below.
    if "memory_system" in task_domains and "memory_system" in unit_domains:
        if sum(term in task_text for term in _MEMORY_STRUCTURE_TERMS) >= 2:
            return False
    # Within one broad domain, require at least one concrete anchor. This
    # prevents “SVG/XML” from inheriting a generic physical-causality rule,
    # and keeps MCP/Bank retrieval separate from unrelated memory prose.
    for domain in task_domains & unit_domains:
        task_anchors = _domain_anchors(task_text, domain)
        unit_anchors = _domain_anchors(unit_text, domain)
        # Keep a category/condition match authoritative when the task uses a
        # broader synonym (e.g. “交付” -> “验收”).
        if task_anchors and unit_anchors and task_anchors.isdisjoint(unit_anchors) and not _direct_condition_match(request, unit):
            return True
    return False


def _direct_condition_match(request: dict, unit: dict) -> bool:
    task = request.get("task") or {}
    text = " ".join([task.get("objective", ""), task.get("current_user_message", ""), task.get("context_summary", ""), *task.get("previous_user_messages", [])]).casefold()
    return any(condition and condition.casefold() in text for condition in unit.get("applies_when", []))


def _score(unit: dict, terms: set[str] | dict[str, float], categories: dict[str,int], query_text: str = "") -> tuple[float, str]:
    corpus = " ".join([unit.get("text", ""), *unit.get("applies_when", []), *unit.get("scope", {}).get("domains", [])]).casefold()
    if isinstance(terms, dict):
        overlap = sum(weight for term, weight in terms.items() if term in corpus)
    else:
        overlap = sum(term in corpus for term in terms)
    # A complete applies_when phrase is stronger than incidental n-gram overlap.
    direct = any(condition and condition.casefold() in query_text.casefold() for condition in unit.get("applies_when", []))
    bonus = 6.0 if direct else 0.0
    category_bonus=categories.get(unit.get("primary_category"),0)
    return overlap + bonus + category_bonus, "task_action_category_and_conditions" if direct or category_bonus or overlap else "active_general_guidance"


def _dedup_key(unit: dict) -> str:
    """Stable content key so revised copies do not consume the same page."""
    def norm(value: str) -> str:
        return re.sub(r"\s+", "", (value or "").casefold())
    text = norm(unit.get("text", ""))
    conditions = "|".join(sorted(norm(v) for v in unit.get("applies_when", []) if v))
    return text + "\x1f" + conditions


def get_task_guidance(repo: GuidanceRepository, request: dict, char_budget: int | None = None) -> dict:
    from recall_first import select
    return select(repo, request, char_budget)


def legacy_get_task_guidance(repo: GuidanceRepository, request: dict, char_budget: int | None = None) -> dict:
    max_tokens=max(500,min(8000,int(request.get('max_tokens') or 3000)))
    if char_budget is None:char_budget=max_tokens*2
    if request.get("memory_policy") == "forbidden":
        return {"selection_revision": repo.active_revision(), "included": [], "model_sections": [], "already_loaded_valid": [], "deferred": [], "held": [], "coverage": "not_requested", "errors": []}
    task = request.get("task") or {}
    if not isinstance(task.get("objective"), str) or not task["objective"].strip():
        return {"selection_revision": repo.active_revision(), "included": [], "model_sections": [], "already_loaded_valid": [], "deferred": [], "held": [], "coverage": "invalid_request", "errors": ["task_objective_required"]}
    loaded = {(row.get("id"), row.get("revision"), row.get("content_sha256")) for row in request.get("loaded", []) if isinstance(row, dict)}
    query_revision = sha256(json.dumps(request.get("task"), ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    start=0
    if request.get("cursor"):
        try:
            cursor=json.loads(base64.urlsafe_b64decode(request["cursor"]+'='*(-len(request["cursor"])%4)))
            if cursor.get("query_revision")!=query_revision or cursor.get("selection_revision")!=repo.active_revision():raise ValueError
            start=int(cursor["offset"])
        except Exception:
            return {"selection_revision":repo.active_revision(),"included":[],"model_sections":[],"already_loaded_valid":[],"deferred":[],"held":[],"coverage":"cursor_invalidated","next_cursor":None,"errors":["cursor_scope_or_revision_changed"]}
    chosen, deferred, loaded_valid, used = [], [], [], 0
    categories=_task_categories(request)
    audited=[]
    seen_keys=set()
    model_ref_ids={ref.get("id") for model in repo.active_models() for section in model.get("sections",[]) for ref in section.get("guidance_refs",[]) if ref.get("id")}
    term_weights = _term_weights(request)
    query_text = " ".join([task.get("objective", ""), task.get("current_user_message", ""), task.get("context_summary", ""), *task.get("previous_user_messages", []), *task.get("current_constraints", [])])
    for unit in repo.active_units():
        audit=(unit.get("preference_audit") or {}).get("state","not_reviewed")
        if audit in {"needs_review","superseded","stale"}:
            continue
        if unit.get("id") == "starter:explanation-and-unfamiliar-terms" and not explanation_preference_requested(query_text):
            continue
        # Explicit corrections such as “没让你做 PPT” must suppress the
        # otherwise strong lexical hit on the rejected topic.
        if _topic_is_negated(query_text, "visual_document") and _document_specific_unit(unit):
            continue
        if _domain_conflict(request, unit):
            continue
        score=_score(unit,term_weights,categories,query_text)[0]
        # No semantic/category match is not a reason to inject an unrelated
        # active preference. The host may still answer with no preference.
        task_text = " ".join([task.get("objective", ""), task.get("current_user_message", ""), task.get("context_summary", ""), *task.get("previous_user_messages", [])])
        unit_text = " ".join([unit.get("text", ""), *unit.get("applies_when", []), *unit.get("scope", {}).get("domains", [])])
        shared_domains = _domains(task_text) & _domains(unit_text)
        domain_match = any(_domain_anchors(task_text, domain) & _domain_anchors(unit_text, domain) for domain in shared_domains)
        cross_cutting = bool((unit.get("scope") or {}).get("cross_cutting"))
        direct_match = _direct_condition_match(request, unit)
        # A phase/category prior may rank candidates, but it cannot create a
        # match by itself. Require direct conditions, a topic match, or actual
        # lexical evidence before returning an item. This prevents short
        # prompts from being filled with the current phase's most common rule.
        category_bonus = categories.get(unit.get("primary_category"), 0)
        lexical_evidence = score - category_bonus
        unit_corpus = " ".join([unit.get("text", ""), *unit.get("applies_when", []), *unit.get("scope", {}).get("domains", [])]).casefold()
        # “页面/界面” is a valid software-delivery anchor, but it is not
        # enough to activate PPT/Word layout rules. Require a document anchor
        # before selecting a document-specific unit unless its exact condition
        # was stated by the user.
        if _document_specific_unit(unit) and not direct_match and not any(term in query_text.casefold() for term in _DOCUMENT_SPECIFIC_TERMS):
            continue
        strong_lexical = sum(weight for term, weight in term_weights.items() if weight >= 3 and term in unit_corpus)
        category_only_ok = categories.get(unit.get("primary_category"), 0) >= 12 and any(signal in query_text.casefold() and signal in unit_corpus for signal in ("为什么", "机制", "解释", "是什么", "什么意思", "哪来的", "怎么回事", "归类", "分类", "学科", "理论", "分析", "原因", "证据", "交付", "验收", "测试", "修改", "执行", "建议", "推荐", "相关", "问题", "修正", "复查", "复测", "复盘", "缺失", "错误", "故障", "方案", "需求", "优势", "应用"))
        # Questions about an unfamiliar term often omit the word “解释”.
        # Let the audited learning preference cover that shape, while the
        # domain gate above still blocks unrelated specialised models.
        learning_question_ok = unit.get("primary_category") == "learning" and categories.get("learning", 0) >= 12 and any(signal in query_text.casefold() for signal in ("是什么", "什么意思", "哪来的", "怎么回事"))
        learning_concept_question_ok = unit.get("primary_category") == "learning" and categories.get("learning", 0) >= 12 and any(signal in query_text.casefold() for signal in ("归类", "分类", "学科", "理论")) and any(signal in unit_corpus for signal in ("解释", "例子", "比喻", "全称", "中文含义"))
        memory_structure_question_ok = unit.get("primary_category") in {"reasoning", "delivery", "collaboration"} and "memory_system" in _domains(unit_corpus) and sum(term in query_text for term in _MEMORY_STRUCTURE_TERMS) >= 2 and any(term in unit_corpus for term in ("注入", "召回", "事实", "实体", "观察", "模型", "职责"))
        delivery_incident_ok = unit.get("primary_category") == "delivery" and "software_delivery" in _domains(query_text) and any(term in query_text for term in _DELIVERY_INCIDENT_TERMS) and any(term in unit_corpus for term in ("修复", "复测", "复盘", "回归"))
        model_linked_unclassified = not unit.get("primary_category") and unit.get("id") in model_ref_ids and bool(categories)
        if unit.get("primary_category") and not direct_match and not domain_match and not cross_cutting and strong_lexical < 1.5 and not category_only_ok and not learning_question_ok and not learning_concept_question_ok and not memory_structure_question_ok and not delivery_incident_ok:
            continue
        if not direct_match and not domain_match and not cross_cutting and not category_only_ok and not learning_question_ok and not learning_concept_question_ok and not memory_structure_question_ok and not delivery_incident_ok and not model_linked_unclassified and strong_lexical < 4.0:
            continue
        if audit=="restricted" and score<=categories.get(unit.get("primary_category"),0):
            continue
        key = _dedup_key(unit)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        audited.append(unit)
    ordered=sorted(audited, key=lambda value: (_score(value, term_weights,categories,query_text)[0], bool(_direct_condition_match(request, value))), reverse=True)
    next_offset=None
    for index,unit in enumerate(ordered[start:],start=start):
        content_hash = sha256(json.dumps({key: unit.get(key) for key in ("text", "applies_when", "exceptions", "effect_on_action")}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        compact = {key: unit.get(key) for key in ("id", "revision", "primary_category", "related_categories", "nature", "text", "scope", "applies_when", "exceptions", "effect_on_action", "evidence_refs", "source_family_ids", "status")}
        compact["content_sha256"] = content_hash
        compact["preference_audit"] = unit.get("preference_audit")
        compact["selection_reason"] = _score(unit, term_weights,categories,query_text)[1]
        # Guidance is advisory context, never an execution command.  The host
        # Agent must independently reconcile it with the current Prompt,
        # current authoritative sources, tool output, permissions and safety.
        audit_state = (unit.get("preference_audit") or {}).get("state", "not_reviewed")
        validity = (unit.get("preference_audit") or {}).get("validity_kind", "unknown")
        compact["guidance_role"] = "advisory_reference"
        compact["decision_precedence"] = ["current_user_prompt", "current_authoritative_source", "tool_result_and_permissions", "multi_dimensional_preference"]
        compact["may_override_current_prompt"] = False
        compact["may_authorize_action"] = False
        compact["requires_agent_judgment"] = True
        compact["use_mode"] = "review_before_use" if validity in {"volatile_method", "time_sensitive", "unknown"} or audit_state != "approved" else "advisory"
        if (unit["id"], unit["revision"], content_hash) in loaded:
            loaded_valid.append(compact)
        elif used + len(json.dumps(compact, ensure_ascii=False)) <= char_budget:
            chosen.append(compact); used += len(json.dumps(compact, ensure_ascii=False))
        else:
            deferred.append({"id": unit["id"], "revision": unit["revision"], "reason": "budget_requires_next_page", "requires_read_before_dependent_action": True})
            if next_offset is None:next_offset=index
    included_refs={(item["id"],item["revision"]) for item in chosen+loaded_valid}
    model_sections=[]
    for model in repo.active_models():
        for section in model.get("sections",[]):
            if any((ref.get("id"),ref.get("revision")) in included_refs for ref in section.get("guidance_refs",[])):
                model_sections.append({
                    **section,
                    "model_id": model["id"],
                    "model_revision": model["revision"],
                    "model_title": model["title"],
                    "model_kind": model.get("model_kind", "legacy_domain_aggregate"),
                    "model_dimensions": list(model.get("dimensions") or []),
                    "model_mechanism": model.get("mechanism") or section.get("text"),
                    "model_status": model.get("status", "active"),
                })
    return {"request_id": request.get("context_ref"), "selection_revision": repo.active_revision(), "validity_token": "sha256:" + query_revision,
            "included": chosen, "model_sections": model_sections, "already_loaded_valid": loaded_valid, "deferred": deferred, "held": [],
            "coverage": "complete_active_set" if not deferred else "partial_page_with_deferred",
            "next_cursor": (base64.urlsafe_b64encode(json.dumps({"offset":next_offset,"query_revision":query_revision,"selection_revision":repo.active_revision()},separators=(',',':')).encode()).decode().rstrip('=') if deferred else None),
            "budget":{"requested_max_tokens":max_tokens,"soft":True,"candidate_scope":"all_active_units","estimated_response_tokens":used//2},
            "foreground_model_calls":0,"long_term_model_created":False,
            "decision_policy":{"guidance_is_advisory":True,"current_prompt_wins":True,"current_authoritative_source_wins":True,
                                "tool_results_and_permissions_win":True,"preference_cannot_authorize_or_force_execution":True,
                                "conflict_action":"report_conflict_and_use_current_evidence; keep historical preference for audit"},
            "errors": []}
