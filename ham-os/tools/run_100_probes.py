#!/usr/bin/env python3
"""Run the Phase 0 non-writing 100-iteration live health probe."""
import json,time,urllib.request
from pathlib import Path
url='http://127.0.0.1:8879/health'; rows=[]
for n in range(1,101):
    start=time.monotonic()
    try:
        with urllib.request.urlopen(url,timeout=5) as r:
            body=json.load(r); ok=r.status==200 and body.get('status')=='healthy'
            rows.append({'n':n,'http':r.status,'status':body.get('status'),'elapsed_ms':round((time.monotonic()-start)*1000,2),'ok':ok})
    except Exception as e:
        rows.append({'n':n,'error':f'{type(e).__name__}:{e}','elapsed_ms':round((time.monotonic()-start)*1000,2),'ok':False})
    time.sleep(.05)
lat=[r['elapsed_ms'] for r in rows if r['ok']]
report={'schema':'ham.phase0.health_100.v1','count':len(rows),'success_count':sum(r['ok'] for r in rows),'failure_count':sum(not r['ok'] for r in rows),'p95_ms':sorted(lat)[max(0,int(len(lat)*.95)-1)] if lat else None,'rows':rows}
print(json.dumps(report,ensure_ascii=False,indent=2))
