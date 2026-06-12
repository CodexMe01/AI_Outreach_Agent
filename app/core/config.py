import os
from typing import Annotated, List, Optional
from pydantic import BaseModel, Field
from typing_extensions import TypedDict
from dotenv import load_dotenv

load_dotenv()



# Environment
# ─────────────────────────────────────────────
GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")
TAVILY_API_KEY  = os.getenv("TAVILY_API_KEY", "")
GROQ_MODEL      = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
MAX_SEARCH_RESULTS = int(os.getenv("MAX_SEARCH_RESULTS", "5"))



# Input / domain models
# ─────────────────────────────────────────────
class SenderInfo(BaseModel):
    """Information about the email sender / sending company."""
    name:           str = Field(..., description="Full name of sender")
    role:           str = Field(..., description="Job title / role")
    company_name:   str = Field(..., description="Sender's company name")
    company_website:Optional[str] = Field(None,  description="Sender company website URL")
    company_desc:   Optional[str] = Field(None,  description="Brief description of sender company")
    service_offered:str = Field(..., description="The product / service being pitched")
    usp:            Optional[str] = Field(None,  description="Unique selling point of the service")


class ReceiverInfo(BaseModel):
    """Information about the email recipient / target company."""
    name:           str = Field(..., description="Recipient's name (if known)")
    role:           str = Field(..., description="Recipient's role (if known)")
    company_name:   str = Field(..., description="Recipient company name")
    company_website:Optional[str] = Field(None,  description="Recipient company website URL")
    company_type:   str = Field("startup", description="'startup' or 'enterprise'")
    industry:       Optional[str] = Field(None,  description="Industry / domain of recipient company")
    funding_amount: str = Field(..., description = "Recent Funding Amount (Must)")
    funding_type: str = Field(..., description = "Type of Recent Funding or Investment round like [grant, pre_seed, seed, pre_series_a, series_a, series_b, series_c, series_d_plus, debt, private_equity, unknown  (Must)" )
    funding_date: str = Field(..., description = "Date of Recent funding round")
    company_location: str = Field(..., description = "What is the location headquarter of company")
    trigger_point:  Optional[str] = Field(None,  description="Insight or trigger point explaining why to contact them now")

class CompanyList(BaseModel):
    companies: List[ReceiverInfo] = Field(
        description="All companies found, must be non-empty",
        min_length=1
    )

class PitchContext(BaseModel):
    """The context and goal for this outreach email."""
    subject_hint:   Optional[str] = Field(None,  description="Optional hint for email subject line")
    goal:           str = Field(..., description="Main objective: demo, partnership, trial, etc.")
    pain_points:    Optional[str] = Field(None,  description="Known pain points of the target")
    tone:           str = Field("professional", description="Desired tone: professional / friendly / bold")
    email_length:   str = Field("medium", description="short / medium / long")
    custom_notes:   Optional[str] = Field(None,  description="Any extra instructions for the agent")


# LangGraph State  (all fields are reducers-compatible)
# ─────────────────────────────────────────────
class AgentState(TypedDict):
    # ── inputs ──────────────────────────────
    sender:          SenderInfo
    receiver:        ReceiverInfo
    pitch_context:   PitchContext

    # ── research outputs ────────────────────
    sender_research:   str      # raw research text about sender company
    receiver_research: str      # raw research text about receiver company
    market_insights:   str      # industry / market context

    # ── analysis ────────────────────────────
    relevance_analysis: str     # how sender's service maps to receiver's needs
    hook:               str     # compelling opening hook

    # ── drafting ────────────────────────────
    subject_line:   str
    email_draft:    str
    revision_notes: str

    # ── final ───────────────────────────────
    final_email:    str
    review_passed:  bool

    # ── control ─────────────────────────────
    iteration_count: int
    errors:          List[str]
