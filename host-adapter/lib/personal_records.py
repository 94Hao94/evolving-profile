"""Local structured index for user-supplied personal records.

This is additive to Bank facts: the original transcript remains the source of
truth, while this index makes explicit person/contact/identity lookups fast and
keeps the source session/turn relationship intact.  The file is local and
0600; values are returned only through an explicit personal-record query.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
LANDLINE_RE = re.compile(r"(?<!\d)0\d{2,3}[- ]?\d{7,8}(?!\d)")
ID_RE = re.compile(r"(?<![0-9Xx])[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[0-9Xx](?![0-9Xx])")
PLATE_RE = re.compile(r"(?<![A-Za-z0-9])[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z][A-Z0-9]{5,6}(?![A-Za-z0-9])")
EMAIL_RE = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?![A-Za-z0-9._-])")
CREDENTIAL_RE = re.compile(r"(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[A-Za-z0-9_-]{20,})(?![A-Za-z0-9_-])")
NAME_LABEL_RE = re.compile(r"(?:姓名|联系人|人员|负责人|对接人|老师|同学|医生|家长)\s*[:：]\s*([\u4e00-\u9fff]{2,6})")
NAME_BEFORE_RE = re.compile(r"([\u4e00-\u9fff]{2,4})(?:的)?(?:电话|手机|手机号|身份证|证件号|邮箱)")

# Labels in transcripts are often followed by a noun phrase rather than a
# person's name (for example ``姓名：项目`` or ``联系人：自动推送``).  Keep
# these as source text, but do not promote them to person entities.
NAME_STOPWORDS = {
    "项目", "应用", "公务", "固定", "电话和", "接器实现", "你写形成", "端和对应",
    "不能显示", "是都先打", "就不给你", "自动推送", "诉他一个", "让他打", "输出一个",
    "系统", "平台", "模块", "功能", "用户", "学生", "教师", "联系人", "人员", "负责人",
}


def _looks_like_person_name(value: str) -> bool:
    value = str(value or "").strip()
    if not 2 <= len(value) <= 4 or not re.fullmatch(r"[\u4e00-\u9fff]+", value):
        return False
    if value in NAME_STOPWORDS:
        return False
    # Common predicate/object phrases are not names even when a label is
    # present.  This is deliberately conservative; uncertain values stay in
    # the original transcript and can be promoted after explicit review.
    if any(token in value for token in ("电话", "邮箱", "身份证", "输出", "实现", "对应", "显示", "推送", "形成", "不给", "打")):
        return False
    return True


def _path(root=None) -> Path:
    base = Path(root or os.environ.get("EVOLVING_PROFILE_STATE_ROOT", "~/.evolving-profile")).expanduser()
    return Path(os.environ.get("EVOLVING_PROFILE_PERSONAL_RECORDS_PATH", str(base / "host-integrations/personal-records.json")))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict) and isinstance(value.get("records"), list):
            return value
    except (OSError, ValueError, TypeError):
        pass
    return {"schema": "ep.personal-record-index.v1", "records": [], "updated_at": None}


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, path)
    path.chmod(0o600)


def _extract(text: str) -> list[dict]:
    found = []
    for value in PHONE_RE.findall(text):
        found.append({"field": "phone", "value": value.replace(" ", "")})
    for value in LANDLINE_RE.findall(text):
        found.append({"field": "landline", "value": value.replace(" ", "")})
    for value in ID_RE.findall(text):
        found.append({"field": "national_id", "value": value.upper()})
    for value in EMAIL_RE.findall(text):
        found.append({"field": "email", "value": value})
    for value in CREDENTIAL_RE.findall(text):
        found.append({"field": "credential", "value": value})
    for value in PLATE_RE.findall(text):
        found.append({"field": "vehicle_plate", "value": value.upper()})
    names = NAME_LABEL_RE.findall(text) + NAME_BEFORE_RE.findall(text)
    for value in names:
        if _looks_like_person_name(value):
            found.append({"field": "person_name", "value": value})
    unique = {}
    for item in found:
        unique[(item["field"], item["value"])] = item
    return list(unique.values())


def _extract_groups(text: str) -> list[list[dict]]:
    """Extract explicit person blocks such as ``姓名\n手机号\n身份证号``.

    A block is accepted only when its first non-empty line is a plausible
    person name and the remaining lines contain a contact/identity field.
    This lets us bind fields from structured forms without assigning values by
    mere document order.
    """
    groups = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line.strip(" \t：:") for line in block.splitlines() if line.strip()]
        if len(lines) < 2 or not _looks_like_person_name(lines[0]):
            continue
        fields = [{"field": "person_name", "value": lines[0]}] + _extract("\n".join(lines[1:]))
        if any(item["field"] in {"phone", "landline", "email", "national_id", "vehicle_plate"} for item in fields):
            groups.append(fields)
    return groups


def record_messages(messages: list[dict], *, session_id: str = "", turn_id: str = "", host_id: str = "", transcript_path: str = "", root=None) -> dict:
    path = _path(root)
    data = _load(path)
    records = data["records"]
    created = 0
    for message in messages or []:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content", "")
        if isinstance(content, list):
            content = "\n".join(str(block.get("text") or block.get("input_text") or "") for block in content if isinstance(block, dict))
        text = str(content or "").strip()
        if not text:
            continue
        fields = _extract(text)
        if not fields:
            continue
        groups = _extract_groups(text)
        if groups:
            seen = {(item["field"], item["value"]) for item in fields}
            for group in groups:
                for item in group:
                    if (item["field"], item["value"]) not in seen:
                        fields.append(item)
                        seen.add((item["field"], item["value"]))
        field_group = {}
        for group in groups:
            for item in group:
                field_group[(item["field"], item["value"])] = group
        names = {item["value"] for item in fields if item["field"] == "person_name"}
        relation_confidence = "explicit_block" if groups else "message_single_person" if len(names) == 1 else "unbound"
        related_fields = fields if relation_confidence == "message_single_person" else [item for item in fields if item["field"] == "person_name"]
        source_record = dict(message.get("source_record") or {})
        source = {"session_id": session_id or source_record.get("session_id"), "turn_id": turn_id or source_record.get("turn_id"), "host_id": host_id or source_record.get("host_id"), "transcript_path": transcript_path or source_record.get("transcript_path"), "message_id": source_record.get("message_id")}
        source = {key: value for key, value in source.items() if value}
        text_hash = _hash(text)
        for field in fields:
            record_type = "credential_reference" if field["field"] == "credential" else "identity_record" if field["field"] in {"national_id", "vehicle_plate"} else "contact_record" if field["field"] in {"phone", "landline", "email"} else "person_record"
            record_id = _hash(f"{record_type}\0{field['field']}\0{field['value']}\0{text_hash}")
            if any(row.get("record_id") == record_id for row in records):
                continue
            group = field_group.get((field["field"], field["value"]))
            row_related = group if group else [] if groups else related_fields
            row_confidence = "explicit_block" if group else relation_confidence
            records.append({"record_id": record_id, "record_type": record_type, "field": field["field"], "value": field["value"], "source_text_sha256": text_hash, "source": source, "observed_at": _now(), "verification_state": "candidate" if field["field"] == "person_name" else "observed", "status": "current", "relation_confidence": row_confidence, "related_fields": row_related, "schema": "evolving-profile.personal-record.v1"})
            created += 1
    data["records"] = records[-20000:]
    data["updated_at"] = _now()
    if created:
        _write(path, data)
    return {"created": created, "total_records": len(data["records"]), "path": str(path), "source": "user_supplied_transcript"}


def search(query: str, *, limit: int = 20, root=None) -> dict:
    path = _path(root)
    data = _load(path)
    needle = str(query or "").strip().casefold()
    rows = []
    for row in reversed(data.get("records", [])):
        if row.get("status") in {"rejected", "superseded"}:
            continue
        haystack = " ".join(str(row.get(key) or "") for key in ("value", "field", "record_type"))
        related = ""
        if row.get("relation_confidence") in {"message_single_person", "explicit_block", "explicit_source_binding"}:
            related = " ".join(f"{item.get('field')} {item.get('value')}" for item in (row.get("related_fields") or []) if isinstance(item, dict))
        if needle and needle not in (haystack + " " + related).casefold():
            continue
        rows.append(row)
        if len(rows) >= max(1, min(100, int(limit))):
            break
    return {"schema": "ep.personal-record-search.v1", "query": query, "records": rows, "returned_count": len(rows), "total_indexed": len(data.get("records", [])), "source": "local_structured_personal_record_index", "exact_match": bool(needle)}

