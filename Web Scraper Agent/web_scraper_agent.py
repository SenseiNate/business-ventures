"""
Web Scraper Agent
------------------
Structured research agent. Answer 4 quick questions about what you're looking
for, why, what you'll do with it, and which sources matter most. The agent runs
two search passes (general/institutional + social/forum), scores everything
it finds, and keeps only perfect 5/5 matches — up to 5 institutional and 5
social, tournament style. Report saves to a timestamped folder.

One query in, one report out. No looping.

Supported LLM providers: Anthropic (Claude), OpenAI (GPT), Google (Gemini)
Supported search providers: Anthropic built-in, Brave Search, SerpAPI

Configure via .env — see .env.example for all required variables.
"""

import json
import os
import re
import textwrap
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────
# Configuration — read from .env
# ──────────────────────────────────────────────────────────────────────────

LLM_PROVIDER      = os.environ.get("LLM_PROVIDER", "anthropic").lower()
LLM_MODEL         = os.environ.get("LLM_MODEL", "")
SEARCH_PROVIDER   = os.environ.get("SEARCH_PROVIDER", "anthropic").lower()
BRAVE_API_KEY     = os.environ.get("BRAVE_API_KEY", "")
SERPAPI_KEY       = os.environ.get("SERPAPI_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY    = os.environ.get("OPENAI_API_KEY", "")
GOOGLE_API_KEY    = os.environ.get("GOOGLE_API_KEY", "")

REPORTS_DIR   = Path(__file__).parent / "reports"
PERFECT_SCORE = 5   # only items scoring exactly this survive
MAX_PER_BUCKET = 5  # ceiling per source bucket, not a floor

# Default models per provider if LLM_MODEL is not set
DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai":    "gpt-4o-mini",
    "google":    "gemini-1.5-flash",
}


# ──────────────────────────────────────────────────────────────────────────
# LLM adapter layer — one complete() call per message, provider-agnostic
# ──────────────────────────────────────────────────────────────────────────

def get_model() -> str:
    return LLM_MODEL or DEFAULT_MODELS.get(LLM_PROVIDER, "")


def complete(prompt: str) -> str:
    """Send a single prompt to the configured LLM and return the text response."""
    model = get_model()

    if LLM_PROVIDER == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    elif LLM_PROVIDER == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    elif LLM_PROVIDER == "google":
        import google.generativeai as genai
        genai.configure(api_key=GOOGLE_API_KEY)
        gemini = genai.GenerativeModel(model)
        response = gemini.generate_content(prompt)
        return response.text

    else:
        raise SystemExit(
            f"Unknown LLM_PROVIDER: '{LLM_PROVIDER}'. "
            "Set LLM_PROVIDER to 'anthropic', 'openai', or 'google' in your .env file."
        )


# ──────────────────────────────────────────────────────────────────────────
# Search adapter layer — provider-agnostic web search
# ──────────────────────────────────────────────────────────────────────────

def search_web(query: str) -> list[dict[str, str]]:
    """Run a web search using the configured search provider.
    Returns a list of {title, url, snippet} dicts."""

    if SEARCH_PROVIDER == "anthropic":
        return _search_anthropic(query)
    elif SEARCH_PROVIDER == "brave":
        return _search_brave(query)
    elif SEARCH_PROVIDER == "serpapi":
        return _search_serpapi(query)
    else:
        raise SystemExit(
            f"Unknown SEARCH_PROVIDER: '{SEARCH_PROVIDER}'. "
            "Set SEARCH_PROVIDER to 'anthropic', 'brave', or 'serpapi' in your .env file."
        )


def _search_anthropic(query: str) -> list[dict[str, str]]:
    """Use Anthropic's built-in web search tool. Requires LLM_PROVIDER=anthropic."""
    if LLM_PROVIDER != "anthropic":
        raise SystemExit(
            "SEARCH_PROVIDER=anthropic requires LLM_PROVIDER=anthropic. "
            "Switch to 'brave' or 'serpapi' to use a different LLM provider."
        )
    import anthropic as anthropic_sdk
    client = anthropic_sdk.Anthropic(api_key=ANTHROPIC_API_KEY)
    model = get_model()

    message = client.messages.create(
        model=model,
        max_tokens=4096,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": query}],
    )

    # Handle tool-use continuation loop
    text_blocks = [b.text for b in message.content if b.type == "text"]
    raw = "\n".join(text_blocks).strip()

    if message.stop_reason == "tool_use":
        conversation = [
            {"role": "user", "content": query},
            {"role": "assistant", "content": message.content},
        ]
        for _ in range(3):
            follow_up = client.messages.create(
                model=model,
                max_tokens=4096,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=conversation,
            )
            if follow_up.stop_reason != "tool_use":
                text_blocks = [b.text for b in follow_up.content if b.type == "text"]
                raw = "\n".join(text_blocks).strip()
                break
            conversation.append({"role": "assistant", "content": follow_up.content})

    return _parse_search_results(raw)


def _search_brave(query: str) -> list[dict[str, str]]:
    """Use the Brave Search API. Requires BRAVE_API_KEY in .env."""
    import urllib.request
    import urllib.parse

    if not BRAVE_API_KEY:
        raise SystemExit("BRAVE_API_KEY not found in .env. Add it to use Brave Search.")

    params = urllib.parse.urlencode({"q": query, "count": 15})
    url = f"https://api.search.brave.com/res/v1/web/search?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": BRAVE_API_KEY,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())

    results = []
    for item in data.get("web", {}).get("results", []):
        results.append({
            "title":   item.get("title", "").strip(),
            "url":     item.get("url", "").strip(),
            "snippet": item.get("description", "").strip(),
        })
    return results


def _search_serpapi(query: str) -> list[dict[str, str]]:
    """Use the SerpAPI Google Search API. Requires SERPAPI_KEY in .env."""
    import urllib.request
    import urllib.parse

    if not SERPAPI_KEY:
        raise SystemExit("SERPAPI_KEY not found in .env. Add it to use SerpAPI.")

    params = urllib.parse.urlencode({
        "q":      query,
        "api_key": SERPAPI_KEY,
        "num":    15,
        "engine": "google",
    })
    url = f"https://serpapi.com/search?{params}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.loads(resp.read().decode())

    results = []
    for item in data.get("organic_results", []):
        results.append({
            "title":   item.get("title", "").strip(),
            "url":     item.get("link", "").strip(),
            "snippet": item.get("snippet", "").strip(),
        })
    return results


def _parse_search_results(raw: str) -> list[dict[str, str]]:
    """Parse a JSON array of search results from an LLM response."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        items = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
        if match:
            try:
                items = json.loads(match.group(0))
            except json.JSONDecodeError:
                print(f"  [debug] Could not parse search results. Raw (first 500 chars):\n{cleaned[:500]}")
                return []
        else:
            print(f"  [debug] Could not parse search results. Raw (first 500 chars):\n{cleaned[:500]}")
            return []

    results = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            results.append({
                "title":   str(item.get("title", "")).strip(),
                "url":     str(item.get("url", "")).strip(),
                "snippet": str(item.get("snippet", "")).strip(),
            })
    return results


# ──────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:60].strip("-") or "query"


# ──────────────────────────────────────────────────────────────────────────
# Step 1: structured intake
# ──────────────────────────────────────────────────────────────────────────

def ask_intake_questions() -> dict[str, str]:
    print("\nFour quick questions to lock in a precise search.\n")
    what    = input("1. What are you looking for? > ").strip()
    why     = input("2. Why are you looking for it? > ").strip()
    use     = input("3. What are you planning on doing with the information? > ").strip()
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
    sources = intake["sources"].lower()
    if not sources:
        return True
    return (
        "institutional" not in sources
        and "articles only" not in sources
        and "no social" not in sources
    )


def wants_institutional(intake: dict[str, str]) -> bool:
    sources = intake["sources"].lower()
    if not sources:
        return True
    return "social media only" not in sources and "social only" not in sources


# ──────────────────────────────────────────────────────────────────────────
# Step 2: dual-pass search
# ──────────────────────────────────────────────────────────────────────────

def gather_institutional_candidates(goal: str) -> list[dict[str, str]]:
    if SEARCH_PROVIDER == "anthropic":
        # Anthropic search: embed instructions directly in the search prompt
        prompt = (
            "Use web search to find content relevant to this research topic:\n\n"
            f'"{goal}"\n\n'
            "Focus on articles, news, official guidance, research, and professional/"
            "institutional sources — NOT social media or forum posts. "
            "Don't rank or filter yet, just gather candidates.\n\n"
            "Respond with ONLY a JSON array. Each item must have exactly these keys: "
            '"title", "url", "snippet" (1-3 sentence summary). Include up to 15 items.'
        )
        results = search_web(prompt)
    else:
        # External search APIs: run targeted query, get raw results back
        results = search_web(f"{goal} site:news OR site:research OR site:org")

    for r in results:
        r["bucket"] = "institutional"
    return results


def gather_social_candidates(goal: str) -> list[dict[str, str]]:
    if SEARCH_PROVIDER == "anthropic":
        prompt = (
            "Use web search to find first-person social media and forum content "
            "relevant to this research topic:\n\n"
            f'"{goal}"\n\n'
            "Search for posts, comments, threads, and reviews from Reddit, X (Twitter), "
            "Facebook groups, and similar forums — real people describing their own "
            "experience in their own words, NOT articles or institutional content. "
            'Try searches like "site:reddit.com [topic]" and similar. '
            "X and Facebook content is often not publicly indexed, so Reddit may "
            "dominate — that's expected.\n\n"
            "Respond with ONLY a JSON array. Each item must have exactly these keys: "
            '"title", "url", "snippet" (1-3 sentence summary). Include up to 15 items.'
        )
        results = search_web(prompt)
    else:
        results = search_web(f"site:reddit.com OR site:twitter.com {goal}")

    for r in results:
        r["bucket"] = "social"
    return results


# ──────────────────────────────────────────────────────────────────────────
# Step 3: tournament-style scoring — only perfect 5/5 survives, per bucket
# ──────────────────────────────────────────────────────────────────────────

def format_candidates_for_prompt(candidates: list[dict[str, str]]) -> str:
    blocks = []
    for i, c in enumerate(candidates, start=1):
        body = c.get("snippet") or c.get("body") or "(no body text)"
        blocks.append(
            f"Candidate {i}\n"
            f"Title: {c['title']}\n"
            f"URL: {c['url']}\n"
            f"Content: {body}"
        )
    return "\n\n---\n\n".join(blocks)


def score_bucket(
    goal: str,
    candidates: list[dict[str, str]],
    bucket_label: str,
    strict_social_check: bool = False,
) -> str:
    """Score one bucket's candidates. Returns markdown for perfect-5 survivors only.

    strict_social_check: when True, disqualifies any institutional/published domain
    that slipped into the social bucket via search — only genuine platform posts
    (Reddit, X, Facebook, TeamBlind, Glassdoor, etc.) are eligible for a 5.
    """
    if not candidates:
        return ""

    candidates_text = format_candidates_for_prompt(candidates)

    social_rule = ""
    if strict_social_check:
        social_rule = (
            "\n\nIMPORTANT DOMAIN CHECK: this bucket should contain only genuine "
            "social media and forum content — Reddit, X/Twitter, Facebook, TeamBlind, "
            "Glassdoor reviews, forum threads, etc. If a candidate's URL is from a "
            "news outlet, .gov site, nonprofit, blog, or any published/edited article "
            "(even one that quotes a real person), DISQUALIFY it — score it 1 and "
            "exclude it. Only direct posts or comments from social platforms qualify."
        )

    prompt = (
        f'A researcher has this goal: "{goal}"\n\n'
        f"Below are {len(candidates)} {bucket_label} candidates. Score each 1-5 for "
        "how precisely and usefully it matches the goal. Be strict — a 5 means an "
        f"excellent, highly specific match. Keep ONLY items scoring exactly "
        f"{PERFECT_SCORE}/5. Include nothing scoring 4 or below, even if that means "
        f"zero items survive. Rank survivors best to worst, up to {MAX_PER_BUCKET}."
        f"{social_rule}\n\n"
        "For each surviving item write a section in this exact format:\n\n"
        "## [Title]\n"
        "**URL:** [url]\n"
        "**Score:** 5/5\n"
        "**What it says:** [2-3 sentence summary in your own words]\n"
        "**Why it's relevant:** [1-2 sentences tying it to the stated goal]\n\n"
        "Do not invent details. If zero items score 5/5, respond with exactly: NONE\n\n"
        f"Candidates:\n\n{candidates_text}"
    )

    result = complete(prompt).strip()
    return "" if result.upper() == "NONE" else result


# ──────────────────────────────────────────────────────────────────────────
# Step 4: save and print report
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

def run_query(intake: dict[str, str]) -> None:
    now = datetime.now()
    goal = build_goal_statement(intake)

    do_institutional = wants_institutional(intake)
    do_social = wants_social(intake)

    institutional_candidates: list[dict[str, str]] = []
    social_candidates: list[dict[str, str]] = []

    if do_institutional:
        print("\nSearching articles, news, and institutional sources...")
        institutional_candidates = gather_institutional_candidates(goal)
        print(f"  Got {len(institutional_candidates)} results.")

    if do_social:
        print("\nSearching Reddit, X, Facebook, and forums...")
        social_candidates = gather_social_candidates(goal)
        print(f"  Got {len(social_candidates)} results.")

    total = len(institutional_candidates) + len(social_candidates)
    if total == 0:
        print("\nNo candidates found. Try rephrasing your goal.")
        return

    institutional_section = ""
    social_section = ""

    if institutional_candidates:
        print(f"\nScoring {len(institutional_candidates)} institutional candidates (5/5 only)...")
        institutional_section = score_bucket(goal, institutional_candidates, "article/institutional")

    if social_candidates:
        print(f"\nScoring {len(social_candidates)} social/forum candidates (5/5 only)...")
        social_section = score_bucket(
            goal, social_candidates, "social media/forum", strict_social_check=True
        )

    sections = []
    if institutional_section:
        sections.append(f"## Institutional & Articles\n\n{institutional_section}")
    if social_section:
        sections.append(f"## Social Media & Forums\n\n{social_section}")

    if not sections:
        report_body = (
            f"**{total} candidates reviewed; none scored a perfect 5/5.**\n\n"
            "Try rephrasing your goal to be more specific, or broaden your source "
            "preference — this topic may genuinely lack highly precise public matches."
        )
    else:
        buckets_with_results = sum([bool(institutional_section), bool(social_section)])
        report_body = (
            f"**{total} candidates reviewed; "
            f"{buckets_with_results} bucket(s) produced perfect-5 matches.**\n\n"
            + "\n\n---\n\n".join(sections)
        )

    filepath = save_report(goal, report_body, now)
    print_report(report_body)
    print(f"\nSaved to {filepath}")


def main() -> None:
    print("\nWeb Scraper Agent")
    print("Answer the questions below, or type 'quit' at the first one to exit.\n")

    # Validate configuration before asking intake questions
    if not any([ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY]):
        raise SystemExit(
            "No API key found. Set at least one of ANTHROPIC_API_KEY, "
            "OPENAI_API_KEY, or GOOGLE_API_KEY in your .env file."
        )
    if not get_model():
        raise SystemExit(
            f"No model configured for LLM_PROVIDER='{LLM_PROVIDER}'. "
            "Set LLM_MODEL in your .env or use a supported provider."
        )

    intake = ask_intake_questions()
    if not intake["what"] or intake["what"].lower() in ("quit", "exit"):
        print("Nothing to do. Bye.")
        return

    run_query(intake)


if __name__ == "__main__":
    main()
