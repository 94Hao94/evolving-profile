"""Small reviewed preference view whose evidence is revalidated on every read.

This is a view, not a new source of user facts or blanket execution authority.
It does not infer human authorship from legacy role markers, or infer absence
of newer conflicting sources from unchanged dependencies.
"""
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request
import urllib.error
import socket
import uuid
from evidence_workspace import source_witness, _save

DEFAULT_MANIFEST=Path.home()/'.evolving-profile/memory-os/profile/view.json'
DEFAULT_RECEIPTS=Path.home()/'.evolving-profile/memory-os/profile/receipts'

def build_view(manifest,bank,get):
    if manifest.get('schema')!=1 or manifest.get('bank')!=bank:raise ValueError('profile bank/schema mismatch')
    entries=manifest.get('entries')
    if not isinstance(entries,list) or len(entries)>8:raise ValueError('profile view resource limit: review a smaller default view explicitly')
    if len({e.get('id') for e in entries})!=len(entries):raise ValueError('duplicate profile entry IDs')
    for entry in entries:
        if not all(isinstance(entry.get(k),str) and entry[k].strip() for k in ('id','text','scope')):raise ValueError('missing profile identity/text/scope')
        if entry.get('classification') not in ('declared_preference','scoped_requirement'):raise ValueError('unreviewed profile classification')
        if not isinstance(entry.get('sources'),list) or not 1<=len(entry['sources'])<=4:raise ValueError('missing or excessive profile dependencies')
        for source in entry['sources']:
            uuid.UUID(source['memory_id'])
            if not all(source.get(k) for k in ('quote','source_sha256','document_id','chunk_id')):raise ValueError('incomplete source witness')
    started=time.monotonic()
    def inspect(entry):
        result={'id':entry['id'],'status':'ready','source_ids':[], 'scope':entry['scope'],'classification':entry['classification']}
        try:
            for source in entry['sources']:
                mid=source['memory_id'];m=get('/v1/default/banks/'+urllib.parse.quote(bank,safe='')+'/memories/'+mid)
                if m.get('id')!=mid or m.get('chunk_id')!=source['chunk_id'] or m.get('document_id')!=source['document_id']:
                    result['status']='source_identity_mismatch';break
                if m.get('state')!='valid':
                    result['status']='source_withdrawn' if m.get('state')=='invalidated' else 'source_validity_unknown';break
                chunk=get('/v1/default/chunks/'+urllib.parse.quote(source['chunk_id'],safe=''))
                if chunk.get('bank_id')!=bank or chunk.get('chunk_id')!=source['chunk_id'] or chunk.get('document_id')!=source['document_id']:
                    result['status']='source_identity_mismatch';break
                text=chunk.get('chunk_text')
                if not isinstance(text,str) or hashlib.sha256(text.encode()).hexdigest()!=source['source_sha256']:
                    result['status']='source_revision_changed';break
                matches=source_witness(text,source['quote'])['quote_matches']
                if not matches or any(m['format_role']!='user' or not m['complete_role_span'] for m in matches):
                    result['status']='not_a_user_source_span';break
                result['source_ids'].append(mid)
            if result['status']=='ready':result['text']=entry['text']
        except Exception as error:
            result.update(status='source_unavailable',error_type=type(error).__name__)
        return result
    with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(inspect,entries))
    ready=[r for r in rows if r['status']=='ready']
    context=''
    if ready:
        lines=['<evolving_profile_preference_view>',
            '来源可回读的默认协作参考；当前用户要求和更高优先级指令优先。只在所列范围适用，不是执行授权。',
            '以下为人工审阅的来源释义，不是用户逐字原话。旧文本 user 标记不证明人类身份；本次仅复查依赖未撤回、原文未改变，未穷尽核对所有新证据。',
            '最近语义审阅：'+str(manifest.get('reviewed_at','unknown'))]
        for r in ready:lines.append(f"- [{r['id']}] 范围：{r['scope']}；{r['text']} 来源：{', '.join(r['source_ids'])}。")
        lines.append('需要跨任务事实或核对变化时，用 Evolving Profile（EP）的 recall/research 检索并用 read_source 核对原文；不要把这份小视图当作完整长期记忆。')
        lines.append('</evolving_profile_preference_view>');context='\n'.join(lines)
    if len(context)>8000:raise ValueError('profile output exceeds 8000 characters; no partial entry was emitted')
    return {'kind':'source_backed_preference_view','bank':bank,'checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),
        'manifest_sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
        'entries':rows,'ready_entry_ids':[r['id'] for r in ready],
        'ready_source_ids':list(dict.fromkeys(mid for r in ready for mid in r['source_ids'])),
        'context':context,'newer_independent_evidence':'not_exhaustively_checked','seconds':time.monotonic()-started,
        'delivery_stage':'prepared_only','host_visibility':'unknown'}

def load_view(bank,manifest_path=DEFAULT_MANIFEST,get=None):
    manifest_path=Path(manifest_path)
    if not manifest_path.exists():return None
    if manifest_path.stat().st_size>256*1024:raise ValueError('oversize profile manifest')
    deadline=time.monotonic()+2.0
    def local_get(path):
        with urllib.request.urlopen('http://127.0.0.1:12088'+path,timeout=min(0.8,max(0.01,deadline-time.monotonic()))) as r:data=r.read(256*1024+1)
        if len(data)>256*1024:raise ValueError('oversize profile source')
        return json.loads(data)
    transport=get or local_get
    def bounded_get(path):
        for attempt in range(2):
            if time.monotonic()>=deadline:raise TimeoutError('profile validation deadline')
            try:return transport(path)
            except (TimeoutError,socket.timeout,urllib.error.URLError) as error:
                transient=isinstance(error,(TimeoutError,socket.timeout)) or isinstance(getattr(error,'reason',None),(TimeoutError,socket.timeout))
                if attempt or not transient or time.monotonic()>=deadline:raise
    return build_view(json.loads(manifest_path.read_text()),bank,bounded_get)

def record_output(report,hook_input,root=DEFAULT_RECEIPTS):
    """Call only after the containing Hook JSON was flushed successfully."""
    if not report:return
    row=dict(report);row.update(delivery_stage='hook_stdout_write_completed',session_id=hook_input.get('session_id'),
        turn_id=hook_input.get('turn_id'),hook_event='SessionStart',source=hook_input.get('source'),host_visibility='unknown')
    _save(Path(root)/(uuid.uuid4().hex+'.json'),row)
