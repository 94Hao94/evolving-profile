"""Small, bounded semantic candidate retrieval for reviewed guidance units.

Semantic similarity discovers paraphrases.  It never grants applicability:
lifecycle and explicit scope are checked before any vector score is considered.
"""
from __future__ import annotations

import math
from hashlib import sha256
import json
import os
from pathlib import Path
import urllib.error
import urllib.request


def _unit_text(unit: dict) -> str:
    return " ".join([str(unit.get("text") or ""), *(unit.get("applies_when") or [])])


class SemanticVectorCache:
    """Version-keyed derived cache; it is not a second memory store.

    Only the vector and a content hash are retained. The underlying preference
    remains in GuidanceRepository and an edit/revision naturally invalidates it.
    """
    def __init__(self, path: str | Path, *, embed_many):
        self.path = Path(path)
        self.embed_many = embed_many
        try:
            self._values = json.loads(self.path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            self._values = {}

    def document_vector(self, unit: dict) -> list[float]:
        text = _unit_text(unit)
        digest = sha256(text.encode()).hexdigest()
        key = f"{unit['id']}:{unit['revision']}:{digest}"
        value = self._values.get(key)
        if value is not None:
            return value
        vector = list(self.embed_many([text])[0])
        self._values[key] = vector
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self._values, separators=(",", ":")))
        temporary.replace(self.path)
        return vector

    def document_vectors(self, units: list[dict]) -> list[list[float]]:
        """Fill all missing revisions with one bounded batch request."""
        keys=[]; missing=[]
        for unit in units:
            text=_unit_text(unit)
            digest=sha256(text.encode()).hexdigest()
            key=f"{unit['id']}:{unit['revision']}:{digest}"
            keys.append(key)
            if key not in self._values:
                missing.append((key,text))
        if missing:
            vectors=self.embed_many([text for _,text in missing])
            if len(vectors)!=len(missing):
                raise RuntimeError('semantic_embedding_batch_mismatch')
            for (key,_),vector in zip(missing,vectors):
                self._values[key]=list(vector)
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.path.with_suffix(self.path.suffix+'.tmp')
            temporary.write_text(json.dumps(self._values,separators=(',',':')))
            temporary.replace(self.path)
        return [self._values[key] for key in keys]


class LocalGuidanceEmbeddingClient:
    """Small local HTTP client for Evolving Profile's already-loaded encoder."""
    def __init__(self, endpoint: str, *, timeout_seconds: float = 1.5):
        self.endpoint=endpoint.rstrip('/')
        self.timeout_seconds=timeout_seconds

    def embed_many(self, texts: list[str], input_type: str = 'document') -> list[list[float]]:
        payload=json.dumps({'texts':texts,'input_type':input_type},ensure_ascii=False).encode()
        headers={'Content-Type':'application/json'}
        api_key=os.getenv('EVOLVING_PROFILE_GUIDANCE_SEMANTIC_API_KEY')
        if api_key:
            headers['Authorization']='Bearer '+api_key
        request=urllib.request.Request(self.endpoint,data=payload,headers=headers,method='POST')
        try:
            with urllib.request.urlopen(request,timeout=self.timeout_seconds) as response:
                body=json.loads(response.read())
        except (urllib.error.URLError,TimeoutError,json.JSONDecodeError) as exc:
            raise RuntimeError('semantic_embedding_unavailable') from exc
        vectors=body.get('vectors') if isinstance(body,dict) else None
        if not isinstance(vectors,list) or len(vectors)!=len(texts):
            raise RuntimeError('semantic_embedding_response_invalid')
        return vectors


class SemanticRecallService:
    """Query-once, cached-document semantic retrieval with explicit fallback."""
    def __init__(self, client: LocalGuidanceEmbeddingClient, cache_path: str | Path):
        self.client=client
        self.cache=SemanticVectorCache(cache_path,embed_many=lambda texts:self.client.embed_many(texts,'document'))

    def candidates(self, units: list[dict], task: dict) -> list[dict]:
        query=str(task.get('current_user_message') or task.get('objective') or '')
        if not query:
            return []
        query_vector=self.client.embed_many([query],'query')[0]
        documents=self.cache.document_vectors(units)
        mapping={_unit_text(unit):vector for unit,vector in zip(units,documents)}
        return semantic_candidates(units,query,embed=lambda text:query_vector if text==query else mapping[text],task=task)


def _scoped_out(unit: dict, task: dict) -> bool:
    scope = unit.get("scope") or {}
    for key in ("project_ids", "task_ids", "agent_roles"):
        required = set(scope.get(key) or [])
        if required and not required.intersection(task.get(key) or []):
            return True
    return False


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding_dimension_mismatch")
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def semantic_candidates(units: list[dict], query: str, *, embed, task: dict | None = None,
                        minimum_score: float = 0.55, relative_margin: float = 0.035,
                        max_candidates: int = 12) -> list[dict]:
    """Return reviewed, scope-compatible semantic candidates in score order.

    ``embed`` deliberately remains injected: tests can use fixed vectors and the
    runtime can provide a cached local model without coupling selection policy to
    a particular provider.
    """
    task = task or {}
    query_vector = embed(query)
    results = []
    for unit in units:
        state = (unit.get("preference_audit") or {}).get("state", "not_reviewed")
        if state not in {"approved", "restricted"} or _scoped_out(unit, task):
            continue
        document = _unit_text(unit)
        score = _cosine(query_vector, embed(document))
        if score < minimum_score:
            continue
        results.append({"unit": unit, "reason": {"source": "semantic", "score": round(score, 4)}})
    results=sorted(results,key=lambda item:(item['reason']['score'],item['unit']['id']),reverse=True)
    if not results:
        return []
    # Short, similarly phrased guidance units often occupy a narrow high cosine
    # band. A global floor would mark the whole registry "related". Keep the
    # local head instead; lexical and condition routes still preserve recall.
    floor=max(minimum_score,results[0]['reason']['score']-relative_margin)
    return [item for item in results if item['reason']['score']>=floor][:max_candidates]


def semantic_candidates_with_batch(units: list[dict], query: str, *, embed_many, task: dict | None = None,
                                   minimum_score: float = 0.55) -> list[dict]:
    """Batch adapter used by the entry path to avoid one model call per unit."""
    documents = [_unit_text(unit) for unit in units]
    vectors = embed_many([query, *documents])
    if len(vectors) != len(documents) + 1:
        raise RuntimeError("semantic_embedding_batch_mismatch")
    by_text = dict(zip([query, *documents], vectors))
    return semantic_candidates(
        units, query, embed=lambda text: by_text[text], task=task, minimum_score=minimum_score
    )
