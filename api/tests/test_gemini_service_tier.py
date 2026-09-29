"""Plumbing tests for the Gemini service tier flag."""

from unittest.mock import MagicMock, patch

import pytest

from evolving_profile_api.engine.llm_wrapper import LLMConfig


def test_llm_config_threads_gemini_service_tier_to_provider_impl():
    """End-to-end: LLMConfig -> create_llm_provider -> GeminiLLM carries the tier."""
    pytest.importorskip("google.genai")
    with patch("google.genai.Client", return_value=MagicMock()):
        llm = LLMConfig(
            provider="gemini",
            api_key="fake-key",
            base_url="",
            model="gemini-2.5-flash",
            gemini_service_tier="flex",
        )

    assert llm._provider_impl._service_tier == "flex"


def test_llm_provider_from_env_validates_gemini_service_tier(monkeypatch):
    """Direct env construction rejects the same invalid tiers as HindsightConfig."""
    from evolving_profile_api.config import clear_config_cache
    from evolving_profile_api.engine.llm_wrapper import LLMProvider

    monkeypatch.setenv("EVOLVING_PROFILE_API_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("EVOLVING_PROFILE_API_LLM_API_KEY", "fake-key")
    monkeypatch.setenv("EVOLVING_PROFILE_API_LLM_GEMINI_SERVICE_TIER", "standard")
    clear_config_cache()

    with pytest.raises(ValueError, match="EVOLVING_PROFILE_API_LLM_GEMINI_SERVICE_TIER"):
        LLMProvider.from_env()

    clear_config_cache()


def test_llm_provider_from_env_ignores_gemini_tier_for_non_gemini(monkeypatch):
    """Invalid Gemini-only tier env values do not break other providers."""
    from evolving_profile_api.config import clear_config_cache
    from evolving_profile_api.engine.llm_wrapper import LLMProvider

    monkeypatch.setenv("EVOLVING_PROFILE_API_LLM_PROVIDER", "mock")
    monkeypatch.setenv("EVOLVING_PROFILE_API_LLM_GEMINI_SERVICE_TIER", "standard")
    clear_config_cache()

    provider = LLMProvider.from_env()

    assert provider.gemini_service_tier is None
    clear_config_cache()


def test_llm_provider_from_env_keeps_lightweight_loader(monkeypatch):
    """Reading the Gemini tier must not construct the full application config."""
    from evolving_profile_api.config import clear_config_cache
    from evolving_profile_api.engine.llm_wrapper import LLMProvider

    monkeypatch.setenv("EVOLVING_PROFILE_API_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("EVOLVING_PROFILE_API_LLM_API_KEY", "fake-key")
    monkeypatch.setenv("EVOLVING_PROFILE_API_LLM_GEMINI_SERVICE_TIER", "flex")
    monkeypatch.setenv("EVOLVING_PROFILE_API_RETAIN_MAX_COMPLETION_TOKENS", "1000")
    monkeypatch.setenv("EVOLVING_PROFILE_API_RETAIN_CHUNK_SIZE", "2000")
    clear_config_cache()

    with patch("google.genai.Client", return_value=MagicMock()):
        provider = LLMProvider.from_env()

    assert provider.gemini_service_tier == "flex"
    clear_config_cache()


def test_llm_provider_constructor_validates_gemini_service_tier():
    """Direct Gemini construction rejects invalid tiers before API calls."""
    from evolving_profile_api.engine.llm_wrapper import LLMProvider

    with pytest.raises(ValueError, match="EVOLVING_PROFILE_API_LLM_GEMINI_SERVICE_TIER"):
        LLMProvider(
            provider="gemini",
            api_key="fake-key",
            base_url="",
            model="gemini-2.5-flash",
            gemini_service_tier="standard",
        )


def test_vertexai_ignores_gemini_service_tier():
    """The Gemini-only tier flag is not forwarded to Vertex AI providers."""
    from evolving_profile_api.engine.llm_wrapper import create_llm_provider

    with patch("evolving_profile_api.engine.providers.GeminiLLM") as mock_gemini:
        create_llm_provider(
            provider="vertexai",
            api_key="",
            base_url="",
            model="gemini-2.5-flash",
            reasoning_effort="low",
            gemini_service_tier="flex",
        )

    assert mock_gemini.call_args.kwargs["gemini_service_tier"] is None
