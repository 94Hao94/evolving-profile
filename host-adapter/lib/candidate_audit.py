"""Bounded historical candidate snapshots, separate from model delivery."""

import hashlib
from datetime import datetime, timezone

from source_safety import mask_text


def snapshot(row, *, outcome, reason, max_chars=600, stage='discovery'):
    raw = str(row.get('text') or '')
    readable = row.get('state') != 'invalidated' and outcome != 'blocked'
    preview = mask_text(raw)[:max_chars] if readable else ''
    return {
        'id': str(row.get('id') or ''), 'type': row.get('type') or row.get('fact_type'),
        'text': preview, 'text_truncated': len(raw) > len(preview) if readable else False,
        'text_sha256': hashlib.sha256(raw.encode()).hexdigest() if readable else None,
        'source_revision': (row.get('metadata') or {}).get('revision'),
        'document_id': row.get('document_id'), 'chunk_id': row.get('chunk_id'),
        'session_ids': (row.get('metadata') or {}).get('session_ids') or [],
        'outcome': outcome, 'reason': reason, 'delivery': 'not_returned',
        'snapshot_stage':stage,'snapshot_at':datetime.now(timezone.utc).isoformat(),
        'snapshot_boundary': 'retrieval_time_preview_not_verified_fact',
    }


def mark_delivery(rows, output_items):
    output = {str(item.get('id')): item for item in output_items if isinstance(item, dict)}
    result = []
    for row in rows:
        copy = dict(row)
        item = output.get(str(row.get('id')))
        if item is not None:
            text = str(item.get('text') or '')
            if copy.get('outcome')=='blocked':
                copy['delivery']='previously_returned_currently_blocked'
                copy['delivered_text']=''
                copy['text']=''
            else:
                copy['delivery'] = 'text_returned' if text else 'locator_returned'
                copy['delivered_text'] = mask_text(text)
        result.append(copy)
    return result


def page(rows, *, offset=0, limit=10, actor):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError('invalid_candidate_pagination')
    return {'actor': actor, 'total': len(rows), 'offset': offset, 'limit': limit,
            'next_offset': offset + limit if offset + limit < len(rows) else None,
            'items': rows[offset:offset + limit], 'snapshot_status': 'recorded'}
