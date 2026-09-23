"""Query-shape router backed by the local Memory Query Controller.

The role policy remains the authorization boundary.  When the local controller
is restarting, the former V3 router is used for one-turn graceful degradation.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .memory_router_v3 import build_plan as build_plan_v3
from .memory_router_v3 import load_policy


def resolve_client_adapter(hook_input: dict[str, Any], configured_role: str = "codex") -> tuple[str, str]:
    """Map known local Codex-backed surfaces by runtime path, never by topic."""
    # Test and audit callers may label their own traces so dashboards do not
    # mistake regression probes for a real user conversation.  The override
    # changes only the trace client label; role permissions remain configured.
    override = str(hook_input.get("memory_client_override") or "").strip()
    if override and len(override) <= 96 and all(ch.isalnum() or ch in "._-" for ch in override):
        return configured_role, override
    cwd = str(hook_input.get("cwd") or "").replace("\\", "/").casefold()
    transcript = str(hook_input.get("transcript_path") or "").replace("\\", "/").casefold()
    location = f"{cwd}\n{transcript}"
    if "/.y-core/trainer-terra" in location:
        return "trainer", "trainer-codex-hook"
    if "/iphone-special-chat/gateway" in location or "/.iphone-codex/" in location:
        return "xiaodai", "xiaodai-codex-hook"
    return configured_role, "codex-hook"


def build_payload(
    role: str,
    query: str,
    client: str,
    bank_id: str,
    contextual_intent: dict[str, Any] | None = None,
    agent_plan: dict[str, Any] | None = None,
    full_prompt: str = "",
    full_prompt_source: str = "",
) -> dict[str, Any]:
    """Build the bounded Controller plan payload without exposing a transcript."""
    payload: dict[str, Any] = {
        "role": role,
        "query": query,
        "client": client,
        "bank_id": bank_id,
    }
    runtime_context: dict[str, Any] = {}
    if isinstance(contextual_intent, dict) and contextual_intent:
        # The envelope contains a small, selected context receipt.  Deliberately
        # do not forward transcript paths or arbitrary Hook input.
        runtime_context["contextual_intent"] = contextual_intent
    if full_prompt:
        runtime_context["full_prompt"] = str(full_prompt)[:48000]
        runtime_context["full_prompt_source"] = str(full_prompt_source or "agent_contract")[:80]
    if runtime_context:
        payload["runtime_context"] = runtime_context
    if isinstance(agent_plan, dict):
        payload["agent_plan"] = agent_plan
    return payload


def build_plan(
    role: str,
    query: str,
    policy: dict[str, Any],
    *,
    controller_url: str = "http://127.0.0.1:12079",
    timeout: float = 0.8,
    client: str = "codex",
    bank_id: str = "",
    contextual_intent: dict[str, Any] | None = None,
    agent_plan: dict[str, Any] | None = None,
    full_prompt: str = "",
    full_prompt_source: str = "",
) -> dict[str, Any]:
    payload = build_payload(
        role, query, client, bank_id, contextual_intent, agent_plan,
        full_prompt, full_prompt_source,
    )
    # Codex/Hermes may send a later explicit semantic judgment.  The controller
    # validates it and grants route/coverage hints only; permissions and source
    # level remain governed by the central policy.
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        controller_url.rstrip("/") + "/v1/plan",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Memory-Role": role,
            # The plan call is a sub-second routing probe. It must remain
            # deterministic and never wait for optional model planning.
            "X-Memory-Plan-Only": "1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            plan = json.loads(response.read().decode("utf-8"))
        if plan.get("schema") != 1 or not plan.get("primary_shape"):
            raise ValueError("invalid controller plan")
        plan["router"] = "memory-query-controller"
        plan["controller_fallback"] = False
        return plan
    except Exception as error:
        fallback = build_plan_v3(role, query, policy)
        fallback.update({
            "schema": 1,
            "router": "memory-router-v3-fallback",
            "controller_fallback": True,
            "controller_error": str(error),
            "primary_shape": "point",
            "matched_shapes": ["point"],
            "strategies": ["semantic_point"],
            "budget": "mid",
            "max_tokens": 1200,
            "types": ["observation", "world", "experience"],
            "prefer_observations": True,
            "coverage_dimensions": ["semantic"],
            "coverage_required": False,
            "scope_claim": "indexed_scope_only",
            "requires_direct_evidence": bool(fallback.get("direct_evidence")),
            "mental_model_policy": "routed_only",
            "query_count": 1,
            "queries": [query],
            "fallback": "memory_router_v3",
        })
        return fallback
