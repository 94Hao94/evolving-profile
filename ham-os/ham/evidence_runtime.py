"""Claim-oriented memory retrieval primitives for the Memory Evidence Runtime.

The runtime deliberately treats Bank records as evidence, not as the final
context unit.  A single claim may have many records, channels and graph paths;
the answer-facing pack contains distinct, source-preserving claims.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Callable, Iterable, Protocol


_EVOLUTION_TERMS = (
    '从最开始', '从官方到现在', '从官方', '到现在', '更新履历', '发展历程',
    '演变', '变迁', '经历了多少次', '全部更新', '一路怎么变',
)
_OPEN_TERMS = ('全部', '所有', '盘点', '回顾', '总结', '梳理')
_GENERIC_SEED_TERMS = {
    '那你告诉我', '最开始官方', '经历了大概多少次', '怎么', '为什么', '多少',
    '全部', '所有', '更新履历', '到现在', '从最开始',
}


def _normalise(value: str) -> str:
    return re.sub(r'\s+', ' ', value.strip()).casefold()


def _canonical_entities(request: str) -> tuple[str, ...]:
    """Extract stable named anchors without promoting generic Chinese chunks."""
    found: list[str] = []
    for token in re.findall(r'[A-Za-z][A-Za-z0-9_.+\-]{1,}|[\u4e00-\u9fff]{2,}', request):
        if token in _GENERIC_SEED_TERMS or token in {'官方', '现在', '多少次', '明显'}:
            continue
        if token.casefold() == 'hindsight':
            canonical = 'Hindsight'
        elif token.casefold() == 'agentmemory':
            canonical = 'AgentMemory'
        else:
            canonical = token
        if canonical not in found:
            found.append(canonical)
    return tuple(found)


@dataclass(frozen=True)
class QueryContract:
    request: str
    execution_id: str
    workload: str
    required_slots: tuple[str, ...]
    canonical_entities: tuple[str, ...]
    allow_historical: bool
    required_relation_closure: bool

    @classmethod
    def from_request(cls, request: str, execution_id: str | None = None) -> 'QueryContract':
        q = _normalise(request)
        evolution = any(term in request for term in _EVOLUTION_TERMS)
        open_set = any(term in request for term in _OPEN_TERMS)
        if evolution:
            workload = 'evolution'
            slots = ('origin', 'stages', 'current', 'sources')
            allow_historical = True
            closure = True
        elif open_set:
            workload = 'inventory'
            slots = ('scope', 'findings', 'sources')
            allow_historical = '历史' in request or '以前' in request
            closure = '实体' in request or '关系' in request or '关联' in request
        else:
            workload = 'point'
            slots = ('answer', 'sources')
            allow_historical = '以前' in request or '历史' in request
            closure = '实体' in request or '关系' in request
        return cls(
            request=request,
            execution_id=execution_id or str(uuid.uuid4()),
            workload=workload,
            required_slots=slots,
            canonical_entities=_canonical_entities(request),
            allow_historical=allow_historical,
            required_relation_closure=closure,
        )


@dataclass(frozen=True)
class EvidenceCandidate:
    record_id: str
    text: str
    channel: str
    entities: tuple[str, ...] = ()
    stage: str | None = None
    authority: float = 0.5
    tokens: int = 1
    relation_path: tuple[str, ...] = ()
    occurred_at: str | None = None
    source_uri: str | None = None
    supersedes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Claim:
    claim_key: str
    statement: str
    slot: str
    evidence_ids: tuple[str, ...]
    channels: tuple[str, ...]
    entities: tuple[str, ...]
    relation_paths: tuple[tuple[str, ...], ...]
    authority: float
    tokens: int
    historical: bool = False


@dataclass(frozen=True)
class CoverageDecision:
    status: str
    required_slots: tuple[str, ...]
    covered_slots: tuple[str, ...]
    missing_slots: tuple[str, ...]
    reason: str


class CandidateProvider(Protocol):
    def __call__(self, channel: str, queries: tuple[str, ...], contract: QueryContract) -> Iterable[EvidenceCandidate]:
        ...


@dataclass
class _MutableClaim:
    statement: str
    slot: str
    evidence_ids: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    relation_paths: list[tuple[str, ...]] = field(default_factory=list)
    authority: float = 0.0
    tokens: int = 1
    historical: bool = False


def _slot_for(candidate: EvidenceCandidate, contract: QueryContract) -> str:
    if candidate.stage:
        return candidate.stage
    text = candidate.text
    if contract.workload == 'evolution':
        if any(x in text for x in ('官方', '初始', '最初', 'v1')):
            return 'origin'
        if any(x in text for x in ('当前', '现在', '现行', 'Agent Memory OS')):
            return 'current'
        return 'stage'
    return 'answer' if contract.workload == 'point' else 'finding'


class ClaimLedger:
    def __init__(self, contract: QueryContract):
        self.contract = contract
        self._claims: dict[str, _MutableClaim] = {}

    def add(self, candidate: EvidenceCandidate) -> None:
        key = _normalise(candidate.text)
        slot = _slot_for(candidate, self.contract)
        # The Bank often contains the same stable proposition copied into a
        # world fact, an experience and a later explanatory restatement.  Exact
        # text dedupe alone leaves those long near-duplicates competing for the
        # same context budget.  Merge only when one normalized statement is a
        # substantial prefix of the other *and* both occupy the same semantic
        # slot; a short shared lead is deliberately not enough to collapse two
        # different decisions.
        if key not in self._claims and len(key) >= 48:
            for known_key, known_claim in self._claims.items():
                if (
                    known_claim.slot == slot
                    and min(len(key), len(known_key)) >= 48
                    and (key.startswith(known_key) or known_key.startswith(key))
                ):
                    key = known_key
                    break
        claim = self._claims.get(key)
        if claim is None:
            claim = _MutableClaim(
                statement=candidate.text.strip(),
                slot=slot,
                authority=candidate.authority,
                tokens=max(1, candidate.tokens),
                historical=self.contract.allow_historical and slot not in {'current', 'answer'},
            )
            self._claims[key] = claim
        if candidate.record_id not in claim.evidence_ids:
            claim.evidence_ids.append(candidate.record_id)
        if candidate.channel not in claim.channels:
            claim.channels.append(candidate.channel)
        for entity in candidate.entities:
            if entity not in claim.entities:
                claim.entities.append(entity)
        if candidate.relation_path and candidate.relation_path not in claim.relation_paths:
            claim.relation_paths.append(candidate.relation_path)
        claim.authority = max(claim.authority, candidate.authority)
        claim.tokens = min(claim.tokens, max(1, candidate.tokens))

    def claims(self) -> tuple[Claim, ...]:
        return tuple(
            Claim(
                claim_key=key,
                statement=value.statement,
                slot=value.slot,
                evidence_ids=tuple(value.evidence_ids),
                channels=tuple(value.channels),
                entities=tuple(value.entities),
                relation_paths=tuple(value.relation_paths),
                authority=value.authority,
                tokens=value.tokens,
                historical=value.historical,
            )
            for key, value in self._claims.items()
        )

    def coverage(self) -> CoverageDecision:
        claims = self.claims()
        slots = {claim.slot for claim in claims}
        covered: list[str] = []
        for required in self.contract.required_slots:
            if required == 'stages':
                if any(slot not in {'origin', 'current', 'answer'} for slot in slots):
                    covered.append(required)
            elif required == 'sources':
                if claims:
                    covered.append(required)
            elif required == 'scope':
                if claims:
                    covered.append(required)
            elif required == 'findings':
                if any(slot in {'finding', 'answer'} for slot in slots):
                    covered.append(required)
            elif required in slots:
                covered.append(required)
        missing = tuple(slot for slot in self.contract.required_slots if slot not in covered)
        if not missing:
            status, reason = 'complete', 'all_required_claim_slots_have_evidence'
        elif claims:
            status, reason = 'incomplete', 'required_claim_slots_are_missing'
        else:
            status, reason = 'incomplete', 'no_evidence_candidates'
        return CoverageDecision(status, self.contract.required_slots, tuple(covered), missing, reason)


class RetrievalSession:
    """One execution-scoped, progressively expanded evidence session."""
    def __init__(self, contract: QueryContract):
        self.contract = contract
        self.ledger = ClaimLedger(contract)
        self.rounds: list[tuple[EvidenceCandidate, ...]] = []
        self.channel_trace: list[dict[str, object]] = []

    def graph_seeds(self) -> tuple[str, ...]:
        seeds = list(self.contract.canonical_entities)
        for claim in self.ledger.claims():
            for entity in claim.entities:
                if entity not in seeds:
                    seeds.append(entity)
            for evidence_id in claim.evidence_ids:
                handle = f'memory:{evidence_id}'
                if handle not in seeds:
                    seeds.append(handle)
        return tuple(seeds)

    def add_round(self, candidates: Iterable[EvidenceCandidate], channel: str | None = None) -> tuple[EvidenceCandidate, ...]:
        batch = tuple(candidates)
        for candidate in batch:
            self.ledger.add(candidate)
        self.rounds.append(batch)
        self.channel_trace.append({
            'round': len(self.rounds),
            'channel': channel or (batch[0].channel if batch else 'none'),
            'candidate_count': len(batch),
            'claim_count': len(self.ledger.claims()),
            'graph_seeds': self.graph_seeds(),
        })
        return batch

    def coverage(self) -> CoverageDecision:
        return self.ledger.coverage()

    def collect(self, provider: CandidateProvider, channels: tuple[str, ...] | None = None, max_rounds: int = 3) -> CoverageDecision:
        channels = channels or ('semantic', 'lexical', 'temporal', 'entity', 'graph', 'constellation', 'source')
        previous_required = -1
        stable_rounds = 0
        for _ in range(max_rounds):
            before = len(self.ledger.claims())
            for channel in channels:
                if channel in {'graph', 'constellation'}:
                    queries = self.graph_seeds()
                else:
                    queries = (self.contract.request,) + self.contract.canonical_entities
                self.add_round(provider(channel, tuple(dict.fromkeys(queries)), self.contract), channel)
            coverage = self.coverage()
            after = len(self.ledger.claims())
            required_covered = len(coverage.covered_slots)
            if coverage.status == 'complete' and required_covered == previous_required and after == before:
                stable_rounds += 1
            else:
                stable_rounds = 0
            previous_required = required_covered
            if coverage.status == 'complete' and (stable_rounds >= 1 or after == before):
                return coverage
        return self.coverage()


def _priority(claim: Claim, contract: QueryContract) -> tuple[int, float, int, str]:
    if contract.workload == 'evolution':
        order = {'origin': 0, 'stage': 1, 'hooks_controller': 1, 'graph_constellation': 1, 'current': 2}
        slot_rank = order.get(claim.slot, 1)
    else:
        slot_rank = 0 if claim.slot in {'answer', 'finding'} else 1
    return (slot_rank, -claim.authority, claim.tokens, claim.statement)


def pack_claims(ledger: ClaimLedger, token_budget: int) -> dict[str, object]:
    """Pack distinct claims, preferring required stages over duplicate evidence."""
    selected: list[dict[str, object]] = []
    used = 0
    for claim in sorted(ledger.claims(), key=lambda item: _priority(item, ledger.contract)):
        if used + claim.tokens > token_budget:
            continue
        selected.append({
            'claim_key': claim.claim_key,
            'statement': claim.statement,
            'slot': claim.slot,
            'evidence_ids': list(claim.evidence_ids),
            'channels': list(claim.channels),
            'entities': list(claim.entities),
            'relation_paths': [list(path) for path in claim.relation_paths],
            'authority': claim.authority,
            'tokens': claim.tokens,
            'historical': claim.historical,
        })
        used += claim.tokens
    coverage = ledger.coverage()
    return {
        'schema': 'ham.claim_pack.v1',
        'execution_id': ledger.contract.execution_id,
        'claims': selected,
        'token_budget': token_budget,
        'used_tokens': used,
        'coverage': {
            'status': coverage.status,
            'required_slots': list(coverage.required_slots),
            'covered_slots': list(coverage.covered_slots),
            'missing_slots': list(coverage.missing_slots),
            'reason': coverage.reason,
        },
        'expansion_handle': None if coverage.status == 'complete' else f'mer:{ledger.contract.execution_id}',
    }
