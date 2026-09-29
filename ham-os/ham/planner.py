from __future__ import annotations

def need_graph(query:str,workload='ordinary_semantic')->dict:
 q=query.lower(); facets=[]
 for key,name in [('当前','current_state'),('继续','task_capsule'),('接管','task_capsule'),('原文','provenance'),('证据','provenance'),('为什么','causal'),('冲突','conflict'),('文件','artifact')]:
  if key in q: facets.append(name)
 if not facets: facets=['semantic']
 facets=list(dict.fromkeys(facets))
 return {'schema':'ham.need_graph.v1','query':query,'workload_class':workload,'facets':facets,'stages':['stage_a','stage_b']+(['stage_c'] if len(facets)>1 else []),'fallback':'deterministic_v1'}
