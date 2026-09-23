"""Source-role and derivation checks for guidance, never execution authority."""
from __future__ import annotations
import hashlib,json,re,time,urllib.request,urllib.parse
from pathlib import Path

REGISTRY=Path.home()/'.evolving-profile/control-plane/guidance-source-review.json'
_CACHE={}

def _normalize(value):
    return ''.join(re.findall(r'[\w\u3400-\u9fff]+',str(value or '').casefold()))

def directive_user_spans(source):
    plain=re.sub(r'<evolving_profile_midtask_journal>.*?(?:</evolving_profile_midtask_journal>|\Z)','',str(source or ''),flags=re.S)
    spans=re.findall(r'^\[role:\s*user\]\s*\n(.*?)^\[user:end\]',plain,re.M|re.S)
    # A question about a hypothetical user's preference is not adoption of it.
    return [span for span in spans if not (re.search(r'(?:如果|当用户|用户要求|某人要求)',span) and re.search(r'(?:属于什么|哪类.*观察|如何影响|应该怎样|怎样归纳|什么.*偏好)',span))]

def classify_directive_source(source,claim,*,origin=None):
    digest=hashlib.sha256(str(source or '').encode()).hexdigest()
    result={'source_sha256':digest,'human_author_verified':False}
    if origin in {'test_probe','diagnostic','fixture','benchmark','agent_generated_test'}:
        return dict(result,status='synthetic_source',reason='原始发生记录标记为自动测试，user角色不能提升为用户政策。')
    source=str(source or '')
    # Journals may embed prompts sent by agents to other test tasks. They
    # remain event evidence, never a human-authored instruction span.
    plain=re.sub(r'<evolving_profile_midtask_journal>.*?(?:</evolving_profile_midtask_journal>|\Z)','',source,flags=re.S)
    all_users=re.findall(r'^\[role:\s*user\]\s*\n(.*?)^\[user:end\]',plain,re.M|re.S)
    users=directive_user_spans(source)
    target=_normalize(claim)
    matched=[]
    for span in users:
        normalized=_normalize(span)
        anchors={target[i:i+10] for i in range(max(0,len(target)-9)) if target[i:i+10] in normalized}
        if (len(target)>=6 and target in normalized) or len(anchors)>=3:
            matched.append(span)
    if matched:
        return dict(result,status='user_attributed',reason='原始片段中存在支持该指示的user角色范围；不独立认证真人身份。',
                    matched_user_spans=matched,attribution='stored_user_role')
    if all_users and not users:
        return dict(result,status='quoted_scenario',reason='原文是在分析假设或引用中的用户要求，不代表当前发言者采纳该偏好。')
    if re.search(r'^\[role:\s*user\]',plain,re.M) and not all_users:
        return dict(result,status='needs_source_review',reason='当前片段的user范围不完整；须回读所属文档，不能当作非用户来源。')
    if '<evolving_profile_midtask_journal>' in source and any(x in source for x in ('send_message_to_thread','create_thread','测试题','test_probe')) and not users:
        return dict(result,status='synthetic_source',reason='来源是智能体生成或发送测试问题的过程记录。')
    if not users:
        return dict(result,status='non_user_source' if source else 'missing_source',reason='没有可支持用户直接指示的原始user范围。')
    return dict(result,status='needs_source_review',reason='存在user范围，但未证明该政策归属于该范围。')

def propagate_source_restrictions(nodes,roots):
    restricted={key:dict(value,blocked_ancestors=[key]) for key,value in roots.items()}
    while True:
        changed=False
        for key,row in nodes.items():
            ancestors=sorted({a for parent in row.get('source_memory_ids') or [] for a in restricted.get(parent,{}).get('blocked_ancestors',[])})
            if ancestors and key not in roots and ancestors!=restricted.get(key,{}).get('blocked_ancestors'):
                restricted[key]={'status':'derived_source_review_required','blocked_ancestors':ancestors};changed=True
        if not changed:break
    return restricted

def registry(path=REGISTRY):
    path=Path(path)
    key=str(path)
    entries=_CACHE.setdefault('entries',{})
    try:
        stamp=path.stat().st_mtime_ns
        entry=entries.get(key,{})
        if entry.get('stamp')!=stamp:
            entry={'stamp':stamp,'data':json.loads(path.read_text())}
            entries[key]=entry
        if path==REGISTRY:_CACHE.update(stamp=stamp,data=entry.get('data') or {})
        return entry.get('data') or {}
    except (OSError,ValueError):
        return (entries.get(key,{}) .get('data') or _CACHE.get('data') or {})


def registry_revision(path=REGISTRY):
    """Return an exact source-review revision suitable for turn binding."""
    try:
        return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return 'unavailable'

def guidance_source_decision(item, *, review_data=None, review_state=None):
    mid=str(item.get('id') or item.get('chunk_id') or '')
    is_policy=mid.startswith('direct-policy:') or item.get('type')=='direct_policy'
    for prefix in ('direct-policy:','candidate:'):
        if mid.startswith(prefix):mid=mid[len(prefix):]
    data=registry() if review_data is None else dict(review_data or {})
    state=review_state or ('available' if registry_revision()!='unavailable' else ('stale' if data else 'unavailable'))
    item_type=str(item.get('type') or '').casefold()
    is_derived_guidance=is_policy or item_type in {'observation','mental_model','direct_policy'}
    if state == 'unavailable' and is_derived_guidance:
        return {'allowed':False,'record_id':mid,'review':{'status':'source_registry_unavailable'},'reason':'source_registry_unavailable'}
    row=(data.get('restrictions') or {}).get(mid)
    if row and row.get('scope')=='direct_policy_only' and not is_policy:row=None
    model_id=(item.get('metadata') or {}).get('mental_model_id')
    if model_id:
        model=(data.get('model_reviews') or {}).get(model_id,{})
        if model.get('status')=='source_review_required':row=model
    return {'allowed':not bool(row),'record_id':mid,'review':row,'reason':row.get('status') if row else 'no_known_source_restriction',
            'registry_state':state}

def fetch_policy_source(memory_id,bank='personal-memory'):
    base='http://127.0.0.1:12088'
    def get(path):
        with urllib.request.urlopen(base+path,timeout=5) as response:return json.loads(response.read())
    memory=get('/v1/default/banks/'+urllib.parse.quote(bank,safe='')+'/memories/'+urllib.parse.quote(memory_id,safe=''))
    if memory.get('id')!=memory_id or memory.get('state')!='valid':
        return {'status':'source_unavailable','user_spans':[]}
    cid=memory.get('chunk_id')
    if not cid:return {'status':'source_missing','user_spans':[]}
    chunk=get('/v1/default/chunks/'+urllib.parse.quote(cid,safe=''))
    if chunk.get('bank_id')!=bank or chunk.get('document_id')!=memory.get('document_id'):raise ValueError('source identity mismatch')
    text=chunk.get('chunk_text') or ''
    if re.search(r'^\[role:\s*user\]',text,re.M) and '[user:end]' not in text:
        document=get('/v1/default/banks/'+urllib.parse.quote(bank,safe='')+'/documents/'+urllib.parse.quote(memory['document_id'],safe=''))
        if document.get('id')==memory['document_id'] and document.get('bank_id')==bank:text=document.get('original_text') or text
    spans=directive_user_spans(text)
    return {'status':'user_spans_available' if spans else 'no_user_directive_source','user_spans':spans,
            'source_sha256':hashlib.sha256(text.encode()).hexdigest(),'source_text':text}

def check_policy_source_quote(source,decision):
    quote=str(decision.get('source_quote') or '')
    allowed=source.get('status')=='user_spans_available' and bool(decision.get('accept')) and bool(quote) and any(quote in span for span in source.get('user_spans') or [])
    semantic=decision.get('independent_source_review') or {}
    policy_hash=hashlib.sha256(str(decision.get('policy') or '').encode()).hexdigest()
    allowed=allowed and semantic.get('supported') is True and semantic.get('policy_sha256')==policy_hash and semantic.get('source_sha256')==source.get('source_sha256')
    return {'allowed':allowed,'status':'source_checked_provisional' if allowed else 'pending_source_review',
            'source_sha256':source.get('source_sha256'),'source_quote':quote if allowed else '',
            'human_author_verified':False,'reason':'原文范围与引用已核对，身份不作独立认证。' if allowed else '没有可回读的指示来源引用，不能提升为用户政策。'}

def revalidate_model_section(model,section,*,source_reader=None,timeout=.75):
    data=registry();review=(data.get('model_reviews') or {}).get(model.get('id'),{})
    ids=sorted(set(re.findall(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',section)))
    result={'allowed':False,'source_ids':ids,'scope':'cited_sources_only_not_exhaustive_new_evidence','upstream_staleness_preserved':True}
    if not ids or review.get('status')!='source_links_audited' or review.get('content_sha256')!=hashlib.sha256(str(model.get('content') or '').encode()).hexdigest():
        return dict(result,reason='模型版本未审阅、来源链待复核或章节没有明确来源。')
    if source_reader is None:
        def source_reader(mid):
            url='http://127.0.0.1:12088/v1/default/banks/personal-memory/memories/'+mid
            with urllib.request.urlopen(url,timeout=max(.1,timeout)) as response:return json.loads(response.read())
    try:
        for mid in ids:
            current=source_reader(mid);expected=(data.get('source_unit_hashes') or {}).get(mid)
            if current.get('id')!=mid or current.get('state')!='valid' or not guidance_source_decision(current)['allowed'] or not expected or hashlib.sha256(str(current.get('text') or '').encode()).hexdigest()!=expected:
                return dict(result,reason='引用来源已撤回、改变或未完成核对。',failed_source=mid)
    except (OSError,ValueError):return dict(result,reason='引用来源当前不可回读，不能提升为可用指导。')
    return dict(result,allowed=True,reason='章节引用来源仍有效且原文未改；只作为历史指导参考，不证明模型已覆盖全部新增证据。')
