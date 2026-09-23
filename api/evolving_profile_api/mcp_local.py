"""
Local MCP server entry point for use with Claude Code (HTTP transport).

This is a thin wrapper around the main evolving-profile-api server that pre-configures
sensible defaults for local use (embedded PostgreSQL via pg0, warning log level).

The full API runs on localhost:8888. Configure Claude Code's MCP settings:
    claude mcp add --transport http hindsight http://localhost:8888/mcp/

Or pinned to a specific bank (single-bank mode):
    claude mcp add --transport http hindsight http://localhost:8888/mcp/default/

Run with:
    hindsight-local-mcp

Or with uvx:
    uvx evolving-profile-api@latest hindsight-local-mcp

Environment variables:
    EVOLVING_PROFILE_API_LLM_API_KEY: Required. API key for LLM provider.
    EVOLVING_PROFILE_API_LLM_PROVIDER: Optional. LLM provider (default: "openai").
    EVOLVING_PROFILE_API_LLM_MODEL: Optional. LLM model (default: "gpt-4o-mini").
    EVOLVING_PROFILE_API_DATABASE_URL: Optional. Override database URL (default: pg0://hindsight-mcp).
"""

import os


def main() -> None:
    """Start the Evolving Profile API server with local defaults."""
    # Set local defaults (only if not already configured by the user)
    os.environ.setdefault("EVOLVING_PROFILE_API_DATABASE_URL", "pg0://hindsight-mcp")

    from evolving_profile_api.main import main as api_main

    api_main()


if __name__ == "__main__":
    main()
