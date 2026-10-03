from datetime import datetime, timezone

from lib.history_bootstrap import scan_history_lines, paginate_candidates, candidate_quality_stats


def test_history_scan_returns_read_only_high_signal_candidates():
    lines = [
        '{"session_id":"s1","timestamp":"2026-09-01T10:00:00Z","role":"user","content":"修复这个程序"}',
        '{"session_id":"s1","timestamp":"2026-09-01T10:01:00Z","role":"assistant","content":"测试失败，重试后修复并验证通过"}',
        '{"session_id":"s1","timestamp":"2026-09-01T10:02:00Z","role":"tool","name":"pytest","content":"passed"}',
        '{"session_id":"s2","timestamp":"2026-09-02T10:00:00Z","role":"user","content":"你好"}',
    ]
    rows = scan_history_lines(lines, cutoff=datetime(2026, 9, 30, tzinfo=timezone.utc))
    assert len(rows) == 1
    assert rows[0]["session_id"] == "s1"
    assert rows[0]["status"] == "candidate_read_only"
    assert rows[0]["promotion_allowed"] is False


def test_history_scan_understands_codex_rollout_shape():
    lines = [
        '{"timestamp":"2026-07-02T23:36:35Z","type":"session_meta","payload":{"session_id":"rollout-1"}}',
        '{"timestamp":"2026-07-02T23:37:00Z","type":"response_item","payload":{"role":"assistant","content":[{"text":"测试失败后重试并修复"}]}}',
        '{"timestamp":"2026-07-02T23:38:00Z","type":"response_item","payload":{"type":"function_call","name":"pytest","call_id":"c1"}}',
    ]
    rows = scan_history_lines(lines, cutoff=datetime(2026, 9, 30, tzinfo=timezone.utc))
    assert rows[0]["session_id"] == "rollout-1"
    assert rows[0]["tool_event_count"] == 1


def test_history_scan_excludes_post_cutoff_and_malformed_lines():
    lines = [
        'not-json',
        '{"session_id":"late","timestamp":"2026-10-01T10:00:00Z","role":"assistant","content":"测试失败重试"}',
    ]
    assert scan_history_lines(lines, cutoff=datetime(2026, 9, 30, tzinfo=timezone.utc)) == []


def test_history_candidates_are_paginated_and_quality_is_explicit():
    rows = [{"session_id": str(i), "signal_count": i + 1, "tool_event_count": 2, "promotion_allowed": False} for i in range(5)]
    page = paginate_candidates(rows, offset=2, limit=2)
    assert page["offset"] == 2 and page["next_offset"] == 4
    assert [row["session_id"] for row in page["items"]] == ["2", "3"]
    stats = candidate_quality_stats(rows)
    assert stats["candidate_count"] == 5
    assert stats["promotion_allowed_count"] == 0
    assert stats["high_signal_count"] == 4
