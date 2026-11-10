"""Opt-in diagnostic-focused regeneration; independent review still owns acceptance."""
from __future__ import annotations

import copy
import urllib.request

FOCUS_SCHEMA = 'evolving-profile.scenario-draft-repair-focus.v1'
MAX_FOCUS_MESSAGES = 8
# An explicit omission stays terminal for reviewer reselection. A caller may
# instead request a new source-bound draft, which still requires fresh review.
DRAFT_ONLY_REPAIR_ERRORS = frozenset({'user_intent_omitted'})

def _substantive_draft_content(draft):
    def normalized(value):
        if isinstance(value,str):return ' '.join(value.split())
        if isinstance(value,list):return [normalized(item) for item in value]
        if isinstance(value,dict):return {key:normalized(item) for key,item in value.items()}
        return value
    return normalized({key:draft.get(key) for key in
        ('schema','source_revision','state','summaries','evidence','events','unknowns')})


def repair_context_for_source(context, source, *, filter_missing=False):
    """Validate source-bound controlled focus, optionally project into a chunk."""
    if context is None:
        return None
    from .memory_recovery_scenario import RESELECTABLE_MAPPING_ERRORS
    if (not isinstance(context, dict)
            or set(context) != {'schema', 'source_revision', 'reason', 'focus_message_ids'}
            or context.get('schema') != FOCUS_SCHEMA
            or context.get('source_revision') != source.get('source_revision')
            or not isinstance(context.get('reason'), str)
            or context.get('reason') not in (RESELECTABLE_MAPPING_ERRORS | DRAFT_ONLY_REPAIR_ERRORS)):
        raise ValueError('scenario_draft_repair_context_invalid')
    ids = context.get('focus_message_ids')
    if (not isinstance(ids, list) or not 1 <= len(ids) <= MAX_FOCUS_MESSAGES
            or any(not isinstance(mid, str) or not mid for mid in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError('scenario_draft_repair_context_invalid')
    by_id = {row['evidence_id']: row for row in source['messages']}
    if (any(mid in by_id and by_id[mid]['role'] != 'user' for mid in ids)
            or (not filter_missing and any(mid not in by_id for mid in ids))):
        raise ValueError('scenario_draft_repair_context_invalid')
    selected = [mid for mid in ids if mid in by_id]
    return {**context, 'focus_message_ids': selected} if selected else None


def request_episode_bundle_draft_repair(source, bundle, diagnostic, *, base_url, api_key, model,
                                        opener=urllib.request.urlopen, timeout=90,
                                        max_input_chars=30000):
    """Regenerate one affected episode once, with normal bounded model validation.

    diagnostic is CoverageError.safe_detail() plus source_revision and
    bundle_sha256 captured for that failed review attempt. Missing/untargetable
    diagnostics fail closed. This function performs no review or publication;
    callers must enforce their existing attempt/provider budget and obtain fresh
    independent episode and source-coverage reviews for the returned fingerprint.
    """
    from .memory_recovery_scenario import CoverageError, RESELECTABLE_MAPPING_ERRORS
    from .scenario_episodes import partition_source, validate_episode_bundle
    from .scenario_model import fingerprint_episode_bundle, request_session_state_draft
    from .scenario_source import revision_for_messages
    from .scenario_state_v3 import state_partition_source

    if (not isinstance(source, dict) or source.get('status') != 'complete' or not source.get('messages')
            or source.get('source_revision') != revision_for_messages(
                source['messages'], source.get('context_metadata_exclusions'))):
        raise ValueError('scenario_draft_repair_source_invalid')
    validate_episode_bundle(source, bundle)
    previous_sha = fingerprint_episode_bundle(bundle)
    if (not isinstance(diagnostic, dict)
            or not {'source_revision', 'bundle_sha256', 'reason', 'location', 'fields'} <= set(diagnostic)
            or set(diagnostic) - {'source_revision', 'bundle_sha256', 'reason', 'location', 'fields'}
            or diagnostic.get('source_revision') != source['source_revision']
            or diagnostic.get('bundle_sha256') != previous_sha):
        raise ValueError('scenario_draft_repair_diagnostic_invalid')
    detail = {key: diagnostic[key] for key in ('reason', 'fields', 'location') if key in diagnostic}
    detail.setdefault('fields', [])
    if (not isinstance(detail['fields'], list) or not isinstance(detail['location'], dict)
            or not isinstance(detail['reason'], str)
            or detail['reason'] not in (RESELECTABLE_MAPPING_ERRORS | DRAFT_ONLY_REPAIR_ERRORS)
            or CoverageError(detail['reason'], fields=detail['fields'],
                             location=detail['location']).safe_detail() != detail):
        raise ValueError('scenario_draft_repair_diagnostic_invalid')
    ref = detail['location'].get('message_ref')
    by_ref = {f'm{i}': row for i, row in enumerate(source['messages'], 1)}
    message = by_ref.get(ref)
    if not message or message['role'] != 'user':
        raise ValueError('scenario_draft_repair_diagnostic_not_targetable')
    mid = message['evidence_id']
    affected = [i for i, row in enumerate(bundle['episodes']) if mid in row['message_ids']]
    if len(affected) != 1:
        raise ValueError('scenario_draft_repair_diagnostic_not_targetable')
    index = affected[0]
    parts = partition_source(source, [row['start_message_id'] for row in bundle['episodes'][1:]])
    part = parts[index]
    episode_source = state_partition_source(source, part['_messages'], part['source_revision'])
    focused=[mid]
    prior=bundle.get('draft_repair')
    if (isinstance(prior,dict) and prior.get('status')=='fresh_unreviewed'
            and prior.get('source_revision')==source['source_revision']
            and prior.get('repaired_episode_ids')==[part['episode_id']]):
        old_ids=prior.get('focus_message_ids')
        local_users={m['evidence_id'] for m in episode_source['messages'] if m['role']=='user'}
        if (not isinstance(old_ids,list) or any(not isinstance(value,str) or value not in local_users for value in old_ids)):
            raise ValueError('scenario_draft_repair_context_invalid')
        keep=set(old_ids)|{mid}
        if len(keep)>MAX_FOCUS_MESSAGES:raise ValueError('scenario_draft_repair_context_invalid')
        focused=[m['evidence_id'] for m in episode_source['messages'] if m['evidence_id'] in keep]
    focus = {'schema': FOCUS_SCHEMA, 'source_revision': episode_source['source_revision'],
             'reason': detail['reason'], 'focus_message_ids': focused}
    # No old candidate text is fed back as authority; all semantic decisions
    # remain model judgments against the complete original episode messages.
    draft = request_session_state_draft(episode_source, base_url=base_url, api_key=api_key,
        model=model, opener=opener, timeout=timeout, max_input_chars=max_input_chars,
        repair_context=focus)
    if _substantive_draft_content(draft)==_substantive_draft_content(bundle['episodes'][index]['draft']):
        raise ValueError('scenario_draft_repair_no_content_change')
    candidate = copy.deepcopy(bundle)
    candidate['episodes'][index].update(draft=draft, title=draft['state']['subject']['text'][:120],
                                        title_authority='navigation_label_not_verified_fact')
    candidate['draft_repair'] = {'status': 'fresh_unreviewed',
        'source_revision': source['source_revision'], 'previous_bundle_sha256': previous_sha,
        'reason': detail['reason'], 'focus_message_ids': focused,
        'repaired_episode_ids': [part['episode_id']], 'regeneration_passes': 1,
        'independent_review_required': True, 'source_coverage_review_required': True,
        'publication_performed': False, 'external_fact_verified': False}
    # Validate without normalizing unrelated episode objects or retaining a
    # review verdict. A changed bundle fingerprint invalidates prior receipts.
    validate_episode_bundle(source, candidate)
    return candidate
