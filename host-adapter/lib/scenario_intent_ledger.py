"""Exact model-selected intent spans, with current/history/unknown navigation."""
from .scenario_coverage_contract import fingerprint
from .scenario_coverage_review import valid_local_review


def source_locator(snapshot,unit):
    locator=f"session:{snapshot['location']['session_id']}"
    if unit.get('turn_id'):locator+='/turn/'+unit['turn_id']
    return {'tool':'read_scenario_summary','scenario_type':'session','scenario_id':locator,
        'raw_line_sha256':unit['raw_line_sha256'],'byte_offset':unit['byte_offset'],'offset_space':unit['offset_space']}


def materialize_intents(snapshot,plan,requirements,local_reviews,states=None):
    states=states or {};units={u['unit_id']:u for u in snapshot['units']};out=[]
    spans={s['span_id']:s for p in plan['partitions'] for s in p['primary']}
    requirement_by_unit={r['unit_id']:r for r in requirements['requirements']}
    for receipt in local_reviews:
        if not valid_local_review(receipt) or receipt['status']!='local_reviewed':continue
        for mapping in receipt['result']['intent_mappings']:
            span=spans[mapping['span_id']];unit=units[span['unit_id']]
            # Exact normalization may leave a read, but empty, metadata span.
            # It has no semantic requirement and an optional zero-width mapping
            # must not fabricate one or crash the materialization stage.
            if not span['text'] and mapping['start']==mapping['end']==0:continue
            req=requirement_by_unit[span['unit_id']]
            quote=span['text'][mapping['start']:mapping['end']]
            whole_state=states.get(req['requirement_id'])
            # Whole-message coverage is not permission to erase finer local
            # corrections, omissions or unresolved intent dispositions.
            disposition=whole_state if whole_state in {'superseded','omitted','unresolved'} else mapping['disposition']
            out.append({'intent_id':fingerprint([snapshot['snapshot_id'],mapping]),'requirement_id':req['requirement_id'],
                'source_unit_id':span['unit_id'],'source_span_id':span['span_id'],'source_quote':quote,
                'start':span['start']+mapping['start'],'end':span['start']+mapping['end'],
                'offset_space':'normalized_visible_message_unicode','kind':mapping['kind'],
                'local_disposition':mapping['disposition'],'status':disposition,
                'source_locator':source_locator(snapshot,unit),'external_fact_verified':False})
    return out


def navigation_projection(intents):
    def preview(row):
        quote=row['source_quote']
        return {**{k:v for k,v in row.items() if k!='source_quote'},'source_quote':quote[:512],
            'source_quote_total_chars':len(quote),'has_unread_source_quote':len(quote)>512,'navigation_preview_only':True}
    current=[preview(r) for r in intents if r['status'] in {'covered','answered'}]
    history=[preview(r) for r in intents if r['status']=='superseded']
    gaps=[preview(r) for r in intents if r['status'] in {'omitted','unresolved'}]
    selected=(current or gaps or history)
    return {'current_conditions':current,'historical_conditions':history,'unresolved_conditions':gaps,
        'summary':{'compact':selected[0]['source_quote'][:180] if selected else '',
            'standard':'\n\n'.join(r['source_quote'] for r in selected[:3])[:1200],
            'full':'\n\n'.join(r['source_quote'] for r in selected[:5])[:4000]},
        'summary_is_bounded_source_preview':True,'task_outcome_verified':False}
