from __future__ import annotations
import re
from typing import Any

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END

from config import (
    AgentState, SenderInfo, ReceiverInfo, PitchContext,
    GROQ_API_KEY, GROQ_MODEL, MAX_SEARCH_RESULTS
)


from tools import research_company, research_market_context
from prompts import (
    SENDER_RESEARCH_PROMPT,
    RECEIVER_RESEARCH_PROMPT,
    MARKET_RESEARCH_PROMPT,
    RELEVANCE_ANALYSIS_PROMPT,
    DRAFT_EMAIL_PROMPT,
    REVIEW_EMAIL_PROMPT,
    REFINE_EMAIL_PROMPT,
)


# LLM helper
# ─────────────────────────────────────────────────────────────────────────────
def get_llm(temperature: float = 0.7) -> ChatGroq:
    return ChatGroq(
        api_key=GROQ_API_KEY,
        model=GROQ_MODEL,
        temperature=temperature,
    )


def llm_call(prompt: str, temperature: float = 0.7) -> str:
    """Single-shot LLM call returning the response as a string."""
    llm = get_llm(temperature=temperature)
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content.strip()


# Node: research_sender
# ───────────────────────────────────────────────────────────────────────────────────────────────
def research_sender(state: AgentState) -> dict:
    """Research the sending company to build a strong sender profile."""
    print(" [Node] Researching sender company...")

    sender: SenderInfo = state["sender"]
    search_results = research_company(
        company_name    = sender.company_name,
        website         = sender.company_website,
        extra_context   = sender.service_offered,
    )

    prompt = SENDER_RESEARCH_PROMPT.format(
        company_name = sender.company_name,
        website      = sender.company_website or "N/A",
        description  = sender.company_desc or "N/A",
        service      = sender.service_offered,
        usp          = sender.usp or "N/A",
        search_results = search_results,
    )

    profile = llm_call(prompt, temperature=0.3)
    return {"sender_research": profile, "errors": []}


# Node: research_receiver
# ─────────────────────────────────────────────────────────────────────────────
def research_receiver(state: AgentState) -> dict:
    """Research the target company to personalise the email."""
    print(" [Node] Researching receiver company...")

    receiver: ReceiverInfo = state["receiver"]
    search_results = research_company(
        company_name  = receiver.company_name,
        website       = receiver.company_website,
        extra_context = receiver.industry or "",
    )

    prompt = RECEIVER_RESEARCH_PROMPT.format(
        company_name  = receiver.company_name,
        website       = receiver.company_website or "N/A",
        company_type  = receiver.company_type,
        industry      = receiver.industry or "technology",
        search_results = search_results,
    )

    profile = llm_call(prompt, temperature=0.3)
    return {"receiver_research": profile}



# Node: research_market
# ─────────────────────────────────────────────────────────────────────────────
def research_market(state: AgentState) -> dict:
    """Gather market/industry context to strengthen the pitch narrative."""
    print(" [Node] Researching market context...")

    sender:   SenderInfo   = state["sender"]
    receiver: ReceiverInfo = state["receiver"]

    search_results = research_market_context(
        service      = sender.service_offered,
        industry     = receiver.industry or "technology",
        company_type = receiver.company_type,
    )

    prompt = MARKET_RESEARCH_PROMPT.format(
        service       = sender.service_offered,
        industry      = receiver.industry or "technology",
        company_type  = receiver.company_type,
        search_results = search_results,
    )

    insights = llm_call(prompt, temperature=0.3)
    return {"market_insights": insights}



# Node: analyze_relevance
# ─────────────────────────────────────────────────────────────────────────────
def analyze_relevance(state: AgentState) -> dict:
    """Analyse how sender's service maps to receiver's needs → strategy brief."""
    print(" [Node] Analyzing relevance and building pitch strategy...")

    ctx: PitchContext = state["pitch_context"]

    prompt = RELEVANCE_ANALYSIS_PROMPT.format(
        sender_research   = state.get("sender_research", ""),
        receiver_research = state.get("receiver_research", ""),
        market_insights   = state.get("market_insights", ""),
        goal              = ctx.goal,
        pain_points       = ctx.pain_points or "Not specified",
    )

    analysis = llm_call(prompt, temperature=0.5)

    # Extract best hook (first option listed under hook section)
    hook = ""
    if "Hook Options" in analysis:
        lines = analysis.split("\n")
        for i, line in enumerate(lines):
            if "Hook Options" in line:
                for j in range(i + 1, min(i + 5, len(lines))):
                    candidate = lines[j].strip()
                    if candidate and not candidate.startswith("#"):
                        hook = re.sub(r"^[\d\.\-\*]+\s*", "", candidate)
                        break
                break

    return {
        "relevance_analysis": analysis,
        "hook": hook,
    }


# Node: draft_email
# ─────────────────────────────────────────────────────────────────────────────
def draft_email(state: AgentState) -> dict:
    """Write the first full email draft using all research and strategy."""
    print("  [Node] Drafting email...")

    sender:   SenderInfo   = state["sender"]
    receiver: ReceiverInfo = state["receiver"]
    ctx:      PitchContext = state["pitch_context"]

    prompt = DRAFT_EMAIL_PROMPT.format(
        sender_name       = sender.name,
        sender_role       = sender.role,
        sender_company    = sender.company_name,
        service_offered   = sender.service_offered,
        receiver_name     = receiver.name or "the team",
        receiver_role     = receiver.role or "Decision Maker",
        receiver_company  = receiver.company_name,
        company_type      = receiver.company_type,
        relevance_analysis= state.get("relevance_analysis", ""),
        goal              = ctx.goal,
        tone              = ctx.tone,
        email_length      = ctx.email_length,
        custom_notes      = ctx.custom_notes or "None",
        subject_hint      = ctx.subject_hint or "Create the best subject line",
    )

    draft = llm_call(prompt, temperature=0.75)

    # Parse subject line
    subject = ""
    body    = draft
    if "SUBJECT:" in draft:
        lines   = draft.split("\n")
        for line in lines:
            if line.strip().startswith("SUBJECT:"):
                subject = line.replace("SUBJECT:", "").strip()
                break
        # Remove subject line from body
        body = "\n".join(
            l for l in lines
            if not l.strip().startswith("SUBJECT:")
        ).strip().strip("---").strip()

    return {
        "email_draft":   draft,
        "subject_line":  subject,
        "iteration_count": state.get("iteration_count", 0),
    }

# Node: review_email
# ─────────────────────────────────────────────────────────────────────────────
def review_email(state: AgentState) -> dict:
    """Critically review the email draft and decide: APPROVED or REVISE."""
    print("🔎 [Node] Reviewing email draft...")

    receiver: ReceiverInfo = state["receiver"]
    ctx:      PitchContext = state["pitch_context"]

    prompt = REVIEW_EMAIL_PROMPT.format(
        email_draft       = state.get("email_draft", ""),
        sender_research   = state.get("sender_research", ""),
        receiver_research = state.get("receiver_research", ""),
        goal              = ctx.goal,
        tone              = ctx.tone,
        company_type      = receiver.company_type,
    )

    review_output = llm_call(prompt, temperature=0.2)

    approved      = "DECISION: APPROVED" in review_output
    revision_notes = ""
    if not approved and "REVISION_NOTES:" in review_output:
        revision_notes = review_output.split("REVISION_NOTES:")[-1].strip()

    return {
        "review_passed":  approved,
        "revision_notes": revision_notes,
    }

# Node: refine_email
# ─────────────────────────────────────────────────────────────────────────────
def refine_email(state: AgentState) -> dict:
    """Rewrite the email draft based on the reviewer's notes."""
    print("🔧 [Node] Refining email based on review feedback...")

    sender:   SenderInfo   = state["sender"]
    receiver: ReceiverInfo = state["receiver"]
    ctx:      PitchContext = state["pitch_context"]

    prompt = REFINE_EMAIL_PROMPT.format(
        email_draft      = state.get("email_draft", ""),
        revision_notes   = state.get("revision_notes", ""),
        sender_name      = sender.name,
        sender_role      = sender.role,
        sender_company   = sender.company_name,
        receiver_name    = receiver.name or "the team",
        receiver_company = receiver.company_name,
        tone             = ctx.tone,
        email_length     = ctx.email_length,
    )

    refined = llm_call(prompt, temperature=0.7)

    # Parse updated subject line
    subject = state.get("subject_line", "")
    if "SUBJECT:" in refined:
        for line in refined.split("\n"):
            if line.strip().startswith("SUBJECT:"):
                subject = line.replace("SUBJECT:", "").strip()
                break

    return {
        "email_draft":     refined,
        "subject_line":    subject,
        "iteration_count": state.get("iteration_count", 0) + 1,
    }


# Node: finalize
# ─────────────────────────────────────────────────────────────────────────────
def finalize(state: AgentState) -> dict:
    """Package the final approved email."""
    print(" [Node] Finalizing email...")

    draft = state.get("email_draft", "")

    # Clean up any leftover formatting artifacts
    final = draft.strip()
    if final.startswith("---"):
        final = final[3:].strip()
    if final.endswith("---"):
        final = final[:-3].strip()

    return {"final_email": final}


# Conditional edge: should we revise or finalize?
# ─────────────────────────────────────────────────────────────────────────────
def route_after_review(state: AgentState) -> str:
    """
    - APPROVED → finalize
    - REVISE and iteration < 3 → refine_email (loop back)
    - REVISE but too many iterations → finalize anyway
    """
    approved    = state.get("review_passed", False)
    iterations  = state.get("iteration_count", 0)
    MAX_ITERS   = 1

    if approved:
        return "finalize"
    if iterations >= MAX_ITERS:
        print(f"  Max revisions ({MAX_ITERS}) reached. Finalizing best draft.")
        return "finalize"
    return "refine_email"


# Build the LangGraph
# ─────────────────────────────────────────────────────────────────────────────
def build_graph():
    """Construct and compile the email drafter StateGraph."""
    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("research_sender",    research_sender)
    graph.add_node("research_receiver",  research_receiver)
    graph.add_node("research_market",    research_market)
    graph.add_node("analyze_relevance",  analyze_relevance)
    graph.add_node("draft_email",        draft_email)
    graph.add_node("review_email",       review_email)
    graph.add_node("refine_email",       refine_email)
    graph.add_node("finalize",           finalize)

    # ── Edges ────────────────────────────────────────────────────────────────
    # Parallel research phase: all three run concurrently
    graph.add_edge(START, "research_sender")
    graph.add_edge(START, "research_receiver")

    # After both sender + receiver research, do market research
    graph.add_edge("research_sender",   "research_market")
    graph.add_edge("research_receiver", "research_market")

    # Market research → analysis
    graph.add_edge("research_market",   "analyze_relevance")

    # Analysis → first draft
    graph.add_edge("analyze_relevance", "draft_email")

    # Draft → review
    graph.add_edge("draft_email",       "review_email")

    # Conditional: approve or revise
    graph.add_conditional_edges(
        "review_email",
        route_after_review,
        {
            "finalize":    "finalize",
            "refine_email":"refine_email",
        }
    )

    # Revision loops back to review
    graph.add_edge("refine_email", "review_email")

    # Final output
    graph.add_edge("finalize", END)

    return graph.compile()


# Main callable entry point
# ─────────────────────────────────────────────────────────────────────────────
def run_email_drafter(
    sender:        SenderInfo,
    receiver:      ReceiverInfo,
    pitch_context: PitchContext,
) -> dict[str, Any]:
    """
    Run the complete email drafter agent.

    Returns:
        dict with keys:
            final_email    : str  – polished outreach email
            subject_line   : str  – email subject line
            iterations     : int  – number of revision cycles
            review_passed  : bool – whether review auto-approved
            analysis       : str  – relevance analysis (debug)
    """
    app = build_graph()

    initial_state: AgentState = {
        "sender":          sender,
        "receiver":        receiver,
        "pitch_context":   pitch_context,
        # initialise all other fields
        "sender_research":   "",
        "receiver_research": "",
        "market_insights":   "",
        "relevance_analysis":"",
        "hook":              "",
        "subject_line":      "",
        "email_draft":       "",
        "revision_notes":    "",
        "final_email":       "",
        "review_passed":     False,
        "iteration_count":   0,
        "errors":            [],
    }

    final_state = app.invoke(initial_state)
    
    return {
        "final_email":   final_state.get("final_email", ""),
        "subject_line":  final_state.get("subject_line", ""),
        "iterations":    final_state.get("iteration_count", 0),
        "review_passed": final_state.get("review_passed", False),
        "analysis":      final_state.get("relevance_analysis", ""),
    }
