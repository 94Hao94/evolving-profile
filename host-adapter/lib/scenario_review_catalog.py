"""Exact review choices, not model judgments or synthesized evidence."""
from __future__ import annotations
import copy,hashlib,json,re
from difflib import SequenceMatcher
from .scenario_state_v3 import whole_user_clauses,state_field_catalog


def review_source_layer(source):
    """The mandatory raw-message and quote-directory transport, independent of drafts."""
    aliases={m['evidence_id']:f'm{i}' for i,m in enumerate(source['messages'],1)}
    messages=[{'message_ref':aliases[m['evidence_id']],**{key:m.get(key) for key in ('role','text','turn_id','at')}}
              for m in source['messages']]
    quotes=[];transport_quotes=[]
    for message in source['messages']:
        if message['role']!='user':continue
        clauses=whole_user_clauses(message['text'])
        # Clause parsing normalizes whitespace for state validation. Review
        # quotes must still be contiguous bytes from the original user text.
        candidates=[message['text']]
        for clause in clauses:
            match=re.search(r'\s+'.join(re.escape(word) for word in clause.split()),message['text'])
            if match:candidates.append(match.group())
        candidates=list(dict.fromkeys(candidates))
        for index,text in enumerate(candidates,1):
            quotes.append({'ref':f"{aliases[message['evidence_id']]}q{index}",'message_ref':aliases[message['evidence_id']],
                           'source_quote':text,'whole_clause':' '.join(text.split()) in clauses})
            start=message['text'].find(text)
            transport_quotes.append({key:value for key,value in quotes[-1].items() if key!='source_quote'}|
                                    {'source_span':[start,start+len(text)]})
    return {'aliases':aliases,'messages':messages,'source_quotes':quotes,'transport_source_quotes':transport_quotes}


def mandatory_source_review_lower_bound(source):
    """A proven request-content lower bound, or unknown for ineligible shape.

    Every field counted here is emitted by review_transport from this same
    source layer. No draft, state field, prompt instruction or guessed overhead
    contributes to the proof; omitting those only makes this bound smaller.
    """
    if (not isinstance(source,dict) or source.get('status')!='complete'
            or not source.get('source_revision') or not source.get('thread_id')
            or not isinstance(source.get('messages'),list) or not source['messages']):return None
    if any(not isinstance(m,dict) or not isinstance(m.get('evidence_id'),str)
           or not isinstance(m.get('text'),str) or m.get('role') not in {'user','assistant'} for m in source['messages']):return None
    layer=review_source_layer(source)
    return len(json.dumps({'messages':layer['messages'],'review_selection_catalog':{
        'source_quotes':layer['transport_source_quotes']}},ensure_ascii=False))


def review_catalog(source,bundle):
    layer=review_source_layer(source);aliases=layer['aliases'];quotes=layer['source_quotes'];fields=[]
    for index,episode in enumerate(bundle['episodes'],1):
        for n,field in enumerate(state_field_catalog(source,episode['draft'],aliases),1):
            fields.append({'ref':f'e{index}f{n}','episode_ref':f'e{index}',**field})
    from .scenario_model import fingerprint_episode_bundle
    value={'schema':'evolving-profile.review-selection-catalog.v1',
           'thread_id':source['thread_id'],'source_revision':source['source_revision'],
           'bundle_sha256':fingerprint_episode_bundle(bundle),'source_quotes':quotes,'state_fields':fields}
    return value


def catalog_sha(catalog):
    return hashlib.sha256(json.dumps(catalog,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def review_transport(source,bundle,catalog):
    """Lossless transport references; raw source and review authority stay intact.

    The local full catalog remains the response binding/expansion authority.
    Only redundant strings in the request are represented by exact spans and
    state paths; this makes no source-selection or semantic review decision.
    """
    from .memory_recovery_scenario import CoverageError
    if catalog!=review_catalog(source,bundle):
        raise CoverageError('review_catalog_binding_mismatch')
    layer=review_source_layer(source);aliases=layer['aliases'];messages=layer['messages']
    by_ref={m['message_ref']:m for m in messages}
    def alias(value):
        if isinstance(value,str):return aliases.get(value,value)
        if isinstance(value,list):return [alias(v) for v in value]
        if isinstance(value,dict):return {k:alias(v) for k,v in value.items()}
        return value
    def smaller(original,encoded):
        return encoded if len(json.dumps(encoded,ensure_ascii=False))<len(json.dumps(original,ensure_ascii=False)) else original
    def source_parts(text,mrefs):
        # Copy only exact raw matching blocks. Every differing character,
        # including normalized state whitespace, remains an explicit literal.
        # This is a representation of the existing state/summary, never a claim
        # that a normalized string is a verbatim source quotation.
        best=text
        if len(text)<80:return best
        for mref in mrefs:
            raw=by_ref[mref]['text'];parts=[];start=0
            for block in SequenceMatcher(None,text,raw,autojunk=True).get_matching_blocks():
                if block.size<48:continue
                if block.a>start:parts.append(text[start:block.a])
                parts.append({'message_ref':mref,'source_span':[block.b,block.b+block.size]})
                start=block.a+block.size
            if start<len(text):parts.append(text[start:])
            best=smaller(best,{'text_parts':parts})
        return best
    quotes=layer['transport_source_quotes']
    fields=[{key:value for key,value in field.items() if key!='field_text'} for field in catalog['state_fields']]
    episodes=[]
    for index,episode in enumerate(bundle['episodes'],1):
        eref=f'e{index}'
        local=[f for f in catalog['state_fields'] if f['episode_ref']==eref]
        text_refs={}
        for field in local:text_refs.setdefault(field['field_text'],field['ref'])
        def field_text(text):
            if text in text_refs:return smaller(text,{'field_ref':text_refs[text]})
            return text
        long_texts=sorted((text for text in text_refs if len(text)>=24),key=len,reverse=True)
        pattern=re.compile('|'.join(re.escape(text) for text in long_texts)) if long_texts else None
        def summary_text(text):
            mrefs=[aliases[mid] for mid in episode['message_ids']]
            if pattern is None:return source_parts(text,mrefs)
            parts=[];start=0
            for match in pattern.finditer(text):
                if match.start()>start:parts.append(text[start:match.start()])
                parts.append({'field_ref':text_refs[match.group()]});start=match.end()
            if start<len(text):parts.append(text[start:])
            by_field=smaller(text,{'text_parts':parts})
            by_source=source_parts(text,mrefs)
            return smaller(by_field,by_source)
        draft=alias({key:episode['draft'].get(key) for key in ('state','summaries','evidence','unknowns')})
        for field in local:
            node=draft['state'];path=field['state_path'].split('/')
            for key in path[:-1]:node=node[int(key)] if isinstance(node,list) else node[key]
            text=node[path[-1]]
            node[path[-1]]=source_parts(text,field['supported_message_refs'])
            for mref in field['supported_message_refs']:
                start=by_ref[mref]['text'].find(text)
                if start>=0:
                    node[path[-1]]=smaller(text,{'message_ref':mref,'source_span':[start,start+len(text)]})
                    break
        draft['summaries']={tier:summary_text(text) for tier,text in draft['summaries'].items()}
        draft['evidence']=[{**item,'statement':field_text(item['statement'])} for item in draft['evidence']]
        draft['unknowns']=[field_text(text) for text in draft['unknowns']]
        mrefs=[aliases[mid] for mid in episode['message_ids']]
        episodes.append({'episode_ref':eref,'message_refs':mrefs,
                         'host_source_range':{'first_message_ref':mrefs[0],'last_message_ref':mrefs[-1],
                             'message_count':len(mrefs),'authority':'host_episode_membership_not_state_claim_anchors'},
                         'title':field_text(episode['title']),'draft':draft})
    return {'messages':messages,'episodes':episodes,'review_selection_catalog':{
        'schema':catalog['schema'],'source_quotes':quotes,'state_fields':fields},
        'text_transport':'lossless_unicode_codepoint_spans_and_state_field_refs.v1'}


def expand_review_choices(checked,catalog):
    # Lazy import avoids a module cycle. All expanded fields are validated by
    # the unchanged exact-source/role/episode/primary-link gate afterwards.
    from .memory_recovery_scenario import CoverageError
    result=copy.deepcopy(checked)
    result.pop('selection_annotations',None)  # Internal authority is never provider-controlled.
    quotes={r['ref']:r for r in catalog['source_quotes']};fields={r['ref']:r for r in catalog['state_fields']}
    entries=result.get('user_intent_coverage')
    if not isinstance(entries,list):return result,False
    has_choices=any(isinstance(entry,dict) and isinstance(entry.get('intents'),list) and any(
        isinstance(intent,dict) and ('source_quote_ref' in intent or 'superseding_quote_ref' in intent or
        isinstance(intent.get('field_links'),list) and any(isinstance(link,dict) and 'field_ref' in link for link in intent['field_links']))
        for intent in entry['intents']) for entry in entries)
    if has_choices and result.get('selection_catalog_sha256')!=catalog_sha(catalog):
        raise CoverageError('review_catalog_binding_mismatch')
    used=False;annotations=[]
    for entry in entries:
        if not isinstance(entry,dict) or not isinstance(entry.get('intents'),list):continue
        for intent in entry['intents']:
            if not isinstance(intent,dict):continue
            selected_reply_fields=[]
            for ref_key,quote_key,message_key in [('source_quote_ref','source_quote','message_ref'),('superseding_quote_ref','superseding_quote','superseded_by_ref')]:
                if ref_key not in intent:continue
                ref=intent[ref_key];item=quotes.get(ref) if isinstance(ref,str) else None
                expected=entry.get(message_key) if message_key=='message_ref' else intent.get(message_key)
                if ref_key=='superseding_quote_ref' and item is not None:
                    current=entry.get('message_ref');later=item['message_ref']
                    if (intent.get('disposition')!='superseded' or not isinstance(current,str)
                            or not re.fullmatch(r'm[1-9][0-9]*',current)
                            or not re.fullmatch(r'm[1-9][0-9]*',later)
                            or int(later[1:])<=int(current[1:])):
                        raise CoverageError('review_catalog_choice_invalid')
                    if expected is None and message_key not in intent:
                        # The reviewer selected this exact later user quote;
                        # resolve its one source, without deciding supersession.
                        expected=later;intent[message_key]=later
                if item is None or item['message_ref']!=expected or quote_key in intent:
                    raise CoverageError('review_catalog_choice_invalid')
                intent[quote_key]=item['source_quote'];del intent[ref_key];used=True
            links=intent.get('field_links')
            if not isinstance(links,list):continue
            for index,link in enumerate(links):
                if not isinstance(link,dict) or 'field_ref' not in link:continue
                ref=link['field_ref'];item=fields.get(ref) if isinstance(ref,str) else None
                if item is None or set(link)-{'field_ref','context_note'}:raise CoverageError('review_catalog_choice_invalid')
                if 'context_note' in link:
                    from source_safety import mask_text
                    note=link['context_note']
                    if not isinstance(note,str) or len(note)>500:raise CoverageError('review_catalog_choice_invalid')
                    annotations.append({'message_ref':entry.get('message_ref'),'field_ref':ref,
                        'text':mask_text(note),'authority':'model_comment_not_source_or_verdict'})
                links[index]={'episode_ref':item['episode_ref'],'state_path':item['state_path'],
                              'field_quote':item['field_text'],'summary_paths':item['summary_paths']}
                if item['role']=='assistant' and item['state_path'].startswith('assistant_reports/'):
                    selected_reply_fields.append(item)
                used=True
            if intent.get('disposition')=='answered' and 'answer_message_ref' not in intent and selected_reply_fields:
                # The model already selected the exact reply field. Resolve
                # its single source, never infer an answer from unselected text.
                message_ref=entry.get('message_ref')
                all_refs={ref for field in selected_reply_fields for ref in field['supported_message_refs']}
                if (len(all_refs)==1 and isinstance(message_ref,str) and message_ref.startswith('m')
                    and message_ref[1:].isdigit()):
                    answer_ref=next(iter(all_refs))
                    if isinstance(answer_ref,str) and answer_ref.startswith('m') and answer_ref[1:].isdigit() and int(answer_ref[1:])>int(message_ref[1:]):
                        intent['answer_message_ref']=answer_ref
    if annotations:result['selection_annotations']=annotations
    return result,used
