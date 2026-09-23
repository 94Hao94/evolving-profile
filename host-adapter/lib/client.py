"""Hindsight REST API client.

Communicates with a Hindsight server via HTTP. Mirrors the HTTP mode of the
Openclaw HindsightClient (client.js), adapted for Python stdlib.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

DEFAULT_TIMEOUT = 15  # seconds
HEALTH_CHECK_RETRIES = 3
HEALTH_CHECK_DELAY = 2  # seconds


def _plugin_version() -> str:
    """Read the plugin version from settings.json (single source of truth)."""
    manifest = Path(__file__).resolve().parents[2] / "settings.json"
    try:
        return json.loads(manifest.read_text()).get("version", "0.0.0")
    except (OSError, ValueError):
        return "0.0.0"


# Sent on every request so self-hosted deployments behind Cloudflare (or any
# reverse proxy with UA-based bot filtering) don't block the stdlib default
# "Python-urllib/X.Y", which trips Cloudflare error 1010.
USER_AGENT = f"hindsight-codex/{_plugin_version()}"


def _validate_api_url(url: str) -> str:
    """Validate and normalize the API URL. Reject non-HTTP schemes."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Evolving Profile API URL must use http or https, got: {parsed.scheme!r}")
    if not parsed.hostname:
        raise ValueError(f"Evolving Profile API URL has no hostname: {url!r}")
    return url.rstrip("/")


class HindsightClient:
    """HTTP client for the Hindsight API."""

    def __init__(
        self,
        api_url: str,
        api_token: Optional[str] = None,
        request_headers: Optional[dict[str, str]] = None,
    ):
        self.api_url = _validate_api_url(api_url)
        self.api_token = api_token
        self.request_headers = dict(request_headers or {})

    def _headers(self) -> dict:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        headers.update(self.request_headers)
        return headers

    def _request(self, method: str, path: str, body: Optional[dict] = None, timeout: int = DEFAULT_TIMEOUT) -> dict:
        url = f"{self.api_url}{path}"
        data = json.dumps(body).encode() if body else None
        headers = self._headers()
        if method == "POST" and path.endswith("/memories/recall"):
            # Per-request socket contract; do not mutate shared client headers
            # while primary/shared-bank calls run concurrently.
            headers["X-Memory-Transport-Timeout-Ms"] = str(int(timeout * 1000))
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body_text = ""
            try:
                body_text = e.read().decode()
            except Exception:
                pass
            raise RuntimeError(f"HTTP {e.code} from {url}: {body_text}") from e

    def health_check(self, timeout: int = 5) -> bool:
        """Check if the Hindsight server is reachable.

        Mirrors Openclaw's checkExternalApiHealth: retries up to 3 times
        with 2s delay between attempts.
        """
        import time

        for attempt in range(1, HEALTH_CHECK_RETRIES + 1):
            try:
                url = f"{self.api_url}/health"
                req = urllib.request.Request(url, headers=self._headers(), method="GET")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                pass
            if attempt < HEALTH_CHECK_RETRIES:
                time.sleep(HEALTH_CHECK_DELAY)
        return False

    def recall(
        self,
        bank_id: str,
        query: str,
        max_tokens: int = 1024,
        budget: str = "mid",
        types: Optional[list] = None,
        prefer_observations: Optional[bool] = None,
        min_scores: Optional[dict] = None,
        raw_user_prompt: Optional[str] = None,
        full_prompt: Optional[str] = None,
        full_prompt_source: Optional[str] = None,
        timeout: int = 10,
    ) -> dict:
        """Recall memories from a bank.

        Returns the raw API response dict with 'results' list.
        """
        path = f"/v1/default/banks/{urllib.parse.quote(bank_id, safe='')}/memories/recall"
        body = {
            "query": query,
            "max_tokens": max_tokens,
        }
        # ``query`` is the resolved Full Prompt used for retrieval.  Preserve
        # the user's extracted raw turn separately so Controller/9998 can show
        # the real wording without confusing it with semantic expansion.
        # This is an audit field only; it never changes retrieval ranking.
        if raw_user_prompt is not None:
            body["raw_user_prompt"] = str(raw_user_prompt)
        # Headers are retained for backward-compatible small adapters, but a
        # resolved Full Prompt is semantic input rather than metadata.  Carry
        # it in the JSON body too so multi-paragraph/large contracts are not
        # silently dropped at a proxy/header ceiling.
        if full_prompt is not None:
            body["full_prompt"] = str(full_prompt)
        if full_prompt_source is not None:
            body["full_prompt_source"] = str(full_prompt_source)
        if budget:
            body["budget"] = budget
        if types:
            body["types"] = types
        if prefer_observations is not None:
            body["prefer_observations"] = bool(prefer_observations)
        # Explicit floors override the server-wide retrieval defaults.  This is
        # useful for evidence banks imported in chunks mode: the local
        # cross-encoder may assign a low absolute reranker score even when the
        # result is the best direct quotation for a query.
        if min_scores is not None:
            body["min_scores"] = min_scores
        return self._request("POST", path, body, timeout=timeout)

    def get_mental_model(
        self,
        bank_id: str,
        mental_model_id: str,
        detail: str = "full",
        timeout: int = 5,
    ) -> dict:
        """Return one curated mental model for routed, low-latency injection."""
        path = (
            f"/v1/default/banks/{urllib.parse.quote(bank_id, safe='')}/mental-models/"
            f"{urllib.parse.quote(mental_model_id, safe='')}?detail="
            f"{urllib.parse.quote(detail, safe='')}"
        )
        return self._request("GET", path, timeout=timeout)

    def retain(
        self,
        bank_id: str,
        content: str,
        document_id: str = "conversation",
        context: Optional[str] = None,
        metadata: Optional[dict] = None,
        tags: Optional[list] = None,
        observation_scopes=None,
        strategy: Optional[str] = None,
        timeout: int = 15,
    ) -> dict:
        """Retain content into a bank's memory.

        Posts with async=true so the server processes in the background.
        The context field helps Hindsight cluster memories by provenance
        (e.g. "claude-code" vs manual retains).
        """
        path = f"/v1/default/banks/{urllib.parse.quote(bank_id, safe='')}/memories"
        item = {
            "content": content,
            "document_id": document_id,
            "metadata": metadata or {},
        }
        if context:
            item["context"] = context
        if tags:
            item["tags"] = tags
        if observation_scopes is not None:
            item["observation_scopes"] = observation_scopes
        if strategy:
            item["strategy"] = strategy
        body = {
            "items": [item],
            "async": True,
        }
        return self._request("POST", path, body, timeout=timeout)

    def operation_status(self, bank_id: str, operation_id: str, timeout: int = 10) -> dict:
        """Return the status of one asynchronous bank operation."""
        path = (
            f"/v1/default/banks/{urllib.parse.quote(bank_id, safe='')}/operations/"
            f"{urllib.parse.quote(operation_id, safe='')}"
        )
        return self._request("GET", path, timeout=timeout)

    def set_bank_mission(
        self, bank_id: str, mission: str, retain_mission: Optional[str] = None, timeout: int = 15
    ) -> dict:
        """Set the mission/persona for a bank.

        Uses PATCH /banks/{id}/config with reflect_mission and retain_mission.
        The old PUT /banks/{id} with 'mission' field is deprecated in v0.4.19.
        """
        path = f"/v1/default/banks/{urllib.parse.quote(bank_id, safe='')}/config"
        updates = {"reflect_mission": mission}
        if retain_mission:
            updates["retain_mission"] = retain_mission
        return self._request("PATCH", path, {"updates": updates}, timeout=timeout)
