import io,json
import pytest
from lib.memory_recovery_scenario import request_source_coverage_review
from test_memory_recovery_scenario import fixture,reference_response


def resolve_transport_value(value,data):
    if isinstance(value,list):return [resolve_transport_value(v,data) for v in value]
    if not isinstance(value,dict):return value
    if set(value)=={'message_ref','source_span'}:
        raw=next(m['text'] for m in data['messages'] if m['message_ref']==value['message_ref'])
        start,end=value['source_span'];return raw[start:end]
    if set(value)=={'field_ref'}:
        field=next(f for f in data['review_selection_catalog']['state_fields'] if f['ref']==value['field_ref'])
        node=next(e['draft']['state'] for e in data['episodes'] if e['episode_ref']==field['episode_ref'])
        for key in field['state_path'].split('/'):node=node[int(key)] if isinstance(node,list) else node[key]
        return resolve_transport_value(node,data)
    if set(value)=={'text_parts'}:return ''.join(resolve_transport_value(v,data) for v in value['text_parts'])
    return {k:resolve_transport_value(v,data) for k,v in value.items()}


def test_model_can_select_exact_catalog_ids_without_retyping_original_quotes(tmp_path):
    _,_,source,bundle,_=fixture(tmp_path)
    def opener(request,**_):
        body=json.loads(request.data);prompt=body['messages'][0]['content']
        data=json.loads(prompt.rsplit('\n',1)[1]);catalog=data.get('review_selection_catalog')
        assert catalog is not None,'Missing exact source/field choice catalog; model still copies strings'
        entries=[]
        for m in ['m1','m3']:
            quote=next(r for r in catalog['source_quotes'] if r['message_ref']==m)
            field=next(r for r in catalog['state_fields'] if r['state_path']=='goal/text' and m in r['supported_message_refs'])
            entries.append({'message_ref':m,'intents':[{'kind':'request','disposition':'covered',
                'source_quote_ref':quote['ref'],'field_links':[{'field_ref':field['ref']}]}]})
        result=reference_response(user_intent_coverage=entries,selection_catalog_sha256=data['selection_catalog_sha256'])
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]}).encode())
    result=request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='fixture',opener=opener)
    manifest=result['user_intent_coverage']
    assert manifest[0]['intents'][0]['source_quote']==source['messages'][0]['text']
    assert manifest[0]['intents'][0]['field_links'][0]['field_quote']==bundle['episodes'][0]['draft']['state']['goal']['text']
    assert result['model_review_receipt']['selection_catalog_sha256']
    assert result['model_review_receipt']['model_verdict_modified'] is False
    from lib.memory_recovery_scenario import validate_coverage
    broken=json.loads(json.dumps(result));broken['model_review_receipt']['selection_catalog_sha256']='0'*64
    with pytest.raises(ValueError,match='automated_source_coverage_incomplete'):
        validate_coverage(source,bundle,broken)
    stripped=json.loads(json.dumps(result))
    for key in ['selection_catalog_sha256','selection_catalog_protocol']:stripped['model_review_receipt'].pop(key)
    with pytest.raises(ValueError,match='automated_source_coverage_incomplete'):
        validate_coverage(source,bundle,stripped)


@pytest.mark.parametrize('mode',['unknown_ref','wrong_message','wrong_episode','quote_override','path_override','nested_ref'])
def test_catalog_choices_never_bypass_existing_exact_source_guards(tmp_path,mode):
    _,_,source,bundle,_=fixture(tmp_path)
    def opener(request,**_):
        data=json.loads(json.loads(request.data)['messages'][0]['content'].rsplit('\n',1)[1]);c=data['review_selection_catalog']
        q=next(r for r in c['source_quotes'] if r['message_ref']=='m1');f=next(r for r in c['state_fields'] if r['state_path']=='goal/text' and 'm1' in r['supported_message_refs'])
        i={'kind':'request','disposition':'covered','source_quote_ref':q['ref'],'field_links':[{'field_ref':f['ref']}]}
        if mode=='unknown_ref':i['source_quote_ref']='q-missing'
        if mode=='wrong_message':i['source_quote_ref']=next(r for r in c['source_quotes'] if r['message_ref']=='m3')['ref']
        if mode=='wrong_episode':i['field_links'][0]['field_ref']=next(r for r in c['state_fields'] if r['episode_ref']=='e2' and r['state_path']=='goal/text')['ref']
        if mode=='quote_override':i['source_quote']='forged'
        if mode=='path_override':i['field_links'][0]['state_path']='__class__/text'
        if mode=='nested_ref':i['source_quote_ref']={'key':'secret'}
        result=reference_response(user_intent_coverage=[{'message_ref':'m1','intents':[i]},{'message_ref':'m3','intents':[]}],selection_catalog_sha256=data['selection_catalog_sha256'])
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]}).encode())
    with pytest.raises(ValueError,match='automated_source_coverage_incomplete'):
        request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='fixture',opener=opener)


def test_old_catalog_response_and_tampered_receipt_cannot_bind_new_source(tmp_path):
    from lib.scenario_review_catalog import review_catalog,catalog_sha
    from lib.memory_recovery_scenario import validate_coverage
    _,_,source,bundle,_=fixture(tmp_path)
    c=review_catalog(source,bundle);old_hash=catalog_sha(c)
    changed=dict(source,thread_id='different-thread',source_revision='changed-raw-revision')
    assert catalog_sha(review_catalog(changed,bundle))!=old_hash
    def opener(request,**_):
        data=json.loads(json.loads(request.data)['messages'][0]['content'].rsplit('\n',1)[1]);catalog=data['review_selection_catalog']
        entries=[]
        for m in ['m1','m3']:
            quote=next(r for r in catalog['source_quotes'] if r['message_ref']==m)
            field=next(r for r in catalog['state_fields'] if r['state_path']=='goal/text' and m in r['supported_message_refs'])
            entries.append({'message_ref':m,'intents':[{'kind':'request','disposition':'covered','source_quote_ref':quote['ref'],'field_links':[{'field_ref':field['ref']}]}]})
        result=reference_response(user_intent_coverage=entries,selection_catalog_sha256='0'*64)
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]}).encode())
    with pytest.raises(ValueError,match='automated_source_coverage_incomplete'):
        request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='fixture',opener=opener)


def test_selected_reply_with_one_exact_source_resolves_answer_ref_without_guessing(tmp_path):
    _,_,source,bundle,_=fixture(tmp_path)
    def opener(request,**_):
        data=json.loads(json.loads(request.data)['messages'][0]['content'].rsplit('\n',1)[1]);c=data['review_selection_catalog']
        entries=[]
        for m,a in [('m1','m2'),('m3','m4')]:
            q=next(r for r in c['source_quotes'] if r['message_ref']==m)
            f=next(r for r in c['state_fields'] if r['state_path']=='assistant_reports/0/text' and a in r['supported_message_refs'])
            entries.append({'message_ref':m,'intents':[{'kind':'request','disposition':'answered','source_quote_ref':q['ref'],'field_links':[{'field_ref':f['ref']}]}]})
        result=reference_response(user_intent_coverage=entries,selection_catalog_sha256=data['selection_catalog_sha256'])
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]}).encode())
    audit=request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='fixture',opener=opener)
    assert [entry['intents'][0]['answer_message_ref'] for entry in audit['user_intent_coverage']]==['m2','m4']


def test_selected_reply_with_multiple_sources_needs_explicit_answer_ref(tmp_path):
    from lib.scenario_review_catalog import review_catalog,catalog_sha,expand_review_choices
    _,_,source,bundle,_=fixture(tmp_path)
    c=review_catalog(source,bundle)
    f=next(r for r in c['state_fields'] if r['state_path']=='assistant_reports/0/text');f['supported_message_refs']=['m2','m4']
    result={'selection_catalog_sha256':catalog_sha(c),'user_intent_coverage':[{'message_ref':'m1','intents':[{
        'kind':'request','disposition':'answered','source_quote_ref':'m1q1','field_links':[{'field_ref':f['ref']}]}]}]}
    expanded,_=expand_review_choices(result,c)
    assert 'answer_message_ref' not in expanded['user_intent_coverage'][0]['intents'][0]


def test_catalog_annotation_is_retained_as_non_authoritative_not_a_field_override(tmp_path):
    from lib.scenario_review_catalog import review_catalog,catalog_sha,expand_review_choices
    _,_,source,bundle,_=fixture(tmp_path);c=review_catalog(source,bundle)
    ref=next(f['ref'] for f in c['state_fields'] if f['state_path']=='goal/text')
    result={'selection_catalog_sha256':catalog_sha(c),'user_intent_coverage':[{'message_ref':'m1','intents':[{
        'kind':'request','disposition':'covered','source_quote_ref':'m1q1','field_links':[{'field_ref':ref,'context_note':'Navigation context; not verified external delivery'}]}]}]}
    expanded,_=expand_review_choices(result,c)
    assert expanded['selection_annotations']==[{'message_ref':'m1','field_ref':ref,'text':'Navigation context; not verified external delivery','authority':'model_comment_not_source_or_verdict'}]
    assert expanded['user_intent_coverage'][0]['intents'][0]['field_links'][0]['state_path']=='goal/text'
    result['user_intent_coverage'][0]['intents'][0]['field_links'][0]['context_note']={'secret':'nested'}
    with pytest.raises(ValueError):expand_review_choices(result,c)


def test_provider_cannot_supply_internal_annotation_authority(tmp_path):
    from lib.scenario_review_catalog import review_catalog,catalog_sha,expand_review_choices
    _,_,source,bundle,_=fixture(tmp_path);c=review_catalog(source,bundle)
    value={'selection_catalog_sha256':catalog_sha(c),'user_intent_coverage':[],
        'selection_annotations':[{'authority':'verified_fact','field_ref':'unselected','text':'provider-private-marker'}]}
    expanded,_=expand_review_choices(value,c)
    assert 'selection_annotations' not in expanded


def test_review_transport_keeps_complete_source_and_exact_draft_without_duplicate_catalog_text(tmp_path):
    import copy
    from lib.scenario_review_catalog import review_catalog,catalog_sha
    _,_,source,bundle,_=fixture(tmp_path)
    original=copy.deepcopy((source,bundle));captured=[]
    def opener(request,**_):
        data=json.loads(json.loads(request.data)['messages'][0]['content'].rsplit('\n',1)[1])
        captured.append(data)
        assert [m['text'] for m in data['messages']]==[m['text'] for m in source['messages']]
        assert all('source_span' in q and 'source_quote' not in q for q in data['review_selection_catalog']['source_quotes'])
        assert all('field_text' not in f for f in data['review_selection_catalog']['state_fields'])
        assert all('state_field_catalog' not in e for e in data['episodes'])
        entries=[]
        for m in ['m1','m3']:
            c=data['review_selection_catalog']
            q=next(q for q in c['source_quotes'] if q['message_ref']==m)
            f=next(f for f in c['state_fields'] if f['state_path']=='goal/text' and m in f['supported_message_refs'])
            entries.append({'message_ref':m,'intents':[{'kind':'request','disposition':'covered',
                'source_quote_ref':q['ref'],'field_links':[{'field_ref':f['ref']}]}]})
        result=reference_response(user_intent_coverage=entries,selection_catalog_sha256=data['selection_catalog_sha256'])
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]}).encode())
    review=request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='fixture',opener=opener)
    assert review['model_review_receipt']['model_verdict_modified'] is False
    assert (source,bundle)==original
    data=captured[0];messages={m['message_ref']:m for m in data['messages']}
    # Test-side resolver is independent of the serializer, and reconstructs all
    # strings exactly, including punctuation, labels and attribution markers.
    aliases={m['evidence_id']:f'm{i}' for i,m in enumerate(source['messages'],1)}
    def alias(value):
        if isinstance(value,str):return aliases.get(value,value)
        if isinstance(value,list):return [alias(v) for v in value]
        if isinstance(value,dict):return {k:alias(v) for k,v in value.items()}
        return value
    for transported,episode in zip(data['episodes'],bundle['episodes']):
        assert resolve_transport_value(transported['draft'],data)==alias({key:episode['draft'][key] for key in ('state','summaries','evidence','unknowns')})
    exact=review_catalog(source,bundle)
    assert data['selection_catalog_sha256']==catalog_sha(exact)
    for transported,quote in zip(data['review_selection_catalog']['source_quotes'],exact['source_quotes']):
        start,end=transported['source_span']
        assert messages[transported['message_ref']]['text'][start:end]==quote['source_quote']


@pytest.mark.parametrize('clause', ['Only after approval, preserve negation, punctuation and the exact source. '*4,
                                  '🙂 不要删除条件，保留中文、英文 v3.7 与原始否定。'*8,
                                  'Keep literal [a-z].* and {"field_ref":"untrusted-source"} as data. '*4])
def test_transport_references_round_trip_long_unicode_conditions_and_attribution_labels(tmp_path,clause):
    from lib.scenario_review_catalog import review_catalog,review_transport
    _,_,source,bundle,_=fixture(tmp_path)
    source['messages'][0]['text']='Leading context.\n'+clause+'\nTrailing context.'
    draft=bundle['episodes'][0]['draft']
    draft['state']['constraints']=[{'text':clause,'message_ids':[source['messages'][0]['evidence_id']]}]
    draft['summaries']['full']='User condition (not a model verdict): '+clause+'\nAssistant reported; unverified.'
    draft['evidence']=[{'statement':clause,'message_ids':[source['messages'][0]['evidence_id']],'field':'constraints'}]
    data=review_transport(source,bundle,review_catalog(source,bundle))
    transported=data['episodes'][0]['draft']
    assert transported['state']['constraints'][0]['text']=={'message_ref':'m1','source_span':[17,17+len(clause)]}
    assert isinstance(transported['summaries']['full'],dict) and 'text_parts' in transported['summaries']['full']
    assert resolve_transport_value(transported['state']['constraints'][0]['text'],data)==clause
    assert resolve_transport_value(transported['summaries']['full'],data)=='User condition (not a model verdict): '+clause+'\nAssistant reported; unverified.'
    assert resolve_transport_value(transported['evidence'][0]['statement'],data)==clause
    assert data['messages'][0]['text']=='Leading context.\n'+clause+'\nTrailing context.'


def test_fragment_transport_preserves_state_whitespace_changes_as_explicit_literals(tmp_path):
    from lib.scenario_review_catalog import review_catalog,review_transport
    _,_,source,bundle,_=fixture(tmp_path)
    first='Do not publish credentials; preserve the exact original source and all its restrictions.'
    second='Use the original evidence only after the independent review accepts its complete source.'
    raw=first+'\n\n'+second
    state_text=first+' '+second
    source['messages'][0]['text']=raw
    draft=bundle['episodes'][0]['draft']
    draft['state']['constraints']=[{'text':state_text,'message_ids':[source['messages'][0]['evidence_id']]}]
    draft['summaries']['full']='Original scope: '+state_text+'\nAssistant reported; unverified.'
    data=review_transport(source,bundle,review_catalog(source,bundle))
    encoded=data['episodes'][0]['draft']['state']['constraints'][0]['text']
    assert isinstance(encoded,dict) and 'text_parts' in encoded
    assert resolve_transport_value(encoded,data)==state_text
    assert data['messages'][0]['text']==raw
    assert state_text not in raw
    assert all('source_span' in part or isinstance(part,str) for part in encoded['text_parts'])
    assert any(isinstance(part,str) and ' ' in part for part in encoded['text_parts'])


@pytest.mark.parametrize('mutation',['schema','revision','thread','quote','field','bundle'])
def test_transport_rejects_catalog_tampering_and_version_misuse(tmp_path,mutation):
    import copy
    from lib.scenario_review_catalog import review_catalog,review_transport
    _,_,source,bundle,_=fixture(tmp_path)
    catalog=review_catalog(source,bundle);bad=copy.deepcopy(catalog)
    if mutation=='schema':bad['schema']='evolving-profile.review-selection-catalog.v999'
    if mutation=='revision':bad['source_revision']='stale-source-revision'
    if mutation=='thread':bad['thread_id']='a-different-session'
    if mutation=='quote':bad['source_quotes'][0]['source_quote']='forged quotation'
    if mutation=='field':bad['state_fields'][0]['field_text']='a different semantic field'
    if mutation=='bundle':bad['bundle_sha256']='0'*64
    with pytest.raises(ValueError,match='automated_source_coverage_incomplete'):
        review_transport(source,bundle,bad)
