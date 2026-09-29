"""Isolated external-file retrieval. This module never reads the EP Bank."""
from __future__ import annotations

import json
import re
import zipfile
import math
from pathlib import Path
from xml.etree import ElementTree

from runtime_settings import load_runtime_settings, route_policy

_TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json", ".html", ".htm"}
_STOP = {"的", "了", "是", "和", "与", "在", "对", "这个", "那个", "哪些", "什么"}


def _terms(value: str) -> list[str]:
    raw = re.findall(r"[a-zA-Z][a-zA-Z0-9_.-]{1,}|[0-9]+(?:\.[0-9]+)?|[\u4e00-\u9fff]{2,}", value.casefold())
    terms = []
    for term in raw:
        if term in _STOP:
            continue
        terms.append(term)
        if re.fullmatch(r"[\u4e00-\u9fff]+", term):
            terms.extend(term[index:index + 2] for index in range(len(term) - 1))
    return list(dict.fromkeys(terms))


def _read_file(path: Path) -> str:
    if path.suffix.lower() in _TEXT_EXTENSIONS:
        return path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".docx":
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
        return " ".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
            return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        except Exception:
            return ""
    return ""


def _chunks(text: str, size: int = 1400) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    return [normalized[index:index + size] for index in range(0, len(normalized), size)] if normalized else []


def _vector_scores(query: str, chunks: list[str], model_name: str) -> tuple[list[float] | None, str]:
    if not model_name:
        return None, "not_configured"
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name)
        vectors = model.encode([query, *chunks], normalize_embeddings=True)
        query_vector = vectors[0]
        scores = [sum(float(a) * float(b) for a, b in zip(query_vector, vector)) for vector in vectors[1:]]
        return scores, "sentence_transformers"
    except Exception as error:
        return None, f"unavailable:{type(error).__name__}"


def _rerank(query: str, items: list[dict], model_name: str) -> tuple[list[dict], str]:
    if not model_name or not items:
        return items, "not_configured"
    try:
        from flashrank import Ranker, RerankRequest
        passages = [{"id": item["id"], "text": item["text"]} for item in items]
        ranked = Ranker(model_name=model_name).rerank(RerankRequest(query=query, passages=passages))
        by_id = {item["id"]: item for item in items}
        result = []
        for row in ranked:
            item = dict(by_id.get(row.get("id"), {}))
            if item:
                item["rerank_score"] = float(row.get("score", 0.0))
                item["retrieval"]["reranked"] = True
                result.append(item)
        return result or items, "flashrank"
    except Exception as error:
        return items, f"unavailable:{type(error).__name__}"


def _retrieval_model(settings: dict, kind: str, profile_id: str | None) -> tuple[dict, str]:
    """Resolve the model selected in the UI, without crossing into EP data."""
    models = settings.get("retrieval_models") or {}
    model = models.get(kind) if isinstance(models.get(kind), dict) else {}
    profiles = models.get(f"{kind}_profiles")
    if profile_id and isinstance(profiles, list):
        selected = next((item for item in profiles if isinstance(item, dict) and str(item.get("profile_id")) == str(profile_id)), None)
        if selected is not None:
            model = selected
    configured_id = str(model.get("profile_id") or "")
    if profile_id and configured_id and profile_id != configured_id:
        return {}, ""
    if not model.get("enabled", True):
        return model, ""
    local_path = str(model.get("local_path") or "").strip()
    name = local_path or str(model.get("model") or "").strip()
    return model, name


def search_external_rag(query: str, *, limit: int = 8) -> dict:
    settings = load_runtime_settings()
    policy = route_policy(settings, "external_rag")
    rag = settings.get("rag") or {}
    if not policy["rag_enabled"]:
        return {"schema": "evolving-profile.external-rag.v1", "status": "disabled_by_runtime_settings", "items": [], "source": "external_rag", "ep_accessed": False}
    root = Path(str(rag.get("root_path") or "")).expanduser()
    if not root.exists() or not root.is_dir():
        return {"schema": "evolving-profile.external-rag.v1", "status": "root_unavailable", "root_path": str(root), "items": [], "source": "external_rag", "ep_accessed": False}
    query_terms = _terms(query)
    rows = []
    documents = []
    for path in root.rglob("*"):
        if not path.is_file() or path.name.startswith("."):
            continue
        text = _read_file(path)
        for index, chunk in enumerate(_chunks(text)):
            documents.append((path, index, chunk))
    embedding, embedding_name = _retrieval_model(settings, "embedding", rag.get("embedding_profile_id"))
    reranker, reranker_name = _retrieval_model(settings, "reranker", rag.get("reranker_profile_id"))
    vector_values, vector_backend = _vector_scores(query, [row[2] for row in documents], embedding_name) if rag.get("vector_enabled", True) else (None, "disabled")
    for position, (path, index, chunk) in enumerate(documents):
            chunk_terms = set(_terms(chunk))
            overlap = len(chunk_terms.intersection(query_terms))
            lexical = overlap / max(1, len(query_terms))
            vector = float(vector_values[position]) if vector_values else 0.0
            if overlap or vector > 0:
                rows.append((lexical, vector, path, index, chunk))
    rows.sort(key=lambda row: (row[0] + row[1], str(row[2])), reverse=True)
    items = [{"id": f"rag:{path}:{index}", "source": "external_rag", "path": str(path), "chunk_index": index,
              "score": round(lexical, 4), "text": chunk, "retrieval": {"lexical": lexical > 0, "vector": vector > 0, "reranked": False}, "vector_score": round(vector, 4)}
             for lexical, vector, path, index, chunk in rows[:max(1, min(50, int(limit) * 5))] ]
    items, rerank_backend = _rerank(query, items, reranker_name if rag.get("rerank_enabled", True) else "")
    items = items[:max(1, min(50, int(limit)))]
    return {"schema": "evolving-profile.external-rag.v1", "status": "ok", "items": items,
            "source": "external_rag", "ep_accessed": False, "query_terms": query_terms,
            "retrieval": {"mode": "hybrid", "fusion": rag.get("fusion", "rrf"), "rerank_enabled": bool(rag.get("rerank_enabled", True)), "rerank_backend": rerank_backend, "vector_enabled": bool(rag.get("vector_enabled", True)), "vector_backend": vector_backend, "embedding_profile_id": rag.get("embedding_profile_id") or embedding.get("profile_id"), "reranker_profile_id": rag.get("reranker_profile_id") or reranker.get("profile_id")}}
