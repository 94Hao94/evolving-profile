"""Deterministic recall governance for volatile local state and identity corrections."""

from __future__ import annotations

import json
import hashlib
import os
import re
import socket
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib


HOME = Path.home()
HOOKS_PATH = HOME / ".codex" / "hooks.json"
CODEX_CONFIG_PATH = HOME / ".codex" / "config.toml"
HINDSIGHT_PROFILE_ENV_PATH = HOME / ".evolving-profile" / "profiles" / "agentmemory.env"
HINDSIGHT_BACKUP_SCRIPT_PATH = HOME / ".evolving-profile" / "bin" / "hindsight-backup.zsh"

LIB_ROOT = Path(__file__).resolve().parent
if str(LIB_ROOT) not in sys.path:
    sys.path.insert(0, str(LIB_ROOT))

try:
    from .input_origin import user_surface_text as _user_surface_text
except ImportError:
    from input_origin import user_surface_text as _user_surface_text

_CURRENT_MARKERS = ("现在", "当前", "目前", "这一刻", "本机", "实时", "实际")
_RUNTIME_MARKERS = (
    "hindsight",
    "agentmemory",
    "记忆",
    "钩子",
    "hook",
    "mcp",
    "写入",
    "配置",
    "运行",
    "开启",
    "停用",
)
# A platform name plus the vague word “实际” is not enough to claim that the
# user asks for the live configuration.  It often occurs in explanatory or
# architectural questions (for example, why AgentMemory remains as a name but
# is not an independent memory system).  Source-first mode is reserved for a
# proposition that can actually be answered from a local runtime source.
_RUNTIME_STATE_MARKERS = (
    "状态", "端口", "监听", "enabled", "disabled", "配置", "路径", "版本",
    "服务", "进程", "是否接入", "有没有接入", "启用", "停用", "运行", "hook", "mcp",
    "钩子", "写入策略", "并发", "限流",
)
# A question can require both durable Bank history and a live version
# arbitration.  The historical-scope guard below must not suppress the live
# authority in that mixed case: otherwise an older memory saying
# ``Controller 1.37.0`` can sit beside a running ``1.45.22`` service with no
# deterministic source-first anchor.  Keep this detector narrow so ordinary
# architecture explanations still use Bank evidence only.
_CURRENT_VERSION_QUERY_MARKERS = (
    "版本", "版本号", "采用哪个", "当前采用", "现行版本", "生产版本", "运行版本",
    "架构版本", "当前架构", "正式采用", "实际采用",
)
# A timeline/evolution question often contains “关键版本” and “当前状态”
# together.  That is not a live-only version lookup: it asks for the dated
# history as well as the present boundary.  Only an explicit selection of the
# live version may enable the mixed current-version route.  Keeping this
# distinction here (rather than in the Hook) makes the same decision hold for
# plan probes, foreground recalls and continuations.
_EXPLICIT_CURRENT_VERSION_SELECTION_MARKERS = (
    "采用哪个版本", "当前采用哪个版本", "现行版本", "生产版本", "运行版本",
    "正式采用的版本", "实际采用的版本", "当前版本号", "当前版本是", "当前版本为",
    "现在用的版本", "现在采用的版本",
)
_EVOLUTION_SCOPE_MARKERS = (
    "官方下载安装到", "官方安装到", "从官方到", "从安装到", "架构经历",
    "阶段变化", "阶段演进", "阶段变迁", "架构演进", "架构演变", "架构变迁",
    "历史过程", "时间线", "关键版本", "转折", "失败边界", "演进", "演变", "变迁",
)
# ``现在`` + a generic word such as ``运行`` or ``配置`` is not enough to
# establish that the user is asking about this local Hindsight runtime.  A
# real hardware question (“GB10 能否运行、需要什么配置”) previously met all
# three broad marker sets and was therefore forced into source-first, where an
# unrelated local-runtime configuration row crossed the Hook boundary.  Keep
# this domain gate explicit and narrow: other current-state families (backup,
# Coding Plan, WPS, identity and operational timelines) have their own
# recognizers and must not inherit this local Hindsight authority by accident.
_RUNTIME_DOMAIN_MARKERS = (
    "hindsight", "agentmemory", "记忆", "钩子", "hook", "mcp", "controller",
    "memorypacket", "memory packet", "retain", "reflect", "consolidation",
)
_RUNTIME_EXPLANATION_MARKERS = (
    "为什么", "原因", "作为名字", "名字保留", "独立记忆系统", "有什么区别", "原理",
    # A request can mention “现在” and “Hook” while asking for a historical
    # architecture comparison.  That needs Bank evidence, not a one-row live
    # runtime snapshot.  Keep this semantic family broad instead of hardcoding
    # one product name or one phrasing.
    "比较", "变化", "演变", "演进", "架构", "阶段", "升级", "前后", "还缺", "未完成",
    "分别", "关系", "正式路径", "职责", "角色", "构成",
    # These words often mention Hook but ask for the durable acceptance model,
    # not a local process fact.  Routing them to local-runtime-only erases the
    # very observations and evidence standards needed to answer correctly.
    "验收", "端到端", "投递", "模型实际可用", "脚本测试", "测试通过",
)
# A multi-component causal/diagnostic question is durable architecture
# evidence, even when the wording contains ``实际``/``当前``.  It cannot be
# answered by one volatile local-runtime row: the answer must connect the
# historical contracts between the Hook, Controller, Bank, Packet and the
# owner-facing receipt.  Keep this detector structural (component count plus a
# relation/failure predicate), rather than a Q7/project allow-list, so new
# component names can use the same boundary without making ordinary health
# checks broad recalls.
_ARCHITECTURE_COMPONENT_MARKERS = (
    "hindsight", "agentmemory", "codexhook", "hook", "controller", "bank",
    "memorypacket", "packet", "9998", "状态页", "fullprompt", "mcp",
)
_ARCHITECTURE_RELATION_MARKERS = (
    "因果链", "链路", "关系", "上下游", "负责什么", "作用", "职责", "角色",
    "哪个组件", "组件出问题", "出问题", "造成", "导致", "实际注入", "候选很多",
    "候选", "投递", "回执", "边界", "区别", "如何连接",
)
_EXPLICIT_CURRENT_ONLY_MARKERS = (
    "只给当前", "仅给当前", "当前有效", "当前生效",
    "排除旧版", "不要旧版", "不看旧版", "以实时配置为准",
)
_HISTORY_MARKERS = ("官方原版", "官方文档", "历史", "当时", "以前", "最开始", "初版")
# A historical task can still contain words such as “当前/状态/配置” because
# the user is asking what must be checked *now* while reconstructing an older
# task.  Those words must not turn the whole request into a live-authority
# lookup.  Keep this recognizer explicit and semantic: it requires a durable
# history scope (usually “长期记忆/之前/迁移/接管”) plus a request to recover
# facts, evidence or rollback, rather than blacklisting a product name.
_LONG_TERM_SCOPE_MARKERS = (
    "长期记忆", "跨任务", "跨会话", "之前", "此前", "曾经", "历史任务",
    "迁移任务", "文件夹迁移", "接管", "交接", "回退", "回滚",
)
_HISTORICAL_RECOVERY_MARKERS = (
    "已完成事实", "完成了什么", "做了什么", "具体迁移", "迁移了什么",
    "当前接管", "核对哪些", "验证", "回退要求", "回滚要求", "遗留",
    "未完成", "待验证", "计划", "过程", "结果", "收尾",
)
_ZERO_INJECTION_DIAGNOSTIC_MARKERS = (
    "注入0", "注入为0", "注入是0", "候选很多但实际", "一个该召回的都没有",
    "该召回的都没有", "注入都是0", "注入全是0", "记忆注入为0",
)
# Version-retention questions are durable evidence questions even when they do
# not literally say “历史”.  They compare multiple points in a lifecycle and
# ask which old/failed/rollback state must remain distinguishable.  If we let
# the generic ``实际`` + ``版本`` runtime recognizer win here, Hook sends an
# authority-only header and the Controller legitimately performs zero Bank
# queries, which hides the very historical examples the question requests.
_VERSION_RETENTION_MARKERS = (
    "不同时间版本", "不同版本", "旧版本", "失败版本", "回退版本", "回滚版本",
    "版本不能简单去重", "版本不能去重", "简单去重", "保留旧版本", "保留失败版本",
    "保留回退版本", "版本沿革", "版本演进", "版本历史",
)
_VERSION_RETENTION_EVIDENCE_MARKERS = (
    "保留", "去重", "回退", "回滚", "失败", "召回", "注入", "hindsight",
    "历史", "证据", "实际场景", "什么时候",
)
# A source-first phrase can describe either a genuinely live-only lookup or a
# durable question about how to arbitrate new and old evidence.  The latter
# must still search Bank: otherwise words such as “当前来源/状态已更新” make
# the Hook return a one-row authority snapshot and silently drop the historical
# conflict rules the user explicitly asked us to explain.  Keep this detector
# structural (multiple conflict markers + a memory/retention anchor + an
# explanatory/ordering cue), rather than adding a question-specific whitelist.
_SOURCE_CONFLICT_MARKERS = (
    "source-first", "sourcefirst", "supersession", "相反结论", "新旧冲突",
    "冲突", "仲裁", "旧记忆", "旧版本", "被替代", "替代", "权威来源",
)
_SOURCE_CONFLICT_MEMORY_ANCHORS = (
    "hindsight", "记忆", "bank", "长期", "召回", "检索", "心智模型",
)
_SOURCE_CONFLICT_EXPLANATION_CUES = (
    "如何", "怎么", "为什么", "应如何", "正确顺序", "说明", "解释", "处理",
)
_LEGACY_RUNTIME_PATTERNS = (
    re.compile(r"通过三个\s*(?:hooks?|钩子)", re.IGNORECASE),
    re.compile(r"只使用\s*SessionStart[\s\S]*UserPromptSubmit[\s\S]*Stop", re.IGNORECASE),
    re.compile(r"三个\s*Python\s*(?:hooks?|钩子)", re.IGNORECASE),
    re.compile(r"每(?:累计)?\s*(?:10|十)\s*轮(?:分批)?写入", re.IGNORECASE),
    re.compile(r"当前\s*Codex\s*尚未接入\s*Hindsight\s*MCP", re.IGNORECASE),
    re.compile(r"Hindsight\s*尚未安装", re.IGNORECASE),
    re.compile(r"AgentMemory[\s\S]*(?:worker|watchdog)[\s\S]*(?:正在运行|running)", re.IGNORECASE),
    re.compile(r"不再把\s*12[,.]?000\s*tokens?\s*当作硬指标", re.IGNORECASE),
)
# A dated memory can truthfully contain the word "当前" from the day it was
# written.  For an explicitly live-only query, volatile configuration claims
# from semantic memory must therefore yield to local executable/configuration
# authority.  Durable explanations remain eligible.
_VOLATILE_RUNTIME_CLAIM_PATTERNS = (
    re.compile(r"(?:当前|本机|实际).{0,80}(?:mcp|bank|hooks?|端口|监听|plugin|进程|服务).{0,100}(?:enabled|disabled|启用|停用|关闭|接入|运行|未运行|为|=)", re.I | re.S),
    re.compile(r"(?:mcp|bank|hooks?|端口|监听|plugin).{0,80}(?:enabled\s*=|disabled\s*=|当前|现在|本机|未启用|已启用|未接入|已接入)", re.I | re.S),
)
_CORRECTION_MARKERS = ("语音识别", "错字", "错误", "不是用户姓名", "不是姓名", "纠正", "作废")
_CODING_PLAN_MARKERS = (
    "codingplan",
    "coding plan",
    "阿里百炼",
    "百炼",
    "qwen3.7-plus",
    "3211",
)
_CODING_PLAN_LIMIT_MARKERS = (
    "并发",
    "串行",
    "限流",
    "429",
    "consolidation",
    "retain",
    "reflect",
    "maxconcurrency",
    "几路",
    "三类模型任务",
)
_BACKUP_RUNTIME_MARKERS = (
    "hindsight", "备份", "恢复", "wps", "加密", "密钥", "keychain", "钥匙串",
)
_WPS_SYNC_MARKERS = ("wps", "同步", "云盘", "云同步", "同步文件夹")
_SUPERSEDED_CODING_PLAN_PATTERNS = (
    re.compile(r"全局最大模型并发(?:数)?(?:为|=)?\s*1", re.IGNORECASE),
    re.compile(r"全局并发(?:数)?(?:为|=)?\s*1", re.IGNORECASE),
    re.compile(r"全机(?:稳态)?最多并发\s*2", re.IGNORECASE),
    re.compile(r"全机硬上限(?:为|=)?\s*2", re.IGNORECASE),
    re.compile(r"全机最大并发数(?:为|配置为|=)?\s*2", re.IGNORECASE),
    re.compile(r"全机严格串行", re.IGNORECASE),
    re.compile(r"coding\s*plan.{0,100}(?:严格串行|全局串行|全机串行)", re.IGNORECASE | re.DOTALL),
    re.compile(r"consolidation\s*子批[\s\S]*最多并发数(?:为|=)?\s*2", re.IGNORECASE),
    # Current production values are Retain=4 and Consolidation=1.  Historical
    # memories used both Retain=1 and Consolidation=4; filter those records as
    # a whole for current-state questions so they cannot sit beside the live
    # authority snapshot and force the downstream model to guess which wins.
    re.compile(r"retain.{0,40}(?:为|=|保持|最多)?\s*1(?:路|个)?\s*并发", re.IGNORECASE),
    re.compile(r"consolidation.{0,50}(?:为|=|保持|最多|上限)?\s*4(?:路|个)?\s*并发", re.IGNORECASE),
    re.compile(r"consolidation.{0,60}(?:batch|批(?:次|处理)?).{0,30}(?:为|=)?\s*128\b", re.IGNORECASE),
)

_AUTO_CONTEXT_TAGS = (
    "recommended_plugins",
    "environment_context",
    "evolving_profile_checkpoint",
    "evolving_profile_midtask_journal",
    "heartbeat",
    "in-app-browser-context",
    "response-annotations",
    "app-context",
)


def _sanitize_user_text(value: str) -> str:
    """Remove app-supplied context before creating semantic authority records.

    Codex can place environment, plugin and checkpoint blocks next to the real
    user request.  Those blocks are useful to the runtime but are never user
    claims and must not enter the deterministic timeline/directive ledgers.
    """
    text = str(value or "")
    for tag in _AUTO_CONTEXT_TAGS:
        text = re.sub(
            rf"<{re.escape(tag)}\b[^>]*>.*?</{re.escape(tag)}\s*>",
            " ",
            text,
            flags=re.I | re.S,
        )
    if "## My request" in text:
        text = text.rsplit("## My request", 1)[-1]
    return re.sub(r"\s+", " ", text).strip()


def _timeline_state_path(config: dict) -> Path:
    return Path(
        os.path.expanduser(
            config.get(
                "operationalTimelineStatePath",
                "~/.evolving-profile/codex/state/operational-timeline.json",
            )
        )
    )


def _timeline_state_events(config: dict) -> list[dict]:
    """Merge provisional state with verified action evidence.

    The action ledger is append-only and only receives entries after local
    evidence paths were verified.  These entries remain historical for timeline
    questions; for a current-state question the existing selector chooses the
    latest verified value for the same entity and field.
    """
    events = []
    path = _timeline_state_path(config)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            events.extend(payload.get("events", []))
    except (OSError, ValueError):
        pass
    action_path = Path(os.path.expanduser(config.get(
        "verifiedActionLedgerPath", "~/.evolving-profile/control-plane/verified-actions.jsonl"
    )))
    try:
        with action_path.open(encoding="utf-8") as handle:
            for raw in handle:
                try:
                    item = json.loads(raw)
                except ValueError:
                    continue
                if item.get("kind") != "action_result" or item.get("status") != "verified":
                    continue
                events.append({
                    "id": item.get("id"), "entity": item.get("entity"),
                    "field": item.get("field"), "aliases": item.get("aliases") or [],
                    "status": "verified", "effectiveAt": item.get("effectiveAt") or item.get("valid_from"),
                    "valid_to": item.get("valid_to"), "supersedes": item.get("supersedes") or [],
                    "text": item.get("text"),
                    "supersededPatterns": item.get("superseded_patterns") or [],
                })
    except OSError:
        pass
    return [event for event in events if isinstance(event, dict)]


def record_provisional_timeline_events(messages: list[dict], config: dict) -> int:
    """Durably record a user correction before the 12k semantic batch runs.

    A provisional event is deliberately not a new truth claim. It blocks stale
    current-state answers until a live service/configuration check promotes it
    to ``verified``. Watches are explicit, so ordinary conversation cannot
    silently create operational state.
    """
    watches = config.get("operationalTimelineWatches") or []
    user_texts = [
        _sanitize_user_text(row.get("content") or "")
        for row in messages or []
        if str(row.get("role") or "") == "user"
    ]
    user_texts = [text for text in user_texts if text]
    if not user_texts or not watches:
        return 0
    additions = []
    for watch in watches:
        if not isinstance(watch, dict):
            continue
        aliases = [str(value) for value in watch.get("aliases") or []]
        patterns = [str(value) for value in watch.get("provisionalPatterns") or []]
        matching_texts = [
            text for text in user_texts
            if any(_compact(alias) in _compact(text) for alias in aliases)
            and any(re.search(pattern, text, re.I | re.S) for pattern in patterns)
        ]
        if not aliases or not patterns or not matching_texts:
            continue
        excerpt = matching_texts[-1][:500]
        signature = f"{watch.get('entity')}|{watch.get('field')}|{excerpt}"
        additions.append(
            {
                "id": hashlib.sha256(signature.encode("utf-8")).hexdigest()[:24],
                "entity": watch.get("entity"),
                "aliases": aliases,
                "field": watch.get("field"),
                "status": "provisional",
                "effectiveAt": datetime.now(timezone.utc).isoformat(),
                "text": (
                    f"待核验的用户更正涉及“{watch.get('entity')} / {watch.get('field')}”：{excerpt}。"
                    "此条尚未写成长期事实；涉及当前状态时，禁止引用旧状态下结论，必须先核验实时服务或配置。"
                ),
            }
        )
    if not additions:
        return 0
    path = _timeline_state_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _timeline_state_events(config)
    known = {str(event.get("id")) for event in existing if isinstance(event, dict)}
    additions = [event for event in additions if event["id"] not in known]
    if not additions:
        return 0
    payload = {"version": 1, "events": existing + additions}
    descriptor, temporary = tempfile.mkstemp(prefix=f"{path.name}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return len(additions)


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _context_implies_hindsight_runtime(contextual_intent: dict | None) -> bool:
    """Recover a lost runtime domain from the adapter's bounded intent receipt.

    The agent may resolve a terse turn such as ``当前采用哪个版本`` into a
    Full Prompt that omits the product name.  We must not make every generic
    version question inject this machine's Controller snapshot, so the
    fallback is intentionally restricted to a validated context-intent
    envelope that both used prior context and routes through Hindsight's
    distinctive Full Prompt/Claim Bundle system vocabulary.
    """
    if not isinstance(contextual_intent, dict):
        return False
    if contextual_intent.get("used_context") is not True:
        return False
    routing = contextual_intent.get("routing_hints") or {}
    forced = {str(value).casefold() for value in routing.get("force_shapes") or []}
    if not forced.intersection({"system_map", "synthesis", "current"}):
        return False
    try:
        payload = json.dumps(contextual_intent, ensure_ascii=False).casefold()
    except (TypeError, ValueError):
        return False
    # These anchors are deliberately paired.  A bare “系统/图谱” context is
    # too generic; Full Prompt or Claim Bundle identifies this memory runtime.
    return (
        ("full prompt" in payload or "fullprompt" in payload or "claim bundle" in payload or "claimbundle" in payload)
        and any(marker in payload for marker in ("hindsight", "当前版本", "最新运行状态", "记忆"))
    )


def is_current_version_query(query: str, contextual_intent: dict | None = None) -> bool:
    """Recognize a mixed current-version question without dropping Bank history.

    ``is_current_runtime_query`` intentionally rejects broad architecture and
    timeline prompts.  A prompt that explicitly asks *which version is live*
    is different: it needs the executable Controller authority *and* the
    historical evidence explaining what the older versions were.  This helper
    is deliberately marker-based and does not depend on a product allow-list.
    """
    normalized = _compact(query)
    runtime_domain = any(marker in normalized for marker in _RUNTIME_DOMAIN_MARKERS)
    if not runtime_domain:
        runtime_domain = _context_implies_hindsight_runtime(contextual_intent)
    explicit_selection = any(
        marker in normalized for marker in _EXPLICIT_CURRENT_VERSION_SELECTION_MARKERS
    )
    # A version-retention/rollback explanation mentions “实际/版本” but does
    # not select the live version.  Historical Bank evidence wins over the
    # generic current-version recognizer; an explicit “当前采用哪个版本” in a
    # mixed prompt remains eligible for the live authority prefix.
    if not explicit_selection and requires_historical_bank_recall(normalized):
        return False
    # “从官方下载安装到当前……关键版本/阶段变化” is a durable timeline
    # request.  Do not let the generic ``版本`` and ``当前状态`` words turn it
    # into the one-row local-runtime authority adapter.  A prompt that really
    # asks “当前采用哪个版本” remains on the mixed route above.
    if not explicit_selection and any(marker in normalized for marker in _EVOLUTION_SCOPE_MARKERS):
        return False
    return bool(
        any(marker in normalized for marker in _CURRENT_VERSION_QUERY_MARKERS)
        and any(marker in normalized for marker in _CURRENT_MARKERS)
        and runtime_domain
        and any(marker in normalized for marker in _RUNTIME_STATE_MARKERS)
    )


def _controller_health_snapshot() -> dict[str, str]:
    """Read the tiny live Controller health receipt for version arbitration."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:12079/health", timeout=0.45) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
        if not isinstance(payload, dict):
            return {}
        version = str(payload.get("version") or "").strip()
        status = str(payload.get("status") or "").strip()
        if not version:
            return {"status": status} if status else {}
        return {"version": version, "status": status or "unknown"}
    except (OSError, ValueError, TypeError):
        return {}


def is_current_runtime_query(query: str, contextual_intent: dict | None = None) -> bool:
    normalized = _compact(query)
    # Mixed current-version prompts still require durable Bank recall, but the
    # live Controller version must be present to arbitrate dated memories.
    if is_current_version_query(normalized, contextual_intent=contextual_intent):
        return True
    # “仅基于长期记忆” is an explicit provenance boundary.  It may mention
    # current status as one field to verify, but it does not authorize the
    # Hook's volatile local snapshot to replace the requested historical Bank
    # evidence.  This check runs before the broad runtime markers below so a
    # current-looking sub-question cannot short-circuit the durable recall.
    if requires_historical_bank_recall(normalized):
        return False
    runtime_domain = any(marker in normalized for marker in _RUNTIME_DOMAIN_MARKERS)
    explicit_current_only = any(marker in normalized for marker in _EXPLICIT_CURRENT_ONLY_MARKERS)
    # A request can explicitly ask for the *current* production fact while
    # asking us to label historical experiments and future plans separately.
    # Treating the mere word "历史" as a history-only request disabled the
    # runtime authority snapshot precisely when the caller was trying to avoid
    # that confusion.  This remains narrow: the current-production anchor and
    # an explicit distinction marker must both be present.
    current_vs_history_comparison = (
        any(marker in normalized for marker in ("当前生产", "当前运行", "当前正式", "现在生产"))
        and any(marker in normalized for marker in ("区分", "历史试验", "未来计划", "历史和未来"))
    )
    return (
        runtime_domain
        and
        any(marker in normalized for marker in _CURRENT_MARKERS)
        and any(marker in normalized for marker in _RUNTIME_MARKERS)
        and any(marker in normalized for marker in _RUNTIME_STATE_MARKERS)
        and (current_vs_history_comparison or not any(marker in normalized for marker in _HISTORY_MARKERS))
        and (
            explicit_current_only
            or not any(marker in normalized for marker in _RUNTIME_EXPLANATION_MARKERS)
        )
    )


def is_memory_architecture_chain_query(query: str) -> bool:
    """Recognize a durable multi-component architecture/chain question.

    ``当前`` or ``实际`` often appears while the user is asking why a
    cross-component chain produced an outcome.  Treating that wording as a
    live-source query loses the historical Bank evidence needed to explain the
    chain.  A plain health check names at most one or two components and has no
    causal predicate, so it remains eligible for the deterministic authority
    adapter.  Explicit current-only wording is an intentional exception.
    """
    normalized = _compact(query)
    if any(marker in normalized for marker in _EXPLICIT_CURRENT_ONLY_MARKERS):
        return False
    component_hits = {
        marker for marker in _ARCHITECTURE_COMPONENT_MARKERS if marker in normalized
    }
    relation_hits = {
        marker for marker in _ARCHITECTURE_RELATION_MARKERS if marker in normalized
    }
    return len(component_hits) >= 3 and bool(relation_hits)


def requires_historical_bank_recall(query: str) -> bool:
    """Whether the prompt explicitly requires durable historical evidence.

    This is intentionally narrower than a generic ``历史`` keyword.  It is
    used as a safety boundary for Hook source-first authority: a prompt that
    asks to reconstruct an older cross-task operation must still query Bank
    even when it also asks which *current* checks or rollback conditions apply.
    The function is deterministic and shared by Hook and Controller so a stale
    authority-only header cannot silently convert a history request into a
    zero-query live snapshot.
    """
    normalized = _compact(query)
    # Architecture chain/audit questions need the durable component contracts
    # even if they omit literal words such as “历史” or “之前”.  Without this
    # branch a prompt like “which component causes many candidates but zero
    # actual injection?” was misclassified as current runtime authority and
    # skipped every Bank facet.
    architecture_chain = is_memory_architecture_chain_query(normalized)
    source_conflict_explanation = is_source_conflict_explanation_query(normalized)
    evolution_scope = any(marker in normalized for marker in _EVOLUTION_SCOPE_MARKERS)
    long_term_scope = any(marker in normalized for marker in _LONG_TERM_SCOPE_MARKERS)
    recovery_request = any(marker in normalized for marker in _HISTORICAL_RECOVERY_MARKERS)
    retention_intent = re.sub(r'(?:排除|不要|不看|不含|忽略)旧版本?', '', normalized)
    version_retention_scope = (
        any(marker in retention_intent for marker in _VERSION_RETENTION_MARKERS)
        and any(marker in normalized for marker in _VERSION_RETENTION_EVIDENCE_MARKERS)
    )
    zero_injection_diagnostic = (
        any(marker in normalized for marker in _ZERO_INJECTION_DIAGNOSTIC_MARKERS)
        and any(marker in normalized for marker in ("记忆", "召回", "注入", "候选", "观察", "心智模型", "实体", "状态页", "hindsight"))
        and any(marker in normalized for marker in ("为什么", "不对", "问题", "没有", "都", "正常", "作用"))
    )
    explicit_long_term_only = any(
        marker in normalized
        for marker in ("仅基于长期记忆", "只基于长期记忆", "仅使用长期记忆", "只用长期记忆")
    )
    return bool(
        architecture_chain
        or source_conflict_explanation
        # An origin-to-present architecture/evolution request must retain
        # durable Bank history even when it asks for the current state.  This
        # prevents the live-authority shortcut from erasing the old stages and
        # failure evidence that the answer explicitly requests.
        or evolution_scope
        or version_retention_scope
        or zero_injection_diagnostic
        or (explicit_long_term_only and (long_term_scope or recovery_request))
        or (long_term_scope and recovery_request and any(marker in normalized for marker in ("hindsight", "codex", "任务", "项目", "文件夹", "迁移", "接管")))
    )


def is_source_conflict_explanation_query(query: str) -> bool:
    """Recognize durable arbitration/explanation of current vs old evidence.

    ``source_first`` is a precedence rule, not a permission to skip Hindsight.
    A prompt that asks how to resolve a conflict needs the historical policy,
    supersession evidence and counterexamples from Bank.  Conversely, a
    current-only request remains live-authority-only through the explicit
    markers below, and an ordinary status check with no conflict structure does
    not become a broad historical recall.
    """
    normalized = _compact(query)
    if any(marker in normalized for marker in _EXPLICIT_CURRENT_ONLY_MARKERS):
        return False
    conflict_hits = {marker for marker in _SOURCE_CONFLICT_MARKERS if marker in normalized}
    memory_anchor = any(marker in normalized for marker in _SOURCE_CONFLICT_MEMORY_ANCHORS)
    explanation = any(marker in normalized for marker in _SOURCE_CONFLICT_EXPLANATION_CUES)
    # Require at least two distinct conflict/precedence cues.  This keeps a
    # plain “当前状态是什么” query on the fast authority path while admitting
    # variants such as “新来源和旧结论冲突时怎么处理” and English aliases.
    return bool(len(conflict_hits) >= 2 and memory_anchor and explanation)


def is_identity_query(query: str, config: dict | None = None) -> bool:
    normalized = _compact(query)
    if any(marker in normalized for marker in ("我的名字", "我叫什么", "姓名", "身份")):
        return True
    identity = (config or {}).get("authoritativeIdentity") or {}
    names = [identity.get("name"), *((identity.get("invalidAliases") or {}).keys())]
    return any(_compact(name) and _compact(name) in normalized for name in names)


def is_current_coding_plan_query(query: str) -> bool:
    normalized = _compact(query)
    return (
        any(marker in normalized for marker in _CODING_PLAN_MARKERS)
        and any(marker in normalized for marker in _CODING_PLAN_LIMIT_MARKERS)
        and not any(marker in normalized for marker in _HISTORY_MARKERS)
    )


def is_current_hindsight_limits_query(query: str) -> bool:
    """Recognize live Hindsight worker-limit questions without requiring the
    caller to know that Coding Plan owns the shared model queue."""
    normalized = _compact(query)
    return (
        "hindsight" in normalized
        and any(marker in normalized for marker in ("retain", "reflect", "consolidation"))
        and any(marker in normalized for marker in ("并发", "限制", "配置", "几路"))
        and any(marker in normalized for marker in _CURRENT_MARKERS)
        and not any(marker in normalized for marker in _HISTORY_MARKERS)
    )


def is_backup_runtime_query(query: str) -> bool:
    normalized = _compact(query)
    return (
        "备份" in normalized
        and any(marker in normalized for marker in _BACKUP_RUNTIME_MARKERS)
        and any(marker in normalized for marker in (
            "当前", "现在", "算法", "加密", "密钥", "钥匙串", "keychain", "保留", "多少套",
        ))
        and not any(marker in normalized for marker in (
            "规则", "约定", "历史", "演练", "方案", "为什么", "原理", "已确认", "流程",
        ))
    )


def _port_open(port: int, timeout: float = 0.08) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _load_hooks() -> list[str]:
    try:
        payload = json.loads(HOOKS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    hooks = payload.get("hooks") or {}
    preferred = ("SessionStart", "UserPromptSubmit", "PostToolUse", "PreCompact", "Stop")
    return [name for name in preferred if hooks.get(name)]


def _load_codex_config() -> dict:
    try:
        return tomllib.loads(CODEX_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _load_coding_plan_runtime() -> dict:
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:3211/__serial_proxy/status", timeout=0.25
        ) as response:
            payload = json.load(response)
    except (OSError, ValueError):
        payload = {}
    return {
        "max_concurrency": payload.get("maxConcurrency"),
        "active": payload.get("active"),
        "queued": payload.get("queued"),
        "rate_limits": payload.get("rateLimits"),
    }


def _load_hindsight_runtime_limits() -> dict:
    wanted = {
        "EVOLVING_PROFILE_API_LLM_MAX_CONCURRENT": "global",
        "EVOLVING_PROFILE_API_RETAIN_LLM_MAX_CONCURRENT": "retain",
        "EVOLVING_PROFILE_API_REFLECT_LLM_MAX_CONCURRENT": "reflect",
        "EVOLVING_PROFILE_API_CONSOLIDATION_LLM_MAX_CONCURRENT": "consolidation",
        "EVOLVING_PROFILE_API_CONSOLIDATION_LLM_PARALLELISM": "consolidation_parallelism",
    }
    values = {}
    try:
        lines = HINDSIGHT_PROFILE_ENV_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        if key.strip() in wanted:
            values[wanted[key.strip()]] = value.strip().strip('"\'')
    return values


def coding_plan_authority_result() -> dict:
    status = _load_coding_plan_runtime()
    limits = _load_hindsight_runtime_limits()
    maximum = status.get("max_concurrency")
    rendered_maximum = maximum if maximum is not None else "unavailable"
    text = (
        "Coding Plan 实时权威状态（从本机 127.0.0.1:3211 代理读取）："
        f"maxConcurrency={rendered_maximum}，"
        f"active={status.get('active', 'unavailable')}，"
        f"queued={status.get('queued', 'unavailable')}，"
        f"rateLimits={status.get('rate_limits', 'unavailable')}。"
        f"Hindsight 模型任务实时限制：retain {limits.get('retain', 'unavailable')}，"
        f"reflect {limits.get('reflect', 'unavailable')}，"
        f"consolidation {limits.get('consolidation', 'unavailable')}，"
        f"consolidation 内部 parallelism {limits.get('consolidation_parallelism', 'unavailable')}。"
        "当前并发问题以此实时状态和较新的实测结论为准；过期并发结论"
        "只能作为历史时间线，不得覆盖当前配置。"
    )
    return {
        "text": text,
        "type": "world",
        "mentioned_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "source": "coding-plan-runtime-authority",
            "volatile": True,
            "admission_class": "deterministic_runtime_authority",
        },
    }


def backup_authority_result() -> dict:
    """Read non-secret backup policy from the executable backup script."""
    try:
        script = HINDSIGHT_BACKUP_SCRIPT_PATH.read_text(encoding="utf-8")
    except OSError:
        script = ""

    def extract(pattern: str, default: str) -> str:
        match = re.search(pattern, script, re.I | re.M)
        return match.group(1) if match else default

    keep = extract(r"^CLOUD_KEEP_SETS=(\d+)", "unavailable")
    service = extract(r'^KEYCHAIN_SERVICE="([^"]+)"', "unavailable")
    iterations = extract(r"-iter\s+(\d+)", "unavailable")
    text = (
        "Hindsight 当前备份策略（从可执行脚本 ~/.evolving-profile/bin/hindsight-backup.zsh 读取）："
        "云端全量与配置归档使用 AES-256-CBC，密钥派生使用 PBKDF2-HMAC-SHA256，"
        f"迭代 {iterations} 次；恢复密钥由 macOS 钥匙串 Keychain 服务 {service} 保存；"
        f"WPS 云端只保留最近 {keep} 套完整备份。此记录不包含密钥正文。"
    )
    return {
        "text": text,
        "type": "world",
        "mentioned_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "source": "backup-runtime-authority",
            "volatile": True,
            "admission_class": "deterministic_runtime_authority",
        },
    }


def runtime_authority_result(config: dict) -> dict:
    codex = _load_codex_config()
    mcp = codex.get("mcp_servers") or {}
    plugins = codex.get("plugins") or {}
    hooks = _load_hooks()
    # The raw upstream Hindsight MCP remains intentionally absent.  Codex uses
    # only the read-only facade, which is governed by Query Controller first.
    raw_hindsight_mcp_enabled = bool((mcp.get("hindsight") or {}).get("enabled"))
    controller_mcp = mcp.get("evolving_profile_controller", mcp.get("hindsight-controller", {}))
    controller_mcp_enabled = bool(controller_mcp) and controller_mcp.get("enabled", True) is not False
    agentmemory_mcp_enabled = bool((mcp.get("agentmemory") or {}).get("enabled"))
    agentmemory_plugin_enabled = bool(
        (plugins.get("agentmemory@agentmemory") or {}).get("enabled")
    )
    threshold = int(config.get("retainTokenThreshold") or 12000)
    mode = config.get("retainMode") or "unknown"
    tool_calls = bool(config.get("retainToolCalls"))
    bank = config.get("bankId") or "unknown"
    port_state = "open" if _port_open(3111) else "closed"
    controller_health = _controller_health_snapshot()
    controller_version = controller_health.get("version") or "unknown"
    controller_status = controller_health.get("status") or "unavailable"
    text = (
        "当前本机实时配置（从 ~/.codex/hooks.json、~/.codex/config.toml 和 "
        "~/.evolving-profile/codex.json 读取）："
        f"Query Controller live health version={controller_version}, status={controller_status}（127.0.0.1:12079/health）；"
        f"原始 Hindsight MCP configured={str(raw_hindsight_mcp_enabled).lower()}；"
        f"Evolving Profile Controller MCP enabled={str(controller_mcp_enabled).lower()}（配置启用状态；宿主工具连接须另核），bank={bank}；"
        f"Hooks={','.join(hooks) or 'none'}；"
        f"写入模式={mode}，retainTokenThreshold={threshold}，"
        f"retainToolCalls={str(tool_calls).lower()}；"
        f"AgentMemory MCP enabled={str(agentmemory_mcp_enabled).lower()}，"
        f"plugin enabled={str(agentmemory_plugin_enabled).lower()}，port3111={port_state}。"
        "这是当前运行状态的权威来源；历史配置只能作为时间线，不能覆盖此状态。"
    )
    return {
        "text": text,
        "type": "world",
        "mentioned_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "source": "local-runtime-authority",
            "volatile": True,
            "verification_status": "verified" if controller_health.get("version") else "unresolved",
            "controller_version": controller_health.get("version"),
            "admission_class": "deterministic_runtime_authority",
        },
    }


def identity_authority_result(config: dict) -> dict | None:
    identity = config.get("authoritativeIdentity") or {}
    name = str(identity.get("name") or "").strip()
    aliases = identity.get("invalidAliases") or {}
    if not name:
        return None
    alias_text = "；".join(f"“{alias}”{reason}" for alias, reason in aliases.items())
    text = f"用户明确确认的姓名是{name}。"
    if alias_text:
        text += f"{alias_text}。这些错误别名不得建立身份关联。"
    return {
        "text": text,
        "type": "world",
        "mentioned_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {"source": "identity-authority", "curated": True},
    }


def role_route_authority_results(query: str, config: dict) -> list[dict]:
    """Inject explicitly curated role-routing facts before archive retrieval.

    Role migrations are operational facts, not soft preferences.  A retired
    OpenClaw stanza can remain for scheduling compatibility after its direct
    transport has become authoritative, so semantic recall alone must never
    decide the live routing path.
    """
    normalized = _compact(_user_surface_text(query))
    # Role names in lesson context do not make service-routing facts relevant.
    # The default lane is for explicit operational questions, not all role use.
    operational_cues=('路由','入口','服务','配置','链路','迁移','故障','调用','接入','注入','openclaw','mcp','hook','routing','gateway','deployment','service')
    if not any(cue in normalized for cue in operational_cues):
        return []
    results = []
    for role, route in (config.get("authoritativeRoleRoutes") or {}).items():
        if not isinstance(route, dict):
            continue
        aliases = [str(value) for value in route.get("aliases") or [role]]
        if not any(_compact(alias) and _compact(alias) in normalized for alias in aliases):
            continue
        text = str(route.get("text") or "").strip()
        if not text:
            continue
        results.append(
            {
                "text": text,
                "type": "world",
                "mentioned_at": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "source": "role-routing-authority",
                    "role": role,
                    "curated": True,
                },
            }
        )
    return results


def entity_boundary_authority_results(query: str, config: dict) -> list[dict]:
    """Inject configured non-alias boundaries when multiple entities co-occur.

    Vector recall can be crowded by documents that merely list two companies.
    A versioned distinct-entity boundary is deterministic identity governance,
    not a semantic ranking preference, so it belongs before archive results.
    """
    normalized = _compact(query)
    results = []
    policy = config.get("entityCanonicalization") or {}
    for boundary in policy.get("distinctEntities") or []:
        if not isinstance(boundary, dict):
            continue
        groups = boundary.get("entityGroups") or []
        matched = 0
        for group in groups:
            aliases = [str(item) for item in group or []]
            if any(_compact(alias) and _compact(alias) in normalized for alias in aliases):
                matched += 1
        text = str(boundary.get("text") or "").strip()
        if matched < 2 or not text:
            continue
        results.append({
            "text": text,
            "type": "world",
            "mentioned_at": str(boundary.get("verifiedAt") or datetime.now(timezone.utc).isoformat()),
            "metadata": {
                "source": "entity-boundary-authority",
                "boundary_id": boundary.get("id"),
                "curated": True,
            },
        })
    return results


def operational_timeline_authority_results(query: str, config: dict) -> list[dict]:
    """Return latest *effective* facts for operational entities mentioned in a query.

    Hindsight retrieval is intentionally relevance-first: that is right for
    broad biography and knowledge questions, but insufficient for a question
    such as "does trainer currently use OpenClaw?".  For the same entity and
    field, a verified later event supersedes an older one.  The older event is
    retained for historical questions; it is simply not injected as current
    state.

    This layer is deterministic and local.  It never calls an LLM and is kept
    deliberately narrow (service route, canonical name, active model and
    migration status), so it does not reduce normal Hindsight recall depth.
    """
    normalized = _compact(query)
    if any(marker in normalized for marker in _HISTORY_MARKERS):
        return []

    candidates: dict[tuple[str, str], dict] = {}
    for event in [*(config.get("operationalTimeline") or []), *_timeline_state_events(config)]:
        if not isinstance(event, dict) or event.get("status") not in {"verified", "provisional"}:
            continue
        entity = str(event.get("entity") or "").strip()
        field = str(event.get("field") or "").strip()
        aliases = [entity, *[str(item) for item in event.get("aliases") or []]]
        if not entity or not field or not any(_compact(alias) in normalized for alias in aliases if _compact(alias)):
            continue
        key = (entity, field)
        previous = candidates.get(key)
        event_rank = 1 if event.get("status") == "verified" else 0
        previous_rank = 1 if previous and previous.get("status") == "verified" else 0
        if (
            previous is None
            or event_rank > previous_rank
            or (
                event_rank == previous_rank
                and str(event.get("effectiveAt") or "") > str(previous.get("effectiveAt") or "")
            )
        ):
            candidates[key] = event

    results = []
    for event in candidates.values():
        text = str(event.get("text") or "").strip()
        if event.get("status") == "provisional":
            text = (
                f"检测到涉及“{event.get('entity')} / {event.get('field')}”的待核验更正；"
                "此条不是已确认事实，回答当前状态前须核验实时服务或配置。"
            )
        if not text:
            continue
        results.append(
            {
                "text": text,
                "type": "world",
                "mentioned_at": str(event.get("effectiveAt") or datetime.now(timezone.utc).isoformat()),
                "metadata": {
                    "source": "operational-timeline-authority",
                    "entity": event.get("entity"),
                    "field": event.get("field"),
                    "effective_at": event.get("effectiveAt"),
                    "verification_status": event.get("status"),
                    "superseded_patterns": event.get("supersededPatterns") or [],
                    "curated": True,
                },
            }
        )
    return results


def has_current_operational_authority(query: str, config: dict) -> bool:
    """Whether a current-state query can be answered from verified/provisional ledger state."""
    return bool(operational_timeline_authority_results(query, config))


def _has_invalid_uncorrected_alias(text: str, config: dict) -> bool:
    aliases = (config.get("authoritativeIdentity") or {}).get("invalidAliases") or {}
    for alias in aliases:
        if alias not in text:
            continue
        if any(marker in text for marker in _CORRECTION_MARKERS):
            continue
        return True
    return False


def apply_recall_governance(
    query: str,
    results: list[dict],
    config: dict,
    *,
    contextual_intent: dict | None = None,
    raw_user_prompt: str = "",
) -> list[dict]:
    """Filter superseded claims and prepend deterministic authority facts."""
    governed = []
    # Full Prompt is the retrieval text, while the optional bounded intent
    # receipt carries only the context-resolution boundary.  Use both for the
    # narrow current-version recognizer so a domain token omitted by an agent
    # model cannot hide the live authority.  Raw user wording is considered
    # only as a fallback marker; it never replaces Full Prompt semantics.
    runtime_query = is_current_runtime_query(
        query,
        contextual_intent=contextual_intent,
    ) or is_current_runtime_query(
        raw_user_prompt,
        contextual_intent=contextual_intent,
    )
    coding_plan_query = is_current_coding_plan_query(query) or is_current_hindsight_limits_query(query)
    backup_query = is_backup_runtime_query(query)
    wps_sync_query = is_wps_sync_current_query(query)
    for result in results or []:
        text = str(result.get("text") or "")
        source = str((result.get("metadata") or {}).get("source") or "")
        if source in {'semantic-directive-ledger','role-routing-authority'}:
            # Query-dependent local views must be regenerated below. A cached
            # prior response must not preserve a rule that no longer applies.
            continue
        if _has_invalid_uncorrected_alias(text, config):
            continue
        if runtime_query and any(pattern.search(text) for pattern in _LEGACY_RUNTIME_PATTERNS):
            continue
        if (
            runtime_query
            and not source.endswith("authority")
            and any(pattern.search(text) for pattern in _VOLATILE_RUNTIME_CLAIM_PATTERNS)
        ):
            continue
        if coding_plan_query and any(
            pattern.search(text) for pattern in _SUPERSEDED_CODING_PLAN_PATTERNS
        ):
            continue
        governed.append(result)

    prefix = []
    if coding_plan_query:
        prefix.append(coding_plan_authority_result())
    if runtime_query:
        prefix.append(runtime_authority_result(config))
    if backup_query:
        prefix.append(backup_authority_result())
    if wps_sync_query:
        prefix.append(wps_sync_authority_result())
    if is_memory_pipeline_explanation_query(query):
        prefix.append(memory_pipeline_authority_result())
    if is_no_fixed_item_cap_query(query):
        prefix.append(no_fixed_item_cap_authority_result(config))
    if is_continuation_policy_question(query):
        prefix.append(continuation_policy_authority_result())
    if is_unknown_attribute_policy_question(query):
        prefix.append(unknown_attribute_policy_authority_result())
    if is_smalltalk_memory_policy_question(query):
        prefix.append(smalltalk_memory_policy_authority_result())
    if is_local_edit_memory_policy_question(query):
        prefix.append(local_edit_memory_policy_authority_result())
    if is_identity_query(query, config):
        identity = identity_authority_result(config)
        if identity:
            prefix.append(identity)
    prefix.extend(entity_boundary_authority_results(query, config))
    # Generic event timeline takes precedence over legacy role-specific
    # compatibility entries.  The latter remains supported during migration.
    timeline_results = operational_timeline_authority_results(query, config)
    superseded_patterns = [
        re.compile(pattern, re.I | re.S)
        for item in timeline_results
        if (item.get("metadata") or {}).get("verification_status") == "verified"
        for pattern in (item.get("metadata") or {}).get("superseded_patterns") or []
    ]
    if superseded_patterns:
        governed = [
            result for result in governed
            if not any(pattern.search(str(result.get("text") or "")) for pattern in superseded_patterns)
        ]
    # A general verified system event and a role-routing fact can both apply.
    # Keep both: the former must not hide the latter merely because it matched
    # a broad term such as “Hindsight”.
    prefix.extend(timeline_results)
    prefix.extend(role_route_authority_results(query, config))
    prefix.extend(semantic_directive_authority_results(query, config))
    prefix.extend(semantic_dependency_contract_results(query, config))
    return prefix + governed


def is_wps_sync_current_query(query: str) -> bool:
    """Whether a user asks for the *present* WPS cloud-sync state.

    This is deliberately narrower than a historical WPS troubleshooting query.
    The authoritative answer is the visible WPS client/transfer record; local
    Hindsight facts remain background only and must not impersonate cloud state.
    """
    compact = _compact(query)
    historical_reference_is_excluded = any(
        marker in compact for marker in ("不是历史", "而不是历史", "不要历史", "不问历史")
    )
    policy_scope = compact
    if historical_reference_is_excluded:
        # Negated history language describes what the user is excluding, not
        # the requested answer scope.  Evaluating the raw word “历史” below
        # turned an explicit live-source request into a historical-policy
        # query and suppressed the volatile WPS authority snapshot.
        for marker in ("不是历史", "而不是历史", "不要历史", "不问历史"):
            policy_scope = policy_scope.replace(marker, "")
    # “WPS 云盘” can be the storage endpoint of a historical Hindsight backup
    # policy.  It is not itself a request for the *live* WPS sync state.  Do
    # not let the broad word “云端” short-circuit a question that explicitly
    # asks about retention rules, recovery drills, or provenance.
    historical_or_policy_question = any(
        marker in policy_scope for marker in (
            "备份", "规则", "约定", "历史", "演练", "方案", "为什么", "原理", "已确认", "流程",
        )
    )
    return (
        "wps" in compact
        and any(marker in compact for marker in ("同步", "云盘", "云同步", "同步文件夹"))
        and any(marker in compact for marker in _CURRENT_MARKERS + ("以什么来源为准", "最终", "云端"))
        and not historical_or_policy_question
        and (historical_reference_is_excluded or not any(marker in compact for marker in _HISTORY_MARKERS))
    )


def wps_sync_authority_result() -> dict:
    return {
        "text": (
            "当前 WPS 云同步状态的权威来源是 WPS 客户端中的同步文件夹、传输记录和云端文件列表的实时回读。"
            "本机 Hindsight 只能核对本地备份目录和最近备份回执，不能把历史教程或本地目录存在直接当作云端已同步。"
        ),
        "type": "world",
        "mentioned_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "source": "wps-sync-runtime-authority",
            "volatile": True,
            "admission_class": "deterministic_runtime_authority",
        },
    }


def is_memory_pipeline_explanation_query(query: str) -> bool:
    compact = _compact(query)
    stages = sum(term in compact for term in ("实际注入", "检索返回", "回答引用"))
    return stages >= 2 and any(marker in compact for marker in ("区别", "关系", "解释", "分别"))


def memory_pipeline_authority_result() -> dict:
    return {
        "text": (
            "Hindsight 链路口径：‘检索返回’是 Bank 找到的候选；‘实际注入’是候选经相关性、来源和上下文去重后，"
            "真正写入本轮 Agent 上下文的内容；‘回答引用’是 Agent 在最终回答中明确使用或说明使用了其中哪条。"
            "候选不等于注入，注入也不自动等于回答已引用；三者分别以检索轨迹、Hook 注入回执和回答闭环记录核对。"
        ),
        "type": "world",
        "mentioned_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {"source": "memory-pipeline-authority", "curated": True},
    }


def is_no_fixed_item_cap_query(query: str) -> bool:
    compact = _compact(query)
    return (
        any(marker in compact for marker in ("固定上限", "固定条数", "固定项数", "因为固定上限", "数量上限"))
        and any(marker in compact for marker in ("相关记忆", "召回", "注入", "截断", "候选"))
    )


def no_fixed_item_cap_authority_result(config: dict) -> dict:
    coordination = config.get("contextMemoryCoordination") or {}
    strategy = str(coordination.get("strategy") or "按逐条相关性准入和自适应 token 预算控制体积")
    return {
        "text": (
            "当前 Hindsight 对通过相关性准入的记忆不设固定条数上限；会按每条相关性、来源、关联闭包和动态 token 预算决定保留范围。"
            f"现行策略：{strategy}。因此应防止无关候选，而不是为了凑固定条数删掉相关链条。"
        ),
        "type": "world",
        "mentioned_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {"source": "no-fixed-item-cap-authority", "curated": True},
    }


def is_continuation_policy_question(query: str) -> bool:
    compact = _compact(query)
    return (
        "继续" in compact
        and any(marker in compact for marker in ("什么时候", "何时", "应激活", "项目状态", "长期记忆", "跨任务"))
    )


def continuation_policy_authority_result() -> dict:
    return {
        "text": (
            "‘继续’本身不自动打开长期记忆：若当前任务上下文已有明确对象和未完成项，先用项目状态继续；"
            "若它涉及跨任务、历史项目、已移交对象、来源/版本或当前上下文不足，才激活 Hindsight 补齐相关事实与关联闭包。"
            "这样既保留项目连续性，也避免把无关历史塞入当前任务。"
        ),
        "type": "world",
        "mentioned_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {"source": "continuation-policy-authority", "curated": True},
    }


def is_unknown_attribute_policy_question(query: str) -> bool:
    compact = _compact(query)
    return (
        any(marker in compact for marker in ("从未记录", "没有记录过", "未知属性", "不知道属性"))
        and any(marker in compact for marker in ("个人属性", "偏好", "无关", "注入", "记忆"))
    )


def unknown_attribute_policy_authority_result() -> dict:
    return {
        "text": (
            "当用户询问一个没有直接记录的个人属性时，Hindsight 不得以相近偏好、相似项目或向量近邻补成答案，"
            "也不为了凑注入数量带入无关记忆；应明确标注缺少直接证据，必要时请用户补充或转为可验证的来源查询。"
        ),
        "type": "world",
        "mentioned_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {"source": "unknown-attribute-policy-authority", "curated": True},
    }


def is_smalltalk_memory_policy_question(query: str) -> bool:
    compact = _compact(query)
    return (
        any(marker in compact for marker in ("普通闲聊", "你好", "寒暄"))
        and any(marker in compact for marker in ("凑数量", "注入长期记忆", "长期记忆"))
    )


def smalltalk_memory_policy_authority_result() -> dict:
    return {
        "text": "普通问候、寒暄和没有可复用任务信息的闲聊不触发长期记忆注入，也不为显示数量读取任何历史内容；只保留当前对话自然上下文。",
        "type": "world",
        "mentioned_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {"source": "smalltalk-memory-policy-authority", "curated": True},
    }


def is_local_edit_memory_policy_question(query: str) -> bool:
    compact = _compact(query)
    return (
        any(marker in compact for marker in ("只改", "一处", "这一处", "局部修改"))
        and any(marker in compact for marker in ("整个历史项目", "全历史", "长期记忆", "塞进", "全部历史"))
    )


def local_edit_memory_policy_authority_result() -> dict:
    return {
        "text": "局部修改任务默认只依赖当前对象与当前任务上下文；Hindsight 仅在存在明确跨页依赖、已确认关联闭包或用户要求核对历史版本时补入对应小颗粒事实，不能把整个历史项目批量注入。",
        "type": "world",
        "mentioned_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {"source": "local-edit-memory-policy-authority", "curated": True},
    }


# Conditional delivery rule: a named semantic element changed in a structured
# artifact must be traced across dependent surfaces before completion.  This is
# a behavior contract, not a claim about the current file; it is safe to inject
# even while a current-source guard suppresses older factual memories.
_DEPENDENCY_ACTION_MARKERS = ("新增", "增加", "加入", "添加", "修改", "改", "替换", "删除", "调整", "补上", "同步")
_DEPENDENCY_ELEMENT_MARKERS = ("岗位", "角色", "模块", "功能", "指标", "课程", "章节", "页面", "图表", "流程", "字段", "节点", "组件")
_DEPENDENCY_ARTIFACT_MARKERS = ("ppt", "pptx", "word", "docx", "excel", "xlsx", "方案", "文档", "幻灯", "材料", "表格", "项目")


def semantic_dependency_contract_results(query: str, config: dict) -> list[dict]:
    contract = dict(config.get("semanticDependencyContract") or {})
    if not contract.get("enabled", True):
        return []
    compact = _compact(query)
    has_action = any(_compact(term) in compact for term in _DEPENDENCY_ACTION_MARKERS)
    has_element = any(_compact(term) in compact for term in _DEPENDENCY_ELEMENT_MARKERS)
    has_artifact = any(_compact(term) in compact for term in _DEPENDENCY_ARTIFACT_MARKERS)
    # "岗位三" / "模块二" is enough even if the user uses a short follow-up
    # without repeating PPT/Word.  Otherwise require both edit action and a
    # structured-artifact cue so generic chats never receive this instruction.
    numbered_element = bool(re.search(r"(?:岗位|角色|模块|功能|指标|课程|章节|页面|图表|流程|字段|节点|组件)[一二三四五六七八九十0-9]", compact))
    if not has_action or not (has_element and (has_artifact or numbered_element)):
        return []
    text = str(contract.get("text") or "").strip()
    if not text:
        return []
    return [{
        "text": "结构关联完整性规则（条件触发）：" + text,
        "type": "world",
        "metadata": {
            "source": "semantic-dependency-contract",
            "authority": "direct_user",
            "curated": True,
            "_ccy_direct_evidence": True,
            "contract": "semantic_dependency_completeness",
        },
    }]


# --- Hindsight Intelligence V4: typed lifecycle ledger -----------------------
_DIRECTIVE_MARKERS = (
    "以后", "默认", "记住", "统一", "固定", "必须", "不要", "不准", "优先",
    "改成", "改为", "只用", "不再", "我的偏好", "我的习惯",
)
_QUOTE_MARKERS = ("他说", "她说", "别人说", "大V说", "原话是", "引用")
_HYPOTHESIS_MARKERS = ("我猜", "可能", "假设", "是不是", "会不会", "我怀疑")
_GLOBAL_SCOPE_MARKERS = ("所有智能体", "任何智能体", "无论哪个智能体", "所有任务", "任何任务", "以后所有回答")
_ROLE_SCOPE_MARKERS = ("trainer", "训练师", "专家y", "秘书y", "小黛", "培训导师")


def _semantic_ledger_path(config: dict) -> Path:
    return Path(os.path.expanduser(config.get(
        "semanticDirectiveLedgerPath",
        "~/.evolving-profile/control-plane/semantic-directives.jsonl",
    )))


def _classify_user_utterance(text: str) -> tuple[str, str, str]:
    compact = _compact(_user_surface_text(text))
    if any(marker in compact for marker in _QUOTE_MARKERS):
        kind = "third_party_quote"
    elif any(marker in compact for marker in _HYPOTHESIS_MARKERS) and not any(
        marker in compact for marker in ("我确认", "确定", "就是")
    ):
        kind = "hypothesis_or_question"
    elif any(marker in compact for marker in _CORRECTION_MARKERS) or re.search(
        r"(?:不是|不叫).{0,30}(?:而是|应该是|改成)", text, re.I | re.S
    ):
        kind = "correction"
    elif any(marker in compact for marker in _DIRECTIVE_MARKERS):
        kind = "direct_rule"
    else:
        kind = "ordinary"
    if any(marker in compact for marker in _GLOBAL_SCOPE_MARKERS):
        scope = "global"
    elif any(marker in compact for marker in _ROLE_SCOPE_MARKERS):
        scope = "role"
    elif any(marker in compact for marker in ("这个项目", "本项目", "当前项目", "这份文档")):
        scope = "project"
    else:
        scope = "task"
    authority = "direct_user" if kind in {"correction", "direct_rule"} else "context_only"
    return kind, scope, authority


def record_semantic_lifecycle_events(messages: list[dict], config: dict) -> int:
    """Persist high-value user rules/corrections immediately, before model batching.

    Quotes, questions and hypotheses are typed but never promoted as current rules.
    This ledger is deterministic, append-only and lives inside Hindsight.
    """
    path = _semantic_ledger_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                existing_ids.add(json.loads(line).get("id"))
            except ValueError:
                pass
    rows = []
    now = datetime.now(timezone.utc).isoformat()
    for message in messages or []:
        if str(message.get("role") or "") != "user":
            continue
        text = _sanitize_user_text(_user_surface_text(message.get("content") or ""))
        if not text:
            continue
        if text.startswith("<heartbeat>") or text.startswith("<evolving_profile_midtask_journal>"):
            continue
        kind, scope, authority = _classify_user_utterance(text)
        if kind == "ordinary":
            continue
        signature = hashlib.sha256(f"{kind}|{scope}|{text}".encode("utf-8")).hexdigest()[:24]
        if signature in existing_ids:
            continue
        rows.append({
            "id": signature,
            "kind": kind,
            "scope": scope,
            "authority": authority,
            "status": "active" if kind in {"correction", "direct_rule"} else "context_only",
            "recorded_at": now,
            "text": text[:1200],
        })
    if rows:
        with path.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def semantic_directive_authority_results(query: str, config: dict) -> list[dict]:
    """Return only relevant active direct-user rules/corrections.

    Token overlap is deliberately conservative.  Questions, quotes and hypotheses
    remain auditable in the ledger but are never injected as facts.
    """
    if not config.get("semanticDirectiveRecallEnabled", True):
        return []
    path = _semantic_ledger_path(config)
    if not path.exists():
        return []
    compact_query = _compact(query)
    role_markers = {
        marker for marker in _ROLE_SCOPE_MARKERS if _compact(marker) in compact_query
    }
    ascii_query = set(re.findall(r"[a-z0-9_-]{3,}", compact_query))
    chinese_query = {
        compact_query[index:index + size]
        for size in (2, 3, 4)
        for index in range(max(0, len(compact_query) - size + 1))
        if re.fullmatch(r"[\u4e00-\u9fff]+", compact_query[index:index + size])
    }
    generic_terms = {
        "现在", "当前", "这个", "那个", "什么", "怎么", "以后", "应该",
        "可以", "需要", "问题", "直接", "已经", "还是", "记忆", "用户",
    }
    candidates = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[-1000:]:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("status") != "active" or row.get("kind") not in {"correction", "direct_rule"}:
            continue
        if '[TRAINER_TRANSACTION_CONTEXT]' in str(row.get('text') or ''):
            clean=_user_surface_text(row['text'])
            kind,scope,authority=_classify_user_utterance(clean)
            if kind not in {'correction','direct_rule'}:continue
            row=dict(row,text=clean,kind=kind,scope=scope,authority=authority)
        scope = str(row.get("scope") or "task")
        if scope == 'global' and not any(marker in _compact(row.get('text') or '') for marker in _GLOBAL_SCOPE_MARKERS):
            # Old heuristic ledgers confused project-wide consistency with a
            # universal personal rule. Keep the original record for audit,
            # but do not elevate it into every future task's instructions.
            continue
        # Task/project directives have no stable route key in the historical
        # ledger.  They remain auditable but must not leak into unrelated tasks.
        if scope not in {"global", "role"}:
            continue
        text = _sanitize_user_text(row.get("text") or "")
        compact_text = _compact(text)
        if not text:
            continue
        ascii_text = set(re.findall(r"[a-z0-9_-]{3,}", compact_text))
        chinese_overlap = {
            term for term in chinese_query
            if term not in generic_terms and term in compact_text
        }
        ascii_overlap = ascii_query & ascii_text
        score = len(ascii_overlap) * 2 + len(chinese_overlap)
        if scope == "role":
            shared_roles = {
                marker for marker in role_markers if _compact(marker) in compact_text
            }
            if not shared_roles or score < 1:
                continue
            score += 3
        elif score < 2:
            continue
        candidates.append((score, str(row.get("recorded_at") or ""), row))
    results = []
    # Multiple directives can share the same recorded_at timestamp.  Sorting
    # whole tuples then falls through to comparing the dict payloads, which is
    # invalid in Python 3.  Order only by the timestamp and preserve file order
    # for ties.
    for _, _, row in sorted(candidates, key=lambda item: (item[0], item[1]), reverse=True)[:1]:
        results.append({
            "text": (
                f"直接用户规则（范围={row.get('scope')}，状态={row.get('status')}，"
                f"记录时间={row.get('recorded_at')}）：{row.get('text')}"
            ),
            "type": "world",
            "mentioned_at": row.get("recorded_at"),
            "metadata": {
                "source": "semantic-directive-ledger",
                "kind": row.get("kind"),
                "scope": row.get("scope"),
                "authority": row.get("authority"),
                "curated": True,
            },
        })
    return results
