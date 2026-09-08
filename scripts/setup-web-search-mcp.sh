#!/usr/bin/env bash
# Set up general-purpose web search + extraction MCP servers for Claude Code.
# Run this in a terminal (NOT inside a `claude` session), from your project dir.
#
# Prereqs:
#   - Node.js 18+ (for npx)
#   - Claude Code on the first-party Anthropic API (server-side WebSearch is NOT
#     available on Bedrock/Vertex; the MCP servers below still work there)
#
# Get free API keys first, then export them (or add to ~/.zshrc / ~/.bashrc):
#   Tavily     (1,000 req/mo free, no card):   https://app.tavily.com  -> TAVILY_API_KEY
#   Firecrawl  (1,000 credits/mo free):        https://firecrawl.dev   -> FIRECRAWL_API_KEY
#   Exa        (free signup credits, optional): https://exa.ai         -> EXA_API_KEY
#
# NOTE: the npm package names below are current as of setup. If npx can't resolve one,
# check that provider's MCP docs for the exact package name or a hosted URL.

set -euo pipefail

SCOPE="${1:-user}"   # user = all projects (~/.claude.json); project = this repo (.mcp.json)

echo "Adding search MCP servers (scope: $SCOPE)…"
echo

# 1) Tavily — clean, LLM-ready general web search (returns content, not just links)
if [ -n "${TAVILY_API_KEY:-}" ]; then
  claude mcp add tavily --scope "$SCOPE" --env TAVILY_API_KEY="$TAVILY_API_KEY" \
    -- npx -y tavily-mcp
  echo "  added tavily"
else
  echo "  skip tavily     (TAVILY_API_KEY not set)"
fi

# 2) Firecrawl — search + full-page scrape/crawl (the extraction workhorse)
if [ -n "${FIRECRAWL_API_KEY:-}" ]; then
  claude mcp add firecrawl --scope "$SCOPE" --env FIRECRAWL_API_KEY="$FIRECRAWL_API_KEY" \
    -- npx -y firecrawl-mcp
  echo "  added firecrawl"
else
  echo "  skip firecrawl  (FIRECRAWL_API_KEY not set)"
fi

# 3) Exa — semantic / "find similar" search (optional)
if [ -n "${EXA_API_KEY:-}" ]; then
  claude mcp add exa --scope "$SCOPE" --env EXA_API_KEY="$EXA_API_KEY" \
    -- npx -y exa-mcp-server
  echo "  added exa"
else
  echo "  skip exa        (EXA_API_KEY not set — optional)"
fi

echo
echo "Done. Verify with:  claude mcp list"
echo "Restart any running claude session to pick up the new servers."
