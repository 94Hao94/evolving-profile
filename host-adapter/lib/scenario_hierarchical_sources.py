"""Exact original-source pages and request-bound selections; no semantic verdict."""
from copy import deepcopy
from .scenario_evidence_capsule import restore_capsules
from .scenario_raw_readback import read_materialized_page


def merge_source_reader(snapshot,capsule,root,permission_getter,max_chars):
    restored=restore_capsules(capsule)
    rows={r['atom_id']:r for values in restored.values() for r in values}
    units={u['unit_id']:u for u in snapshot['units']};cache={}
    def read(ids):
        pages={}
        for identity in ids:
            for ref in rows[identity]['source_refs']:
                unit=units[ref['unit_id']]
                if unit['role']!=ref['role'] or unit['raw_line_sha256']!=ref['raw_line_sha256']:
                    raise ValueError('merge_source_identity_changed')
                start,end=ref.get('message_start'),ref.get('message_end')
                if type(start) is not int or type(end) is not int:start,end=0,len(unit['text'])
                if not 0<=start<end<=len(unit['text']):raise ValueError('merge_source_range_invalid')
                for offset in range(start,end,max_chars):
                    chars=min(max_chars,end-offset);key=(unit['unit_id'],offset,chars)
                    if key not in cache:
                        page=read_materialized_page(snapshot,unit_id=unit['unit_id'],text_offset=offset,
                            max_chars=chars,permission=permission_getter(),coverage_root=root)
                        page['sequence']=unit['sequence'];cache[key]=page
                    page=cache[key];pages[page['page_id']]=page
        return sorted(pages.values(),key=lambda p:(p['sequence'],p['text_offset']))
    return read


def expand_source_selections(value,request):
    if request['stage'] not in {'merge','readback'}:return value
    pages={p['page_id']:p for p in request['inputs'].get('source_pages',[]) if p.get('source_readback') is True}
    def expand(row):
        if isinstance(row,list):return [expand(v) for v in row]
        if not isinstance(row,dict):return row
        if 'page_id' in row and 'source_selection' in row:
            page=pages.get(row['page_id']) if isinstance(row['page_id'],str) else None
            if (row['source_selection']!='entire_page' or set(row)!={'page_id','source_selection'}
                    or page is None or not isinstance(page.get('text'),str) or not page['text'].strip()):
                raise ValueError('relation_source_selector_invalid')
            return {'page_id':row['page_id'],'quote':page['text'],'offset_binding':'host_selected_entire_page'}
        return {k:expand(v) for k,v in row.items()}
    return expand(deepcopy(value))
