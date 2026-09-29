import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parent))

from runtime_recovery import refresh_runtime_guidance


class Repo:
    def active_revision(self): return 'r1'
    def active_models(self): return []
    def active_units(self):
        return [{
            'id':'recover','revision':'v1','text':'关键验证工具失败时先修复工具，不能把替代验证写成原工具已通过。',
            'applies_when':['工具故障与验收恢复'],'exceptions':['当前要求优先'],'scope':{},'primary_category':'delivery',
            'preference_audit':{'state':'approved'},'evidence_refs':[],
        }]


class RuntimeRecoveryTests(unittest.TestCase):
    def test_requires_a_observed_failure_event(self):
        with self.assertRaisesRegex(ValueError, 'runtime_event_required'):
            refresh_runtime_guidance(Repo(), {'task': {'objective':'验收页面'}})

    def test_returns_current_recovery_guidance_without_publishing(self):
        result=refresh_runtime_guidance(Repo(), {
            'task': {'objective':'完成页面验收','current_user_message':'完成页面验收','phase':'verify'},
            'runtime_event': {'capability':'computer_use','failure':'get_state_timeout','occurrence':3,'required_for':'visual_interaction_acceptance'},
        })
        self.assertEqual(result['mode'], 'runtime_guidance_refresh')
        self.assertFalse(result['long_term_model_created'])
        self.assertEqual([item['id'] for item in result['included']], ['recover'])

