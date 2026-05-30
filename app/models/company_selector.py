import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import re
import math
import pickle
import sqlite3
import pandas as pd
from typing import List, Tuple, Dict, Any, Optional

from app.core.config import ReceiverInfo
from app.services.cache import DB_PATH

# ── Load Model ─────────────────────────────────────────────────────────────────
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "smart_outreach_DT.pkl")

try:
    import joblib
    modelSelector = joblib.load(MODEL_PATH)
except Exception:
    modelSelector = pickle.load(open(MODEL_PATH, "rb"))

# ── Data Preprocessors & Encoders ──────────────────────────────────────────────

def parse_funding_amount(amount_str: Optional[str]) -> float:
    """
    Parses a funding amount string (e.g. '$5M', '10,000,000', '5000000', 'unknown') into float value.
    Defaults to 1.0 if not parsed to avoid log(0) issues.
    """
    if not amount_str:
        return 1.0
    
    # Remove dollar signs, commas, spaces
    clean = re.sub(r'[\$,\s]', '', amount_str).upper()
    
    # Check for multiplier suffix
    multiplier = 1.0
    if clean.endswith('M'):
        multiplier = 1_000_000.0
        clean = clean[:-1]
    elif clean.endswith('K'):
        multiplier = 1_000.0
        clean = clean[:-1]
    elif clean.endswith('B'):
        multiplier = 1_000_000_000.0
        clean = clean[:-1]
        
    try:
        # Extract the first numeric substring
        match = re.search(r'[-+]?\d*\.\d+|\d+', clean)
        if match:
            val = float(match.group()) * multiplier
            return max(val, 1.0)
    except Exception:
        pass
    
    return 1.0


def parse_funding_date(date_str: Optional[str]) -> Tuple[int, int, int, float]:
    """
    Parses a funding date string (e.g. '2025-05-01', 'May 2026', '2026-05-24')
    and returns (year, month, quarter, months_since_funding).
    Defaults to May 2026 if parsing fails.
    """
    # Baseline current date is May 25, 2026
    now_year = 2026
    now_month = 5
    
    year = now_year
    month = now_month
    
    if date_str:
        # Try to find a 4-digit year
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', date_str)
        if year_match:
            year = int(year_match.group(1))
            
        # Try to find month name
        month_str = date_str.lower()
        months_map = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
        }
        found_month = False
        for m_name, m_num in months_map.items():
            if m_name in month_str:
                month = m_num
                found_month = True
                break
                
        if not found_month:
            # Try MM/DD/YYYY or YYYY-MM-DD pattern
            digits = re.findall(r'\b\d{1,2}\b', date_str)
            if digits:
                iso_match = re.match(r'^\d{4}[-/](\d{1,2})[-/](\d{1,2})', date_str)
                if iso_match:
                    month = int(iso_match.group(1))
                else:
                    for d in digits:
                        d_val = int(d)
                        if 1 <= d_val <= 12:
                            month = d_val
                            break
                            
    if month < 1 or month > 12:
        month = 5
    quarter = (month - 1) // 3 + 1
    
    # Months difference calculation
    months_diff = (now_year - year) * 12 + (now_month - month)
    months_since_funding = max(float(months_diff), 0.0)
    
    return year, month, quarter, months_since_funding


def map_funding_stage(stage_str: Optional[str]) -> Tuple[int, int]:
    """
    Maps funding_type string to:
    1. funding_stage_ord (ordinal representation)
    2. stage_enc (alphabetical label encoded index)
    """
    if not stage_str:
        stage_str = "unknown"
        
    s = stage_str.lower().strip().replace(" ", "_").replace("-", "_")
    
    # Ordinal mapping: early-to-mid stages (1-6) vs late/non-equity stages (7-10)
    ord_map = {
        'pre_seed': 1,
        'seed': 2,
        'pre_series_a': 3,
        'series_a': 4,
        'series_b': 5,
        'series_c': 6,
        'series_d_plus': 7,
        'private_equity': 8,
        'debt': 9,
        'grant': 10,
        'unknown': 0
    }
    
    funding_stage_ord = 0
    for k, v in ord_map.items():
        if k in s:
            funding_stage_ord = v
            break
            
    # Alphabetical encoder mapping
    enc_map = {
        'debt': 0,
        'grant': 1,
        'pre_seed': 2,
        'pre_series_a': 3,
        'private_equity': 4,
        'seed': 5,
        'series_a': 6,
        'series_b': 7,
        'series_c': 8,
        'series_d_plus': 9,
        'unknown': 10
    }
    
    stage_enc = 10  # default to unknown
    for k, v in enc_map.items():
        if k in s:
            stage_enc = v
            break
            
    return funding_stage_ord, stage_enc


def map_bucket(amount: float) -> int:
    """
    Maps funding amount to a bucket code:
    0: large_50M_plus
    1: medium_10M_50M
    2: micro_under_1M
    3: small_1M_10M
    4: unknown
    """
    if amount <= 1.0:
        return 4
    elif amount >= 50_000_000:
        return 0
    elif 10_000_000 <= amount < 50_000_000:
        return 1
    elif amount < 1_000_000:
        return 2
    else:
        return 3


def map_location(location_str: Optional[str]) -> Tuple[int, int]:
    """
    Determines if location is a tier 1 city and maps the city name to an encoded integer.
    """
    if not location_str:
        return 0, 13
        
    loc = location_str.lower().strip()
    
    tier1_cities = [
        'bangalore', 'bengaluru', 'san francisco', 'sf', 'new york', 'nyc', 
        'london', 'singapore', 'mumbai', 'delhi', 'noida', 'gurgaon', 
        'seattle', 'boston', 'austin', 'tokyo', 'berlin', 'paris', 
        'bay area', 'silicon valley'
    ]
    
    is_tier1 = 0
    for c in tier1_cities:
        if c in loc:
            is_tier1 = 1
            break
            
    # Alphabetical common cities list for city_enc
    cities_list = [
        'austin', 'bangalore', 'bengaluru', 'berlin', 'boston', 'delhi', 
        'gurgaon', 'london', 'mumbai', 'new york', 'noida', 'paris', 
        'san francisco', 'seattle', 'singapore', 'tokyo'
    ]
    
    city_enc = 13  # Default fallback
    for idx, c in enumerate(cities_list):
        if c in loc:
            city_enc = idx
            break
            
    return is_tier1, city_enc


def map_industry(industry_str: Optional[str]) -> int:
    """
    Maps industry string to industry_enc index.
    """
    if not industry_str:
        return 14
        
    ind = industry_str.lower().strip()
    
    industries = [
        "ai", "analytics", "biotech", "cleantech", "cybersecurity",
        "e-commerce", "edtech", "enterprise", "fintech", "healthcare",
        "hrtech", "logistics", "marketing", "proptech", "saas", "web3"
    ]
    
    for idx, name in enumerate(industries):
        if name in ind:
            return idx
            
    if "artificial" in ind or "intelligence" in ind:
        return 0
    if "financial" in ind:
        return 8
    if "health" in ind or "medical" in ind or "bio" in ind:
        return 9
    if "software" in ind:
        return 14
        
    return 14  # Default to SaaS


def extract_features(receiver: ReceiverInfo) -> Dict[str, Any]:
    """Converts a ReceiverInfo object into a dictionary of 14 encoded model features."""
    amount = parse_funding_amount(receiver.funding_amount)
    log_amt = math.log(amount)
    
    year, month, quarter, months_since = parse_funding_date(receiver.funding_date)
    funding_stage_ord, stage_enc = map_funding_stage(receiver.funding_type)
    bucket_enc = map_bucket(amount)
    is_tier1, city_enc = map_location(receiver.company_location)
    industry_enc = map_industry(receiver.industry)
    
    return {
        'industry_enc': industry_enc,
        'stage_enc': stage_enc,
        'funding_stage_ord': funding_stage_ord,
        'city_enc': city_enc,
        'is_tier1_city': is_tier1,
        'log_amount': log_amt,
        'bucket_enc': bucket_enc,
        'investor_count': 1,
        'has_lead_investor': 1,
        'has_subvertical': 1,
        'funding_year': year,
        'funding_month': month,
        'funding_quarter': quarter,
        'months_since_funding': months_since
    }

# ── Data Fetching ──────────────────────────────────────────────────────────────

def fetch_companies_cached() -> List[ReceiverInfo]:
    """Fetches companies from the local SQLite cache."""
    if not os.path.exists(DB_PATH):
        print(f"Database cache '{DB_PATH}' not found.")
        return []
    try:
        con = sqlite3.connect(DB_PATH)
        rows = con.execute(
            "SELECT receiver FROM receiver_cache ORDER BY fetched_at DESC"
        ).fetchall()
        con.close()
        return [ReceiverInfo.model_validate_json(row[0]) for row in rows]
    except Exception as e:
        print(f"Error fetching from cache: {e}")
        return []


def fetch_companies_live(query: str = None) -> List[ReceiverInfo]:
    """Runs the Reasearcher.py graph to scrape and extract companies in real-time."""
    try:
        from app.agents.researcher import graph, RESEARCH_SYSTEM, RESEARCH_HUMAN
        from langchain_core.messages import HumanMessage
        
        human_msg = HumanMessage(content=query) if query else RESEARCH_HUMAN
        import uuid
        config = {"configurable": {"thread_id": uuid.uuid4().hex}}
        
        print("Running Reasearcher live search (this may take a minute)...")
        result = graph.invoke(
            {
                "messages":            [RESEARCH_SYSTEM, human_msg],
                "validated_companies": None,
                "validation_error":    None,
                "retry_count":         0,
            },
            config=config
        )
        return result.get("validated_companies") or []
    except Exception as e:
        print(f"Error executing live researcher: {e}")
        return []

# ── Prediction & Filter ────────────────────────────────────────────────────────

def select_companies(companies: List[ReceiverInfo]) -> List[Tuple[ReceiverInfo, int]]:
    """
    Takes a list of ReceiverInfo, extracts features, makes predictions using
    the Decision Tree classifier, and returns a list of (ReceiverInfo, prediction) tuples.
    """
    if not companies:
        return []
        
    results = []
    for comp in companies:
        feat_dict = extract_features(comp)
        df_input = pd.DataFrame([feat_dict])
        
        # Ensure column order matches the model's expected features
        feature_names = getattr(modelSelector, "feature_names_in_", None)
        if feature_names is not None:
            df_input = df_input[list(feature_names)]
            
        prediction = int(modelSelector.predict(df_input)[0])
        results.append((comp, prediction))
        
    return results

# ── Main / CLI Interface ───────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print(" Smart Outreach Company Selector (Machine Learning Filter)")
    print("=" * 60)
    
    # Choose fetch method
    print("\nHow would you like to retrieve company data?")
    print("1. From SQLite Cache (fast, offline)")
    print("2. Run Live Researcher (slower, hits Tavily & Groq APIs)")
    
    choice = input("Enter choice (1 or 2, default 1): ").strip()
    
    companies = []
    if choice == "2":
        query = input("Enter research query (or press Enter for default startup search): ").strip()
        companies = fetch_companies_live(query if query else None)
    else:
        companies = fetch_companies_cached()
        
    print(f"\nRetrieved {len(companies)} companies.")
    
    if not companies:
        print("No companies found. Exiting.")
        sys.exit(0)
        
    # Run prediction and filter
    print("\nRunning Decision Tree classifier to select high-relevance leads...")
    predictions = select_companies(companies)
    
    selected = [comp for comp, pred in predictions if pred == 1]
    not_selected = [comp for comp, pred in predictions if pred == 0]
    
    print("\n" + "=" * 60)
    print(f" SELECTED FOR OUTREACH ({len(selected)})")
    print("=" * 60)
    for idx, comp in enumerate(selected, 1):
        print(f"{idx}. {comp.company_name} | {comp.industry or 'Unknown'} | Location: {comp.company_location}")
        print(f"   Funding: {comp.funding_amount} ({comp.funding_type}) on {comp.funding_date}")
        print(f"   Trigger: {comp.trigger_point}")
        print()
        
    print("=" * 60)
    print(f" NOT SELECTED ({len(not_selected)})")
    print("=" * 60)
    for idx, comp in enumerate(not_selected, 1):
        print(f"{idx}. {comp.company_name} | {comp.industry or 'Unknown'} | Location: {comp.company_location}")
        print(f"   Funding: {comp.funding_amount} ({comp.funding_type}) on {comp.funding_date}")
        print()