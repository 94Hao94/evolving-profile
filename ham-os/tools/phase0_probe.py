#!/usr/bin/env python3
"""Read-only Phase 0 health, version, and recall probe."""
from __future__ import annotations
import json, time, urllib.request
from pathlib import Path

PORTS=(8879,8888,8898,9998,9999)
BANK='ep-default-bank-v2-shadow-20260811'

def request(url, payload=None, timeout=20):
    data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode()
    req=urllib.request.Request(url,data=data,headers={'Content-Type':'application/json'} if data else {})
    started=time.monotonic()
    with urllib.request.urlopen(req,timeout=timeout) as response:
        raw=response.read()
        return {'status':response.status,'elapsed_ms':round((time.monotonic()-started)*1000,2),'json':json.loads(raw.decode())}

def main():
    result={'schema':'ham.phase0_probe.v1','ports':{},'recall':{},'timestamp':time.time()}
    for port in PORTS:
        row={}
        for path in ('/health','/openapi.json'):
            try: row[path]=request(f'http://127.0.0.1:{port}{path}')
            except Exception as exc: row[path]={'error':f'{type(exc).__name__}:{exc}'}
        result['ports'][str(port)]=row
    payload={'query':'当前 Hindsight 共享记忆的 bank 是什么？','budget':'low','max_tokens':300}
    try:
        answer=request(f'http://127.0.0.1:8879/v1/default/banks/{BANK}/memories/recall',payload,timeout=30)
        body=answer.get('json',{})
        result['recall']={'transport':'ok','http_status':answer['status'],'elapsed_ms':answer['elapsed_ms'], 'result_count':len(body.get('results') or body.get('memories') or []), 'keys':sorted(body)[:32]}
    except Exception as exc:
        result['recall']={'transport':'failed','error':f'{type(exc).__name__}:{exc}'}
    print(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True))

if __name__=='__main__': main()
