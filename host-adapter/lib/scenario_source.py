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


def _native_stop_hook_context(path, source_record, text, previous, thread_id):
    """Require the exact adjacent host HookPrompt receipt, not tag-like prose.

    This classifies runtime context only; neither envelope nor receipt grants
    factual authority. Missing or unfamiliar provenance stays semantic input.
    """
    turn_id = source_record.get("turn_id")
    if (not previous or previous.get("role") != "assistant" or not turn_id
            or previous.get("turn_id") != turn_id):
        return None
    if text.count("<hook_prompt") != 1 or text.count("</hook_prompt>") != 1:
        return None
    match = re.fullmatch(r'<hook_prompt hook_run_id="(stop:[0-9]+:[^<>"\r\n]+)">([\s\S]+)</hook_prompt>', text)
    message_id = source_record.get("message_id")
    offset = source_record.get("byte_offset")
    if (not match or not isinstance(message_id, str) or not message_id
            or type(offset) is not int or offset < 0
            or source_record.get("session_id") != thread_id):
        return None
    hook_run_id, body = match.groups()
    try:
        with Path(path).open("rb") as stream:
            stream.seek(offset)
            raw = stream.readline(1024 * 1024)
            event_offset = stream.tell()
            event_raw = stream.readline(1024 * 1024)
        if hashlib.sha256(raw).hexdigest() != source_record.get("raw_line_sha256"):
            return None
        record, event = json.loads(raw), json.loads(event_raw)
        payload = record.get("payload") or {}
        receipt = event.get("payload") or {}
        item = receipt.get("item") or {}
        if (record.get("type") != "response_item" or payload.get("type") != "message"
                or payload.get("role") != "user" or payload.get("id") != message_id
                or payload.get("content") != [{"type": "input_text", "text": text}]
                or event.get("type") != "event_msg" or receipt.get("type") != "item_completed"
                or receipt.get("thread_id") != thread_id or receipt.get("turn_id") != turn_id
                or item.get("type") != "HookPrompt" or item.get("id") != message_id
                or item.get("fragments") != [{"text": body, "hookRunId": hook_run_id}]):
            return None
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    return {"message_id": message_id, "hook_run_id": hook_run_id,
            "byte_offset": event_offset, "raw_line_sha256": hashlib.sha256(event_raw).hexdigest()}


def normalize_scenario_user(content, *, preserve_question_reply=False):
    """Separate structurally identified host UI metadata from human text.

    Only a leading, well-formed native page-context block is recognized;
    quoted examples and ordinary user prose are preserved.
    """
    value=str(content or '')
    if preserve_question_reply:
        import inspect
        if 'preserve_question_reply' in inspect.signature(extract_user_request).parameters:
            text=extract_user_request(value,preserve_question_reply=True)
        else:
            # A long-lived Desktop MCP may have the previous content module
            # cached when this source module is first imported. Preserve the
            # form body through its existing cleanup without a new keyword.
            tag='send_user_message_question_reply'
            marker='opaque_form_'+hashlib.sha256(value.encode()).hexdigest()
            while marker in value:marker+='x'
            masked=value.replace('<'+tag+'>','<'+marker+'>').replace('</'+tag+'>','</'+marker+'>')
            text=extract_user_request(masked).replace('<'+marker+'>','<'+tag+'>').replace('</'+marker+'>','</'+tag+'>')
    else:
        text=extract_user_request(value)
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
    # Bind occurrence disambiguation into snapshots only where the legacy
    # raw-hash prefix was ambiguous. Unaffected sessions retain their revision.
    for item, row in zip(messages, canonical):
        evidence_id = item.get("evidence_id")
        if isinstance(evidence_id, str) and evidence_id.startswith(str(item.get("raw_line_sha256") or "")[:16] + ":"):
            row["evidence_id"] = evidence_id
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
    evidence_occurrences = {}
    machine_candidates = []
    from .claude_mirror_context import machine_context_proof, proof_is_current
    for path in paths:
        machine_proof = machine_context_proof(path, identity)
        for item in read_transcript(str(path)):
            role = item.get("role")
            text = str(item.get("content") or "").strip()
            source_record = item.get("source_record") or {}
            if role not in {"user", "assistant"}:
                continue
            raw_hash = str(source_record.get("raw_line_sha256") or "")
            if not raw_hash:
                continue
            # Identical JSONL bytes can occur in different turns (including
            # bridged Claude sessions). A content hash is not an occurrence ID.
            prefix = raw_hash[:16]
            occurrence = evidence_occurrences.get(prefix, 0) + 1
            evidence_occurrences[prefix] = occurrence
            evidence_id = prefix if occurrence == 1 else f"{prefix}:{occurrence}"
            form_reply = None
            form_like = role == 'user' and 'send_user_message_question_reply' in text
            if role == "user":
                original_text = text
                legacy_text,exclusions = normalize_scenario_user(text)
                text = legacy_text
                if form_like:
                    text,exclusions = normalize_scenario_user(original_text, preserve_question_reply=True)
                    from .scenario_form_source import native_form_reply
                    form_reply = native_form_reply(path, source_record, original_text, identity)
                    text = form_reply['text'] if form_reply else text
                for excluded in exclusions:
                    context_metadata.append({**excluded,'evidence_id':evidence_id,
                        'turn_id':source_record.get('turn_id'),'source_path':str(path),
                        'byte_offset':source_record.get('byte_offset'),'raw_line_sha256':raw_hash})
            if not text: continue
            message={"evidence_id": evidence_id, "role": role, "text": text,
                             "turn_id": source_record.get("turn_id"), "at": source_record.get("recorded_at"),
                             "source_path": str(path), "byte_offset": source_record.get("byte_offset"),
                             "raw_line_sha256": raw_hash}
            # Preserve the pre-classification budget input: normalizer upgrades
            # must not manufacture a fresh provider retry allowance.
            previous=budget_messages[-1] if budget_messages else None
            budget_messages.append({**message,'text':legacy_text} if form_like else message)
            if form_like:
                message['form_reply_unverified'] = form_reply is None
            if form_reply:
                message['form_reply_context'] = form_reply['context']
                context_metadata.append({**{k:message[k] for k in ('evidence_id','turn_id','source_path','byte_offset','raw_line_sha256')},
                    'metadata_kind':'native_form_question_context','original_role':'user','fact_authority':'assistant_question_context_not_user_request',
                    'excluded_from_semantic_input':False,'normalization_scope':'decoded_answers_only_question_separately_attributed',
                    'form_reply_context':form_reply['context']})
            host_event = (_native_stop_hook_context(path, source_record, text, previous, identity)
                          if role == 'user' else None)
            if host_event:
                context_metadata.append({**{k:message[k] for k in ('evidence_id','turn_id','source_path','byte_offset','raw_line_sha256')},
                    'metadata_kind':'native_stop_hook_prompt','original_role':'user','fact_authority':'none',
                    'excluded_from_semantic_input':True,'excluded_chars':len(text),'host_event':host_event,
                    'normalization_scope':'whole_stop_envelope_with_exact_adjacent_native_hook_receipt'})
                continue
            if role=='user' and _paired_skill_context(text,previous,message['turn_id']):
                context_metadata.append({**{k:message[k] for k in ('evidence_id','turn_id','source_path','byte_offset','raw_line_sha256')},
                    'metadata_kind':'native_paired_skill_definition','original_role':'user','fact_authority':'none',
                    'excluded_from_semantic_input':True,'excluded_chars':len(text),
                    'paired_user_evidence_id':previous['evidence_id'],
                    'normalization_scope':'whole_structurally_paired_reference_not_authorship_proof'})
                continue
            if role == 'user' and machine_proof:
                excluded = machine_proof['exclusions'].get((message['byte_offset'], raw_hash))
                if excluded:
                    machine_candidates.append((message, machine_proof, excluded))
            messages.append(message)
    # Delay semantic removal until the full read completes, so native/mirror
    # drift during parsing falls back to the unchanged legacy message view.
    unique_proofs = {id(proof): proof for _,proof,_ in machine_candidates}
    current_proofs = {key: proof_is_current(proof) for key,proof in unique_proofs.items()}
    removed = set()
    for message,proof,excluded in machine_candidates:
        if current_proofs[id(proof)]:
            removed.add(id(message))
            context_metadata.append({**{k:message[k] for k in ('evidence_id','turn_id','source_path','byte_offset','raw_line_sha256')},**excluded})
    if removed:messages=[message for message in messages if id(message) not in removed]
    for position, item in enumerate(messages, start=1):
        item["model_ref"] = f"m{position}"
    total_chars = sum(len(item["text"]) for item in messages)
    digest = revision_for_messages(messages,context_metadata) if messages else None
    result = {**base, "total_chars": total_chars, "user_count": sum(item["role"] == "user" for item in messages),
              "assistant_count": sum(item["role"] == "assistant" for item in messages), "source_revision": digest,
              'context_metadata_exclusions':context_metadata,'source_record_coverage':{
                  'semantic_message_count':len(messages),'excluded_context_metadata_count':len(context_metadata),
                  'review_scope':'semantic_messages_with_explicit_host_context_exclusions_not_fact_authority'}}
    if len(budget_messages)!=len(messages) or any(m.get('form_reply_unverified') is not None for m in messages):result['_budget_messages']=budget_messages
    if not messages:
        return {**result, "status": "source_empty"}
    if total_chars > max_chars:
        return {**result, "status": "over_budget"}
    return {**result, "status": "complete", "messages": messages}
