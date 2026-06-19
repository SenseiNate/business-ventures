"""
Web Scraper Agent
------------------
Structured research agent. Answer 4 quick questions about what you're looking
for, why, what you'll do with it, and which sources matter most. Claude runs
two search passes (general/institutional + social/forum), scores everything
it finds, and keeps only perfect 5/5 matches — up to 5 institutional and 5
social, tournament style. Report saves to a timestamped folder.

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
PERFECT_SCORE = 5  # only items scoring exactly this survive — tournament style
MAX_PER_BUCKET = 5  # ceiling per source bucket, not a floor


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


def parse_json_response(raw: str) -> list:
    """Parse a JSON array out of a model response, salvaging it from extra
    prose if needed. Returns [] and prints a debug snippet on failure."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    print(f"  [debug] Could not parse JSON response. Raw (first 500 chars):\n{cleaned[:500]}")
    return []


# ──────────────────────────────────────────────────────────────────────────
# Step 1: structured intake
# ──────────────────────────────────────────────────────────────────────────

def ask_intake_questions() -> dict[str, str]:
    print("\nFour quick questions to lock in a precise search.\n")

    what = input("1. What are you looking for? > ").strip()
    why = input("2. Why are you looking for it? > ").strip()
    use = input("3. What are you planning on doing with the information? > ").strip()
    sources = input(
        "4. Which sources matter most? (e.g. \"mix of articles and social media\", "
        "\"social media only\", \"best results regardless of type\") > "
    ).strip()

    return {"what": what, "why": why, "use": use, "sources": sources}


def build_goal_statement(intake: dict[str, str]) -> str:
    parts = [intake["what"]]
    if intake["why"]:
        parts.append(f"Why this matters: {intake['why']}.")
    if intake["use"]:
        parts.append(f"What the findings will be used for: {intake['use']}.")
    return " ".join(parts)


def wants_social(intake: dict[str, str]) -> bool:
    """Whether the social/forum search pass should run at all."""
    sources = intake["sources"].lower()
    if not sources:
        return True  # default to running both passes if unspecified
    return "institutional" not in sources and "articles only" not in sources and "no social" not in sources


def wants_institutional(intake: dict[str, str]) -> bool:
    """Whether the general/institutional search pass should run at all."""
    sources = intake["sources"].lower()
    if not sources:
        return True
    return "social media only" not in sources and "social only" not in sources


# ──────────────────────────────────────────────────────────────────────────
# Step 2: dual-pass web research via Claude's built-in web search tool
# ──────────────────────────────────────────────────────────────────────────

def run_search_pass(client: anthropic.Anthropic, prompt: str) -> list[dict[str, str]]:
    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )

    text_blocks = [b.text for b in message.content if b.type == "text"]
    raw = "\n".join(text_blocks).strip()

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
                break
            conversation.append({"role": "assistant", "content": follow_up.content})

    items = parse_json_response(raw)
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


def gather_institutional_candidates(client: anthropic.Anthropic, goal: str) -> list[dict[str, str]]:
    prompt = (
        "Use web search to find content relevant to this research topic:\n\n"
        f'"{goal}"\n\n'
        "Focus this search on articles, news, official guidance, research, and "
        "professional/institutional sources — NOT social media or forum posts. "
        "Don't worry about ranking, scoring, or filtering yet, just gather candidates.\n\n"
        "After searching, respond with ONLY a JSON array, no other text before or "
        "after it. Each item must have these exact keys: "
        '"title", "url", "snippet" (1-3 sentences summarizing what the page says). '
        "Include up to 15 items."
    )
    candidates = run_search_pass(client, prompt)
    for c in candidates:
        c["bucket"] = "institutional"
    return candidates


def gather_social_candidates(client: anthropic.Anthropic, goal: str) -> list[dict[str, str]]:
    prompt = (
        "Use web search to find first-person social media and forum content "
        "relevant to this research topic:\n\n"
        f'"{goal}"\n\n'
        "Search specifically for posts, comments, threads, and reviews from "
        "Reddit, X (Twitter), Facebook groups, and similar forums — real people "
        "describing their own experience in their own words, NOT articles, "
        "guides, or institutional content. Try searches like "
        '"site:reddit.com [topic]" and similar. Note: X and Facebook content is '
        "often not publicly indexed, so Reddit may dominate these results — "
        "that's expected, include whatever genuine first-person content you find. "
        "Don't worry about ranking, scoring, or filtering yet, just gather candidates.\n\n"
        "After searching, respond with ONLY a JSON array, no other text before or "
        "after it. Each item must have these exact keys: "
        '"title", "url", "snippet" (1-3 sentences summarizing what the post/comment says). '
        "Include up to 15 items."
    )
    candidates = run_search_pass(client, prompt)
    for c in candidates:
        c["bucket"] = "social"
    return candidates


# ──────────────────────────────────────────────────────────────────────────
# Step 3: tournament-style scoring — only perfect 5/5 survives, per bucket
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


def score_bucket(
    client: anthropic.Anthropic,
    goal: str,
    candidates: list[dict[str, str]],
    bucket_label: str,
    strict_social_check: bool = False,
) -> str:
    """Score one bucket's candidates, return only the markdown sections for
    items that score a perfect 5/5, up to MAX_PER_BUCKET.

    If strict_social_check is True, candidates from news/institutional domains
    are disqualified outright even if the search pass that found them was
    targeting social media — a search pass surfacing a result doesn't mean
    the result actually IS social media."""
    if not candidates:
        return ""

    candidates_text = format_candidates_for_prompt(candidates)

    social_rule = ""
    if strict_social_check:
        social_rule = (
            "\n\nIMPORTANT DOMAIN CHECK: this bucket is supposed to be actual social "
            "media and forum content (Reddit, X/Twitter, Facebook, forums, review "
            "sites where regular people post directly). Some candidates below may "
            "actually be news articles, nonprofit sites, government sites, or other "
            "institutional/published content that merely QUOTES a person — that does "
            "NOT count as social media, even if the quote itself is first-person. "
            "If a candidate's URL or content is from a news outlet, government site "
            "(.gov), nonprofit, blog, or any published/edited article rather than a "
            "direct social media post or forum comment, DISQUALIFY it regardless of "
            "how relevant or well-quoted it is — score it 1 and exclude it from this "
            "bucket. Only genuine direct posts/comments from platforms like Reddit, "
            "X, Facebook, TeamBlind, Glassdoor reviews, etc. are eligible for a 5 here."
        )

    prompt = (
        f'A researcher has this goal: "{goal}"\n\n'
        f"Below are {len(candidates)} {bucket_label} candidate items. This is a "
        "tournament: score each one 1-5 for how precisely and usefully it matches "
        "the goal. Be strict — a 5 means this is an excellent, highly specific "
        f"match, not just loosely related. Keep ONLY items scoring a perfect "
        f"{PERFECT_SCORE}/5. Do not include anything scoring 4 or below, even if "
        f"that means very few or zero items survive. Rank survivors best to "
        f"worst, up to {MAX_PER_BUCKET} items."
        f"{social_rule}\n\n"
        "For each surviving item, write a section with this exact format:\n\n"
        "## [Title]\n"
        "**URL:** [url]\n"
        "**Score:** 5/5\n"
        "**What it says:** [2-3 sentence summary in your own words]\n"
        "**Why it's relevant:** [1-2 sentences tying it directly to the stated goal]\n\n"
        "Do not invent details not present in the candidates. If zero items "
        "score a perfect 5, respond with exactly: NONE\n\n"
        f"Candidates:\n\n{candidates_text}"
    )

    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    result = message.content[0].text.strip()
    return "" if result.upper() == "NONE" else result


# ──────────────────────────────────────────────────────────────────────────
# Step 4: save report
# ──────────────────────────────────────────────────────────────────────────

def save_report(goal: str, report_body: str, now: datetime) -> Path:
    folder_name = f"{now:%Y-%m-%d}_{slugify(goal)}"
    report_dir = REPORTS_DIR / folder_name
    report_dir.mkdir(parents=True, exist_ok=True)
    filepath = report_dir / "report.md"
    content = (
        f"# Research Report\n\n"
        f"**Goal:** {goal}\n"
        f"**Date:** {now:%B %d, %Y %I:%M %p}\n\n"
        f"---\n\n{report_body}\n"
    )
    filepath.write_text(content, encoding="utf-8")
    return filepath


def print_report(report_body: str) -> None:
    width = 72
    print()
    print("=" * width)
    print(" RESEARCH REPORT".center(width))
    print("=" * width)
    print()
    print(textwrap.indent(report_body.strip(), prefix="  "))
    print()
    print("=" * width)


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────

def run_query(client: anthropic.Anthropic, intake: dict[str, str]) -> None:
    now = datetime.now()
    goal = build_goal_statement(intake)

    do_institutional = wants_institutional(intake)
    do_social = wants_social(intake)

    institutional_candidates: list[dict[str, str]] = []
    social_candidates: list[dict[str, str]] = []

    if do_institutional:
        print("\nSearching articles, news, and institutional sources...")
        institutional_candidates = gather_institutional_candidates(client, goal)
        print(f"  Got {len(institutional_candidates)} results.")

    if do_social:
        print("\nSearching Reddit, X, Facebook, and forums...")
        social_candidates = gather_social_candidates(client, goal)
        print(f"  Got {len(social_candidates)} results.")

    total = len(institutional_candidates) + len(social_candidates)
    if total == 0:
        print("\nNo candidates found from either source. Try rephrasing your goal.")
        return

    sections = []
    institutional_section = ""
    social_section = ""

    if institutional_candidates:
        print(f"\nScoring {len(institutional_candidates)} institutional candidates (5/5 only survives)...")
        institutional_section = score_bucket(client, goal, institutional_candidates, "article/institutional")

    if social_candidates:
        print(f"\nScoring {len(social_candidates)} social/forum candidates (5/5 only survives)...")
        social_section = score_bucket(
            client, goal, social_candidates, "social media/forum", strict_social_check=True
        )

    if institutional_section:
        sections.append(f"## Institutional & Articles\n\n{institutional_section}")
    if social_section:
        sections.append(f"## Social Media & Forums\n\n{social_section}")

    if not sections:
        report_body = (
            f"**{total} candidates reviewed across both source types; none scored a perfect 5/5.** "
            "Try rephrasing your goal to be more specific, or lower expectations for this topic — "
            "it may genuinely lack highly precise public matches right now."
        )
    else:
        report_body = (
            f"**{total} candidates reviewed; "
            f"{(1 if institutional_section else 0) + (1 if social_section else 0)} bucket(s) produced perfect-5 matches.**\n\n"
            + "\n\n---\n\n".join(sections)
        )

    filepath = save_report(goal, report_body, now)
    print_report(report_body)
    print(f"\nSaved to {filepath}")


def main() -> None:
    client = get_client()

    print("\nWeb Scraper Agent")
    print("Answer the questions below, or type 'quit' at the first one to exit.\n")

    intake = ask_intake_questions()
    if not intake["what"] or intake["what"].lower() in ("quit", "exit"):
        print("Nothing to do. Bye.")
        return

    run_query(client, intake)


if __name__ == "__main__":
    main()