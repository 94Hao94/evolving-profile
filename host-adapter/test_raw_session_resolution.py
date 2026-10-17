"""Raw location failures must distinguish unknown coverage from absence."""
import json
import sqlite3

import pytest

from lib.raw_session_evidence import read_evidence
from lib.session_paths import session_paths


SID = '00000000-0000-4000-8000-000000000071'


def test_compressed_native_source_is_not_reported_missing(tmp_path):
    # The resolver must recognize the format without decoding any compressed bytes.
    root = tmp_path / 'sessions'
    root.mkdir()
    path = root / f'rollout-test-{SID}.jsonl.zst'
    path.write_bytes(b'compressed bytes are not plain JSONL')

    result = session_paths(root, SID)

    assert result['status'] == 'source_compressed_unavailable'
    assert result['paths'] == [path]
    assert result['coverage']['partial'] is True
    assert result['coverage']['source_presence'] == 'compressed_file_present_unverified'


def test_compressed_only_readback_preserves_unknown_turn_coverage(tmp_path):
    root = tmp_path / 'sessions'
    root.mkdir()
    (root / f'rollout-test-{SID}.jsonl.zst').write_bytes(b'not decoded')

    result = read_evidence(SID, root, turn_id='requested-turn', cache_root=tmp_path / 'cache')

    import shutil
    assert result['status'] == ('source_decode_failed' if shutil.which('zstd') else 'source_compressed_unavailable')
    assert result['source'] == {}
    assert result['coverage']['partial'] is True
    assert result['coverage']['matched_messages'] is None
    assert result['coverage']['source_presence'] == 'compressed_file_present_unverified'


def test_archive_compressed_source_is_also_unknown_not_missing(tmp_path):
    root = tmp_path / 'sessions'
    archive = tmp_path / 'archived_sessions'
    archive.mkdir()
    path = archive / f'rollout-test-{SID}.jsonl.zst'
    path.write_bytes(b'not decoded')

    result = session_paths(root, SID)

    assert result['status'] == 'source_compressed_unavailable'
    assert result['paths'] == [path]


def test_compressed_copy_cannot_be_ignored_when_plain_source_exists(tmp_path):
    root = tmp_path / 'sessions'
    root.mkdir()
    plain = root / f'rollout-test-{SID}.jsonl'
    plain.write_text(json.dumps({'type': 'session_meta', 'payload': {'id': SID}}) + '\n')
    compressed = root / f'rollout-test-{SID}.jsonl.zst'
    compressed.write_bytes(b'unverified alternate source')

    result = session_paths(root, SID)

    assert result['status'] == 'source_compressed_unavailable'
    assert set(result['paths']) == {plain, compressed}
    assert result['coverage']['source_presence'] == 'compressed_file_present_unverified'


def test_bounded_raw_scan_does_not_claim_requested_turn_is_absent(tmp_path):
    root = tmp_path / 'sessions'
    root.mkdir()
    rows = [
        {'type': 'turn_context', 'payload': {'turn_id': 'early'}},
        {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user',
                                            'content': [{'text': 'Early request'}]}},
        {'type': 'turn_context', 'payload': {'turn_id': 'late'}},
        {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user',
                                            'content': [{'text': 'Late request'}]}},
    ]
    lines = [(json.dumps(row) + '\n').encode() for row in rows]
    path = root / f'rollout-test-{SID}.jsonl'
    path.write_bytes(b''.join(lines))
    budget = len(lines[0]) + len(lines[1])

    first = read_evidence(SID, root, turn_id='late', cache_root=tmp_path / 'cache',
                          max_scan_bytes=budget)

    assert first['status'] == 'source_scan_incomplete'
    assert first['source']['text'] == ''
    assert first['coverage']['matched_messages'] == 0
    assert first['coverage']['scan_complete'] is False
    assert first['coverage']['partial'] is True
    assert first['coverage']['scanned_bytes'] <= budget
    # Incremental continuation must preserve turn state and eventually reach
    # the requested turn without a full-file scan on either invocation.
    second = read_evidence(SID, root, turn_id='late', cache_root=tmp_path / 'cache',
                           max_scan_bytes=budget)
    assert second['status'] == 'source_read'
    assert 'Late request' in second['source']['text']
    assert 'Early request' not in second['source']['text']
    assert second['coverage']['scan_complete'] is True


def test_oversized_raw_line_is_bounded_and_reported_unknown(tmp_path):
    root = tmp_path / 'sessions'
    root.mkdir()
    path = root / f'rollout-test-{SID}.jsonl'
    path.write_text(json.dumps({'type': 'response_item', 'payload': {'type': 'message',
        'role': 'user', 'content': [{'text': 'x' * 4096}]}}) + '\n')

    result = read_evidence(SID, root, turn_id='unknown', cache_root=tmp_path / 'cache',
                           max_line_bytes=256, max_scan_bytes=1024)

    assert result['status'] == 'source_scan_incomplete'
    assert result['coverage']['scan_complete'] is False
    assert result['coverage']['scanned_bytes'] <= 257
    assert result['coverage']['scan_stop_reason'] == 'line_exceeds_budget'


def test_found_messages_still_report_incomplete_source_scan(tmp_path):
    root = tmp_path / 'sessions'
    root.mkdir()
    first = (json.dumps({'type': 'response_item', 'payload': {'type': 'message',
        'role': 'user', 'content': [{'text': 'First request'}]}}) + '\n').encode()
    (root / f'rollout-test-{SID}.jsonl').write_bytes(first + first)

    result = read_evidence(SID, root, cache_root=tmp_path / 'cache', max_scan_bytes=len(first))

    assert result['status'] == 'source_read'
    assert result['coverage']['returned_messages'] == 1
    assert result['coverage']['scan_complete'] is False
    assert result['coverage']['partial'] is True


def test_duplicate_comparison_cannot_read_unbounded_sources(tmp_path):
    root = tmp_path / 'sessions'
    archive = tmp_path / 'archived_sessions'
    root.mkdir()
    archive.mkdir()
    raw = (json.dumps({'type': 'session_meta', 'payload': {'id': SID}}) + '\n').encode()
    for directory in (root, archive):
        (directory / f'rollout-test-{SID}.jsonl').write_bytes(raw)

    result = session_paths(root, SID, max_compare_bytes=len(raw))

    assert result['status'] == 'source_comparison_incomplete'
    assert result['coverage']['partial'] is True
    assert result['coverage']['scan_complete'] is False


def test_cached_readback_cannot_bypass_raw_line_budget(tmp_path):
    root = tmp_path / 'sessions'
    root.mkdir()
    path = root / f'rollout-test-{SID}.jsonl'
    path.write_text(json.dumps({'type': 'response_item', 'payload': {'type': 'message',
        'role': 'user', 'content': [{'text': 'x' * 1024}]}}) + '\n')
    cache = tmp_path / 'cache'
    assert read_evidence(SID, root, cache_root=cache)['status'] == 'source_read'

    result = read_evidence(SID, root, cache_root=cache, max_line_bytes=256)

    assert result['status'] == 'source_scan_incomplete'
    assert result['source'] == {}
    assert result['coverage']['partial'] is True
    assert result['coverage']['scan_stop_reason'] == 'readback_line_exceeds_budget'
    assert read_evidence(SID, root, cache_root=cache)['status'] == 'source_read'


@pytest.mark.parametrize('bad,reason', [
    (b'not-json\n', 'invalid_json'),
    (b'\xff\n', 'invalid_json'),
    (b'[]\n', 'invalid_record_shape'),
    (b'null\n', 'invalid_record_shape'),
    (b'{"type":"turn_context","payload":[]}\n', 'invalid_record_payload'),
    (b'{"type":"turn_context","payload":null}\n', 'invalid_record_payload'),
    (b'{"type":"turn_context","payload":{"turn_id":17}}\n', 'invalid_turn_id'),
    (b'{"type":"response_item","payload":"broken"}\n', 'invalid_record_payload'),
    (b'{"type":"response_item","payload":{"type":"message","role":"user","content":17}}\n', 'invalid_message_content'),
    (b'{"type":"response_item","payload":{"type":"message","role":"user","content":[null]}}\n', 'invalid_message_content'),
    (b'{"type":"response_item","payload":{"type":"message","role":"user","content":[{"text":17}]}}\n', 'invalid_message_content'),
    (b'{"type":"response_item","payload":{"type":"message","role":[],"content":[]}}\n', 'invalid_message_role'),
    (b'{"type":"response_item","payload":{"type":"message","role":"assistant","phase":[],"content":[]}}\n', 'invalid_message_phase'),
])
def test_unreadable_records_stop_at_same_offset_and_keep_turn_unknown(tmp_path, bad, reason):
    root = tmp_path / 'sessions'
    root.mkdir()
    prefix = (json.dumps({'type': 'session_meta', 'payload': {'id': SID}}) + '\n').encode()
    following = [
        {'type': 'turn_context', 'payload': {'turn_id': 'requested'}},
        {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user',
                                            'content': [{'text': 'Do not jump past corrupt evidence'}]}},
    ]
    path = root / f'rollout-test-{SID}.jsonl'
    path.write_bytes(prefix + bad + b''.join((json.dumps(row) + '\n').encode() for row in following))
    cache = tmp_path / 'cache'

    for _ in range(2):
        result = read_evidence(SID, root, turn_id='requested', cache_root=cache)
        assert result['status'] == 'source_scan_incomplete'
        assert not result['source'].get('text')
        assert result['coverage']['scan_complete'] is False
        assert result['coverage']['partial'] is True
        assert result['coverage']['scan_stop_reason'] == reason
        with sqlite3.connect(cache / (SID + '.sqlite')) as db:
            assert db.execute('SELECT offset FROM checkpoint').fetchone()[0] == len(prefix)


def test_cached_body_is_not_authority_after_original_line_hash_matches(tmp_path):
    root = tmp_path / 'sessions'
    root.mkdir()
    path = root / f'rollout-test-{SID}.jsonl'
    path.write_text(json.dumps({'type': 'response_item', 'payload': {'type': 'message',
        'role': 'user', 'content': [{'text': 'Original verified message'}]}}) + '\n')
    cache = tmp_path / 'cache'
    original = read_evidence(SID, root, cache_root=cache)
    with sqlite3.connect(cache / (SID + '.sqlite')) as db:
        db.execute('UPDATE message SET text=?,at=?', ('Invented cached prose', 'Invented cached timestamp'))

    result = read_evidence(SID, root, cache_root=cache)

    assert result['status'] == 'source_read'
    assert 'Original verified message' in result['source']['text']
    assert 'Invented cached prose' not in result['source']['text']
    assert result['source']['locators'] == original['source']['locators']


def test_cached_role_mismatch_fails_closed_and_next_read_recovers(tmp_path):
    root = tmp_path / 'sessions'
    root.mkdir()
    path = root / f'rollout-test-{SID}.jsonl'
    path.write_text(json.dumps({'type': 'response_item', 'payload': {'type': 'message',
        'role': 'user', 'content': [{'text': 'Original user statement'}]}}) + '\n')
    cache = tmp_path / 'cache'
    assert read_evidence(SID, root, cache_root=cache)['status'] == 'source_read'
    with sqlite3.connect(cache / (SID + '.sqlite')) as db:
        db.execute('UPDATE message SET role=?', ('assistant',))

    result = read_evidence(SID, root, cache_root=cache)

    assert result['status'] == 'source_changed'
    assert result['source'] == {}
    assert result['coverage']['partial'] is True
    assert result['coverage']['scan_stop_reason'] == 'cache_role_mismatch'
    recovered = read_evidence(SID, root, cache_root=cache)
    assert recovered['status'] == 'source_read'
    assert recovered['source']['locators'][0]['role'] == 'user'


def test_unknown_record_type_remains_ignorable(tmp_path):
    root = tmp_path / 'sessions'
    root.mkdir()
    path = root / f'rollout-test-{SID}.jsonl'
    path.write_text(json.dumps({'type': 'unrelated_native_event', 'payload': 17}) + '\n')

    result = read_evidence(SID, root, turn_id='requested', cache_root=tmp_path / 'cache')

    assert result['status'] == 'source_empty'
    assert result['coverage']['scan_complete'] is True
