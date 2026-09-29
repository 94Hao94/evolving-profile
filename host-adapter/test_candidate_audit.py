import unittest

from lib import candidate_audit


class CandidateAuditTest(unittest.TestCase):
    def test_snapshot_redacts_credentials_and_bounds_body(self):
        row = candidate_audit.snapshot({'id': 'a', 'state': 'valid', 'text': 'api_key=sk-test-private ' + '文' * 2000},
                                       outcome='scope_uncertain', reason='no_literal_match')
        self.assertNotIn('sk-test-private', row['text'])
        self.assertLessEqual(len(row['text']), 600)
        self.assertEqual(row['delivery'], 'not_returned')
        self.assertTrue(row['text_truncated'])

    def test_withdrawn_body_is_not_saved(self):
        row = candidate_audit.snapshot({'id': 'a', 'state': 'invalidated', 'text': 'withdrawn private body'},
                                       outcome='blocked', reason='withdrawn')
        self.assertEqual(row['text'], '')

    def test_actual_output_distinguishes_text_and_locator(self):
        rows = [candidate_audit.snapshot({'id': mid, 'text': '历史记录', 'state': 'valid'},
                                         outcome='prepared', reason='source_valid') for mid in ['a', 'b', 'c']]
        result = candidate_audit.mark_delivery(rows, [{'id': 'a', 'text': '历史'}, {'id': 'b'}])
        self.assertEqual([row['delivery'] for row in result], ['text_returned', 'locator_returned', 'not_returned'])
        self.assertEqual(result[0]['delivered_text'], '历史')
        self.assertEqual(rows[0]['delivery'], 'not_returned')

    def test_delivery_does_not_restore_withdrawn_text(self):
        result=candidate_audit.mark_delivery([{'id':'a','outcome':'blocked','reason':'withdrawn','text':''}],
                                            [{'id':'a','text':'WITHDRAWN BODY'}])
        self.assertNotIn('WITHDRAWN BODY',str(result))
        self.assertEqual(result[0]['delivery'],'previously_returned_currently_blocked')

    def test_audit_paging_is_complete_and_actor_stable(self):
        rows = [{'id': str(i), 'delivery': 'not_returned'} for i in range(36)]
        page = candidate_audit.page(rows, offset=20, limit=10, actor='system_probe')
        self.assertEqual([row['id'] for row in page['items']], [str(i) for i in range(20, 30)])
        self.assertEqual(page['total'], 36)
        self.assertEqual(page['next_offset'], 30)
        self.assertEqual(page['actor'], 'system_probe')
