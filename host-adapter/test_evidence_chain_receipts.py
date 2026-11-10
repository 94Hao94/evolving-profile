import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from evidence_workspace import search, read_page
from host_receipt_projection import response_evidence_chain


def test_successful_empty_recall_is_semantic_zero_with_explicit_chain(tmp_path):
    def api(path, body=None, timeout=8):
        if path.endswith('/recall'):
            return {'results': []}
        raise AssertionError(path)

    result = search('bank', 'unseen question', api, tmp_path)

    assert result['evidence_chain']['status'] == 'semantic_zero'
    assert result['evidence_chain']['stages']['discovered']['count'] == 0
    assert result['evidence_chain']['stages']['admitted']['count'] == 0
    assert 'provider_failure' not in result['evidence_chain']['reason_codes']
    assert result['evidence_chain']['answer_used'] == 'not_measured'


def test_provider_failure_is_recorded_separately_from_semantic_zero(tmp_path):
    def api(path, body=None, timeout=8):
        raise TimeoutError('provider unavailable')

    with pytest.raises(RuntimeError, match='provider'):
        search('bank', 'unavailable question', api, tmp_path)

    manifests = list(tmp_path.glob('*.json'))
    assert len(manifests) == 1
    state = json.loads(manifests[0].read_text())
    assert state['evidence_chain']['status'] == 'provider_failure'
    assert state['evidence_chain']['reason_codes'] == ['provider_failure']
    assert state['provider_failure']['failed_facets'] == 1


def test_partial_provider_failure_does_not_collapse_to_semantic_zero(tmp_path):
    def api(path, body=None, timeout=8):
        if 'memories/recall' in path:
            if body and 'fail-side' in body.get('query', ''):
                raise TimeoutError('provider unavailable')
            return {'results': []}
        raise AssertionError(path)

    result = search('bank', 'semantic zero', api, tmp_path,
                    facets=['empty-side', 'fail-side'])

    assert result['evidence_chain']['status'] == 'partial'
    assert 'provider_failure_partial' in result['evidence_chain']['reason_codes']
    assert 'semantic_zero' not in result['evidence_chain']['reason_codes']


def test_page_exposes_stage_chain_and_preserves_unmeasured_answer_use(tmp_path):
    memory_id = str(uuid.uuid4())

    def api(path, body=None, timeout=8):
        if path.endswith('/recall'):
            return {'results': [{'id': memory_id, 'state': 'valid', 'text': 'evidence'}]}
        if path.endswith('/memories/' + memory_id):
            return {'id': memory_id, 'state': 'valid', 'text': 'evidence'}
        raise AssertionError(path)

    result = search('bank', 'evidence', api, tmp_path)

    chain = result['evidence_chain']
    assert chain['status'] == 'observed'
    assert chain['stages']['discovered']['count'] == 1
    assert chain['stages']['admitted']['count'] == 1
    assert chain['stages']['source_read']['count'] == 1
    assert chain['stages']['delivered']['count'] == 1
    assert chain['stages']['answer_used']['status'] == 'not_measured'
    assert chain['stages']['independently_verified']['status'] == 'not_measured'


def test_host_projection_keeps_adapter_chain_without_promoting_answer_use():
    chain = {
        'schema': 'ep.evidence_chain_receipt.v1',
        'status': 'semantic_zero',
        'stages': {'answer_used': {'count': None, 'status': 'not_measured'}},
    }
    response = {'content': [{'type': 'text', 'text': json.dumps({'evidence_chain': chain})}]}
    assert response_evidence_chain(response) == chain
