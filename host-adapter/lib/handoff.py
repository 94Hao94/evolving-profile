"""Deterministic cross-task handoff ledger for Codex hooks.

The ledger closes the short freshness gap between a finished Codex task and
Hindsight's token-batched long-term retain.  It stores a bounded task receipt
locally (0600), never calls a model, and is only injected for explicit
continuity language such as "继续刚才" or "另一个任务".
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_PATH = Path(
    os.environ.get(
        "HINDSIGHT_HANDOFF_STATE_PATH",
        str(Path.home() / ".evolving-profile/codex/state/task-handoffs.json"),
    )
).expanduser()
SCHEMA = 1
MAX_RECORDS = 120
MAX_MESSAGE_CHARS = 1800
MAX_SECTION_ITEMS = 6
DEFAULT_MAX_AGE_SECONDS = 7 * 24 * 60 * 60

CONTINUITY_TERMS = (
    "继续刚才", "接着刚才", "继续上次", "接着上次", "上个任务", "上一个任务",
    "另一个任务", "另一个会话", "其他任务", "跨任务", "跨会话", "刚才那个",
    "前一个任务", "之前那个任务", "接着做", "继续做", "接管", "接手", "移交", "交接", "未完成项", "source thread",
    "previous task", "other thread", "continue from",
)

DECISION_MARKERS = (
    "按你推荐", "就按", "确定", "确认", "采用", "决定", "不要", "取消", "保留",
    "改成", "统一为", "记住", "默认", "必须", "以后", "不再", "开工",
)
OPEN_MARKERS = (
    "继续", "还没", "没有完成", "未完成", "下一步", "剩下", "遗漏", "别停",
    "干到底", "执行到最后", "需要优化", "还有问题", "再检查",
)
CONTROL_ONLY_RE = re.compile(
    r"^(?:继续(?:啊)?|别停(?:啊)?|加油(?:哈)?|怎么样了[？?]?|进度怎么样了[？?]?|"
    r"完成了吗[？?]?|都完成了[？?]?|赶紧继续(?:啊)?|开工(?:吧)?)[！!。\s]*$"
)

_PATH_RE = re.compile(r"(?:~|/Users/[^\s\"'<>]+|/var/[^\s\"'<>]+|/tmp/[^\s\"'<>]+)")
_URL_RE = re.compile(r"https?://[^\s\]\[)）>\"']+")
_PORT_RE = re.compile(r"(?<!\d)(?:127\.0\.0\.1|localhost):([1-9]\d{1,4})(?!\d)")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short(value: Any, limit: int = MAX_MESSAGE_CHARS) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[: max(0, limit - 14)] + " …[已截断]"


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        os.chmod(path, 0o600)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            Path(name).unlink()
        except FileNotFoundError:
            pass


def _load() -> dict[str, Any]:
    try:
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        value = {}
    records = [row for row in value.get("records", []) if isinstance(row, dict)]
    return {"schema": SCHEMA, "records": records[-MAX_RECORDS:]}


def is_continuity_query(query: str) -> bool:
    text = re.sub(r"\s+", "", str(query or "")).casefold()
    return any(re.sub(r"\s+", "", term).casefold() in text for term in CONTINUITY_TERMS)


def _lexical_tokens(value: str) -> set[str]:
    """Return compact Chinese n-grams plus normal latin tokens for routing.

    A regex that treats a complete Chinese sentence as one token gives every
    unrelated task the same lexical score.  Two-to-four-character n-grams make
    “继续那个备份页面” prefer the backup task without adding an embedding or
    model call to this immediate handoff layer.
    """
    text = str(value or "").casefold()
    tokens = set(re.findall(r"[a-z0-9_.-]{3,}", text))
    for chunk in re.findall(r"[\u3400-\u9fff]+", text):
        for width in (2, 3, 4):
            tokens.update(chunk[index:index + width] for index in range(max(0, len(chunk) - width + 1)))
    return tokens


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return _short(content)
    if isinstance(content, list):
        values = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                values.append(str(block.get("text") or ""))
        return _short("\n".join(values))
    return _short(content)


def _select_marked(messages: list[dict[str, Any]], role: str, markers: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    for message in reversed(messages):
        if str(message.get("role")) != role:
            continue
        text = _message_text(message)
        if text and any(marker in text for marker in markers) and text not in values:
            values.append(text)
        if len(values) >= MAX_SECTION_ITEMS:
            break
    return list(reversed(values))


def _references(messages: list[dict[str, Any]]) -> dict[str, list[str]]:
    text = "\n".join(_message_text(item) for item in messages[-12:])
    paths = list(dict.fromkeys(match.rstrip(".,;，。；") for match in _PATH_RE.findall(text)))[:12]
    urls = list(dict.fromkeys(match.rstrip(".,;，。；") for match in _URL_RE.findall(text)))[:8]
    ports = list(dict.fromkeys(match.group(1) for match in _PORT_RE.finditer(text)))[:8]
    return {"paths": paths, "urls": urls, "ports": ports}


def _current_goal(users: list[str]) -> str:
    for value in reversed(users):
        text = _short(value)
        if len(text) >= 12 and not CONTROL_ONLY_RE.fullmatch(text):
            return text
    return users[-1] if users else ""


def save_handoff(
    session_id: str,
    project: str,
    messages: list[dict[str, Any]],
    transcript_path: str = "",
    bank_id: str = "",
) -> dict[str, Any] | None:
    """Save one idempotent, bounded task receipt and return it."""
    clean = [item for item in messages if isinstance(item, dict) and _message_text(item)]
    if not clean:
        return None
    users = [_message_text(item) for item in clean if item.get("role") == "user"]
    assistants = [_message_text(item) for item in clean if item.get("role") == "assistant"]
    if not users:
        return None
    updated = _utc_now()
    record = {
        "id": hashlib.sha256(f"{session_id}|{project}".encode("utf-8")).hexdigest()[:20],
        "session_id": str(session_id or "unknown"),
        "project": str(project or "unknown"),
        "bank_id": str(bank_id or ""),
        "transcript_path": str(transcript_path or ""),
        "updated_at": updated,
        "updated_epoch": time.time(),
        "current_goal": _current_goal(users),
        "latest_result": assistants[-1] if assistants else "",
        "recent_decisions": _select_marked(clean[-18:], "user", DECISION_MARKERS),
        "open_items": _select_marked(clean[-18:], "user", OPEN_MARKERS),
        "references": _references(clean),
        "source": "codex-stop-deterministic-handoff",
    }
    ledger = _load()
    records = [row for row in ledger["records"] if row.get("id") != record["id"]]
    records.append(record)
    ledger["records"] = sorted(records, key=lambda row: float(row.get("updated_epoch") or 0))[-MAX_RECORDS:]
    _atomic_json(STATE_PATH, ledger)
    return record


def select_handoff(
    query: str,
    current_session_id: str = "",
    current_project: str = "",
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> dict[str, Any] | None:
    """Return the best recent cross-task receipt for an explicit continuity query."""
    if not is_continuity_query(query):
        return None
    now = time.time()
    query_text = str(query or "").casefold()
    candidates = []
    for record in _load()["records"]:
        age = now - float(record.get("updated_epoch") or 0)
        if age < -300 or age > max(60, int(max_age_seconds)):
            continue
        # "另一个任务/跨会话" must not echo the current session back to itself.
        explicit_other = any(term in query_text for term in ("另一个", "其他任务", "跨任务", "跨会话", "上个任务", "上一个任务"))
        if explicit_other and str(record.get("session_id")) == str(current_session_id):
            continue
        haystack = " ".join(
            str(record.get(key) or "")
            for key in ("project", "current_goal", "latest_result")
        ).casefold()
        lexical = len(_lexical_tokens(query_text) & _lexical_tokens(haystack))
        same_project = bool(current_project and str(record.get("project")) == str(current_project))
        score = lexical * 6 + (2 if same_project else 0) - age / 86400.0
        candidates.append((score, float(record.get("updated_epoch") or 0), record))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def format_handoff(record: dict[str, Any] | None, max_chars: int = 4200) -> str:
    if not record:
        return ""
    refs = record.get("references") or {}
    sections = [
        "<evolving_profile_task_handoff>",
        "以下是刚结束任务的确定性交接记录，优先用于恢复即时状态；长期背景仍以 Hindsight 召回为准。",
        f"source_session={record.get('session_id')}｜updated_at={record.get('updated_at')}｜project={record.get('project')}",
        f"当前目标：{record.get('current_goal') or '未记录'}",
        f"最新结果：{record.get('latest_result') or '未记录'}",
    ]
    decisions = record.get("recent_decisions") or []
    if decisions:
        sections.append("最近明确决定：\n- " + "\n- ".join(map(str, decisions[-4:])))
    open_items = record.get("open_items") or []
    if open_items:
        sections.append("待继续/待核对：\n- " + "\n- ".join(map(str, open_items[-4:])))
    if refs.get("paths") or refs.get("urls") or refs.get("ports"):
        sections.append(
            "关键定位："
            + "；".join(
                part for part in (
                    "路径=" + ", ".join(refs.get("paths") or []),
                    "网址=" + ", ".join(refs.get("urls") or []),
                    "端口=" + ", ".join(refs.get("ports") or []),
                ) if not part.endswith("=")
            )
        )
    sections.append("</evolving_profile_task_handoff>")
    return _short("\n".join(sections), max_chars)
