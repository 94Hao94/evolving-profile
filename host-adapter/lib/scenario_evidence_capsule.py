"""Lossless paged evidence transport. A manifest is not semantic approval."""
import json
from .scenario_coverage_contract import canonical, fingerprint


def build_capsules(binding, atoms, residuals, leaf_receipts, limits, *, claims=()):
    size=limits['partition_input_tokens']
    if type(size) is not int or size<4:raise ValueError('capsule_capacity_invalid')
    seen=set();owners=[];pages=[]
    for kind,items in [('atoms',atoms),('residuals',residuals),('assistant_claims',claims)]:
        for item in items:
            identity=item.get('atom_id')
            if not isinstance(identity,str) or identity in seen:raise ValueError('capsule_duplicate_or_missing_owner')
            seen.add(identity);text=canonical(item).decode();chunks=[];chars=[];used=0
            for char in text:
                n=len(char.encode())
                if used+n>size:chunks.append(''.join(chars));chars=[];used=0
                chars.append(char);used+=n
            if chars:chunks.append(''.join(chars))
            owner={'atom_id':identity,'kind':kind,'content_sha256':fingerprint(item),'page_count':len(chunks)}
            owners.append(owner)
            for i,chunk in enumerate(chunks):
                pages.append({'atom_id':identity,'fragment':i,'total':len(chunks),'text':chunk,'text_sha256':fingerprint(chunk)})
    value={'binding':binding,'owners':owners,'pages':pages,'leaf_receipt_ids':[
        r.get('request_sha256') for r in leaf_receipts], 'semantic_acceptance':False}
    return {**value,'manifest_sha256':fingerprint(value)}


def restore_capsules(value):
    try:
        if fingerprint({k:v for k,v in value.items() if k!='manifest_sha256'})!=value['manifest_sha256']:
            raise ValueError('capsule_manifest_changed')
        result={'atoms':[],'residuals':[],'assistant_claims':[]};seen=set();consumed=0
        for owner in value['owners']:
            identity=owner['atom_id'];pages=[p for p in value['pages'] if p['atom_id']==identity]
            if (identity in seen or owner['kind'] not in result or len(pages)!=owner['page_count']
                    or [p['fragment'] for p in pages]!=list(range(len(pages)))
                    or any(p['total']!=len(pages) or p['text_sha256']!=fingerprint(p['text']) for p in pages)):
                raise ValueError('capsule_pages_incomplete')
            item=json.loads(''.join(p['text'] for p in pages))
            if item.get('atom_id')!=identity or fingerprint(item)!=owner['content_sha256']:raise ValueError('capsule_content_changed')
            result[owner['kind']].append(item);seen.add(identity);consumed+=len(pages)
        if consumed!=len(value['pages']):raise ValueError('capsule_unknown_page')
        return result
    except (KeyError,TypeError,IndexError):raise ValueError('capsule_invalid') from None
