import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()

os.environ["TAVILY_API_KEY"]        = os.getenv("tavily_api_key")
os.environ["LANGCHAIN_API_KEY"]     = os.getenv("LANGCHAIN_API_KEY")
os.environ["LANGCHAIN_TRACKING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"]     = "DisFakeOppurs"

from typing import Annotated, List, Optional
from typing_extensions import TypedDict

from langchain_tavily import TavilySearch
from langchain_groq import ChatGroq
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage, AIMessage
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.tools import tool

from app.core.config import (
    AgentState, SenderInfo, ReceiverInfo, PitchContext, CompanyList,
    GROQ_API_KEY, GROQ_MODEL, MAX_SEARCH_RESULTS
)

# 1. IMPORT the cache module you created ▼▼▼
from app.services.cache import init_db, get_receiver, save_receiver, save_receivers

from app.core.tools import web_search

@tool
def search_companies(query: str) -> str:
    """Search the web for companies, news, funding details, or trigger points using a search query."""
    res = web_search(query, max_results=4)
    # MUST truncate the result, otherwise Groq's 6000 token limit crashes the app
    return res[:3000] 

tools         = [search_companies]

# Use llama-3.1-8b-instant for search tool-calling to avoid TPM limits
research_llm  = ChatGroq(model="llama-3.1-8b-instant", api_key=os.getenv("GROQ_API_KEY"), max_tokens=1500).bind_tools(tools)
# Use llama-3.3-70b-versatile for robust structured extraction
extraction_llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=os.getenv("GROQ_API_KEY"), max_tokens=2000).with_structured_output(CompanyList)

# ── State ──────────────────────────────────────────────────────────────────────
class State(TypedDict):
    messages:            Annotated[list[AnyMessage], add_messages]
    validated_companies: Optional[List[ReceiverInfo]]
    validation_error:    Optional[str]
    retry_count:         int

# ── Node 1 — Research ──────────────────────────────────────────────────────────
def tool_calling_llm(state: State):
    # 2. CHECK cache BEFORE hitting the web 
    # Pull the company name from the last human message if possible
    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None
    )
    if last_human:
        cached = get_receiver(last_human.content[:50])   # use first 50 chars as lookup hint
        if cached:
            print(f"[Cache HIT] Skipping web search for cached company")
            # Inject cached data as an AI message so validate node can pick it up
            return {"messages": [AIMessage(content=cached.model_dump_json())]}

    # Prevent token limit errors by keeping only the last 4 messages + the system message
    msgs = state["messages"]
    sys_msg = next((m for m in msgs if isinstance(m, SystemMessage)), None)
    recent_msgs = msgs[-4:]
    if sys_msg and sys_msg not in recent_msgs:
        recent_msgs = [sys_msg] + recent_msgs

    import time
    time.sleep(10)  # Pause to avoid hitting Groq's 6000 TPM limit on free tier
    return {"messages": [research_llm.invoke(recent_msgs)]}


EXTRACT_SYSTEM = """You are a data extraction engine.
Extract at least 5 distinct companies from the research text into structured JSON.
- Recent_Funding_Amount → plain integer in USD (e.g. 5000000)
- Company_Website       → must start with https://
- Role_of_Target        → short title only: CTO / CEO / VP Engineering
- Insight               → full sentence explaining WHY to contact them NOW
- Never leave any field empty — use "Unknown" only if truly not found
"""

# ── Node 2 — Extract + Validate + SAVE ────────────────────────────────────────
def validate_and_extract(state: State):
    last_ai = next(
        (m for m in reversed(state["messages"]) if isinstance(m, AIMessage)),
        None
    )
    if not last_ai:
        return {
            "validated_companies": [],
            "validation_error":    "No AI response found",
            "retry_count":         state.get("retry_count", 0) + 1,
        }

    try:
        result: CompanyList = extraction_llm.invoke([
            SystemMessage(content=EXTRACT_SYSTEM),
            HumanMessage(content=f"Extract companies:\n\n{last_ai.content}")
        ])

        receiver_list = [
            ReceiverInfo(
                name            = company.name,
                role            = company.role,
                company_name    = company.company_name,
                company_website = company.company_website,
                company_type    = company.company_type,
                industry        = company.industry,
                trigger_point   = company.trigger_point,
                funding_date    = company.funding_date,
                funding_amount  = company.funding_amount,
                funding_type    = company.funding_type,
                company_location = company.company_location
            )
            for company in result.companies
        ]

        #3. SAVE to SQLite right after building the list 
        save_receivers(receiver_list)
        print(f" Saved {len(receiver_list)} companies to cache")

        return {
            "validated_companies": receiver_list,
            "validation_error":    None,
            "retry_count":         0,
        }

    except Exception as e:
        print(f"\n Validation failed: {e}")
        return {
            "validated_companies": [],
            "validation_error":    str(e),
            "retry_count":         state.get("retry_count", 0) + 1,
        }


# ── Build Graph ────────────────────────────────────────────────────────────────
builder = StateGraph(State)
builder.add_node("tool_calling_llm",     tool_calling_llm)
builder.add_node("tools",                ToolNode(tools))
builder.add_node("validate_and_extract", validate_and_extract)

builder.add_edge(START,                  "tool_calling_llm")
builder.add_conditional_edges(
    "tool_calling_llm",
    tools_condition,
    {"tools": "tools", "__end__": "validate_and_extract"}
)
builder.add_edge("tools",                "tool_calling_llm")
builder.add_edge("validate_and_extract", END)

graph = builder.compile(checkpointer=MemorySaver())

# ── Prompts ────────────────────────────────────────────────────────────────────
RESEARCH_SYSTEM = SystemMessage(content=(
    "You are a Sales Research Expert. Find and compile at least 5 distinct companies with outreach triggers:\n"
    "Recent funding (Seed / Series A / B / C / private equity / etc.).\n"
    "Keep searching until you have gathered details for at least 5 distinct companies.\n"
    "Extract ALL companies from the research text into structured JSON.\n"
    "- Recent_Funding_Details → [1. Recent Funding amount, 2. Recent Funding date, 3. Recent Funding Type]\n"
    "- company location -> location or City where company is located.\n"
    "- Company_Website       → must start with https://\n"
    "- Name of the Target    -> Name of the CTO / CEO / VP Engineering have authority to make decision.\n"
    "- Role_of_Target        → short title only: CTO / CEO / VP Engineering\n"
    "- Never leave any field empty — use 'Unknown' only if truly not found"
))
RESEARCH_HUMAN = HumanMessage(content=(
    "Search for recently funded or migrating startups. "
    "Find at least 5 distinct companies with clear outreach triggers and full details."
))

#4. CALL init_db() ONCE before graph.invoke ▼▼▼
init_db()

if __name__ == "__main__":
    # ── Run ────────────────────────────────────────────────────────────────────────
    import uuid
    config = {"configurable": {"thread_id": uuid.uuid4().hex}}
    result = graph.invoke(
        {
            "messages":            [RESEARCH_SYSTEM, RESEARCH_HUMAN],
            "validated_companies": None,
            "validation_error":    None,
            "retry_count":         0,
        },
        config=config
    )

    # ── Output ─────────────────────────────────────────────────────────────────────
    if result.get("validated_companies"):
        for i, compny in enumerate(result["validated_companies"], 1):
            print(f"\n[{i}] {compny.company_name}  |  {compny.company_type}")
            print(f"     Website  : {compny.company_website}")
            print(f"     Industry : {compny.industry}")
            print(f"     Contact  : {compny.name}  —  {compny.role}")
            print(f"trigger point: {compny.trigger_point}")
            print(f" funding_date: {compny. funding_date}")
            print(f"funding_amount: {compny.funding_amount}")
            print(f"funding_type : {compny.funding_type }")
            print(f"company_location : {compny.company_location }")

            
    elif result.get("validation_error"):
        print(f"\n {result['validation_error']}")