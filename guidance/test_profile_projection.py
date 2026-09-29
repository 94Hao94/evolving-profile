import unittest

from profile_projection import stable_profile, preference_candidate


def unit(uid, text, condition, *, validity='stable', scope='global', category='collaboration'):
    return {'id':uid,'revision':'v1','text':text,'applies_when':[condition],
            'exceptions':['当前要求优先'],'effect_on_action':'advisory','primary_category':category,
            'scope':{},'preference_audit':{'state':'approved','validity_kind':validity,'scope_level':scope}}


class ProfileProjectionTest(unittest.TestCase):
    def test_stable_profile_keeps_only_cross_scenario_rules(self):
        general=unit('general','当前用户要求优先，完成前持续核对目标。','多步骤任务')
        narrow=unit('visit','删除客户拜访统计中的去重客户日。','客户拜访统计')
        rows=stable_profile([general,narrow])
        self.assertEqual([row['id'] for row in rows],['general'])

    def test_profile_does_not_trust_global_label_without_semantic_scope(self):
        ppt=unit('ppt','PPT交付前逐页检查排版。','汇报型PPT制作')
        self.assertEqual(stable_profile([ppt]),[])

    def test_candidate_preserves_conditions_and_is_not_marked_applied(self):
        row=preference_candidate(unit('ppt','PPT交付前逐页检查排版。','汇报型PPT制作'))
        self.assertEqual(row['status'],'candidate_requires_agent_judgment')
        self.assertEqual(row['applies_when'],['汇报型PPT制作'])

    def test_candidate_exposes_source_manifest_without_copying_quote(self):
        value=unit('priority','当前 Prompt 优先。','使用历史记忆')
        value['evidence_refs']=[{'memory_id':'m1','document_id':'d1','chunk_id':'c1','stored_role':'user','quote':'PRIVATE ORIGINAL'}]
        row=preference_candidate(value)
        self.assertEqual(row['evidence_manifest'],[{'memory_id':'m1','document_id':'d1','chunk_id':'c1','stored_role':'user','origin':None,'source_revision':None}])
        self.assertNotIn('PRIVATE ORIGINAL',str(row))


if __name__=='__main__':unittest.main()
