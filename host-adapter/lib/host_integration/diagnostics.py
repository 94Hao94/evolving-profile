"""Shareable diagnostics are a projection, not a dump of host state."""
import re
import uuid

FIELDS=frozenset({'host_id','status','state','probe_id','request_id','session_id','error_stage','error_code',
    'platform','mode','version','observed_at','listed_tools','tool_names','capability_id','evidence_kind'})


def diagnostic_report(observations,*,include_content=False):
    events=[]
    for row in observations:
        if not isinstance(row,dict):continue
        event={}
        for key in FIELDS.intersection(row):
            value=row[key]
            if value is None or isinstance(value,(bool,int,float)):event[key]=value
            elif isinstance(value,str):
                value=re.sub(r'(?i)(bearer\s+|(?:token|key|secret|password)=)[^\s&]+',r'\1[REDACTED]',value)
                event[key]=value[:256]
            elif key=='tool_names' and isinstance(value,list):event[key]=[str(v)[:80] for v in value[:128]]
        events.append(event)
    return {'schema':'ep.host-diagnostics.v1','report_id':uuid.uuid4().hex,'events':events,
            'contains_content':False,'host_delivery':'unknown','answer_use':'not_measured',
            'note':'Content remains local; this export contains only allowed diagnostic fields.'}
