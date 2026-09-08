---
name: deep-research
description: >-
  Methodology for thorough, chat-grade information collection: multi-step searching,
  full-content extraction, source triangulation, deduplication, and cited synthesis.
  Use this whenever a task involves researching a topic, gathering information from
  multiple web/doc/paper/GitHub sources, comparing options, or producing a sourced
  overview — even if the user doesn't say the word "research." Preloaded by the
  `researcher` subagent; also usable directly in the main session.
---

# Deep Research

A repeatable loop for collecting and synthesizing information from the web at a level
matching or exceeding the chat web-search experience. The gain over a single search is
**depth** (full page content, not snippets), **breadth** (multiple sources fanned out),
and **rigor** (cross-checking + citations).

## When to use
Any gathering/synthesis task: "what's the current state of X", "compare A vs B", "find
the best approach/tool/paper for Y", "summarize the landscape of Z". Not for a single
trivial lookup the model can answer directly.

## The loop
1. **Plan.** Restate the goal in one line. List the sub-questions to answer and the
   distinct items to look up.
2. **Broad pass.** 1–2 wide queries to map the space and find the strongest sources.
3. **Narrow + fan out.** One targeted query per sub-question/item — search each
   separately; combined queries return shallow results for everything at once.
4. **Extract full content.** From the best 3–8 sources, pull the actual page text
   (extraction tool / scrape / Jina Reader), not just snippets. Favor primary sources:
   official docs, papers/preprints, standards, vendor & GitHub, gov/regulatory.
5. **Cross-check.** Verify load-bearing or surprising claims against a second
   independent source. Record conflicts instead of hiding them.
6. **Deduplicate & rank.** Collapse repeats; keep the most authoritative and most
   recent. Be skeptical of SEO'd listicles and forums unless directly relevant.
7. **Synthesize.** Answer in your own words, attribute claims to sources, list the
   sources with what each contributed, and flag any gaps.

## Source routing (general collection)
- General web / news / current state → **Tavily** or built-in **WebSearch**
- Full page content → **Firecrawl** (search+scrape) or **Jina Reader**
- Semantic "find similar / related work" → **Exa**
- Papers → **arXiv + Semantic Scholar** (or an academic MCP); code → **GitHub MCP**

## Quality bar
- Stop only when every part of the goal is grounded in retrieved material.
- Prefer raw content read by the current model over pre-summarized fetches.
- Paraphrase; keep quotes short and attributed. Never fabricate a source.
