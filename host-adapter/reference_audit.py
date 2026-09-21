"""Read-only projections and output receipts, never a second knowledge store."""
import datetime as dt
import json
import os
from pathlib import Path
import tempfile
import uuid

ROOT=Path.home()/'.evolving-profile/memory-os'

def record_source_stdout(value,root=ROOT/'source-search-receipts'):
    if value.get('mode')!='literal_original_source_search':raise ValueError('wrong source audit mode')
    spans=[{k:s.get(k) for k in ('chunk_id','document_id','span_start','span_end','source_sha256','anchor_memory_id')}
        for s in value.get('items',[])]
    row={'kind':'original_source_output','at':dt.datetime.now(dt.timezone.utc).isoformat(),
        'source_search_id':value.get('source_search_id'),'terms':value.get('terms'),
        'role':value.get('role'),'source_spans':spans,'source_span_count':len(spans),
        'source_anchor_ids':list(dict.fromkeys(s['anchor_memory_id'] for s in spans if s.get('anchor_memory_id'))),
        'has_more':bool(value.get('next_cursor')),'delivery_stage':'mcp_stdout_write_completed',
        'host_visibility':'unknown','model_context_visibility':'unknown','answer_use':'not_measured'}
    root=Path(root);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,tmp=tempfile.mkstemp(dir=root,prefix='.pending-')
    try:
        with os.fdopen(fd,'w') as f:json.dump(row,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
        os.replace(tmp,root/(uuid.uuid4().hex+'.json'))
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return row

def record_prompt_output(value,root=ROOT/'source-prompt-receipts'):
    from source_safety import mask_value
    from evidence_workspace import _save
    value=mask_value(dict(value));value.pop('context',None)
    if value.get('execution_mode') in {'replay','shadow_replay','cassette_replay'}:
        root=Path(root).parent/'replay-source-prompt-receipts'
    if value.get('profile'):value['profile'].pop('context',None)
    _save(Path(root)/(uuid.uuid4().hex+'.json'),value)

def link_prompt_research(prompt,research_rows):
    """Join only observed host receipts for the exact session AND turn.

    Keep the original Hook's pending Full Prompt unchanged: later queries are
    evidence of host interpretation, not a rewritten historical Hook output.
    """
    result=dict(prompt);matched=[];ids=[];queries=[]
    session=prompt.get('session_id');turn=prompt.get('turn_id')
    if session and turn:
        for research in research_rows:
            receipts=[r for r in research.get('host_receipts',[])
                if r.get('session_id')==session and r.get('turn_id')==turn]
            if not receipts:continue
            observed=list(dict.fromkeys(mid for r in receipts for mid in r.get('record_ids',[])))
            count=research.get('discovered_count')
            matched.append({'research_id':research.get('research_id'),'query':research.get('query'),
                'record_ids':observed,'discovered_count':count,
                'undelivered_candidate_count':max(0,count-len(observed)) if isinstance(count,int) else None,
                'host_receipts':receipts})
            ids.extend(observed)
            if research.get('query'):queries.append(research['query'])
    result.update(observed_research=matched,observed_host_queries=list(dict.fromkeys(queries)),
        host_tool_response_record_ids=list(dict.fromkeys(ids)),
        host_tool_response_record_count=len(set(ids)) if matched else None,
        historical_search_observation='host_tool_response_observed' if matched else 'not_observed_in_audit_window',
        model_context_visibility='unknown',answer_use='not_measured')
    return result

def snapshot(profile_root=ROOT/'profile/receipts',source_root=ROOT/'source-search-receipts',prompt_root=ROOT/'source-prompt-receipts',research_rows=()):
    errors=[]
    def read(root,kind):
        rows=[]
        for path in sorted(Path(root).glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:30]:
            try:
                if path.stat().st_size>256*1024:raise ValueError('oversize receipt')
                row=json.loads(path.read_text())
                if row.get('kind')!=kind:raise ValueError('unrecognized receipt kind')
                if row.get('execution_mode') in {'replay','shadow_replay','cassette_replay'}:continue
                row.pop('context',None)
                # A server-side receipt cannot assert model/receiver visibility.
                row.update(host_visibility='unknown',model_context_visibility='unknown',answer_use='not_measured')
                rows.append(row)
            except (OSError,ValueError,TypeError) as e:errors.append({'file':path.name,'error_type':type(e).__name__})
        return rows
    return {'profile_receipts':read(profile_root,'source_backed_preference_view'),
        'guidance_receipts':read(ROOT/'guidance-receipts','mcp_guidance_output'),
        'source_receipts':read(source_root,'original_source_output'),
        'prompt_receipts':[link_prompt_research(p,research_rows) for p in read(prompt_root,'source_driven_prompt')],
        'errors':errors,'host_visibility':'unknown',
        'boundary':'默认视图按来源依赖审计；原文按片段计数，不等于事实数。这里只确认脚本输出，不宣称宿主接收或模型使用。'}
