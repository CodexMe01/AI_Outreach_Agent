"""
Lead Researcher Agent
─────────────────────
Fetches at least 5 companies with recent funding or industry-shift news
and extracts structured details:
  company_name, company_website, industry, funding_date,
  funding_amount, funding_type, company_location, news_Brief
"""

import os
import sys
import json
import random
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()

# ── Env setup ─────────────────────────────────────────────────────────────────
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
TAVILY_API_KEY = os.getenv("tavily_api_key") or os.getenv("TAVILY_API_KEY", "")
os.environ["TAVILY_API_KEY"] = TAVILY_API_KEY

# ── Pydantic models ───────────────────────────────────────────────────────────
from pydantic import BaseModel, Field
from typing import List, Optional

class LeadCompany(BaseModel):
    company_name:     str           = Field(..., description="Name of the company")
    company_website:  Optional[str] = Field(None, description="Company website URL starting with https://")
    industry:         Optional[str] = Field(None, description="Industry or sector of the company")
    funding_date:     Optional[str] = Field(None, description="Date of the most recent funding round or news")
    funding_amount:   Optional[str] = Field(None, description="Amount raised (e.g. '$5M', '50000000')")
    funding_type:     Optional[str] = Field(None, description="Type of funding: Seed, Series A, Series B, IPO, Grant, PE, Unknown")
    company_location: Optional[str] = Field(None, description="City/Country where the company is headquartered")
    news_Brief:       Optional[str] = Field(None, description="One sentence explaining the recent news or why to reach out now")

class LeadList(BaseModel):
    companies: List[LeadCompany] = Field(..., description="List of at least 5 companies")


# ── Search ────────────────────────────────────────────────────────────────────
def run_tavily_searches() -> str:
    """Run multiple targeted Tavily searches and return combined raw text."""
    try:
        try:
            from tavily import TavilyClient
        except ImportError:
            from langchain_tavily import TavilySearchResults  # fallback not used here
            raise ImportError("Use tavily-python package for TavilyClient")
        client = TavilyClient(api_key=TAVILY_API_KEY)
    except Exception as e:
        print(f"[WARN]  Tavily not available ({e}). Install: pip install tavily-python")
        return ""

    sectors = [
        "AI SaaS", "Fintech", "Healthcare Tech",
        "Cleantech", "Cybersecurity", "Edtech", "Proptech"
    ]
    chosen = random.sample(sectors, 3)           # pick 3 random sectors each run

    queries = [
        f"{chosen[0]} startups recent funding 2024 2025",
        f"{chosen[1]} company Series A Series B funding news",
        f"{chosen[2]} startup industry shift expansion news 2025",
        "recently funded startups venture capital 2025",
    ]

    all_text = []
    for q in queries:
        try:
            resp = client.search(query=q, max_results=5)
            for r in resp.get("results", []):
                snippet = f"Title: {r.get('title','')}\nURL: {r.get('url','')}\nContent: {r.get('content','')}\n"
                all_text.append(snippet)
            time.sleep(1)   # gentle rate limit
        except Exception as e:
            print(f"[Search error for '{q}']: {e}")

    return "\n\n---\n\n".join(all_text)


# ── Extraction ────────────────────────────────────────────────────────────────
def extract_companies(raw_text: str) -> LeadList:
    """Send raw search text to Groq and extract structured company data."""
    from langchain_groq import ChatGroq

    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=GROQ_API_KEY,
        max_tokens=3000,
    ).with_structured_output(LeadList)

    system = (
        "You are a B2B lead research expert. "
        "Extract at least 5 DISTINCT companies from the research text below.\n"
        "For each company fill in:\n"
        "  - company_name\n"
        "  - company_website  (must start with https://; guess from company name if not found)\n"
        "  - industry\n"
        "  - funding_date     (YYYY-MM or YYYY if exact date unknown)\n"
        "  - funding_amount   (e.g. '$10M' or '10000000')\n"
        "  - funding_type     (Seed / Series A / Series B / Series C / Grant / PE / Unknown)\n"
        "  - company_location (City, Country)\n"
        "  - news_Brief       (one sentence: what happened and why reach out NOW)\n"
        "Use 'Unknown' only if a field truly cannot be inferred. Never leave a field blank."
    )

    result = llm.invoke([
        {"role": "system", "content": system},
        {"role": "user",   "content": f"Research text:\n\n{raw_text[:8000]}"},
    ])
    return result


# ── Save to cache ─────────────────────────────────────────────────────────────
def save_leads(leads: List[LeadCompany]):
    """Persist leads to the SQLite cache (compatible with main.py)."""
    try:
        from app.core.config import ReceiverInfo
        from app.services.cache import init_db, save_receivers

        init_db()
        receiver_list = [
            ReceiverInfo(
                name             = "Unknown",
                role             = "Unknown",
                company_name     = c.company_name,
                company_website  = c.company_website or "Unknown",
                company_type     = "startup",
                industry         = c.industry or "Unknown",
                trigger_point    = c.news_Brief or "Unknown",
                funding_date     = c.funding_date or "Unknown",
                funding_amount   = c.funding_amount or "Unknown",
                funding_type     = c.funding_type or "Unknown",
                company_location = c.company_location or "Unknown",
            )
            for c in leads
        ]
        save_receivers(receiver_list)
        print(f"[SAVED]  {len(receiver_list)} companies saved to cache.")
    except Exception as e:
        print(f"[WARN]  Could not save to cache: {e}")


# ── Pretty print ───────────────────────────────────────────────────────────────
def print_leads(leads: List[LeadCompany]):
    print(f"\n{'='*60}")
    print(f"[DONE]  {len(leads)} COMPANIES FOUND")
    print(f"{'='*60}\n")
    for i, c in enumerate(leads, 1):
        print(f"[{i}]  {c.company_name}")
        print(f"     company_website  : {c.company_website or 'Unknown'}")
        print(f"     industry         : {c.industry or 'Unknown'}")
        print(f"     funding_date     : {c.funding_date or 'Unknown'}")
        print(f"     funding_amount   : {c.funding_amount or 'Unknown'}")
        print(f"     funding_type     : {c.funding_type or 'Unknown'}")
        print(f"     company_location : {c.company_location or 'Unknown'}")
        print(f"     news_Brief       : {c.news_Brief or 'Unknown'}")
        print()


# ── Main ──────────────────────────────────────────────────────────────────────
def run_lead_researcher() -> List[LeadCompany]:
    """Full pipeline: search → extract → save → return leads."""
    print("[SEARCH]  Searching for recent funding & industry news...")
    raw = run_tavily_searches()

    if not raw:
        print("[ERROR]  No search results. Check your TAVILY_API_KEY.")
        return []

    print(f"[OK]  Gathered {len(raw)} characters of research text. Extracting companies...\n")

    try:
        result = extract_companies(raw)
        leads  = result.companies
    except Exception as e:
        print(f"[FAIL]  Extraction failed: {e}")
        if "Rate limit" in str(e) or "429" in str(e):
            print("[TIP]  Groq rate limit hit. Wait a minute and retry.")
        return []

    print_leads(leads)
    save_leads(leads)
    return leads


if __name__ == "__main__":
    leads = run_lead_researcher()

    # Also dump raw JSON so you can inspect/copy it
    if leads:
        print("\n--- Raw JSON ---")
        print(json.dumps([c.model_dump() for c in leads], indent=2))
