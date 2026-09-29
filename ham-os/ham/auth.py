from __future__ import annotations
import hashlib,hmac,json,time
from dataclasses import dataclass,field
from pathlib import Path
@dataclass
class NonceGuard:
 seen:dict=field(default_factory=dict)
 def verify(self,adapter,key,nonce,payload,now=None):
  now=now or time.time()
  if not nonce or nonce in self.seen:return False,'replay'
  try: stamp=float(nonce.split(':',1)[0])
  except ValueError: return False,'invalid_nonce'
  if abs(now-stamp)>300:return False,'expired'
  sig=hmac.new(key.encode(),(nonce+'\n'+payload).encode(),hashlib.sha256).hexdigest();self.seen[nonce]=now;return True,sig
class AdapterAuth:
 def __init__(self,path:Path): self.path=Path(path);self.guard=NonceGuard()
 def _registry(self):
  try:return json.loads(self.path.read_text())
  except FileNotFoundError:return {'adapters':{}}
 def verify(self,headers,body):
  adapter=headers.get('X-HAM-Adapter') or headers.get('x-ham-adapter')
  nonce=headers.get('X-HAM-Nonce') or headers.get('x-ham-nonce')
  signature=headers.get('X-HAM-Signature') or headers.get('x-ham-signature')
  row=self._registry().get('adapters',{}).get(adapter or '')
  if not row or not row.get('enabled'): return False,'adapter_not_registered'
  key=row.get('hmac_key')
  if not key:return False,'adapter_key_missing'
  ok,expected=self.guard.verify(adapter,key,nonce,body)
  if not ok:return False,expected
  return (hmac.compare_digest(expected,signature or ''),'signature_mismatch')
