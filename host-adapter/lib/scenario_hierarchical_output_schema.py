"""Host-built field domains for v3; provider conformance is still validated locally."""
import re
from .scenario_coverage_contract import contract


def _object(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


def _choice(values):
    return {'type':'string','enum':list(values)}


def _array(items=None,*,minimum=0):
    if items is None:return {'type':'array','maxItems':0}
    return {'type':'array','items':items,**({'minItems':minimum} if minimum else {})}


def output_schema(request):
    config=contract()['review_protocols']['hierarchical_review.v1'];host=config['host_plane_wire']
    if request.get('protocol')!='hierarchical_review.v1' or request.get('binding',{}).get('wire_contract')!=host['schema']:return None
    stage=request['stage'];catalog=request['catalog'];string={'type':'string'};strings=_array(string)
    spans=[r['id'] for r in catalog if r['kind']=='span']
    context_row=_object({'span_ids':_array(_choice(spans),minimum=1),'missing_fields':_array(string,minimum=1)}) if spans else None
    context=_array(context_row)
    if stage=='extract':
        actual={s['span_id']:s for s in request['inputs']['partition']['primary']};alternatives=[]
        for role,policy in host['roles'].items():
            ids=[r['id'] for r in catalog if r['kind']=='span' and actual[r['source_id']]['role']==role]
            if not ids:continue
            alternatives.append(_object({'source_cards':_array(_choice(ids),minimum=1),'kind':_choice(policy['kinds']),
                'action':string,'claim':{'type':['string','null']},'conditions':strings,'negation':{'type':'boolean'},
                'exceptions':strings,'object_hypotheses':strings,
                'time':_object({'event':{'type':['string','null']},'effective':{'type':['string','null']}}),
                'local_state':{'anyOf':[string,{'type':'null'},_object({})]}}))
        row={'anyOf':alternatives} if len(alternatives)>1 else alternatives[0] if alternatives else None
        return _object({'wire_schema':_choice([host['schema']]),'proposal':_object({'items':_array(row)}),'context_requests':context})
    axes=_object({'attribution':_object({'status':_choice(config['attribution_states']),
            'conditions_preserved':{'type':'boolean'},'issues':strings}),
        'scope':_object({'status':_choice(config['scope_states']),'issues':strings}),
        'outcome':_object({'status':_choice(['not_verified'])})})
    props={'wire_schema':_choice([host['schema']]),'judgment_schema':_choice([config['judgment_schema']]),
        'accepted_scope':_choice(['source_attribution_and_intent_only']),
        'read_ids':_array(_choice([r['id'] for r in catalog])) if catalog else _array(),
        'assistant_reports_are_unverified':{'type':'boolean'},'evidence_limits':strings,
        'review_axes':axes,'context_requests':context}
    if stage in {'merge','readback'}:
        registry=config['selection_wire'];records=[r['id'] for r in catalog if r['kind'] in {'atom','assistant_claim','residual','prior_state'}]
        readable={p['page_id'] for p in request['inputs'].get('source_pages',[]) if p.get('source_readback') is True}
        pages=[r['id'] for r in catalog if r['kind']=='source_page' and r['source_id'] in readable]
        obligations=[r['id'] for r in catalog if r['kind']=='obligation']
        sources=_array(_choice(pages)) if pages else _array();state=_choice(['open','supported','refuted','not_applicable'])
        relation=_object({'kind':_choice(registry['relation_kinds']),'from':_choice(records),'to':_choice(records),
            'sources':sources,'state':state,'reason':string}) if len(records)>1 else None
        name={'type':'string','pattern':'^'+re.escape(registry['new_obligation_prefix'])+'.+'}
        if obligations:name={'anyOf':[_choice(obligations),name]}
        obligation=_object({'id':name,'kind':_choice(registry['record_obligation_kinds']),
            'items':_array(_choice(records),minimum=1),'sources':sources,'state':state,'reason':string}) if records else None
        item_state=_object({'item':_choice(records),'state':_choice(['current','historical','unresolved','reported']),
            'sources':sources}) if records else None
        props.update(discovery_complete={'type':'boolean'},relations=_array(relation),record_obligations=_array(obligation),states=_array(item_state))
    return _object(props)
