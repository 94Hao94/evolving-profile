"""Quote-aware explicit memory boundaries shared by Hook and observability."""
from __future__ import annotations

import re

HISTORY_TOOLS = ("catalog", "recall", "research", "find_sources", "read_source")


def _instruction_text(prompt: str) -> str:
    """Remove quoted/code material so examples cannot become instructions."""
    value = str(prompt or "")
    value = re.sub(r"```[\s\S]*?```|~~~[\s\S]*?~~~", " ", value)
    value = re.sub(r"(?m)^\s*>.*$", " ", value)
    value = re.sub(
        r'"[^"\n]*"|“[^”]*”|‘[^’]*’|「[^」]*」|『[^』]*』|`[^`]*`',
        " ", value,
    )
    return re.sub(r"\s+", "", value).casefold()


def _tool_boundaries(text: str) -> tuple[list[str], list[str]]:
    denied, allowed = [], []
    aliases = {
        "catalog": ("catalog", "目录"),
        "recall": ("recall", "召回"),
        "research": ("research", "研究工作区"),
        "find_sources": ("find_sources", "字面查找"),
        "read_source": ("read_source", "回读原文"),
    }
    for tool, names in aliases.items():
        joined = "|".join(re.escape(name) for name in names)
        if re.search(rf"(?:不要|不用|别|无需)(?:再)?(?:使用|调用|用)?(?:{joined})", text):
            denied.append(tool)
        if re.search(rf"(?:可以|允许|仍要|继续|改用|用)(?:使用|调用|查)?(?:{joined})", text):
            allowed.append(tool)
    return denied, allowed


def classify_memory_policy(prompt: str) -> dict:
    """Classify only explicit access boundaries, leaving relevance to the Agent."""
    text = _instruction_text(prompt)
    denied_tools, allowed_tools = _tool_boundaries(text)
    positive_correction = bool(re.search(
        r"(?:不是|并非)(?:说)?(?:不要|不用|别|不).{0,18}(?:记忆|历史|资料|聊天|偏好)"
        r".{0,18}(?:该查就查|可以查|照常查|仍要查|继续查)", text,
    ))
    all_patterns = (
        r"(?:不要|不用|别|无需|不使用|不调用)(?:再)?(?:使用|调用|用)?(?:任何|所有)(?:旧的?|历史|长期|个人|我的)?记忆",
        r"(?:不要|不用|别|无需|不使用|不调用)(?:再)?(?:使用|调用|用)?(?:个人|我的|本地的)记忆",
        r"(?:完全不使用|禁用所有|不要加载)(?:任何|所有|个人|我的|历史|长期|旧的?)?记忆",
    )
    preference_patterns = (
        r"(?:不要|不用|别|无需|不)(?:再)?(?:使用|调用|用|套用|参考)?(?:我的|个人的)?(?:历史|旧的?)?偏好",
        r"(?:不要|不用|别|无需|不)(?:再)?(?:套用|沿用|参考)?(?:我)?(?:以前|过去|原来)的习惯",
    )
    history_patterns = (
        r"(?:不要|不用|别|无需|不)(?:再)?(?:使用|调用|检索|查询|查|参考|读取|翻)?(?:任何|所有|我的)?(?:历史|长期|旧的?|以往|以前|过去|之前)(?:的)?(?:记忆|事实|资料|聊天|内容|记录|截图)",
        r"(?:关闭|禁用)(?:本轮|这次)?(?:历史|长期)(?:检索|读取|记忆)",
        r"(?:只根据|仅根据|只看|仅看)(?:这句话|当前上下文|当前材料|本轮材料|下面材料|这份材料|新附件)",
        r"别翻旧账",
    )
    all_forbidden = not positive_correction and any(re.search(pattern, text) for pattern in all_patterns)
    preferences_forbidden = all_forbidden or any(re.search(pattern, text) for pattern in preference_patterns)
    history_forbidden = all_forbidden or (
        not positive_correction and any(re.search(pattern, text) for pattern in history_patterns)
    )
    if all_forbidden or history_forbidden:
        denied_tools = list(HISTORY_TOOLS)
    if all_forbidden:
        mode = "all_forbidden"
    elif history_forbidden:
        mode = "history_forbidden"
    elif preferences_forbidden:
        mode = "preferences_forbidden"
    elif denied_tools:
        mode = "tools_limited"
    else:
        mode = "allowed"
    return {
        "mode": mode,
        "history_allowed": not history_forbidden,
        "guidance_memory_policy": "forbidden" if preferences_forbidden else "allowed",
        "denied_tools": list(dict.fromkeys(denied_tools)),
        "allowed_tools": [tool for tool in dict.fromkeys(allowed_tools) if tool not in denied_tools],
        "quote_aware": True,
    }


def explicit_memory_opt_out(prompt: str) -> bool:
    """Compatibility predicate for callers that only need the all-memory gate."""
    return classify_memory_policy(prompt)["mode"] == "all_forbidden"
