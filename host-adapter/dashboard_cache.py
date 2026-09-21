"""Demand-driven single-worker snapshots. Never run model or memory writes."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time

class SnapshotCache:
    def __init__(self,ttl=30,backoff=60,clock=time.monotonic):
        self.ttl=ttl;self.backoff=backoff;self.clock=clock
        self.lock=threading.Lock();self.rows={}
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='status-readonly')
    def get(self,key,build,warming):
        with self.lock:
            row=self.rows.setdefault(key,{'value':None,'next_at':0,'building':False,'error':None,'builds':0})
            if not row['building'] and self.clock()>=row['next_at']:
                row['building']=True
                self.pool.submit(self._build,key,build)
            return row['value'] if row['value'] is not None else warming
    def _build(self,key,build):
        try:
            value=build()
            with self.lock:
                self.rows[key].update(value=value,error=None,next_at=self.clock()+self.ttl)
        except Exception as error:
            with self.lock:self.rows[key].update(error=type(error).__name__,next_at=self.clock()+self.backoff)
        finally:
            with self.lock:
                self.rows[key]['building']=False;self.rows[key]['builds']+=1
    def info(self,key):
        with self.lock:return {k:v for k,v in self.rows.get(key,{}).items() if k!='value'}
    def close(self):
        self.pool.shutdown(wait=True)
