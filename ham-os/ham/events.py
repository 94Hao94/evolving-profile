from __future__ import annotations
from .contracts import digest,utcnow

def deterministic_slice(event:dict,slice_index:int,extractor_version='ham-slice-v1')->dict:
 payload={'event_id':event['event_id'],'slice_index':slice_index,'extractor_version':extractor_version,'actor':{},'action':'','object':{},'result':'','input_refs':[],'artifact_ids':[],'evidence_ids':[event['event_id']],'origin_class':event['origin_class'],'status':'active'}
 payload['slice_id']=digest(payload); payload.update({'schema':'ham.event_slice.v1','principal_id':event['principal_id'],'project_id':event['project_id'],'task_id':event['task_id'],'validation_status':'unknown','occurred_at':event['occurred_at'],'recorded_at':utcnow()}); return payload
