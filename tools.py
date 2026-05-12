"""
Search Tools for Email Drafter Agent
Supports Tavily (preferred) with a DuckDuckGo fallback.
"""

from __future__ import annotations
import os
import json
import urllib.parse
import urllib.request
from typing import List, Optional

# ── Optional Tavily ───────────────────────────────────────────────────────────
try:
    from tavily import TavilyClient
    _TAVILY_AVAILABLE = True
except ImportError:
    _TAVILY_AVAILABLE = False



# Base search result
# ─────────────────────────────────────────────────────────────────────────────
class SearchResult:
    def __init__(self, title: str, url: str, content: str):
        self.title   = title
        self.url     = url
        self.content = content

    def __str__(self):
        return f"**{self.title}**\nURL: {self.url}\n{self.content}"



# Tavily search
# ─────────────────────────────────────────────────────────────────────────────
def tavily_search(query: str, max_results: int = 4) -> List[SearchResult]:
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key or not _TAVILY_AVAILABLE:
        return []
    try:
        client   = TavilyClient(api_key=api_key)
        response = client.search(query=query, max_results=max_results)
        results  = []
        for r in response.get("results", []):
            results.append(SearchResult(
                title   = r.get("title", ""),
                url     = r.get("url", ""),
                content = r.get("content", "")
            ))
        return results
    except Exception as e:
        print(f"[Tavily] Search error: {e}")
        return []



# DuckDuckGo instant-answer fallback 
# ─────────────────────────────────────────────────────────────────────────────
def duckduckgo_search(query: str, max_results: int = 4) -> List[SearchResult]:
    """
    Uses DuckDuckGo Instant Answer API (free, no key).
    For real production use, replace with Serper / Brave / SerpAPI.
    """
    try:
        encoded  = urllib.parse.quote_plus(query)
        url      = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
        req      = urllib.request.Request(url, headers={"User-Agent": "EmailDrafterBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        results: List[SearchResult] = []

        # Abstract (top result)
        if data.get("AbstractText"):
            results.append(SearchResult(
                title   = data.get("Heading", query),
                 url     = data.get("AbstractURL", ""),
                content = data["AbstractText"]
            ))

        # Related topics
        for topic in data.get("RelatedTopics", [])[:max_results - 1]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(SearchResult(
                    title   = topic.get("Text", "")[:60],
                    url     = topic.get("FirstURL", ""),
                    content = topic.get("Text", "")
                ))

        return results[:max_results]
    except Exception as e:
        print(f"[DuckDuckGo] Search error: {e}")
        return []


# Unified search entry point
# ─────────────────────────────────────────────────────────────────────────────
def web_search(query: str, max_results: int = 4) -> str:
    """
    Run a web search and return formatted results as a single string.
    Tries Tavily first; falls back to DuckDuckGo.
    """
    results: List[SearchResult] = []

    # 1. Tavily
    if _TAVILY_AVAILABLE and os.getenv("TAVILY_API_KEY"):
        results = tavily_search(query, max_results)

    # 2. DuckDuckGo fallback
    if not results:
        results = duckduckgo_search(query, max_results)

    # 3. No results
    if not results:
        return f"No search results found for: {query}"

    formatted = "\n\n".join(
        f"[{i+1}] {r}" for i, r in enumerate(results)
    )
    return formatted



# Compound search helpers used by agent nodes
# ─────────────────────────────────────────────────────────────────────────────
def research_company(company_name: str, website: Optional[str] = None,
                     extra_context: str = "") -> str:
    """Run multiple targeted queries about a company and aggregate results."""
    queries = [
        f"{company_name} company overview products services",
        f"{company_name} recent news funding growth",
    ]
    if website:
        queries.append(f"site:{website} about")
    if extra_context:
        queries.append(f"{company_name} {extra_context}")

    all_results: List[str] = []
    seen_urls:   set        = set()

    for q in queries:
        raw = web_search(q, max_results=3)
        if raw and "No search results" not in raw:
            all_results.append(f"### Query: {q}\n{raw}")

    return "\n\n---\n\n".join(all_results) if all_results else "No research data available."


def research_market_context(service: str, industry: str, company_type: str) -> str:
    """Research market trends for the service + industry combination."""
    queries = [
        f"{service} solutions for {company_type}s in {industry} 2024 2025",
        f"{industry} {company_type} challenges pain points technology",
        f"best {service} vendors tools {industry}",
    ]
    all_results: List[str] = []
    for q in queries:
        raw = web_search(q, max_results=2)
        if raw and "No search results" not in raw:
            all_results.append(f"### Query: {q}\n{raw}")

    return "\n\n---\n\n".join(all_results) if all_results else "No market data available."
