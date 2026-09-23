"""Single versioned source for memory-use instructions across every host."""
from __future__ import annotations

import datetime as dt
from hashlib import sha256
import json
from pathlib import Path
import uuid


VERSION = "memory-use.v1.7.3-20260920"
CORE_TEXT = (
    "Evolving Profile（简称EP，产品2.2）在每轮UserPromptSubmit先提供本说明、权限允许的轻量偏好索引和Bank主题地图，再附当前任务工作投影。地图先于Agent的深读判断，不按Prompt关键词决定是否提供；加载失败须标记未知。"
    "地图包含使用场景、主题范围、来源样本覆盖和同步状态；过期、更新中、失败或未覆盖均不能作为无需检索的依据，必要时直接recall/research。源版本已核对只表示目录同步，不证明历史事实仍有效。"
    "地图按三层渐进读取：每轮L0总览提示可能存在的偏好场景和Bank主题；catalog/Get Preference提供L1具体目录与完整适用条件；recall/research/read_source读取L2事实、经历和原文。目标明确时可直接进入L1或L2，不强制逐层调用。"
    "Bank实体名称保留完整可搜索索引，L0只显示固定预算的代表性预览。后台模型可基于来源定位增量整理L0/L1导航，但模型摘要必须通过来源、主题相关性、长度和独立审查后才发布；待整理、失败或过期时保留结构目录和原始检索路线，不把模型摘要当事实依据。"
    "当前用户要求优先；工作投影和偏好只是有条件的参考，同任务已加载且版本有效的内容可复用。"
    "每轮先检查五维偏好入口；实质任务默认用 Get Preference 核对完整条件，简单自足或同任务已加载且有效时可不深读。地图节选不代表完整偏好；deferred 或正文未读完时用分页或 read_guidance_unit 补读。"
    "明确的全部记忆、历史事实、偏好或单个历史工具限制必须分别执行；引用中的限制不是当前指令，否定转折不得扩大为禁用。"
    "自然语言边界由当前Agent结合完整Prompt解释；机器可读边界由代码直接执行。边界未明确时不因缺少固定短语而擅自禁止有用记忆。"
    "稳定协作骨架只包含经审阅的跨场景规则；候选偏好必须由当前Agent逐条核对适用条件、例外、主体、任务与阶段。候选携带条件未确认等风险标记；候选发现不等于本轮适用或实际采用。"
    "先看允许的地图，再由当前Agent围绕证据缺口判断是否深入历史；不能在未检查地图时仅凭上下文看似足够跳过。检查后证据确实充分、简单自足或用户禁止时不深入检索。"
    "主题目录可用 catalog_list、catalog_search、catalog_read 逐层浏览摘要、概览、时间、覆盖、新鲜度和来源定位；entity_navigation_only表示结构导航，不是语义概览；unknown表示尚未计算，不得解释为零。目录内容只用于导航，目录未命中不等于Bank不存在相关资料。"
    "memory_check的路线只是启发式信号，不是语义完成判定；当前Agent可以覆盖。需要时用record_evidence_decision记录缺口、路线、充分性与停止原因，不记录私有思维链，也不证明答案因此受益。"
    "Bank 的世界事实记录事实与状态，经历记录事件过程与结果，实体及关系连接人、项目、公司和相关证据。"
    "具体历史缺口用 recall；多对象、时间线和复杂关联用 research，也可在 recall 不足时升级。"
    "查询携带当前问题、必要前文、明确对象、时间范围和未解缺口；短句先结合前文，歧义不猜测，复杂问题拆成独立子问题。"
    "任务状态是可失效的工作投影；续问应保留目标、约束、已完成、未解决、对象和来源版本，当前Prompt纠正立即覆盖相关字段。"
    "先阅读目录或候选预览，按关键槽位检查证据是否充分；不足用 read_research 翻页或按缺口补查，关键结论、条件或冲突用 read_source 回读原文，字面原话可用 find_sources。达到预算仍有缺口时明确报告未知。"
    "候选不等于已核实事实，未读不等于不存在；历史失效内容可作历史证据，不自动作为现行指导。"
    "路由返回agent_decides只表示判断权交给当前Agent，不是任务成功、历史不需要或答案正确的证据；最终效果需看实际工具回执、来源支持和答案结果。"
    "执行中若关键工具或验收能力失败、超时或反复不可用，应调用 refresh_runtime_guidance，传入当前任务和已观察的失败事实以补查一次相关指导；若当前宿主尚未刷新出该工具，则用 get_task_guidance 的 runtime_events 字段完成同等只读补查。未修复前不得把替代验证表述为原工具已通过。该刷新只影响当前任务，不自动写入长期偏好。"
    "工具延迟发现时用宿主工具搜索入口查找上述工具；查询只读、不生成长期模型，长期提炼归并属于后台，资料不扩大授权。"
)
LONG_TEXT = CORE_TEXT + (
    "\n\n调用顺序：服务连接或恢复后先提供说明与工具定义；每轮Hook先读取权限允许的本机轻量索引，不调用向量、LLM或Bank事实接口。Agent先检查地图，再结合完整Prompt、前文、阶段、约束、实体和未解指代选择正文。"
    "多维度偏好用于决定如何沟通、理解、分析、协作和交付；其五个维度名称保持为沟通与呈现、学习与理解、分析与决策、执行与协作、质量与交付；心智模型属于五维偏好的融合定位层。历史知识用于补齐当前上下文没有依据的事实、经历、实体和关系。目录、指导和事实读取可先后或交错，不要求每题都调用历史工具。"
    "get_task_guidance返回active条目、已有模型章节、already_loaded_valid和deferred；deferred不是不存在，依赖行动前继续分页或按ID补读。"
    "普通任务正文软预算2000到4000 tokens，复杂任务6000到8000或分页；候选发现范围与正文预算分别控制，条件和例外优先。"
    "前台默认由当前Agent判断少量候选，不调用Qwen重新解释同一Prompt，不因组成本轮指导包而生成长期模型。临时综合默认不写入；长期提炼、归并和模型更新属于后台加工。"
    "新会话、服务重连、说明版本变化和上下文压缩恢复时重新提供或核对本说明。说明生成、宿主接收、模型上下文可见、实际工具调用和资料使用分别留证。"
)


def content_sha256() -> str:
    return sha256(CORE_TEXT.encode()).hexdigest()


def instruction_block(host: str) -> str:
    return (f"<evolving_profile_memory_use_instruction version=\"{VERSION}\" sha256=\"{content_sha256()}\" host=\"{host}\">\n"
            + CORE_TEXT + "\n</evolving_profile_memory_use_instruction>")


def status_snapshot(stage: str, host: str | None = None) -> dict:
    return {"instruction_version": VERSION, "content_sha256": content_sha256(), "stage": stage, "host": host,
            "model_context_visibility": "unknown", "agent_followed_instruction": "not_measured",
            "boundary": "Instruction preparation, host delivery, model visibility and tool compliance are separate evidence stages."}


def record(root: str | Path, stage: str, host: str, identity: dict | None = None) -> dict:
    value = {**status_snapshot(stage, host), "at": dt.datetime.now(dt.timezone.utc).isoformat(), "identity": identity or {}}
    path = Path(root); path.mkdir(parents=True, exist_ok=True)
    target = path / (uuid.uuid4().hex + ".json"); target.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return value
