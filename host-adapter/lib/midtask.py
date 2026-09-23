"""Bounded, local-only journal used between Codex hook invocations.

This module deliberately has no Hindsight client dependency: it records only
redacted deterministic tool observations.  Network recall is owned by the two
hook entry points and is never a retain/reflect/consolidation operation.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows hook fallback
    fcntl = None


MAX_EVENTS = 80
MAX_JOURNAL_BYTES = 64 * 1024
MAX_EVENT_CHARS = 2000
MAX_CHECKPOINT_CHARS = 6000
MAX_ADDITIONAL_CONTEXT_TOKENS = 512
MAX_ERROR_SIGNATURES = 256
ERROR_SIGNATURE_TTL_SECONDS = 7 * 24 * 60 * 60

_SECRET_PATTERNS = (
    (r"(?i)(authorization\s*[:=]\s*bearer\s+)([^\s'\"]+)", r"\1[REDACTED]"),
    (
        r'(?i)((?:api[_-]?key|token|password|secret|credential)[\'"]?\s*[:=]\s*)([\'"]?)([^\'"\s,;}]+)',
        r"\1\2[REDACTED]",
    ),
    (r"(?i)(bearer\s+)([^\s'\"]+)", r"\1[REDACTED]"),
)
_SENSITIVE_KEY = re.compile(r"(?:authorization|api[_-]?key|token|password|secret|credential)", re.I)
_EDIT_TOOLS = {"edit", "write", "applypatch", "apply_patch", "notebookedit", "notebook_edit", "createfile"}
_READ_TOOLS = {"read", "glob", "grep", "search", "listfiles", "ls"}
_TEST_COMMAND = re.compile(r"\b(pytest|unittest|tox|nox|npm\s+(?:test|run\s+(?:test|build|lint))|pnpm\s+(?:test|run\s+(?:test|build|lint))|yarn\s+(?:test|build|lint)|go\s+test|cargo\s+(?:test|build|check)|make\s+(?:test|build|check)|gradle|mvn\s+(?:test|package|verify)|health(?:check)?|/health)\b", re.I)
_VERIFIED_DIAGNOSTIC_COMMAND = re.compile(
    r"(?:"
    r"\bcurl\b[^\n]*(?:/health\b|/status\b)|"
    r"\b(?:openclaw|agentmemory)\b[^\n]*\b(?:doctor|status)\b|"
    r"\bhindsight(?:-embed)?\b[^\n]*\bstatus\b|"
    r"\blaunchctl\s+(?:print|list)\b|"
    r"\bpg_isready\b|"
    r"\btail\b[^\n]*\.log\b[^\n]*\b(?:error|warning|failed|timeout|429)\b"
    r")",
    re.I,
)
_CONFIG_PATH = re.compile(r"(?:^|/)(?:\.[^/]+|.*(?:config|settings|profile|\.env)[^/]*)$", re.I)
_MUTATING = re.compile(r"\b(create|update|patch|delete|remove|write|set|append|upload|send|submit|mutat)\w*\b", re.I)
_MCP_READ_ACTIONS = {
    "read", "get", "list", "search", "find", "fetch", "lookup", "query",
    "describe", "show", "inspect", "view",
}
_MCP_MUTATING_ACTIONS = {
    "create", "update", "patch", "delete", "remove", "write", "set",
    "append", "upload", "send", "submit", "mutate", "edit", "add",
    "put", "post", "publish",
}
_MCP_DISPATCH_ACTIONS = {"dispatch", "dispatcher", "call", "invoke", "execute", "request"}


def _state_dir() -> Path:
    configured = os.environ.get("HINDSIGHT_MIDTASK_STATE_DIR")
    root = Path(configured).expanduser() if configured else Path.home() / ".evolving-profile/codex/state/midtask"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    return root


def _key(session_id: str) -> str:
    return hashlib.sha256(str(session_id or "unknown").encode("utf-8")).hexdigest()[:24]


def _journal_path(session_id: str) -> Path:
    return _state_dir() / f"journal-{_key(session_id)}.json"


def _checkpoint_path(session_id: str) -> Path:
    return _state_dir() / f"checkpoint-{_key(session_id)}.txt"


def _signature_path(session_id: str) -> Path:
    return _state_dir() / f"signatures-{_key(session_id)}.json"


@contextmanager
def _locked(session_id: str):
    lock_path = _state_dir() / f"journal-{_key(session_id)}.lock"
    descriptor = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "a+", encoding="utf-8") as handle:
        try:
            os.chmod(lock_path, 0o600)
        except OSError:
            pass
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _atomic_write(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(path))
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _redact_structured(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else _redact_structured(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_structured(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_structured(item) for item in value)
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _redact_text(value) -> str:
    text = str(value or "")
    for pattern, replacement in _SECRET_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text


def _redact(value) -> str:
    if isinstance(value, (dict, list, tuple)):
        try:
            value = json.dumps(_redact_structured(value), ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            value = str(value)
    return _redact_text(value)


def _short(value, limit=1600) -> str:
    text = _redact(value).replace("\x00", " ").strip()
    if len(text) > limit:
        return text[: max(0, limit - 16)] + " …[truncated]"
    return text


def _load_journal(session_id: str) -> dict:
    try:
        value = json.loads(_journal_path(session_id).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    events = [event for event in value.get("events", []) if isinstance(event, dict)][-MAX_EVENTS:]
    sequence = 0
    for event in events:
        raw_sequence = event.get("sequence")
        if not isinstance(raw_sequence, int) or raw_sequence <= sequence:
            raw_sequence = sequence + 1
            event["sequence"] = raw_sequence
        sequence = raw_sequence
    value["events"] = events
    value["next_sequence"] = max(sequence + 1, int(value.get("next_sequence") or 1))
    value["error_signatures"] = [str(item) for item in value.get("error_signatures", [])][-MAX_EVENTS:]
    return value


def _save_journal(session_id: str, journal: dict) -> bool:
    journal["events"] = journal.get("events", [])[-MAX_EVENTS:]
    journal.pop("error_signatures", None)
    payload = json.dumps(journal, ensure_ascii=False, separators=(",", ":"))
    while journal["events"] and len(payload.encode("utf-8")) > MAX_JOURNAL_BYTES:
        journal["events"].pop(0)
        payload = json.dumps(journal, ensure_ascii=False, separators=(",", ":"))
    if len(payload.encode("utf-8")) > MAX_JOURNAL_BYTES:
        return False
    try:
        _atomic_write(_journal_path(session_id), payload)
        return True
    except OSError:
        return False


def _load_signature_ledger(session_id: str, now: float) -> dict:
    try:
        value = json.loads(_signature_path(session_id).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        value = {}
    entries = []
    cutoff = now - ERROR_SIGNATURE_TTL_SECONDS
    for item in value.get("entries", []) if isinstance(value, dict) else []:
        if not isinstance(item, dict) or not item.get("signature"):
            continue
        try:
            seen_at = float(item.get("seen_at", 0))
        except (TypeError, ValueError):
            continue
        if seen_at >= cutoff:
            entries.append({"signature": str(item["signature"]), "seen_at": seen_at})
    return {"entries": entries[-MAX_ERROR_SIGNATURES:]}


def _save_signature_ledger(session_id: str, ledger: dict) -> bool:
    ledger["entries"] = ledger.get("entries", [])[-MAX_ERROR_SIGNATURES:]
    try:
        _atomic_write(
            _signature_path(session_id),
            json.dumps(ledger, ensure_ascii=False, separators=(",", ":")),
        )
        return True
    except OSError:
        return False


def _first_value(value, keys):
    if not isinstance(value, dict):
        return ""
    for key in keys:
        if value.get(key) not in (None, ""):
            return value[key]
    return ""


def _tool_input(hook_input: dict) -> dict:
    return hook_input.get("tool_input") or hook_input.get("input") or hook_input.get("arguments") or {}


def _tool_response(hook_input: dict):
    return hook_input.get("tool_response", hook_input.get("tool_result", hook_input.get("result", {})))


def _exit_code(response):
    if isinstance(response, dict):
        value = _first_value(response, ("exit_code", "exitCode", "code", "status_code"))
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value.strip())
        error_flag = response.get("is_error", response.get("isError", False))
        if (
            error_flag is True
            or str(error_flag).lower() in {"1", "true", "yes"}
            or str(response.get("status", "")).lower() in {"error", "failed", "failure"}
        ):
            return 1
    return 0


def _path_from_input(tool_input: dict) -> str:
    return _short(_first_value(tool_input, ("path", "file_path", "file", "filename", "uri")), 300)


def _command_from_input(tool_input: dict) -> str:
    return _short(_first_value(tool_input, ("command", "cmd", "script", "query")), 600)


def _apply_patch_paths(command: str) -> list:
    paths = []
    for match in re.finditer(r"(?m)^\*\*\* (?:Update|Add|Delete) File:\s*(.+?)\s*$", str(command or "")):
        path = match.group(1).strip()
        if path and path not in paths:
            paths.append(path)
    return paths[:40]


def _action_tokens(value) -> set:
    separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(value or ""))
    return set(re.findall(r"[a-z0-9]+", separated.lower()))


def _mcp_is_mutating(tool: str, tool_input: dict) -> bool:
    tool_actions = _action_tokens(tool)
    if tool_actions & _MCP_READ_ACTIONS:
        return False
    if tool_actions & _MCP_MUTATING_ACTIONS:
        return True
    if not tool_actions & _MCP_DISPATCH_ACTIONS:
        return False
    dedicated_action = _first_value(tool_input, ("action", "operation", "method"))
    action_tokens = _action_tokens(dedicated_action)
    if action_tokens & _MCP_READ_ACTIONS:
        return False
    return bool(action_tokens & _MCP_MUTATING_ACTIONS)


def _classify(hook_input: dict):
    tool = str(hook_input.get("tool_name") or hook_input.get("tool") or hook_input.get("name") or "unknown")
    normalized = tool.lower().replace("-", "").replace("_", "")
    tool_input = _tool_input(hook_input)
    response = _tool_response(hook_input)
    raw_command = _first_value(tool_input, ("command", "cmd", "script", "query"))
    command = _short(raw_command, 600)
    path = _path_from_input(tool_input)
    if normalized == "applypatch":
        patch_paths = _apply_patch_paths(raw_command)
        path = _short("\n".join(patch_paths), 900)
        command = ""
    exit_code = _exit_code(response)
    response_text = _short(response, 900)
    if exit_code:
        input_receipt = "" if normalized == "applypatch" else _short(tool_input, 600)
        return "错误", tool, "\n".join(part for part in (command, path, input_receipt, response_text) if part), exit_code
    if normalized in _READ_TOOLS:
        return None
    if "mcp" in normalized:
        if _mcp_is_mutating(tool, tool_input):
            receipt = _short(f"input={_short(tool_input, 650)}\nresponse={response_text}", 1400)
            return "MCP变更", tool, receipt, 0
        return None
    if _CONFIG_PATH.search(path) or (command and _CONFIG_PATH.search(command) and _MUTATING.search(command)):
        return "配置变更", tool, path or command, 0
    if normalized in _EDIT_TOOLS:
        return "编辑", tool, path or _short(tool_input, 900), 0
    if command and _VERIFIED_DIAGNOSTIC_COMMAND.search(command):
        return "诊断证据", tool, f"{command}\n{response_text}", 0
    if _TEST_COMMAND.search(command):
        return "测试/构建", tool, f"{command}\n{response_text}", 0
    return None


def _error_signature(tool: str, detail: str, exit_code: int) -> str:
    normalized = re.sub(r"\b\d+\b", "#", _redact(detail).lower())
    normalized = re.sub(r"/[^\s:]+", "<path>", normalized)
    digest = hashlib.sha256(f"{tool.lower()}|{exit_code}|{normalized[:800]}".encode("utf-8")).hexdigest()[:16]
    return f"{tool.lower()}:{exit_code}:{digest}"


def record_tool_event(hook_input: dict) -> dict:
    """Store one selected redacted event, without contacting Hindsight."""
    result = {"recorded": False, "new_error": False, "signature": "", "recall_query": ""}
    try:
        session_id = str((hook_input or {}).get("session_id") or "unknown")
        classified = _classify(hook_input or {})
        if not classified:
            return result
        kind, tool, detail, exit_code = classified
        detail = _short(detail, 1500)
        signature = _error_signature(tool, detail, exit_code) if kind == "错误" else ""
        with _locked(session_id):
            journal = _load_journal(session_id)
            now = time.time()
            ledger = _load_signature_ledger(session_id, now)
            legacy_signatures = journal.pop("error_signatures", [])
            known = {item["signature"] for item in ledger["entries"]}
            for legacy_signature in legacy_signatures:
                if legacy_signature not in known:
                    ledger["entries"].append({"signature": legacy_signature, "seen_at": now})
                    known.add(legacy_signature)
            if signature and signature in known:
                _save_signature_ledger(session_id, ledger)
                return result
            event = {
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "sequence": journal["next_sequence"],
                "kind": kind,
                "tool": _short(tool, 120),
                "summary": detail,
            }
            journal["next_sequence"] += 1
            if signature:
                event["signature"] = signature
            if len(json.dumps(event, ensure_ascii=False, separators=(",", ":"))) > MAX_EVENT_CHARS:
                event["summary"] = _short(detail, 1000)
            journal.setdefault("events", []).append(event)
            if not _save_journal(session_id, journal):
                return result
            if signature:
                ledger["entries"].append({"signature": signature, "seen_at": now})
                if not _save_signature_ledger(session_id, ledger):
                    return result
        result.update(recorded=True, new_error=bool(signature), signature=signature)
        if signature:
            result["recall_query"] = _short(f"排查错误 {signature}：{detail}", 1800)
        return result
    except Exception:
        return result


def _journal_text(session_id: str) -> str:
    try:
        with _locked(session_id):
            journal = _load_journal(session_id)
        events = journal.get("events", [])
        return _journal_text_from_events(events)
    except Exception:
        return ""


def render_checkpoint(session_id: str, project: str) -> str:
    """Persist and return a bounded Chinese compact/resume checkpoint."""
    journal = _journal_text(session_id)
    if not journal:
        return ""
    project = _short(project or "unknown", 300)
    checkpoint = _short(
        f"<evolving_profile_checkpoint>\n任务恢复检查点：项目 {project}\n{journal}\n恢复时优先核对上述编辑、测试结果和未解决错误。\n</evolving_profile_checkpoint>",
        MAX_CHECKPOINT_CHARS,
    )
    try:
        with _locked(session_id):
            _atomic_write(_checkpoint_path(session_id), checkpoint)
    except Exception:
        pass
    return checkpoint


def load_checkpoint(session_id: str) -> str:
    try:
        return _short(_checkpoint_path(session_id).read_text(encoding="utf-8"), MAX_CHECKPOINT_CHARS)
    except OSError:
        return ""


def consume_journal(session_id: str) -> str:
    """Return and acknowledge the current durable journal snapshot."""
    snapshot = snapshot_journal(session_id)
    if snapshot["text"]:
        acknowledge_journal(session_id, snapshot["through_sequence"])
    return snapshot["text"]


def snapshot_journal(session_id: str) -> dict:
    """Return an identified snapshot that can be safely acknowledged later."""
    try:
        with _locked(session_id):
            journal = _load_journal(session_id)
            events = journal.get("events", [])
            return {
                "text": _journal_text_from_events(events),
                "through_sequence": max((item.get("sequence", 0) for item in events), default=0),
            }
    except Exception:
        return {"text": "", "through_sequence": 0}


def acknowledge_journal(session_id: str, through_sequence: int) -> bool:
    """Remove only events present in an accepted queue snapshot."""
    try:
        boundary = int(through_sequence)
        with _locked(session_id):
            journal = _load_journal(session_id)
            journal["events"] = [
                item for item in journal.get("events", []) if int(item.get("sequence", 0)) > boundary
            ]
            return _save_journal(session_id, journal)
    except Exception:
        return False


def _journal_text_unlocked(session_id: str) -> str:
    journal = _load_journal(session_id)
    return _journal_text_from_events(journal.get("events", []))


def _journal_text_from_events(events: list) -> str:
    if not events:
        return ""
    lines = ["<evolving_profile_midtask_journal>", "工具过程摘要（已脱敏，仅供恢复任务上下文）："]
    lines.extend(f"- {item.get('kind', '事件')}｜{item.get('tool', 'tool')}｜{item.get('summary', '')}" for item in events)
    lines.append("</evolving_profile_midtask_journal>")
    return "\n".join(lines)


def journal_text(session_id: str) -> str:
    return _journal_text(session_id)


def bound_additional_context(value, max_tokens=MAX_ADDITIONAL_CONTEXT_TOKENS) -> str:
    """Conservatively cap hook context by treating every character as one token."""
    text = str(value or "")
    limit = max(0, int(max_tokens))
    if len(text) <= limit:
        return text
    suffix = "\n…[truncated]"
    if limit <= len(suffix):
        return text[:limit]
    return text[: limit - len(suffix)] + suffix


def clear_checkpoint(session_id: str) -> None:
    try:
        with _locked(session_id):
            _checkpoint_path(session_id).unlink(missing_ok=True)
    except Exception:
        pass


def clear_session_state(session_id: str) -> None:
    try:
        with _locked(session_id):
            _journal_path(session_id).unlink(missing_ok=True)
            _checkpoint_path(session_id).unlink(missing_ok=True)
            _signature_path(session_id).unlink(missing_ok=True)
    except Exception:
        pass
