"""Rebuild official mental models from active GuidanceUnit revisions only."""
from __future__ import annotations

from hashlib import sha256
import datetime as dt
import json
from pathlib import Path
import urllib.parse
import urllib.request
from urllib.error import HTTPError

from mcp_runtime import load_repository
from models import publish_model
from observation_rebuild import atomic, load_env


LEGACY_MODEL_TARGETS = [
    ("liuzhongyang-ai-operating-system", "AI使用、记忆权威与个人认知基础设施"),
    ("liuzhongyang-work-project-architecture", "工作与项目推进的边界模型"),
    ("liuzhongyang-business-architecture", "业务分析、建议与决策模型"),
    ("liuzhongyang-cognition-learning", "学习、解释与陌生概念适配模型"),
    ("liuzhongyang-collaboration-delivery", "协作、执行、验收与交付模型"),
]
MODEL_CATEGORIES={
 "liuzhongyang-ai-operating-system":{"collaboration","reasoning"},
 "liuzhongyang-work-project-architecture":{"collaboration","delivery"},
 "liuzhongyang-business-architecture":{"reasoning","communication"},
 "liuzhongyang-cognition-learning":{"learning","communication"},
 "liuzhongyang-collaboration-delivery":{"collaboration","delivery"},
}
MODEL_FLOWS={
 "liuzhongyang-ai-operating-system":"确认当前权威材料与权限边界→选择多维度偏好或历史知识路线→仅取本轮必要证据→执行→分别记录工具输出、宿主接收和实际使用。",
 "liuzhongyang-work-project-architecture":"锁定项目对象、阶段和真实需求方→核对当前事实与历史变化→按适用指导组织推进→验证成果对项目目标的实际贡献。",
 "liuzhongyang-business-architecture":"先明确决策问题和证据缺口→比较事实、估算与假设→形成按推荐度排序的建议→保留反例和不确定性供决策。",
 "liuzhongyang-cognition-learning":"判断概念陌生度与困难程度→先给核心机制→补具体例子→特别抽象时再给有边界的类比→检查能否迁移使用。",
 "liuzhongyang-collaboration-delivery":"确认目标、授权和交付格式→连续推进并处理同类问题→以真实可见结果和来源验收→报告已完成、未知、残留风险和回退。",
}

SECTION_TOPICS={
 "liuzhongyang-ai-operating-system":[
  ("authority-and-scope",("权威","当前","权限","范围","授权","Prompt","来源"),"先确定当前用户要求、权威来源、记忆权限和任务范围，历史资料只能作为参考，不能扩张授权。"),
  ("memory-routing",("记忆","Hindsight","召回","注入","候选","宿主","MCP","偏好"),"根据当前缺口选择多维度偏好或历史事实路线；候选、工具返回、宿主接收、实际注入和答案使用分别记账。"),
  ("agent-boundaries",("Agent","主Agent","专用Agent","分工","委派","技能","工具"),"主Agent保留需求理解和核心架构判断，专用Agent只接收与任务直接相关的偏好、边界和验收标准。"),
 ],
 "liuzhongyang-work-project-architecture":[
  ("objective-and-constraints",("目标","约束","范围","阶段","需求","项目","跑偏"),"先锁定项目对象、阶段、目标、约束、交付物和验收标准，并在执行中持续对照。"),
  ("continuation-and-handoff",("继续","续接","上下文","交接","远距离","活动任务","Full Prompt"),"短句续接时结合活动任务证据、必要远距离上下文和当前Prompt；交接必须携带文件、状态、验证和责任边界。"),
  ("change-impact",("修改","关联","遗漏","同类","整体","范围","影响"),"修改前识别关联范围和不应改变的部分，完成后整体复查同类问题和遗漏。"),
 ],
 "liuzhongyang-business-architecture":[
  ("evidence-and-conflict",("证据","来源","冲突","事实","假设","估算","unresolved","superseded"),"区分事实、估算与假设；遇到冲突按当前要求、权威来源、主体关系范围和时间裁决，证据不足保留unresolved。"),
  ("analysis-and-recommendation",("分析","建议","决策","推荐","排序","权衡","反证"),"明确决策问题和证据缺口，比较替代解释和反证，形成按推荐度排序的建议。"),
  ("business-language",("客户","学校","业务","正式","术语","逻辑","材料"),"正式材料以真实业务阶段和需求方视角组织，不让模板术语或技术堆砌替代业务逻辑。"),
 ],
 "liuzhongyang-cognition-learning":[
  ("mechanism-first",("机制","解释","概念","理解","因果"),"先重建核心机制和因果链，再补充细节。"),
  ("examples-and-analogy",("例子","类比","通俗","陌生","技术","业务读者"),"根据陌生度补具体例子；特别抽象时再使用有边界的类比，并面向业务读者解释图和流程。"),
  ("transfer-check",("迁移","复述","检验","复习","应用"),"最后检查能否复述、迁移或在新场景中使用，而不是只确认看过。"),
 ],
 "liuzhongyang-collaboration-delivery":[
  ("execution-control",("执行","推进","授权","不要停","完成","连续","分工"),"确认授权和边界后连续推进，主任务不因中间检查而丢失；超出授权时停止扩张。"),
  ("artifact-quality",("交付","成品","格式","表格","图片","图表","可读","分页","链接"),"交付物按真实使用场景检查格式、可读性、分页、图表、链接和细节入口。"),
  ("verification-and-recovery",("验收","测试","回归","可见","回读","恢复","回退","状态页"),"用真实可见结果、回读来源和端到端链路验收；失败证据、unknown和回退条件必须保留。"),
 ]
}


def _rank(units:list[dict], keywords:tuple[str,...])->list[dict]:
    def score(unit:dict):
        text=" ".join([str(unit.get("text", "")), *(unit.get("applies_when") or []), *(unit.get("exceptions") or [])])
        return (sum(text.count(keyword) for keyword in keywords), 1 if unit.get("nature") in {"explicit_requirement","declared_preference"} else 0, unit.get("activated_at",0))
    return [unit for unit in sorted(units,key=score,reverse=True) if score(unit)[0] > 0]


def compile_legacy_models(units:list[dict])->list[dict]:
    result=[]
    for model_id,title in LEGACY_MODEL_TARGETS:
        selected=[u for u in units if u.get('primary_category') in MODEL_CATEGORIES[model_id]]
        if not selected:selected=units[:1]
        sections=[]; used=set()
        for section_id,keywords,text in SECTION_TOPICS[model_id]:
            ranked=_rank(selected,keywords)[:10]
            if not ranked: continue
            refs=[{'id':u['id'],'revision':u['revision']} for u in ranked]
            used.update(ref['id'] for ref in refs)
            sections.append({'section_id':section_id,'text':text,'applies_when':['任务涉及'+"、".join(keywords[:3])+'时'],
                             'exceptions':['当前Prompt和当前权威材料优先','单条指导已足够时不强制展开全部章节'],
                             'guidance_refs':refs,'counterevidence':['依赖条目被标记stale、superseded或needs_review时不得使用']})
        remaining=[u for u in selected if u['id'] not in used]
        if remaining:
            refs=[{'id':u['id'],'revision':u['revision']} for u in remaining[:10]]
            sections.append({'section_id':'additional-active-patterns','text':MODEL_FLOWS[model_id],
                             'applies_when':['主题相关但前三个章节未完整覆盖时'],
                             'exceptions':['只选择与当前任务直接相关的条目，不按数量凑满'],
                             'guidance_refs':refs,'counterevidence':['没有直接相关性时不注入']})
        result.append({'id':model_id,'title':title,'purpose':'把已验证指导组织为可执行判断框架，不反向充当底层事实证据。','sections':sections})
    return result


def prompt(units: list[dict], existing_models: list[dict]) -> str:
    compact = [{key: unit.get(key) for key in ("id", "revision", "primary_category", "nature", "text", "applies_when", "exceptions", "effect_on_action")} for unit in units]
    existing = [{key: model.get(key) for key in ("id", "revision", "title", "mechanism", "dimensions", "status")} for model in existing_models]
    return """你是 Evolving Profile 的原子心智模型编译器。active_guidance 是唯一语义来源，existing_models 只用于判断新增、合并、修订或替代，不得把旧模型反向当证据。

心智模型必须是一个可复用的判断或行动机制，至少引用2条有效指导并跨越2个偏好维度。它不是领域目录、主题摘要或条目拼接。数量不固定，可返回0到20个候选。每项必须给出适用条件、例外、反证和精确 guidance id。当前Prompt始终优先。

只返回JSON：{"candidates":[{"title":"简短机制名","mechanism":"判断步骤或行动机制","applies_when":[],"exceptions":[],"counterevidence":[],"guidance_ids":[],"lifecycle_action":"new|merge|revise|supersede|hold","target_model_id":null,"reason":"..."}]}。
active_guidance：\n""" + json.dumps(compact, ensure_ascii=False) + "\nexisting_models：\n" + json.dumps(existing, ensure_ascii=False)


def call_qwen(cfg: dict, units: list[dict], existing_models: list[dict]) -> list[dict]:
    body = {"model": cfg["HINDSIGHT_API_LLM_MODEL"], "messages": [{"role": "user", "content": prompt(units, existing_models)}], "temperature": 0,
            "max_tokens": 12288, "enable_thinking": False, "response_format": {"type": "json_object"}}
    request = urllib.request.Request(cfg["HINDSIGHT_API_LLM_BASE_URL"].rstrip("/") + "/chat/completions", data=json.dumps(body, ensure_ascii=False).encode(),
        headers={"Authorization": "Bearer " + cfg["HINDSIGHT_API_LLM_API_KEY"], "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=900) as response: value = json.loads(response.read())
    raw = value["choices"][0]["message"]["content"].strip()
    if raw.startswith("```"): raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    parsed = json.loads(raw); candidates = parsed if isinstance(parsed, list) else parsed.get("candidates")
    if not isinstance(candidates, list) or len(candidates) > 20: raise ValueError("dynamic_candidate_contract_invalid")
    return candidates


def compile_proposals(units: list[dict], proposals: list[dict], existing_models: list[dict] | None = None,
                      *, verified_at: str | None = None) -> dict:
    active_by_id = {unit["id"]: unit for unit in units}
    existing_by_id = {model["id"]: model for model in (existing_models or [])}
    verified_at = verified_at or dt.datetime.now(dt.timezone.utc).isoformat()
    compiled = {}
    decisions = []
    for proposal in proposals:
        guidance_ids = list(dict.fromkeys(str(value) for value in proposal.get("guidance_ids") or [] if str(value) in active_by_id))
        refs = [{"id": value, "revision": active_by_id[value]["revision"]} for value in guidance_ids]
        dimensions = sorted({str(active_by_id[value].get("primary_category") or "") for value in guidance_ids} - {""})
        action = str(proposal.get("lifecycle_action") or "hold")
        mechanism = " ".join(str(proposal.get("mechanism") or "").split())
        hold_reasons = []
        if len(dimensions) < 2: hold_reasons.append("requires_two_dimensions")
        if len(refs) < 2: hold_reasons.append("requires_two_references")
        if not mechanism: hold_reasons.append("mechanism_required")
        if not proposal.get("applies_when") or not proposal.get("exceptions") or not proposal.get("counterevidence"):
            hold_reasons.append("missing_scope_or_counterevidence")
        if action not in {"new", "revise", "supersede"}:
            hold_reasons.append("lifecycle_review_required")
        target = str(proposal.get("target_model_id") or "")
        if action in {"revise", "supersede"} and target not in existing_by_id:
            hold_reasons.append("target_model_not_found")
        model_id = target if action == "revise" and target else "mental-model:" + sha256(mechanism.casefold().encode()).hexdigest()[:24]
        active = not hold_reasons
        section = {
            "section_id": "mechanism", "text": mechanism,
            "applies_when": list(proposal.get("applies_when") or []),
            "exceptions": list(proposal.get("exceptions") or []),
            "guidance_refs": refs,
            "counterevidence": list(proposal.get("counterevidence") or []),
        }
        model = {
            "id": model_id,
            "model_kind": "atomic_cross_dimensional" if active else "atomic_cross_dimensional_candidate",
            "status": "active" if active else "needs_review",
            "title": str(proposal.get("title") or mechanism[:32] or "待审核心智模型"),
            "purpose": "把多个偏好维度组合成一个可复用的判断或行动机制。",
            "mechanism": mechanism,
            "dimensions": dimensions,
            "confidence": 0.85 if active else 0.6,
            "last_verified_at": verified_at,
            "hold_reasons": hold_reasons,
            "lifecycle_action": action,
            "supersedes": target if action == "supersede" and target else None,
            "sections": [section],
        }
        model["revision"] = "sha256:" + sha256(json.dumps({key:value for key,value in model.items() if key != "revision"}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        prior = compiled.get(model_id)
        if prior is None or (prior["status"] != "active" and model["status"] == "active"):
            compiled[model_id] = model
        decisions.append({"model_id": model_id, "action": action, "active": active, "hold_reasons": hold_reasons, "reason": proposal.get("reason")})
    values = list(compiled.values())
    return {"active": [model for model in values if model["status"] == "active"],
            "candidates": [model for model in values if model["status"] == "needs_review"],
            "decisions": decisions}


def official_get(bank_id: str, model_id: str) -> dict:
    path = "/v1/default/banks/" + urllib.parse.quote(bank_id, safe="") + "/mental-models/" + urllib.parse.quote(model_id, safe="")
    with urllib.request.urlopen("http://127.0.0.1:8888" + path, timeout=20) as response: return json.loads(response.read())


def official_patch(bank_id: str, model_id: str, payload: dict) -> dict:
    path = "/v1/default/banks/" + urllib.parse.quote(bank_id, safe="") + "/mental-models/" + urllib.parse.quote(model_id, safe="")
    request = urllib.request.Request("http://127.0.0.1:8888" + path, data=json.dumps(payload, ensure_ascii=False).encode(),
                                     headers={"Content-Type": "application/json"}, method="PATCH")
    try:
        with urllib.request.urlopen(request, timeout=60) as response: return json.loads(response.read())
    except HTTPError as error:
        raise ValueError('official_model_patch_'+str(error.code)+':'+error.read(1000).decode(errors='replace')) from error


def main(config_path: str, output_dir: str):
    repo = load_repository(config_path); units = [unit for unit in repo.active_units() if (unit.get("preference_audit") or {}).get("state", "not_reviewed") in {"approved", "restricted"}]
    existing = repo.model_inventory()["active"]
    cfg = load_env()
    proposals = call_qwen(cfg, units, existing)
    compiled = compile_proposals(units, proposals, existing)
    results = []
    for candidate in compiled["active"]:
        stored = publish_model(repo, candidate)
        if candidate.get("supersedes"):
            repo.archive_models([candidate["supersedes"]], reason="superseded_by:" + candidate["id"])
        results.append({"model": stored, "dimensions": candidate["dimensions"], "lifecycle_action": candidate["lifecycle_action"]})
    for candidate in compiled["candidates"]:
        repo.store_candidate_model(candidate)
    root = Path(output_dir); root.mkdir(parents=True, exist_ok=True)
    report = {"schema": "guidance.dynamic-model-rebuild.v1", "at": dt.datetime.now(dt.timezone.utc).isoformat(), "active_guidance_count": len(units),
              "published": results, "candidate_count": len(compiled["candidates"]), "decisions": compiled["decisions"], "inventory": repo.model_inventory()["counts"]}
    atomic(root / "model-rebuild-report.json", report); print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    import sys
    main(*sys.argv[1:])
