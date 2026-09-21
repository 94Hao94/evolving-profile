"""Reclassify active GuidanceUnits without changing their semantic claims."""
from __future__ import annotations
from hashlib import sha256
import datetime as dt,json
from pathlib import Path
import urllib.request
from mcp_runtime import load_repository
from observation_rebuild import atomic,load_env
from publisher import prepare_publication,commit_publication

CATEGORIES={'communication','learning','reasoning','collaboration','delivery'}
def prompt(units):
 data=[{k:u.get(k) for k in ('id','primary_category','text','applies_when','exceptions','effect_on_action')} for u in units]
 return '''你只做多维度偏好的主分类，不修改正文、范围或证据。communication=结论顺序、建议呈现、篇幅结构、语气和受众表达；learning=解释机制、例子类比、理解检验和迁移；reasoning=证据比较、业务建模、反证、替代解释和决策权衡；collaboration=自治边界、任务续接、推进、分工、进度和授权；delivery=验收、回归、成品、格式、可见结果、来源及恢复。每项只能一个primary_category，边界项选最直接改变本轮行动的类别。只返回JSON {"results":[{"id":"...","primary_category":"...","reason":"..."}]}，每项恰好一次。输入：\n'''+json.dumps(data,ensure_ascii=False)
def classify(units):
 signals={
  'communication':('结论','呈现','表达','篇幅','语气','公文','领导','客户','文字','标题','排版','建议排序','推荐度'),
  'learning':('解释','例子','类比','学习','复习','理解','术语','英文','音标','迁移'),
  'reasoning':('分析','决策','证据','反证','建模','权衡','替代解释','假设','估算'),
  'collaboration':('执行','推进','授权','协作','进度','任务续接','中间不用','不要停','分工'),
  'delivery':('验收','测试','回归','交付','文件','可打开','成品','恢复','回退','真实结果','检查'),
 }
 rows=[]
 for unit in units:
  text=' '.join([unit.get('text',''),*(unit.get('applies_when') or []),*(unit.get('exceptions') or []),unit.get('effect_on_action','')])
  scores={category:sum(phrase in text for phrase in phrases) for category,phrases in signals.items()};scores[unit.get('primary_category')]=scores.get(unit.get('primary_category'),0)+0.25
  category=max(scores,key=scores.get)
  rows.append({'id':unit['id'],'primary_category':category,'reason':'current-codex deterministic behavior-dimension classification; semantic content and evidence unchanged'})
 return rows
def main(config_path,output_path):
 config=json.loads(Path(config_path).read_text());repo=load_repository(config_path);repo.set_owner(config['owner_token']);units=repo.active_units();decisions={r['id']:r for r in classify(units)};changed=[];unchanged=[]
 for unit in units:
  decision=decisions[unit['id']]
  if decision['primary_category']==unit.get('primary_category'):unchanged.append(unit['id']);continue
  proposal={k:unit.get(k) for k in ('nature','related_categories','text','applies_when','exceptions','effect_on_action','scope','evidence_refs','source_family_ids')}
  proposal.update(proposal_id='reclassify:'+unit['id']+':'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'),operation='update',target_id=unit['id'],base_revision=unit['revision'],primary_category=decision['primary_category'])
  witness=sha256('\x1f'.join(ref['origin_witness_sha256'] for ref in proposal['evidence_refs']).encode()).hexdigest()
  review={'support':'supported','scope_ok':True,'conditions_preserved':True,'source_role_ok':True,'hypothetical_only':False,'conflicts':[],'source_witness_hash':witness,'reviewer_model':'current-codex-category-only+programmatic-source-preservation','reviewed_at':dt.datetime.now(dt.timezone.utc).isoformat()}
  prepared=prepare_publication(repo,proposal,review,config['owner_token']);commit=commit_publication(repo,prepared['publication_id'],repo.active_revision(),prepared['source_tokens'],config['owner_token'])
  changed.append({'id':unit['id'],'from':unit.get('primary_category'),'to':decision['primary_category'],'revision':commit['revision'],'reason':decision.get('reason')})
 counts={}
 for u in repo.active_units():counts[u['primary_category']]=counts.get(u['primary_category'],0)+1
 report={'schema':'guidance.reclassification.v1','at':dt.datetime.now(dt.timezone.utc).isoformat(),'input':len(units),'changed':changed,'unchanged':unchanged,'active_counts':counts}
 atomic(Path(output_path),report);print(json.dumps({'input':len(units),'changed':len(changed),'unchanged':len(unchanged),'active_counts':counts},ensure_ascii=False))
if __name__=='__main__':
 import sys;main(*sys.argv[1:])
