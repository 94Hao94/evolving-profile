import contextlib
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


class McpToolActivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = importlib.import_module('evolving_profile_controller_mcp')

    def _invoke_reply(self, home, tool_name, arguments, result):
        output=io.StringIO()
        with patch.object(self.module.Path,'home',return_value=Path(home)), \
             patch.object(self.module,'CURRENT_TOOL_CALL',{'name':tool_name,'arguments':arguments}), \
             contextlib.redirect_stdout(output):
            self.module.reply('id-1',result=result)
        return json.loads(output.getvalue())['result']

    def test_recall_result_reports_discovered_and_returned_counts_separately(self):
        with tempfile.TemporaryDirectory() as home:
            result={'content':[{'type':'text','text':json.dumps({
                'research_id':'research-1','discovered_reference_count':26,
                'memories':[{'id':'m1','text':'first'},{'id':'m2','text':'second'}],
                'delivery':{'transport':'mcp_tool_result','host_visibility':'unknown','answer_use':'not_measured'},
            })}]}
            payload=self._invoke_reply(home,'recall',{},result)
            value=json.loads(payload['content'][0]['text'])
            self.assertEqual(value['discovered_reference_count'],26)
            self.assertIn('returned_count',value)
            self.assertEqual(value['returned_count'],2)

    def test_preference_result_count_includes_visible_guidance_not_deferred_items(self):
        with tempfile.TemporaryDirectory() as home:
            result={'content':[{'type':'text','text':json.dumps({
                'included':[{'id':'p1'},{'id':'p2'}],
                'stable_profile':[{'id':'p3'}],
                'model_sections':[{'section_id':'model-1'}],
                'deferred':[{'id':'not-delivered'}],
            })}]}
            payload=self._invoke_reply(home,'get_preference',{},result)
            value=json.loads(payload['content'][0]['text'])
            self.assertIn('returned_count',value)
            self.assertEqual(value['returned_count'],4)

    def test_stale_check_id_is_not_written_into_an_older_prompt_receipt(self):
        with tempfile.TemporaryDirectory() as home:
            root=Path(home)/'.evolving-profile'/'audit'
            receipt_root=root/'memory-route-receipts'
            receipt_root.mkdir(parents=True)
            check_id='prompt-old'
            target=receipt_root/(hashlib.sha256(check_id.encode()).hexdigest()+'.json')
            target.write_text(json.dumps({
                'check_id':check_id,
                'prompt_binding':{'session_id':'session-a','turn_id':'turn-old','hook_invocation_id':check_id},
                'tool_events':[],
            }),encoding='utf-8')
            now=datetime.now(timezone.utc)
            ingress=root/'prompt-ingress.jsonl'
            ingress.write_text('\n'.join(json.dumps(row) for row in [
                {'at':(now-timedelta(minutes=3)).isoformat(),'session_id':'session-a','turn_id':'turn-old','hook_invocation_id':check_id},
                {'at':(now-timedelta(minutes=1)).isoformat(),'session_id':'session-a','turn_id':'turn-new','hook_invocation_id':'prompt-new'},
            ])+'\n',encoding='utf-8')
            result={'content':[{'type':'text','text':json.dumps({'memories':[{'id':'m1'}]})}]}
            with patch.dict(os.environ,{'EVOLVING_PROFILE_ROUTE_RECEIPT_ROOT':str(receipt_root)}):
                payload=self._invoke_reply(home,'recall',{'check_id':check_id},result)
            value=json.loads(payload['content'][0]['text'])
            self.assertIn('observability_binding',value)
            self.assertEqual(value['observability_binding']['state'],'stale_prompt_binding')
            receipt=json.loads(target.read_text(encoding='utf-8'))
            self.assertEqual(receipt['tool_events'],[])
            activity=json.loads((root/'mcp-tool-activity.jsonl').read_text(encoding='utf-8').splitlines()[-1])
            self.assertEqual(activity['binding_state'],'stale_prompt_binding')
            self.assertEqual(activity['session_id'],'session-a')
            self.assertEqual(activity['latest_hook_invocation_id'],'prompt-new')


if __name__=='__main__':
    unittest.main()
