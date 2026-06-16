"""
Web Scraper Agent
------------------
Chat-style research agent. You type a goal, Claude searches the web for it,
scores everything it finds against your goal, and writes a ranked report.

One query in, one report out. No looping.

Requires only ANTHROPIC_API_KEY in .env.
"""

import json
import os
import re
import textwrap
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-haiku-4-5-20251001"
REPORTS_DIR = Path(__file__).parent / "reports"
MIN_SCORE = 4  # only items scoring >= this (out of 5) make the final report
TOP_N = 15  # max items in the final ranked report


def get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit(
            "ANTHROPIC_API_KEY not found. Add it to your .env file and try again."
        )
    return anthropic.Anthropic(api_key=api_key)


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:60].strip("-") or "query"


# ──────────────────────────────────────────────────────────────────────────
# Step 1: web research via Claude's built-in web search tool
# ──────────────────────────────────────────────────────────────────────────

def gather_web_candidates(client: anthropic.Anthropic, goal: str) -> list[dict[str, str]]:
    prompt = (
        "Research the following goal using web search:\n\n"
        f'"{goal}"\n\n'
        "Search the web broadly — articles, forums, social media discussions, "
        "product pages, anything relevant. "
        "After searching, respond with ONLY a JSON array of the most relevant "
        "pages you found. Each item must have these exact keys: "
        '"title", "url", "snippet" (1-3 sentences summarizing what the page says). '
        "Include up to 20 items. Respond with ONLY the JSON array, no other text."
    )

    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )

    # Pull out the final text block (after any tool-use rounds)
    text_blocks = [b.text for b in message.content if b.type == "text"]
    raw = "\n".join(text_blocks).strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()

    # If the model didn't finish in one turn (tool use pending), do a follow-up
    if message.stop_reason == "tool_use":
        conversation = [{"role": "user", "content": prompt}, {"role": "assistant", "content": message.content}]
        for _ in range(3):
            follow_up = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=conversation,
            )
            if follow_up.stop_reason != "tool_use":
                text_blocks = [b.text for b in follow_up.content if b.type == "text"]
                raw = "\n".join(text_blocks).strip()
                raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
                break
            conversation.append({"role": "assistant", "content": follow_up.content})

    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return []

    candidates = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            candidates.append(
                {
                    "title": str(item.get("title", "")).strip(),
                    "body": str(item.get("snippet", "")).strip(),
                    "url": str(item.get("url", "")).strip(),
                }
            )
    return candidates


# ──────────────────────────────────────────────────────────────────────────
# Step 2: score + rank everything against the original goal
# ──────────────────────────────────────────────────────────────────────────

def format_candidates_for_prompt(candidates: list[dict[str, str]]) -> str:
    blocks = []
    for i, c in enumerate(candidates, start=1):
        body = c["body"] or "(no body text)"
        blocks.append(
            f"Candidate {i}\n"
            f"Title: {c['title']}\n"
            f"URL: {c['url']}\n"
            f"Content: {body}"
        )
    return "\n\n---\n\n".join(blocks)


def rank_candidates(client: anthropic.Anthropic, goal: str, candidates: list[dict[str, str]]) -> str:
    candidates_text = format_candidates_for_prompt(candidates)

    prompt = (
        f'A researcher has this goal: "{goal}"\n\n'
        f"Below are {len(candidates)} candidate items pulled from the web. "
        "Score each one 1-5 for how relevant and useful it is to the stated goal. "
        f"Keep ONLY items scoring {MIN_SCORE} or higher. "
        f"Rank the survivors best to worst, up to {TOP_N} items.\n\n"
        "For each surviving item, write a section with this exact format:\n\n"
        "## [Rank]. [Title]\n"
        "**URL:** [url]\n"
        "**Score:** [X/5]\n"
        "**What it says:** [2-3 sentence summary in your own words]\n"
        "**Why it's relevant:** [1-2 sentences tying it directly to the stated goal]\n\n"
        "If fewer than 3 items score 4 or higher, say so plainly at the top of the "
        "report rather than padding the list with weak matches. "
        "Do not invent details not present in the candidates. "
        "Start the report with a one-line summary of how many candidates were "
        f"reviewed and how many made the cut.\n\nCandidates:\n\n{candidates_text}"
    )

    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


# ──────────────────────────────────────────────────────────────────────────
# Step 3: save report
# ──────────────────────────────────────────────────────────────────────────

def save_report(goal: str, report: str, now: datetime) -> Path:
    folder_name = f"{now:%Y-%m-%d}_{slugify(goal)}"
    report_dir = REPORTS_DIR / folder_name
    report_dir.mkdir(parents=True, exist_ok=True)
    filepath = report_dir / "report.md"
    content = (
        f"# Research Report\n\n"
        f"**Goal:** {goal}\n"
        f"**Date:** {now:%B %d, %Y %I:%M %p}\n\n"
        f"---\n\n{report}\n"
    )
    filepath.write_text(content, encoding="utf-8")
    return filepath


def print_report(report: str) -> None:
    width = 72
    print()
    print("=" * width)
    print(" RESEARCH REPORT".center(width))
    print("=" * width)
    print()
    print(textwrap.indent(report.strip(), prefix="  "))
    print()
    print("=" * width)


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────

def run_query(client: anthropic.Anthropic, goal: str) -> None:
    now = datetime.now()

    print("\nSearching the web...")
    candidates = gather_web_candidates(client, goal)
    print(f"  Got {len(candidates)} results.")

    if not candidates:
        print("\nNo candidates found. Try rephrasing your goal.")
        return

    print(f"\nScoring and ranking {len(candidates)} candidates...")
    report = rank_candidates(client, goal, candidates)

    filepath = save_report(goal, report, now)
    print_report(report)
    print(f"\nSaved to {filepath}")


def main() -> None:
    client = get_client()

    print("\nWeb Scraper Agent")
    print("Type a research goal, or 'quit' to exit.\n")

    goal = input("What are you researching? > ").strip()
    if not goal or goal.lower() in ("quit", "exit"):
        print("Nothing to do. Bye.")
        return

    run_query(client, goal)


if __name__ == "__main__":
    main()