"""Generic, navigation-only context discovery and competing scope hypotheses.

This module deliberately does not decide which project is true. It exposes
bounded Session/verified-Project locators, keeps unverified workspace buckets
out, and lets the current Agent choose the next evidence route.
"""
from __future__ import annotations

import re


_STOP = {
    '用户', '之前', '历史', '记录', '相关', '项目', '方案', '内容', '什么', '哪个',
    '哪些', '有没有', '查询', '查找', '回顾', '设计过', '做过', '工作', '申报', '方向',
}


def _terms(text: str) -> list[str]:
    value = str(text or '').casefold()
    parts = re.findall(r'[a-z][a-z0-9_.+-]{1,}|[0-9]+(?:\.[0-9]+)?|[\u4e00-\u9fff]{2,}', value)
    terms: list[str] = []
    for part in parts:
        if part in _STOP:
            continue
        if re.fullmatch(r'[\u4e00-\u9fff]{4,}', part):
            terms.extend(part[i:i + 2] for i in range(len(part) - 1))
            terms.extend(part[i:i + 3] for i in range(len(part) - 2))
        else:
            terms.append(part)
    return list(dict.fromkeys(terms))


def _institution_terms(text: str) -> set[str]:
    result: set[str] = set()
    for phrase in re.findall(r'[\u4e00-\u9fff]{2,}(?:大学|学院|学校)', str(text or '').casefold()):
        result.update(_terms(phrase))
    return result


def _semantic_terms(text: str) -> list[str]:
    """Coarse generic concepts, avoiding overlapping character n-gram voting."""
    value = str(text or '').casefold()
    result: list[str] = []
    for part in re.findall(r'[a-z][a-z0-9_.+-]{1,}|[0-9]+(?:\.[0-9]+)?|[\u4e00-\u9fff]{2,}', value):
        if part in _STOP:
            continue
        if re.fullmatch(r'[\u4e00-\u9fff]+', part):
            # Keep a Chinese task phrase intact for qualification. Generic
            # character n-grams remain available through _terms for ranking,
            # but must not make a neighboring project qualify on one shared
            # word such as "智能" or "数据".
            result.append(part)
        else:
            result.append(part)
    return list(dict.fromkeys(result))


def _is_numeric_or_amount_term(term: str) -> bool:
    value = str(term or '').casefold()
    return bool(re.fullmatch(r'\d+(?:\.\d+)?', value)) or value in {'万元', '万', '元', '亿元', '亿'}


def _row_text(row: dict) -> str:
    summary = row.get('summary') or {}
    # Search only navigation labels and bounded compact text internally. Never
    # return this body to the Agent from this route.
    return ' '.join(str(row.get(key) or '') for key in ('title', 'project_key', 'session_id')) + ' ' + str(summary.get('compact') or '')


def _navigation_title(row: dict) -> str:
    title = str(row.get('title') or '').strip()
    if title:
        return title[:160]
    first = str((row.get('summary') or {}).get('compact') or '').split('\n', 1)[0].strip()
    if first.startswith('# '):
        return first[2:].strip()[:160]
    return ''


def search_contexts(index: dict, query: str, *, context_type: str = 'both', limit: int = 8) -> dict:
    if not isinstance(query, str) or not query.strip():
        raise ValueError('query is required')
    if context_type not in {'both', 'session', 'project'}:
        raise ValueError('context_type must be both, session or project')
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError('limit must be 1..20')
    terms = _terms(query)
    institution_terms = _institution_terms(query)
    query_without_institutions = query
    for phrase in re.findall(r'[\u4e00-\u9fff]{2,}(?:大学|学院|学校)', query.casefold()):
        query_without_institutions = query_without_institutions.replace(phrase, ' ')
    content_terms = _semantic_terms(query_without_institutions)
    strong_content_terms = [term for term in content_terms if not _is_numeric_or_amount_term(term)]
    rows = []
    background_rows = []
    excluded = 0
    for kind in ('sessions', 'projects'):
        if context_type != 'both' and kind[:-1] != context_type:
            continue
        for row in index.get(kind) or []:
            if not isinstance(row, dict):
                continue
            if kind == 'projects' and row.get('identity_status') != 'verified_project':
                excluded += 1
                continue
            text = _row_text(row).casefold()
            hits = [term for term in terms if term in text]
            content_hits = [term for term in content_terms if term in text]
            strong_hits = [term for term in strong_content_terms if term in text]
            # If a query includes a discriminative subject/task, institution
            # overlap alone is insufficient. Institution-only queries remain
            # useful broad navigation requests.
            required_content_hits = min(2, len(content_terms)) if content_terms else 0
            institution_hits = [term for term in institution_terms if term in text]
            title = str(row.get('title') or '').casefold()
            title_hits = [term for term in hits if term in title]
            score = len(hits) + (2 * len(title_hits))
            institution_match = (score, len(institution_hits), str(row.get('updated_at') or ''), row, hits)
            content_match = bool(strong_hits) if strong_content_terms else len(content_hits) >= required_content_hits
            if content_terms and not content_match:
                if institution_hits:
                    # An institution-only match is useful audit context, but it
                    # must not consume a competing-project read slot when a
                    # discriminative task match is available.
                    background_rows.append(institution_match)
                continue
            hits = [term for term in terms if term in text]
            rows.append((score, len(title_hits), str(row.get('updated_at') or ''), row, hits, strong_hits))
    rows.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    background_rows.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    items = []
    sorted_rows = rows[:limit]
    top_score = sorted_rows[0][0] if sorted_rows else 0
    second_score = sorted_rows[1][0] if len(sorted_rows) > 1 else 0
    decisive_gap = bool(top_score and (not second_score or top_score >= second_score * 1.5))
    for position, (score, title_hits, _, row, hits, strong_hits) in enumerate(sorted_rows):
        role = 'primary_candidate' if position == 0 and decisive_gap else ('competing_candidate' if position < 3 else 'background_signal')
        items.append({
            'scenario_id': row.get('context_id'),
            'scenario_type': row.get('context_type'),
            'session_id': row.get('session_id'),
            'project_key': row.get('project_key'),
            'navigation_title': _navigation_title(row),
            'status': row.get('status') or 'unknown',
            'identity_status': 'session_id_matched' if row.get('context_type') == 'session' else 'verified_project',
            'updated_at': row.get('updated_at'),
            'source_ids': list(row.get('source_ids') or []),
            'source_revision': row.get('source_revision'),
            'match_signals': {'terms': hits[:20], 'strong_terms': strong_hits[:20], 'score': score, 'title_hits': title_hits},
            'navigation_role': role,
            'navigation_only': True,
            'next_tool': 'read_scenario_summary',
        })
    background_items = []
    for score, title_hits, _, row, hits in background_rows[:limit]:
        background_items.append({
            'scenario_id': row.get('context_id'),
            'scenario_type': row.get('context_type'),
            'session_id': row.get('session_id'),
            'project_key': row.get('project_key'),
            'navigation_title': _navigation_title(row),
            'status': row.get('status') or 'unknown',
            'identity_status': 'session_id_matched' if row.get('context_type') == 'session' else 'verified_project',
            'updated_at': row.get('updated_at'),
            'source_ids': list(row.get('source_ids') or []),
            'source_revision': row.get('source_revision'),
            'match_signals': {'terms': hits[:20], 'score': score, 'title_hits': title_hits, 'match_kind': 'institution_only'},
            'navigation_role': 'background_signal',
            'navigation_only': True,
            'next_tool': 'read_scenario_summary',
        })
    top_scores = [item['match_signals']['score'] for item in items[:2]]
    ambiguous = len(top_scores) > 1 and top_scores[0] <= max(1, int(top_scores[1] * 1.25))
    return {
        'schema': 'evolving-profile.scenario-context-search.v1',
        'source': 'scenario_context_index',
        'items': items,
        'background_items': background_items,
        'coverage': {
            'status': 'returned' if items else 'not_found_in_context_index',
            'navigation_only': True,
            'bank_absence': 'unknown',
            'query_terms': terms[:20], 'content_terms': content_terms[:20],
            'excluded_unverified_projects': excluded,
            'background_candidates': len(background_items),
            'ambiguous_top_candidates': ambiguous,
            'decisive_top_candidate': decisive_gap,
            'index_status': index.get('status') or 'unknown',
        },
        'route_policy': {
            'state': 'scope_unresolved' if ambiguous or len(items) > 1 else 'scope_candidate_only',
            'required_next_action': 'read_scenario_summary_compact_for_top_competing_sessions',
            'defer_bank_retrieval_until_scope_check': bool(items and (ambiguous or len(items) > 1)),
            'reason': 'Do not let same-institution Bank candidates redefine the target project before Session scope is checked.',
            'read_budget': {
                'scenario_compact_max': 2,
                'direct_source_max_per_hypothesis': 3,
                'stop_if_no_new_unresolved_slot': True,
                'stop_if_same_source_or_session_repeats': True,
                'on_conflict': 'retain_unresolved_and_report',
            },
        },
        'boundary': 'Directory candidates are not Bank facts, not project identity proof, and not a complete history search.',
    }


def build_hypotheses(query: str, candidates: list[dict]) -> dict:
    """Return competing, non-authoritative scope bundles for the Agent."""
    if not isinstance(candidates, list):
        raise ValueError('candidates must be an array')
    hypotheses = []
    for item in candidates[:20]:
        if not isinstance(item, dict) or not item.get('scenario_id'):
            continue
        signals = item.get('match_signals') or {}
        hypotheses.append({
            'hypothesis_id': 'scope:' + str(item['scenario_id']),
            'scenario_ids': [item['scenario_id']],
            'navigation_title': item.get('navigation_title') or '',
            'match_signals': signals,
            'status': 'ambiguous' if len(candidates) > 1 else 'candidate',
            'required_next_evidence': ['read_scenario_summary', 'read_source'],
            'accepted_as_fact': False,
            'reason': 'same-level candidates remain competing explanations; current Agent must verify object, version and source range',
        })
    return {
        'schema': 'evolving-profile.scope-hypotheses.v1',
        'query': query,
        'decision': 'agent_decides' if hypotheses else 'none',
        'hypotheses': hypotheses,
        'unresolved': ['target project identity', 'version/currentness', 'direct source support'] if hypotheses else ['no context candidate found'],
        'boundary': 'Hypotheses are navigation aids only; no candidate is promoted to a fact or injected conclusion.',
    }
