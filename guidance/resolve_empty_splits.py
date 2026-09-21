"""Resolve split decisions where review found only one semantic side."""
from __future__ import annotations
from hashlib import sha256
import datetime as dt,json
from pathlib import Path
import urllib.parse,urllib.request
from observation_rebuild import atomic

API='http://127.0.0.1:8888';BANK='personal-memory'
def get(mid):
 with urllib.request.urlopen(API+'/v1/default/banks/'+urllib.parse.quote(BANK,safe='')+'/memories/'+mid,timeout=20) as r:return json.loads(r.read())
def patch(mid,body):
 req=urllib.request.Request(API+'/v1/default/banks/'+urllib.parse.quote(BANK,safe='')+'/memories/'+mid,data=json.dumps(body,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'},method='PATCH')
 with urllib.request.urlopen(req,timeout=120) as r:return json.loads(r.read())
def main(audit_path,split_report_path,output_path):
 audit=json.loads(Path(audit_path).read_text());held={x['id'] for x in json.loads(Path(split_report_path).read_text())['held_items']};decisions=[x for x in audit['results'] if x['id'] in held];results=[]
 for d in decisions:
  current=get(d['id'])
  current_type=current.get('fact_type') or current.get('type')
  if current.get('state')!='valid' or current_type!=d['actual_type'] or sha256(current['text'].encode()).hexdigest()!=d['text_sha256']:
   results.append({'id':d['id'],'state':'held_revision_changed'});continue
  world=str(d.get('world_text') or '').strip();experience=str(d.get('experience_text') or '').strip()
  if world and not experience:target,text='world',world
  elif experience and not world:target,text='experience',experience
  else:results.append({'id':d['id'],'state':'held_not_single_side'});continue
  if target==current_type and text==current['text']:results.append({'id':d['id'],'state':'kept','fact_type':target});continue
  patch(d['id'],{'text':text,'fact_type':target})
  read=get(d['id']);ok=(read.get('fact_type') or read.get('type'))==target and read.get('text')==text
  results.append({'id':d['id'],'state':'updated' if ok else 'readback_failed','from':current_type,'to':target,'text_sha256':sha256(text.encode()).hexdigest()})
 report={'schema':'guidance.empty-split-resolution.v1','at':dt.datetime.now(dt.timezone.utc).isoformat(),'total':len(results),'updated':sum(x['state']=='updated' for x in results),'kept':sum(x['state']=='kept' for x in results),'held':sum(x['state'].startswith('held') for x in results),'failed':sum(x['state']=='readback_failed' for x in results),'items':results}
 atomic(Path(output_path),report);print(json.dumps({k:report[k] for k in ('total','updated','kept','held','failed')},ensure_ascii=False))
if __name__=='__main__':
 import sys;main(*sys.argv[1:])
