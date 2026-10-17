"""Bounded current-protocol navigation; source reading remains independent."""
import base64
import json
from pathlib import Path
from .scenario_coverage_contract import canonical,fingerprint,hierarchical_protocol_fingerprint
from .scenario_coverage_store import CoverageStore
from .scenario_hierarchical_store import HierarchicalStore
from .scenario_raw_readback import read_materialized_page
from .scenario_hierarchical_safety import mark_summary_boundary


def read_hierarchical_view(root,sid,view,*,cursor,permission,expected_scope,requirement_id,expected_review_binding=None):
    from .scenario_coverage_read import _read
    root=Path(root)
    if expected_review_binding is None and root.parent.name=='context':
        from .scenario_coverage_provider import current_review_identity
        try:expected_review_binding=current_review_identity(root.parent.parent)
        except (OSError,ValueError,TypeError):expected_review_binding={'provider':{'status':'unknown_current_configuration'}}
    if view not in {'overview','requirements','relations','source'}:raise ValueError('coverage_view_invalid')
    try:
        status=_read(root/'status'/f'{sid}.json',1024*1024)
        store=CoverageStore(root/'coverage.sqlite3',readonly=True);snap=store.read(status['snapshot_id'])
    except (FileNotFoundError,ValueError):return {'status':'unavailable','reason':'coverage_not_prepared','source_readback':False,'coverage_contract':'hierarchical_review.v1'}
    if not store.validate_snapshot(snap['snapshot_id'],permission)['valid']:raise ValueError('coverage_cursor_stale_source_or_permission')
    if expected_scope and any(snap['scope'].get(k)!=v for k,v in expected_scope.items()):raise ValueError('coverage_scope_changed')
    graph={};stale=False
    try:
        saved=HierarchicalStore(root/'hierarchical/graphs.sqlite3',readonly=True).load_current(snap['scope'],permission)
        if saved['binding']['snapshot_id']==snap['snapshot_id'] and saved['binding']['generation']==snap['generation']:
            graph=saved['graph']
            if saved['binding'].get('protocol_fingerprint')!=hierarchical_protocol_fingerprint():stale=True
            if expected_review_binding is not None and any(saved['binding'].get(k)!=v for k,v in expected_review_binding.items()):stale=True
            expected=status.get('hierarchical_binding_fingerprint')
            if expected and fingerprint(saved['binding'])!=expected:stale=True
        else:stale=True
    except ValueError as error:
        if str(error)!='hierarchical_unavailable':raise
    rows=[*graph.get('atoms',[]),*graph.get('residuals',[]),*graph.get('candidate_atoms',[]),*graph.get('candidate_residuals',[])] if not stale else []
    if snap['source_manifest_complete']:
        inventory=_read(root/'inventories'/(snap['snapshot_id']+'.json'),64*1024*1024)
        if inventory['generation']!=snap['generation']:raise ValueError('coverage_inventory_stale')
        covered={}
        for row in rows:
            for ref in row['source_refs']:
                if type(ref.get('normalized_start')) is int and type(ref.get('normalized_end')) is int:
                    covered.setdefault(ref['unit_id'],[]).append((ref['normalized_start'],ref['normalized_end']))
        for r in inventory['requirements']['requirements']:
            at=0
            for start,end in sorted(covered.get(r['unit_id'],[])):
                if start>at:break
                at=max(at,end)
            if at<len(r['text']):
                rows.append({'atom_id':r['requirement_id'],'source_quote':r['text'],'kind':'unclassified_user_message',
                    'source_refs':[{'unit_id':r['unit_id']}],'semantic_review_status':'not_reviewed'})
    binding={'protocol':'hierarchical_review.v1','snapshot_id':snap['snapshot_id'],'generation':snap['generation'],
        'view':view,'graph_sha256':fingerprint(graph),'requirement_id':requirement_id}
    index=0;offset=0
    if cursor:
        try:
            if not isinstance(cursor,str) or len(cursor)>4096:raise ValueError()
            value=json.loads(base64.urlsafe_b64decode(cursor))
            if not isinstance(value,dict):raise ValueError()
            if any(value.get(k)!=v for k,v in binding.items()):raise ValueError()
            index,offset=value['index'],value['offset']
            if type(index) is not int or type(offset) is not int or min(index,offset)<0:raise ValueError()
        except (ValueError,TypeError,KeyError):raise ValueError('coverage_cursor_stale_or_invalid') from None
    def next_cursor(i,o=0):return base64.urlsafe_b64encode(canonical({**binding,'index':i,'offset':o})).decode()
    coverage=graph.get('coverage',{})
    stale=stale or coverage.get('status')=='stale'
    if stale:
        coverage={**coverage,'status':'stale','target_complete':False,'intent_review':'stale',
            'attribution_review':'stale','scope_review':'stale',
            'obligation_review':'stale','discovery_procedure_coverage':'stale','discovered_obligation_resolution':'stale',
            'unresolved_count':None,'unread_count':None,
            'groups':{key:{**group,'status':'stale'} for key,group in coverage.get('groups',{}).items()}}
    failed=graph.get('failure')
    display_status=('stale' if stale else failed if failed in {'capacity_paused','budget_paused','intent_gap','relation_pending'}
        else 'unavailable' if failed else coverage.get('status','local_candidate'))
    result={'coverage_contract':'hierarchical_review.v1','review_protocol':'hierarchical_review.v1',**binding,
        'status':display_status,'coverage':coverage,
        'source_manifest_complete':snap['source_manifest_complete'],'source_readback':False,
        'raw_source_status':'not_read','host_delivery':'not_measured','answer_use':'not_measured','external_fact_verified':False,
        'scope':snap['scope'],'requirement_count':len(rows),'atom_count':len(graph.get('atoms',[])) if graph else None,
        'has_unread_requirements':bool(rows),'requires_readback':True,'coverage_cursor':None,
        'reason':graph.get('failure') or ('previous_generation_stale' if stale else None),
        'discovery_procedure_coverage':coverage.get('discovery_procedure_coverage','not_reviewed'),
        'cross_scope_exhaustiveness':'not_exhaustive','unresolved_count':coverage.get('unresolved_count'),
        'unread_count':coverage.get('unread_count'),'budget':status.get('budget')}
    result['context_recovery']=[{k:v for k,v in row.items() if k!='pages'} for row in graph.get('context_recovery',[])] if not stale else []
    mark_summary_boundary(result)
    result['capacity_recovery']=graph.get('capacity_recovery') if not stale else None
    result['outcome_notes']=graph.get('outcome_notes',[]) if graph and not stale else None
    result['context_original_pages_materialized']=sum(r.get('materialized_page_reads',0) for r in result['context_recovery']) if graph and not stale else None
    repairs=graph.get('format_repairs',[]);plan=graph.get('plan',{});adaptation=plan.get('transport_adaptation')
    result['processing_diagnostics']=({'format_reselections':len(repairs),
        'repair_model_calls':sum(r.get('repair_model_calls',0) for r in repairs),
        'transport_windows':plan.get('leaf_count'),'max_extract_wire_bytes':adaptation.get('max_extract_wire_bytes') if adaptation else None,
        'source_scope_reduced':adaptation.get('source_scope_reduced') if adaptation else None}
        if graph and not stale else None)
    if view=='requirements':
        if index>len(rows):raise ValueError('coverage_cursor_invalid')
        out=[];used=0
        while index<len(rows) and len(out)<10 and used<4096:
            row=rows[index];text=row['source_quote']
            if offset>len(text):raise ValueError('coverage_cursor_invalid')
            chunk=text[offset:offset+4096-used];used+=len(chunk)
            state=next((r for r in graph.get('states',[]) if r['atom_id']==row['atom_id']),None) if not stale else None
            reviewed=bool(graph and any(row['atom_id'] in ids for ids in graph.get('manifest',{}).get('groups',{}).values()) and not stale)
            disposition='superseded' if state and state['verification']=='source_readback_supported' and state['state']=='historical' else 'covered' if state and state['verification']=='source_readback_supported' and state['state']=='current' else 'unresolved'
            out.append({'requirement_id':row['atom_id'],'text':chunk,'text_offset':offset,'text_total_chars':len(text),
                'kind':row.get('kind','unclassified_user_message'),'status':disposition,'intent_count':1 if reviewed else None,
                'semantic_state':state,'semantic_review_status':'reviewed' if reviewed else 'not_reviewed',
                'scope_review_status':row.get('scope_review_status','not_reviewed') if reviewed else 'not_reviewed',
                'source_locator':{'tool':'read_scenario_summary','scenario_type':'session','scenario_id':'session:'+sid,
                    'coverage_view':'source','coverage_requirement_id':row['atom_id']},'requires_source_readback':True})
            mark_summary_boundary(out[-1])
            offset+=len(chunk)
            if offset<len(text):break
            index+=1;offset=0
        result.update(requirements=out,requirements_total=len(rows),coverage_cursor=next_cursor(index,offset) if index<len(rows) else None,
            has_unread_requirements=index<len(rows),reading_state_scope='this_response_not_host_attention_or_prior_pages')
    elif view=='relations':
        relations=coverage.get('obligations',graph.get('obligations',[]))
        if index>len(relations):raise ValueError('coverage_cursor_invalid')
        out=[];used=0
        while index<len(relations) and len(out)<20 and used<4096:
            r=relations[index];text=r['reason']
            if offset>len(text):raise ValueError('coverage_cursor_invalid')
            chunk=text[offset:offset+min(512,4096-used)];used+=len(chunk)
            out.append({'type':'obligation','from':r['atom_ids'][0],'to':r['atom_ids'][-1],
                'atom_ids':r['atom_ids'],'state':r['state'],'evidence_quote':chunk,'detail_offset':offset,
                'has_unread_relation_details':offset+len(chunk)<len(text)})
            offset+=len(chunk)
            if offset<len(text):break
            index+=1;offset=0
        result.update(relations=out,relations_total=len(relations),relations_coverage=coverage.get('obligation_review','not_reviewed'),
            coverage_cursor=next_cursor(index,offset) if index<len(relations) else None)
    elif view=='source':
        row=next((r for r in rows if r['atom_id']==requirement_id),None)
        if row is None:raise ValueError('source_requirement_scope_unverified')
        units=list(dict.fromkeys(r['unit_id'] for r in row['source_refs']))
        if index>=len(units):raise ValueError('coverage_cursor_invalid')
        page=read_materialized_page(snap,unit_id=units[index],text_offset=offset,max_chars=4096,permission=permission,coverage_root=root)
        i,o=(index,page['next_offset']) if page['next_offset'] is not None else (index+1,0)
        result.update(raw_source_status='source_read' if page['source_readback'] else 'source_empty',
            raw_source={'text':page['text'],'locators':[{k:page[k] for k in ('raw_line_sha256','role','turn_id','text_offset')}],
                'source_type':'codex_thread_history'},source_readback=page['source_readback'],
            raw_source_coverage={'partial':i<len(units),'text_total_chars':page['text_total_chars']},
            coverage_cursor=next_cursor(i,o) if i<len(units) else None)
        result.update(constraint_use='original_source_page_not_verified_outcome',
            record_source_complete_in_response=index==0 and offset==0 and i==len(units) and page['source_readback'])
    if len(canonical(result))>192*1024:raise ValueError('coverage_page_serialized_limit')
    return result
