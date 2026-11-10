from ham.slo import classify,alert
def test_slo_uses_three_states_and_receipt_fields():
 assert classify('retain_outbox',10)=='healthy'; assert classify('retain_outbox',301)=='attention'; assert classify('retain_outbox',1801)=='critical'; assert {'first_seen_at','recovery_receipt'}<=set(alert('capsule',121))
