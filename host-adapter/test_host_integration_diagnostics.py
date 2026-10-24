def test_export_excludes_credentials_env_and_private_content():
    from lib.host_integration.diagnostics import diagnostic_report
    report=diagnostic_report([{'host_id':'workbuddy','status':'failed','probe_id':'p','request_id':'r',
        'session_id':'s','Authorization':'Bearer private-secret','url':'https://host/?token=private-secret',
        'env':{'ANY_NAME':'private-env'},'content':'private-message','error_code':'timeout'}])
    assert 'private-secret' not in str(report) and 'private-env' not in str(report) and 'private-message' not in str(report)
    assert report['events'][0]['probe_id']=='p' and report['events'][0]['request_id']=='r'


def test_failure_stage_is_preserved_and_unknown_is_not_zero():
    from lib.host_integration.diagnostics import diagnostic_report
    report=diagnostic_report([{'error_stage':'handshake','status':'failed','error_code':'timeout'}])
    assert report['events'][0]['error_stage']=='handshake'
    assert report['host_delivery']=='unknown'
