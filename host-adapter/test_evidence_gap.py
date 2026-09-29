import tempfile,unittest
from pathlib import Path
from evidence_gap import record_decision

class EvidenceGapTest(unittest.TestCase):
    def test_records_bounded_observable_decision(self):
        with tempfile.TemporaryDirectory() as root:
            row=record_decision(Path(root),{'check_id':'c1','need':'history','known_from_current_context':False,'unresolved_slots':['报销字段最终是否恢复限制'],'chosen_route':'recall','sufficiency':'insufficient','source_ids':[],'next_action':'查找结束状态'})
        self.assertEqual(row['chosen_route'],'recall');self.assertNotIn('reasoning',row)
    def test_sufficient_decision_cannot_hide_unresolved_slot(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError,'unresolved'):
                record_decision(Path(root),{'check_id':'c1','need':'history','unresolved_slots':['结束状态'],'chosen_route':'recall','sufficiency':'sufficient'})

if __name__=='__main__':unittest.main()
