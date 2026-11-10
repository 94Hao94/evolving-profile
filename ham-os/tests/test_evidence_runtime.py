from ham.evidence_runtime import ClaimLedger, EvidenceCandidate, QueryContract, RetrievalSession, pack_claims


def candidate(identifier, text, *, channel='semantic', entities=(), stage=None, authority=0.5, tokens=20, relation_path=()):
    return EvidenceCandidate(
        record_id=identifier,
        text=text,
        channel=channel,
        entities=tuple(entities),
        stage=stage,
        authority=authority,
        tokens=tokens,
        relation_path=tuple(relation_path),
    )


def test_evolution_contract_requires_origin_stages_current_and_sources():
    contract = QueryContract.from_request('Hindsight 从最开始官方到现在经历了多少次明显变迁？')
    assert contract.workload == 'evolution'
    assert {'origin', 'stages', 'current', 'sources'} <= set(contract.required_slots)
    assert 'Hindsight' in contract.canonical_entities


def test_point_contract_does_not_pretend_to_require_a_timeline():
    contract = QueryContract.from_request('Hindsight 的 API 端口是多少？')
    assert contract.workload == 'point'
    assert 'stages' not in contract.required_slots


def test_claim_ledger_merges_duplicate_evidence_without_losing_provenance():
    ledger = ClaimLedger(QueryContract.from_request('Hindsight 更新履历'))
    ledger.add(candidate('a', '2026年8月进入 Agent Memory OS 阶段', stage='agent_memory_os', authority=0.9))
    ledger.add(candidate('b', '2026年8月进入 Agent Memory OS 阶段', channel='lexical', stage='agent_memory_os', authority=0.8))
    claims = ledger.claims()
    assert len(claims) == 1
    assert claims[0].evidence_ids == ('a', 'b')
    assert set(claims[0].channels) == {'semantic', 'lexical'}


def test_claim_ledger_merges_same_claim_with_only_an_explanatory_suffix():
    ledger = ClaimLedger(QueryContract.from_request('Hindsight 从官方到现在的演变'))
    core = 'Hindsight 迁移阶段顺序为：原始长文重提炼、时间线去重、观察与心智模型重建、真实召回验收。'
    ledger.add(candidate('a', core, tokens=40))
    ledger.add(candidate('b', core + '该流程用于保证迁移稳定性。', channel='temporal', tokens=55))
    claims = ledger.claims()
    assert len(claims) == 1
    assert claims[0].evidence_ids == ('a', 'b')


def test_graph_seeds_put_canonical_entity_before_generic_question_fragments():
    contract = QueryContract.from_request('那你告诉我 Hindsight 从最开始官方到现在经历多少次变迁')
    session = RetrievalSession(contract)
    assert session.graph_seeds()[:1] == ('Hindsight',)


def test_retrieval_converges_only_after_missing_required_stage_is_found():
    contract = QueryContract.from_request('Hindsight 从官方到现在的更新履历')
    session = RetrievalSession(contract)
    session.add_round([
        candidate('origin', '官方 Hindsight 初始版本', stage='origin'),
        candidate('current', '当前 Agent Memory OS 阶段', stage='current'),
    ])
    assert session.coverage().status == 'incomplete'
    session.add_round([
        candidate('mid', 'Hooks 和 Controller 阶段', stage='hooks_controller'),
        candidate('mid2', '图谱与星座阶段', stage='graph_constellation'),
    ])
    assert session.coverage().status == 'complete'


def test_pack_keeps_distinct_required_claims_before_duplicate_evidence():
    contract = QueryContract.from_request('Hindsight 从官方到现在的更新履历')
    ledger = ClaimLedger(contract)
    ledger.add(candidate('origin', '官方 Hindsight 初始版本', stage='origin', authority=0.9, tokens=16))
    ledger.add(candidate('current', '当前 Agent Memory OS 阶段', stage='current', authority=0.9, tokens=16))
    ledger.add(candidate('duplicate', '当前 Agent Memory OS 阶段', channel='lexical', stage='current', authority=0.5, tokens=16))
    pack = pack_claims(ledger, token_budget=32)
    assert [claim['slot'] for claim in pack['claims']] == ['origin', 'current']
    assert pack['coverage']['status'] == 'incomplete'


def test_timeline_keeps_superseded_history_but_point_query_prefers_current():
    history = ClaimLedger(QueryContract.from_request('Hindsight 从官方到现在如何演变'))
    history.add(candidate('old', '旧版本依赖 AgentMemory', stage='hooks_controller', authority=0.8))
    history.add(candidate('new', '当前版本使用 Hindsight Bank', stage='current', authority=0.9))
    assert {claim.slot for claim in history.claims()} == {'hooks_controller', 'current'}
