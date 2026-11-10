import io
import json
import unittest
from unittest.mock import patch
from lib import scenario_model as m
from lib.scenario_source import revision_for_messages

def source_fixture():
    rows=[{'evidence_id':'u1','role':'user','text':'请仔细检查系统。','turn_id':'same'},
          {'evidence_id':'u2','role':'user','text':'请保留桌面兼容。','turn_id':'same'},
          {'evidence_id':'a1','role':'assistant','text':'助手报告检查完成。','turn_id':'same'}]
    return {'status':'complete','thread_id':'test-session','messages':rows,
            'source_revision':revision_for_messages(rows),'source_files':[],'total_chars':sum(len(x['text']) for x in rows)}

class ScenarioRepair(unittest.TestCase):
    def test_draft_revision_echo_error_requires_fresh_corrected_response(self):
        src=source_fixture();state=m.deterministic_source_state_draft(src,user_claim_protocol=None)['state'];calls=[]
        def opener(request,timeout):
            calls.append(json.loads(request.data))
            value={'source_revision':'wrong' if len(calls)==1 else src['source_revision'],'state':state}
            return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}]}).encode())
        result=m._request_session_state_single(src,base_url='https://test.invalid',api_key='test',model='test',opener=opener,user_claim_protocol=None)
        self.assertEqual(result['source_revision'],src['source_revision'])
        self.assertEqual(len(calls),2)
        self.assertIn(src['source_revision'],calls[1]['messages'][0]['content'])
    def test_split_same_turn_keeps_one_boundary_decision(self):
        src=source_fixture()
        def classify(source,targets,**kwargs):
            return [{'message_id':x,'decision':'same_episode','method':'model_boundary_review'} for x in targets]
        def draft(source,**kwargs):return m.deterministic_source_state_draft(source)
        with patch.object(m,'_request_episode_decisions',side_effect=classify), patch.object(m,'request_session_state_draft',side_effect=draft):
            bundle=m.request_episode_bundle(src,base_url='https://test.invalid',api_key='test',model='test',max_input_chars=12)
        self.assertEqual([x['message_id'] for x in bundle['boundary_decisions']],['u2'])
        self.assertEqual(len(bundle['episodes']),1)
    def review(self, answers):
        src=source_fixture();draft={'schema':'test-v1','source_revision':src['source_revision'],'summaries':{},'evidence':[]}
        self.requests=[]
        def opener(request,timeout):
            self.requests.append(json.loads(request.data));answer=answers.pop(0)
            if answer.get('source_revision')=='correct':answer={**answer,'source_revision':src['source_revision']}
            return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(answer)}}]}).encode())
        return m._request_session_review_single(src,draft,base_url='https://test.invalid',api_key='test',model='test',opener=opener)
    def test_revision_echo_error_gets_one_explicit_correction(self):
        result=self.review([{'source_revision':'wrong','accept':True,'issues':[]},{'source_revision':'correct','accept':True,'issues':[]}])
        self.assertEqual(result['status'],'model_review_passed')
        self.assertEqual(len(self.requests),2)
        self.assertIn(source_fixture()['source_revision'],self.requests[1]['messages'][-1]['content'])
    def test_wrong_revision_twice_stays_rejected(self):
        with self.assertRaisesRegex(ValueError,'scenario_review_source_mismatch'):
            self.review([{'source_revision':'wrong','accept':True,'issues':[]}]*2)
        self.assertEqual(len(self.requests),2)
    def test_semantic_rejection_is_never_retried_into_acceptance(self):
        result=self.review([{'source_revision':'correct','accept':False,'issues':[{'tier':'evidence','code':'missing_scope','detail':'Missing user condition'}]}])
        self.assertEqual(result['status'],'model_review_rejected')
        self.assertEqual(len(self.requests),1)

if __name__=='__main__':unittest.main()
