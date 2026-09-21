"""Observable evidence decisions without storing private reasoning traces."""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path

ALLOWED_NEEDS={'none','current_context','history','exact_source'}
ALLOWED_ROUTES={'skip','catalog','recall','research','find_sources','read_source'}
ALLOWED_SUFFICIENCY={'sufficient','insufficient','conflicted','unknown'}

def record_decision(root:Path,value:dict)->dict:
    check_id=str(value.get('check_id') or '').strip()
    if not check_id:raise ValueError('check_id required')
    need=str(value.get('need') or '');route=str(value.get('chosen_route') or '');sufficiency=str(value.get('sufficiency') or '')
    if need not in ALLOWED_NEEDS:raise ValueError('invalid need')
    if route not in ALLOWED_ROUTES:raise ValueError('invalid chosen_route')
    if sufficiency not in ALLOWED_SUFFICIENCY:raise ValueError('invalid sufficiency')
    unresolved=[str(item).strip()[:240] for item in value.get('unresolved_slots') or [] if str(item).strip()][:8]
    if sufficiency=='sufficient' and unresolved:raise ValueError('sufficient decision cannot have unresolved slots')
    receipt={'schema':'evolving-profile.evidence-decision.v1','check_id':check_id,'need':need,
        'known_from_current_context':bool(value.get('known_from_current_context')),'unresolved_slots':unresolved,
        'chosen_route':route,'sufficiency':sufficiency,'conflicts':[str(x)[:240] for x in value.get('conflicts') or []][:8],
        'source_ids':[str(x)[:160] for x in value.get('source_ids') or []][:20],
        'next_action':str(value.get('next_action') or '')[:500] or None,'stop_reason':str(value.get('stop_reason') or '')[:500] or None,
        'at':datetime.now(timezone.utc).isoformat(),'boundary':'agent_declared_decision_not_hidden_reasoning_or_causal_proof','persistence':'current_task_audit_only'}
    root=Path(root);root.mkdir(parents=True,exist_ok=True);target=root/(hashlib.sha256(check_id.encode()).hexdigest()+'.json');tmp=target.with_suffix('.tmp')
    tmp.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(target);return receipt
