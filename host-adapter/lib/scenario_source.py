"""Bounded original Session transcript input for Scenario Summary drafts."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path

from .content import extract_user_request, read_transcript
from .session_paths import session_paths


NORMALIZATION_VERSION = "scenario-source-v2"


def _paired_skill_context(text, previous, turn_id):
    """Recognize a complete native definition paired with its explicit invocation.

    This is structural reference classification, not proof of authorship.
    Unpaired, quoted, mixed and unknown formats remain semantic source text.
    """
    if not previous or previous.get('role') != 'user' or not turn_id or previous.get('turn_id') != turn_id:
        return False
    if len(re.findall(r'</?skill\b',text,re.I))!=2:return False
    match=re.fullmatch(r'\s*<skill>\s*<name>([^<>\r\n]+)</name>\s*<path>([^<>\r\n]+)</path>\s*'
                      r'---\r?\n(.*?)\r?\n---\r?\n([\s\S]+?)\s*</skill>\s*',text,re.S)
    if not match:return False
    name,path,frontmatter,_=match.groups()
    frontmatter=frontmatter.replace('\r\n','\n')
    if not name.strip() or not path.endswith(('/SKILL.md','\\SKILL.md')):return False
    names=re.findall(r'^name:\s*([^\r\n]+)$',frontmatter,re.M)
    descriptions=re.findall(r'^description:\s*([^\r\n]+)$',frontmatter,re.M)
    if names!=[name] or len(descriptions)!=1 or not descriptions[0].strip():return False
    invocation=f'[${name}]({path})'
    # Require the actual invocation at the beginning, not an embedded quoted example.
    authored=previous.get('text','').lstrip()
    return authored.startswith(invocation) and (len(authored)==len(invocation) or authored[len(invocation)].isspace())


def normalize_scenario_user(content):
    """Separate structurally identified host UI metadata from human text.

    Only a leading, well-formed native page-context block is recognized;
    quoted examples and ordinary user prose are preserved.
    """
    text = extract_user_request(str(content or ''))
    exclusions = []
    pattern = r'^\s*<external_codex_apps_open_page>(.*?)</external_codex_apps_open_page>'
    while (match := re.match(pattern,text,re.S)):
        try: data=json.loads(match.group(1))
        except (ValueError,TypeError): break
        if not isinstance(data,dict) or 'page_id' not in data: break
        exclusions.append({'metadata_kind':'native_app_page_context','original_role':'user',
            'fact_authority':'none','excluded_from_semantic_input':True,'excluded_chars':match.end(),
            'normalization_scope':'after_existing_prompt_envelope_normalization'})
        text=text[match.end():].strip()
    return text,exclusions


def revision_for_messages(messages: list[dict], context_metadata_exclusions=None) -> str:
    canonical = [{"raw_line_sha256": item.get("raw_line_sha256"), "role": item.get("role"),
                  "text": item.get("text"), "turn_id": item.get("turn_id")}
                 for item in messages]
    payload = {"normalization_version": NORMALIZATION_VERSION, "messages": canonical}
    if context_metadata_exclusions:
        payload['context_metadata_exclusions'] = context_metadata_exclusions
        payload['normalization_version'] = NORMALIZATION_VERSION+'-explicit-host-context-exclusions'
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def read_session_source(thread_id: str, session_root: str | Path, *, max_chars: int = 30000) -> dict:
    identity = str(uuid.UUID(str(thread_id)))
    if type(max_chars) is not int or max_chars < 1:
        raise ValueError("max_chars_must_be_positive")
    root = Path(session_root).expanduser()
    located = session_paths(root,identity)
    paths = located['paths']
    base = {"thread_id": identity, "source": "codex_thread_history", "source_files": [str(path) for path in paths],
            "coverage": "visible_user_and_final_assistant_messages_only_not_tool_outputs", "messages": []}
    if located['status'] != 'ready':
        return {**base, "status": located['status'], "total_chars": 0, "user_count": 0, "assistant_count": 0, "source_revision": None}

    messages = []
    budget_messages = []
    context_metadata = []
    for path in paths:
        for item in read_transcript(str(path)):
            role = item.get("role")
            text = str(item.get("content") or "").strip()
            source_record = item.get("source_record") or {}
            if role not in {"user", "assistant"}:
                continue
            raw_hash = str(source_record.get("raw_line_sha256") or "")
            if not raw_hash:
                continue
            if role == "user":
                text,exclusions = normalize_scenario_user(text)
                for excluded in exclusions:
                    context_metadata.append({**excluded,'evidence_id':raw_hash[:16],
                        'turn_id':source_record.get('turn_id'),'source_path':str(path),
                        'byte_offset':source_record.get('byte_offset'),'raw_line_sha256':raw_hash})
            if not text: continue
            message={"evidence_id": raw_hash[:16], "role": role, "text": text,
                             "turn_id": source_record.get("turn_id"), "at": source_record.get("recorded_at"),
                             "source_path": str(path), "byte_offset": source_record.get("byte_offset"),
                             "raw_line_sha256": raw_hash}
            # Preserve the pre-classification budget input: normalizer upgrades
            # must not manufacture a fresh provider retry allowance.
            previous=budget_messages[-1] if budget_messages else None
            budget_messages.append(message)
            if role=='user' and _paired_skill_context(text,previous,message['turn_id']):
                context_metadata.append({**{k:message[k] for k in ('evidence_id','turn_id','source_path','byte_offset','raw_line_sha256')},
                    'metadata_kind':'native_paired_skill_definition','original_role':'user','fact_authority':'none',
                    'excluded_from_semantic_input':True,'excluded_chars':len(text),
                    'paired_user_evidence_id':previous['evidence_id'],
                    'normalization_scope':'whole_structurally_paired_reference_not_authorship_proof'})
                continue
            messages.append(message)
    for position, item in enumerate(messages, start=1):
        item["model_ref"] = f"m{position}"
    total_chars = sum(len(item["text"]) for item in messages)
    digest = revision_for_messages(messages,context_metadata) if messages else None
    result = {**base, "total_chars": total_chars, "user_count": sum(item["role"] == "user" for item in messages),
              "assistant_count": sum(item["role"] == "assistant" for item in messages), "source_revision": digest,
              'context_metadata_exclusions':context_metadata,'source_record_coverage':{
                  'semantic_message_count':len(messages),'excluded_context_metadata_count':len(context_metadata),
                  'review_scope':'semantic_messages_with_explicit_host_context_exclusions_not_fact_authority'}}
    if len(budget_messages)!=len(messages):result['_budget_messages']=budget_messages
    if not messages:
        return {**result, "status": "source_empty"}
    if total_chars > max_chars:
        return {**result, "status": "over_budget"}
    return {**result, "status": "complete", "messages": messages}
