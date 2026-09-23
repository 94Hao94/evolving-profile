"""One-turn memory strategy selected by the dedicated iPhone gateway.

This module has no dependency on the gateway package so the Hindsight hook can
continue working after either component is upgraded independently.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Optional


FIXED_IPHONE_THREAD_ID = "019fb096-87f6-7692-a648-b6fb0df07a31"
DEFAULT_ENVELOPE_PATH = Path(
    "~/.evolving-profile/codex/state/iphone-memory-mode.json"
).expanduser()
DEFAULT_AUDIT_PATH = Path(
    "~/.evolving-profile/codex/state/iphone-memory-mode-last-consumed.json"
).expanduser()

LENGTHS = {
    "off": 0,
    "short": 800,
    "medium": 2000,
    "long": 5000,
    "extra": 10_000,
}

DEPTHS = {
    "direct": {
        "label": "直接续接",
        "budget": "low",
        "context_turns": 1,
        "relation_hops": "0-1",
        "cross_domain": "necessary_only",
        "query_suffix": "",
        "force_evidence": False,
        "evidence_top_k": 0,
        "source_policy": "structured_first",
    },
    "contextual": {
        "label": "情境理解",
        "budget": "mid",
        "context_turns": 3,
        "relation_hops": "1-2",
        "cross_domain": "adjacent",
        "query_suffix": (
            "\n记忆检索提示：除直接内容外，必要时关联相邻领域、近期变化和关键前因。"
        ),
        "force_evidence": False,
        "evidence_top_k": 1,
        "source_policy": "verify_uncertain",
    },
    "associative": {
        "label": "广泛联想",
        "budget": "high",
        "context_turns": 5,
        "relation_hops": "2-3",
        "cross_domain": "broad",
        "query_suffix": (
            "\n记忆检索提示：主动检查工作、学习、生活、AI使用方式之间"
            "与当前问题有关的迁移关系和长期模式，只保留有实际帮助的关联。"
        ),
        "force_evidence": False,
        "evidence_top_k": 1,
        "source_policy": "trace_key_claims",
    },
    "synthesis": {
        "label": "深度综合",
        "budget": "high",
        "context_turns": 8,
        "relation_hops": "3-4",
        "cross_domain": "deep",
        "query_suffix": (
            "\n记忆检索提示：在相关范围内多跳检索，比较过去与现在，"
            "识别因果链、矛盾、观念变化和跨领域迁移；不得制造关系。"
        ),
        "force_evidence": False,
        "evidence_top_k": 2,
        "source_policy": "compare_sources",
    },
    "evidence": {
        "label": "证据审计",
        "budget": "high",
        "context_turns": 10,
        "relation_hops": "3-4+",
        "cross_domain": "deep",
        "query_suffix": (
            "\n记忆检索提示：进行证据审计；保留来源、时间、版本差异和"
            "必要原话，发现冲突时不要擅自合并。"
        ),
        "force_evidence": True,
        "evidence_top_k": 4,
        "source_policy": "trace_originals",
    },
}


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.strip().encode("utf-8")).hexdigest()


def _write_audit(
    strategy: dict,
    hook_input: dict,
    prompt_hash: str,
) -> None:
    audit_path = Path(
        os.environ.get("IPHONE_CODEX_MEMORY_MODE_AUDIT_PATH")
        or DEFAULT_AUDIT_PATH
    ).expanduser()
    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = audit_path.with_name(f".{audit_path.name}.tmp")
        payload = {
            "version": 1,
            "consumed_at": time.time(),
            "session_id": str(hook_input.get("session_id") or ""),
            "cwd": str(hook_input.get("cwd") or ""),
            "prompt_sha256": prompt_hash,
            "strategy": strategy,
        }
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        os.replace(temporary, audit_path)
    except OSError:
        # Auditability must never break the actual recall hook.
        return


def consume_strategy(
    hook_input: dict,
    prompt: str,
    *,
    path: Optional[Path] = None,
) -> Optional[dict]:
    session_id = str(hook_input.get("session_id") or "")
    envelope_path = Path(
        path
        or os.environ.get("IPHONE_CODEX_MEMORY_MODE_PATH")
        or DEFAULT_ENVELOPE_PATH
    ).expanduser()
    try:
        payload = json.loads(envelope_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if payload.get("expires_at", 0) < time.time():
        envelope_path.unlink(missing_ok=True)
        return None
    # A strategy envelope is scoped to one Codex task. Prompt hash + TTL are
    # additional guards, not a substitute for task identity: two concurrent
    # tasks can legitimately receive the same prompt. Never consume a mode
    # envelope unless the runtime session id exactly matches its producer.
    payload_thread_id = str(payload.get("thread_id") or "")
    if not session_id or payload_thread_id != session_id:
        return None
    prompt_hash = _prompt_hash(prompt)
    if payload.get("prompt_sha256") != prompt_hash:
        return None
    length = payload.get("memory_length")
    depth = payload.get("memory_depth")
    if length not in LENGTHS or depth not in DEPTHS:
        envelope_path.unlink(missing_ok=True)
        return None
    strategy = {
        "source": "iphone_gateway_v2",
        "memory_length": length,
        "memory_depth": depth,
        "max_tokens": LENGTHS[length],
        **DEPTHS[depth],
    }
    envelope_path.unlink(missing_ok=True)
    _write_audit(strategy, hook_input, prompt_hash)
    return strategy


def apply_strategy(config: dict, strategy: Optional[dict]) -> dict:
    effective = dict(config)
    if not strategy:
        return effective
    effective["recallMaxTokens"] = strategy["max_tokens"]
    effective["recallBudget"] = strategy["budget"]
    effective["recallContextTurns"] = strategy["context_turns"]
    effective["evidenceUnifiedTopK"] = strategy["evidence_top_k"]
    effective["iphoneMemoryStrategy"] = strategy
    return effective
