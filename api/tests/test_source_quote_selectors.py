import json

import pytest

from evolving_profile_api.engine.retain import source_attribution as source
from evolving_profile_api.engine.retain.fact_extraction import _extract_facts_from_chunk
from tests.test_fact_extraction_retry import _make_config, _make_llm_config

META = {"source_attribution_required": "role_quote_v1"}


def fixture(role="user"):
    return json.dumps([{"role": role, "content": "原始请求：保留条件。\n旧引文是“不能发布”，但本轮仅讨论。"}], ensure_ascii=False)


def test_selected_quote_keeps_exact_bytes_offsets_and_quoted_authority():
    chunk = fixture()
    catalog = source.source_quote_catalog(chunk)
    entry = next(e for e in catalog["entries"] if e["text"] == "“不能发布”")
    _, kind, evidence = source.verify_attribution(chunk, {
        "source_message_index": 0, "source_role": "user", "source_quote": "",
        "source_quote_ref": entry["id"], "what": "用户确立禁止发布。",
    }, META)
    assert kind == "experience"
    assert evidence["statement_kind"] == "source_repetition"
    assert evidence["independent_user_evidence"] == "false"
    assert evidence["source_quote"] == "“不能发布”"
    assert evidence["source_start"] == str(json.loads(chunk)[0]["content"].index("“不能发布”"))


@pytest.mark.parametrize("mutation", ["role", "index", "quote", "stale", "invented"])
def test_invalid_selector_never_bypasses_attribution(mutation):
    chunk = fixture("assistant")
    entry = source.source_quote_catalog(chunk)["entries"][0]
    fact = {"source_message_index": 0, "source_role": "assistant", "source_quote": "", "source_quote_ref": entry["id"]}
    if mutation == "role": fact["source_role"] = "user"
    if mutation == "index": fact["source_message_index"] = True
    if mutation == "quote": fact["source_quote"] = "改写的句子。"
    if mutation == "stale": chunk = chunk.replace("原始请求", "新的请求")
    if mutation == "invented": fact["source_quote_ref"] = "not-a-real-ref"
    with pytest.raises(ValueError): source.verify_attribution(chunk, fact, META)


def test_catalog_is_bounded_and_contains_only_real_source_spans():
    chunk = json.dumps([{"role":"user","content":"正文。\n"*9000}],ensure_ascii=False)
    catalog = source.source_quote_catalog(chunk)
    assert len(json.dumps(catalog,ensure_ascii=False)) <= 12000
    assert catalog["coverage"] == "partial"
    text = json.loads(chunk)[0]["content"]
    for e in catalog["entries"]:
        assert text[e["start"]:e["end"]] == e["text"]


@pytest.mark.asyncio
async def test_attribution_retry_changes_input_and_resolves_model_selected_source():
    chunk = fixture("assistant")
    llm = _make_llm_config({"facts":[]})
    usage = (await llm.call())[-1]
    calls = []
    async def respond(**kwargs):
        calls.append(kwargs["messages"])
        if len(calls) == 1:
            return {"facts":[{"what":"错误候选","fact_type":"world","source_message_index":0,"source_role":"assistant","source_quote":"拼接后的句子不存在。"}]},usage
        assert calls[1] != calls[0]
        assert "SOURCE_QUOTE_CATALOG" in calls[1][-1]["content"]
        catalog = json.loads(calls[1][-1]["content"].split("SOURCE_QUOTE_CATALOG\n",1)[1])
        selected = catalog["entries"][0]
        return {"facts":[{"what":"助手陈述","fact_type":"world","source_message_index":0,"source_role":"assistant","source_quote":"","source_quote_ref":selected["id"]}]},usage
    llm.call.side_effect = respond
    facts,_ = await _extract_facts_from_chunk(chunk,0,1,None,"test",llm,_make_config(llm_max_retries=1),metadata=META)
    assert len(calls) == 2
    assert len(facts) == 1
    assert facts[0].fact_type == "experience"
    assert facts[0].metadata["independent_user_evidence"] == "false"
