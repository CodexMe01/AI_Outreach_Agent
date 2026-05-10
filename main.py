"""
Email Drafter Agent — Interactive CLI
======================================
Run: python main.py
"""
from __future__ import annotations
import sys
import os

import sqlite3
from cache import DB_PATH       # same DB_PATH = "receiver_cache.db"


from rich.console import Console
from rich.panel   import Panel
from rich.prompt  import Prompt, Confirm
from rich.text    import Text
from rich.rule    import Rule
from rich         import print as rprint
from rich.syntax  import Syntax

from config       import SenderInfo, ReceiverInfo, PitchContext
from agent        import run_email_drafter
from notion_crm   import save_to_notion

console = Console()


# Banner
# ─────────────────────────────────────────────────────────────────────────────
def print_banner():
    console.print()
    console.print(Panel.fit(
        "[bold cyan]✉  AI Email Drafter Agent[/bold cyan]\n"
        "[dim]LangGraph · Groq LLM · Personalised B2B Outreach[/dim]",
        border_style="cyan",
        padding=(1, 4),
    ))
    console.print()



# Input collection helpers
# ───────────────────────────────────────────────────────────────────────────────────────────────────
def collect_sender() -> SenderInfo:
    
    return SenderInfo(
        name            = "Pratyush",
        role            = "Product Manager",
        company_name    = "PRG",
        company_website = "https://pratyushrdesign.framer.website/"  or None,
        company_desc    = "Providing Branding, UI/UX, and Web Design Solutions to Elevate Your Digital Experience."     or None,
        service_offered = "Branding, UI/UX, and Web Design",
        usp             = "Perfection, uniqueness, delivering the best "      or None,
    )

import Reasearcher
# Reasearcher()
def collect_receiver() -> ReceiverInfo:
    console.print(Rule("[bold yellow]📥 Receiver / Target Company[/bold yellow]"))

    # ── Fetch all cached companies from SQLite ─────────────────────────────────
    con  = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT company_key, company_name, receiver FROM receiver_cache ORDER BY fetched_at DESC"
    ).fetchall()
    con.close()

    if not rows:
        console.print("[red]No cached companies found. Run Researcher.py first.[/red]")
        raise SystemExit(1)

    # ── Display the list ───────────────────────────────────────────────────────
    console.print(f"\n[dim]Found {len(rows)} cached companies:[/dim]\n")
    for i, (key, name, _) in enumerate(rows, 1):
        console.print(f"  [cyan]{i}[/cyan]. {name}")

    # ── Let user pick one ──────────────────────────────────────────────────────
    choice = Prompt.ask(
        "\n[yellow]Select company number[/yellow]",
        choices=[str(i) for i in range(1, len(rows) + 1)],
    )

    # ── Deserialize the chosen row back into ReceiverInfo ─────────────────────
    selected_json = rows[int(choice) - 1][2]        # column 2 = receiver JSON
    receiver      = ReceiverInfo.model_validate_json(selected_json)

    # ── Show what was loaded ───────────────────────────────────────────────────
    console.print()
    console.print(Panel(
        f"[bold]{receiver.company_name}[/bold]  ·  {receiver.company_type}\n"
        f"[dim]Industry :[/dim] {receiver.industry or 'N/A'}\n"
        f"[dim]Website  :[/dim] {receiver.company_website or 'N/A'}\n"
        f"[dim]Contact  :[/dim] {receiver.name or 'Unknown'}  —  {receiver.role or 'Unknown'}",
        title="[yellow]Loaded from cache[/yellow]",
        border_style="yellow",
    ))
    console.print()

    return receiver

def collect_pitch_context() -> PitchContext:
    console.print(Rule("[bold magenta] Pitch Context[/bold magenta]"))
    goal    = Prompt.ask(
        "[magenta]Email goal[/magenta]",
        choices=["demo", "discovery_call", "free_trial", "partnership", "custom"],
        default="demo",
    )
    if goal == "custom":
        goal = Prompt.ask("[magenta]Describe your goal[/magenta]")

    tone = Prompt.ask(
        "[magenta]Tone[/magenta]",
        choices=["professional", "friendly", "bold", "concise"],
        default="professional",
    )
    length = Prompt.ask(
        "[magenta]Email length[/magenta]",
        choices=["short", "medium", "long"],
        default="medium",
    )
    pain_points   = Prompt.ask("[magenta]Known pain points of target[/magenta] [dim](press Enter to skip)[/dim]", default="")
    subject_hint  = Prompt.ask("[magenta]Subject line hint[/magenta] [dim](press Enter to skip)[/dim]", default="")
    custom_notes  = Prompt.ask("[magenta]Extra instructions[/magenta] [dim](press Enter to skip)[/dim]", default="")
    console.print()
    return PitchContext(
        goal          = goal,
        tone          = tone,
        email_length  = length,
        pain_points   = pain_points  or None,
        subject_hint  = subject_hint or None,
        custom_notes  = custom_notes or None,
    )


# Display result
# ───────────────────────────────────────────────────────────────────────────────────────────────────

def display_result(result: dict):
    console.print()
    console.print(Rule("[bold cyan] Generated Outreach Email[/bold cyan]"))
    console.print()

    # Subject
    if result.get("subject_line"):
        console.print(Panel(
            f"[bold]{result['subject_line']}[/bold]",
            title="[cyan]Subject Line[/cyan]",
            border_style="cyan",
        ))
        console.print()

    # Email body (strip leading/trailing separators)
    body = result["final_email"]
    for artifact in ["SUBJECT:", "---"]:
        if body.startswith(artifact):
            body = body[len(artifact):].strip()

    console.print(Panel(
        body,
        title="[cyan]Email Body[/cyan]",
        border_style="dim",
        padding=(1, 2),
    ))

    # Metadata
    console.print()
    console.print(
        f"[dim]✔ Review passed:[/dim] {'[green]Yes[/green]' if result['review_passed'] else '[yellow]Forced finalize[/yellow]'}  "
        f"[dim]| Revision cycles:[/dim] [cyan]{result['iterations']}[/cyan]"
    )

    # Optionally show analysis
    if Confirm.ask("\n[dim]Show relevance analysis?[/dim]", default=False):
        console.print()
        console.print(Panel(
            result.get("analysis", "N/A"),
            title="[magenta]Strategy Analysis[/magenta]",
            border_style="magenta",
        ))


# Entry point
# ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def main():
    print_banner()

    # Env check
    if not os.getenv("GROQ_API_KEY"):
        console.print("[bold red]❌ GROQ_API_KEY not set.[/bold red] Add it to your .env file.\n")
        sys.exit(1)

    sender   = collect_sender()
    receiver = collect_receiver()
    ctx      = collect_pitch_context()

    # Confirm before running
    console.print(Panel.fit(
        f"[bold]Sender:[/bold]   {sender.name} · {sender.role} @ {sender.company_name}\n"
        f"[bold]Receiver:[/bold] {receiver.name or 'Unknown'} @ {receiver.company_name} ({receiver.company_type})\n"
        f"[bold]Goal:[/bold]     {ctx.goal}  |  [bold]Tone:[/bold] {ctx.tone}  |  [bold]Length:[/bold] {ctx.email_length}",
        title="[cyan]Summary[/cyan]",
        border_style="cyan",
    ))
    if not Confirm.ask("\nProceed?", default=True):
        console.print("Aborted.")
        return

    console.print()
    with console.status("[bold cyan]Running email drafter agent…[/bold cyan]", spinner="dots"):
        result = run_email_drafter(sender, receiver, ctx)

    display_result(result)
    
    # Save to Notion database
    console.print()
    with console.status("[bold cyan]Saving to Notion database…[/bold cyan]", spinner="dots"):
        save_to_notion(receiver)
        
    console.print()


if __name__ == "__main__":
    main()
