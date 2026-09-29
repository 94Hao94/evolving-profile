from __future__ import annotations
def build_pack(items,token_budget):
 chosen=[]; used=0
 for item in items:
  cost=max(1,int(item.get('tokens',len(item.get('text',''))//2)))
  if used+cost>token_budget: continue
  chosen.append(item); used+=cost
 return {'schema':'ham.memory_pack.v1','items':chosen,'token_budget':token_budget,'used_tokens':used,'expansion_handle':None if len(chosen)==len(items) else 'opaque-handle'}
