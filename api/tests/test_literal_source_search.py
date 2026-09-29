from evolving_profile_api.engine.source_search import literal_source_matches


def test_literal_source_search_matches_any_term_and_returns_stable_spans():
    text = "[role: user]\n请修好固定页脚。\n[user:end]\n\n[role: assistant]\n处理中。\n[assistant:end]"
    items = literal_source_matches(
        text,
        terms=["固定页脚", "不存在"],
        match="any",
        role="user",
        document_id="doc-1",
        chunk_id="chunk-1",
    )
    assert len(items) == 1
    assert items[0]["document_id"] == "doc-1"
    assert items[0]["format_role"] == "user"
    assert items[0]["span_start"] < items[0]["span_end"]
    assert "固定页脚" in items[0]["text"]


def test_literal_source_search_rejects_term_in_wrong_role():
    text = "[role: assistant]\n固定页脚已经处理。\n[assistant:end]"
    assert literal_source_matches(
        text,
        terms=["固定页脚"],
        match="all",
        role="user",
        document_id="doc-1",
        chunk_id="chunk-1",
    ) == []
