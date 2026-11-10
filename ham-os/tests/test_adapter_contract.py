from ham.api import Api
from ham.auth import NonceGuard
import json

def test_four_adapters_share_capability_contract(tmp_path):
 c=tmp_path/'c';c.write_text(json.dumps({'memoryOS':{'enabled':True,'ledgerDualWrite':True,'needGraphShadow':True,'generation':'g','phase':'4'}}));api=Api(tmp_path/'s',c)
 for agent in ('codex','hermes','xiaodai','openclaw'):
  s,v=api.handle('GET','/v2/memory-os/capabilities',b'',{'X-HAM-Adapter':agent});assert s==200 and v['adapter_contract']=='ham.adapter.v1'
def test_nonce_replay_is_rejected():
 g=NonceGuard({});ok,_=g.verify('codex','k','1000:n','p',1000);again,reason=g.verify('codex','k','1000:n','p',1000);assert ok and not again and reason=='replay'
