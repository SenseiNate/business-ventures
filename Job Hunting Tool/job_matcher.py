"""
Job Matcher
-----------
Forked from Web Scraper Agent. Searches job boards and company career pages,
scores each listing against a distilled candidate profile using LLM
comparison (not keyword matching), filters to 60%+ matches, and writes a
ranked report.

Requires profile.json (run distill_profile.py first) and ANTHROPIC_API_KEY
in .env.

Sourcing is web_search only. No ATS scraping, no guaranteed real-time
listing verification. Best effort on freshness — the report says so.
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

MODEL = "claude-sonnet-4-6"
REPORTS_DIR = Path(__file__).parent / "reports"
PROFILE_PATH = Path(__file__).parent / "profile.json"
MIN_MATCH_PCT = 60  # only listings scoring >= this make the final report
MAX_SEARCHES = 8  # number of distinct web_search queries per run


def get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit(
            "ANTHROPIC_API_KEY not found. Add it to your .env file and try again."
        )
    return anthropic.Anthropic(api_key=api_key)


def load_profile() -> dict:
    if not PROFILE_PATH.exists():
        raise SystemExit(
            f"{PROFILE_PATH.name} not found. Run distill_profile.py first "
            "to build it from your master data bank."
        )
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def strip_fences(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"```$", "", raw, flags=re.MULTILINE)
    return raw.strip()


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:60].strip("-") or "search"


# ──────────────────────────────────────────────────────────────────────────
# Inputs
# ──────────────────────────────────────────────────────────────────────────

def collect_search_inputs() -> dict:
    print("\nJob Matcher\n")

    pay_min = input("Minimum target pay (e.g. 110000, or blank to skip) > ").strip()
    location_mode = input(
        "Location preference [onsite/hybrid/remote/any] > "
    ).strip().lower() or "any"
    location_area = ""
    if location_mode in ("onsite", "hybrid"):
        location_area = input(
            "City/region for onsite or hybrid roles > "
        ).strip()
    extra_focus = input(
        "Any specific titles, industries, or focus to prioritize? "
        "(optional, blank to use full profile) > "
    ).strip()

    return {
        "pay_min": pay_min,
        "location_mode": location_mode,
        "location_area": location_area,
        "extra_focus": extra_focus,
    }


# ──────────────────────────────────────────────────────────────────────────
# Step 1: build search queries from profile + inputs, then search
# ──────────────────────────────────────────────────────────────────────────

def build_search_queries(profile: dict, inputs: dict) -> list[str]:
    titles = profile.get("target_titles", [])
    if inputs["extra_focus"]:
        titles = [inputs["extra_focus"]] + titles

    location_clause = ""
    if inputs["location_mode"] == "remote":
        location_clause = "remote"
    elif inputs["location_mode"] in ("onsite", "hybrid") and inputs["location_area"]:
        location_clause = inputs["location_area"]

    queries = []
    boards = ["site:linkedin.com/jobs", "site:indeed.com", "site:greenhouse.io", "site:lever.co"]

    # Pair top titles with job boards, round robin, capped at MAX_SEARCHES
    i = 0
    while len(queries) < MAX_SEARCHES and titles:
        title = titles[i % len(titles)]
        board = boards[i % len(boards)]
        q = f"{board} {title} {location_clause} job opening 2026".strip()
        if q not in queries:
            queries.append(q)
        i += 1
        if i > MAX_SEARCHES * 3:  # safety valve against infinite loop on tiny title lists
            break

    return queries[:MAX_SEARCHES]


def gather_listings(client: anthropic.Anthropic, queries: list[str]) -> list[dict]:
    all_listings = []

    for q in queries:
        prompt = (
            "Search the web for this query:\n\n"
            f'"{q}"\n\n'
            "After searching, respond with ONLY a JSON array of job listings "
            "found. Each item must have these exact keys:\n"
            '"company", "title", "url", "location", '
            '"base_pay" (string, the BASE salary figure or range only, '
            'exactly as stated in the listing — do NOT include bonus, '
            'equity, commission, or signing bonus amounts here, just the '
            'base. If no base salary figure is stated, use "" empty string), '
            '"extra_comp" (string, any bonus/equity/commission/relocation '
            'package details mentioned, in your own words, or "" empty '
            'string if none mentioned), '
            '"snippet" (1-3 sentences on responsibilities/requirements from '
            "the listing).\n\n"
            "Only include items that are actual job postings, not articles "
            "about jobs or career advice pages. If you find no real job "
            "postings, respond with an empty JSON array. Respond with ONLY "
            "the JSON array, no other text."
        )

        message = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )

        text_blocks = [b.text for b in message.content if b.type == "text"]
        raw = strip_fences("\n".join(text_blocks))

        if message.stop_reason == "tool_use":
            conversation = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": message.content},
            ]
            for _ in range(3):
                follow_up = client.messages.create(
                    model=MODEL,
                    max_tokens=4096,
                    tools=[{"type": "web_search_20250305", "name": "web_search"}],
                    messages=conversation,
                )
                if follow_up.stop_reason != "tool_use":
                    text_blocks = [b.text for b in follow_up.content if b.type == "text"]
                    raw = strip_fences("\n".join(text_blocks))
                    break
                conversation.append({"role": "assistant", "content": follow_up.content})

        try:
            items = json.loads(raw)
        except json.JSONDecodeError:
            continue

        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue
            listing = {
                "company": str(item.get("company", "")).strip(),
                "title": str(item.get("title", "")).strip(),
                "url": str(item.get("url", "")).strip(),
                "location": str(item.get("location", "")).strip(),
                "base_pay": str(item.get("base_pay", "")).strip(),
                "extra_comp": str(item.get("extra_comp", "")).strip(),
                "snippet": str(item.get("snippet", "")).strip(),
            }
            if listing["company"] and listing["title"]:
                all_listings.append(listing)

    return dedupe_listings(all_listings)


def dedupe_listings(listings: list[dict]) -> list[dict]:
    """Dedupe by (company, title, url) since multiple board/title queries
    commonly surface the same posting more than once."""
    seen = set()
    deduped = []
    for listing in listings:
        key = (listing["company"].lower(), listing["title"].lower(), listing["url"])
        if key not in seen:
            seen.add(key)
            deduped.append(listing)
    return deduped


# ──────────────────────────────────────────────────────────────────────────
# Step 2: score each listing against the profile
# ──────────────────────────────────────────────────────────────────────────

def format_profile_for_prompt(profile: dict) -> str:
    return json.dumps(profile, indent=2)


def format_listings_for_prompt(listings: list[dict]) -> str:
    blocks = []
    for i, l in enumerate(listings, start=1):
        blocks.append(
            f"Listing {i}\n"
            f"Company: {l['company']}\n"
            f"Title: {l['title']}\n"
            f"Location: {l['location']}\n"
            f"Base pay (as stated, empty if not disclosed): {l['base_pay']}\n"
            f"Extra comp mentioned (bonus/equity/relo, empty if none): {l['extra_comp']}\n"
            f"URL: {l['url']}\n"
            f"Details: {l['snippet']}"
        )
    return "\n\n---\n\n".join(blocks)


def score_listings(client: anthropic.Anthropic, profile: dict, listings: list[dict]) -> list[dict]:
    profile_text = format_profile_for_prompt(profile)
    listings_text = format_listings_for_prompt(listings)

    prompt = (
        "You are scoring job listings against a candidate profile for fit. "
        "Compare based on actual substance, not literal keyword overlap. "
        "Titles and required skills are phrased inconsistently across job "
        "postings and companies, so judge whether the candidate's real "
        "experience and competencies would make them a strong, qualified "
        "applicant for each role, even if exact wording differs.\n\n"
        f"CANDIDATE PROFILE:\n{profile_text}\n\n"
        f"JOB LISTINGS:\n\n{listings_text}\n\n"
        "For each listing, respond with ONLY a JSON array. Each item must "
        "have these exact keys:\n"
        '"company", "title", "location", "url", '
        '"base_pay" (string, copy the base pay value through exactly as '
        'given for this listing, or "" empty string if it was empty), '
        '"extra_comp" (string, copy the extra comp value through exactly '
        'as given, or "" empty string if it was empty), '
        '"match_pct" (integer 0-100, your honest assessment of fit), '
        '"reasoning" (1-2 sentences on why this score, citing specific '
        "overlap or gaps between the profile and the listing).\n\n"
        "Do not invent or estimate pay figures here, just pass through "
        "exactly what was given for base_pay and extra_comp. A later step "
        "handles pay estimation separately.\n\n"
        "Score honestly. Do not inflate scores. A generic PM title at a "
        "company in an unrelated field with no real skill overlap should "
        "score low. A role that closely matches the candidate's actual "
        "competencies and seniority should score high even if the title "
        "wording differs.\n\n"
        "On education requirements: treat these as a pass/fail credential "
        "check, not a fit factor. If a listing requires 'a bachelor's "
        "degree' or 'a bachelor's degree in a related field,' the "
        "candidate's degree satisfies that requirement regardless of "
        "subject matter, and this should not reduce the match score or be "
        "cited as a gap in the reasoning. Only treat a specific degree "
        "field as a real gap if the listing is unambiguous that one "
        "exact discipline is mandatory and non-negotiable (e.g. 'JD "
        "required,' 'must hold a degree in mechanical engineering, no "
        "exceptions'), which is rare. Years of experience and demonstrated "
        "competencies matter far more than degree subject matter and "
        "should drive the score. Respond with ONLY the JSON array, no "
        "other text."
    )

    message = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = strip_fences(message.content[0].text)

    try:
        scored = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(scored, list):
        return []

    results = []
    for item in scored:
        if not isinstance(item, dict):
            continue
        try:
            pct = int(item.get("match_pct", 0))
        except (ValueError, TypeError):
            pct = 0
        results.append(
            {
                "company": str(item.get("company", "")).strip(),
                "title": str(item.get("title", "")).strip(),
                "location": str(item.get("location", "")).strip(),
                "base_pay": str(item.get("base_pay", "")).strip(),
                "extra_comp": str(item.get("extra_comp", "")).strip(),
                "url": str(item.get("url", "")).strip(),
                "match_pct": max(0, min(100, pct)),
                "reasoning": str(item.get("reasoning", "")).strip(),
            }
        )
    return results


# ──────────────────────────────────────────────────────────────────────────
# Step 3: filter, rank, report
# ──────────────────────────────────────────────────────────────────────────

def filter_and_rank(scored: list[dict]) -> list[dict]:
    kept = [s for s in scored if s["match_pct"] >= MIN_MATCH_PCT]
    kept.sort(key=lambda s: s["match_pct"], reverse=True)
    return kept


def enrich_missing_pay(client: anthropic.Anthropic, results: list[dict]) -> list[dict]:
    """For kept results with no disclosed base pay, do a single batched
    lookup call estimating typical base salary range. Only runs on
    listings that already cleared the match threshold, since estimating
    pay for everything found would be wasteful.
    """
    needs_estimate = [r for r in results if not r["base_pay"]]
    if not needs_estimate:
        for r in results:
            r["pay_is_estimate"] = False
        return results

    roles_text = "\n".join(
        f"{i+1}. {r['title']} at {r['company']}, location: {r['location'] or 'not specified'}"
        for i, r in enumerate(needs_estimate)
    )

    prompt = (
        "For each numbered role below, research and estimate a realistic "
        "typical BASE salary range (not total comp) for that title, at "
        "that company if you have specific knowledge of it, in that "
        "location, at a senior level. Use general market knowledge for "
        "similar roles if you don't have company-specific data.\n\n"
        f"{roles_text}\n\n"
        "Respond with ONLY a JSON array with exactly one object per "
        "numbered role above, in the same order, same count, no skipping "
        "and no merging roles together even if two look similar. Each "
        'object needs keys "role_number" (integer, matching the number '
        'above), "estimated_range" (string, e.g. "$140,000 - $175,000"), '
        'and "basis" (string, 3-8 words on what the estimate is based on, '
        'e.g. "similar roles at comparable defense contractors" or '
        '"company-specific data found"). If you genuinely cannot form a '
        "reasonable estimate for a role, still include its object with "
        "empty strings for estimated_range and basis. Respond with ONLY "
        "the JSON array, no other text."
    )

    estimates = []
    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )

        text_blocks = [b.text for b in message.content if b.type == "text"]
        raw = strip_fences("\n".join(text_blocks))

        if message.stop_reason == "tool_use":
            conversation = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": message.content},
            ]
            for _ in range(3):
                follow_up = client.messages.create(
                    model=MODEL,
                    max_tokens=4096,
                    tools=[{"type": "web_search_20250305", "name": "web_search"}],
                    messages=conversation,
                )
                if follow_up.stop_reason != "tool_use":
                    text_blocks = [b.text for b in follow_up.content if b.type == "text"]
                    raw = strip_fences("\n".join(text_blocks))
                    break
                conversation.append({"role": "assistant", "content": follow_up.content})

        parsed = json.loads(raw)
        if isinstance(parsed, list):
            estimates = parsed
    except Exception as e:
        print(f"  Pay estimation call failed, leaving pay as not found: {e}")
        estimates = []

    for r in results:
        r["pay_is_estimate"] = False

    # Match by role_number rather than position, since a batch of 9+ items
    # is prone to the model skipping, merging, or reordering entries.
    estimates_by_number = {}
    for est in estimates:
        if not isinstance(est, dict):
            continue
        try:
            num = int(est.get("role_number", -1))
        except (ValueError, TypeError):
            continue
        estimates_by_number[num] = est

    matched_count = 0
    for i, r in enumerate(needs_estimate, start=1):
        est = estimates_by_number.get(i)
        if est is None:
            continue
        est_range = str(est.get("estimated_range", "")).strip()
        basis = str(est.get("basis", "")).strip()
        if est_range:
            r["base_pay"] = est_range
            r["pay_is_estimate"] = True
            r["pay_basis"] = basis
            matched_count += 1

    if estimates and matched_count == 0:
        print("  Pay estimates came back but didn't match expected format, leaving pay as not found.")

    return results


def format_pay_for_display(r: dict) -> str:
    if not r["base_pay"]:
        return "Not found"
    if r.get("pay_is_estimate"):
        basis = r.get("pay_basis", "")
        suffix = f" (est., {basis})" if basis else " (estimated)"
        return f"{r['base_pay']}{suffix}"
    return r["base_pay"]


def build_report(inputs: dict, total_found: int, results: list[dict], now: datetime) -> str:
    lines = []
    lines.append(f"# Job Match Report")
    lines.append("")
    lines.append(f"**Date:** {now:%B %d, %Y %I:%M %p}")
    lines.append(
        f"**Filters:** pay min {inputs['pay_min'] or 'none'} | "
        f"location {inputs['location_mode']}"
        + (f" ({inputs['location_area']})" if inputs["location_area"] else "")
    )
    lines.append("")
    lines.append(
        "Sourced via web search only. No direct ATS scraping and no "
        "guaranteed real-time open/closed verification per company. "
        "Best effort on freshness, confirm a listing is still live before "
        "applying. Pay marked \"(estimated)\" is a market estimate, not a "
        "figure stated in the listing, confirm before relying on it."
    )
    lines.append("")
    lines.append(
        f"**Found {total_found} listings. {len(results)} scored "
        f"{MIN_MATCH_PCT}% or higher.**"
    )
    lines.append("")

    if not results:
        lines.append(
            "No listings cleared the match threshold this run. Try "
            "broadening location, lowering pay floor, or widening "
            "target titles."
        )
        return "\n".join(lines)

    lines.append("| Rank | Match | Company | Title | Pay | Location | Listing Link | Extra Details |")
    lines.append("|------|-------|---------|-------|-----|----------|--------------|----------------|")
    for i, r in enumerate(results, start=1):
        pay_display = format_pay_for_display(r)
        extra = r["extra_comp"] or "—"
        lines.append(
            f"| {i} | {r['match_pct']}% | {r['company']} | {r['title']} | "
            f"{pay_display} | {r['location'] or '—'} | [Apply]({r['url']}) | {extra} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")

    for i, r in enumerate(results, start=1):
        pay_display = format_pay_for_display(r)
        lines.append(f"## {i}. {r['title']} — {r['company']}")
        lines.append(f"**Match:** {r['match_pct']}%")
        lines.append(f"**Pay:** {pay_display}")
        if r["extra_comp"]:
            lines.append(f"**Extra comp:** {r['extra_comp']}")
        lines.append(f"**Location:** {r['location'] or 'not specified'}")
        lines.append(f"**Apply:** {r['url']}")
        lines.append(f"**Why:** {r['reasoning']}")
        lines.append("")

    return "\n".join(lines)


def save_report(report: str, now: datetime) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{now:%Y-%m-%d_%H%M}_job-matches.md"
    filepath = REPORTS_DIR / filename
    filepath.write_text(report, encoding="utf-8")
    return filepath


def print_report(report: str) -> None:
    width = 78
    print()
    print("=" * width)
    print(" JOB MATCH REPORT".center(width))
    print("=" * width)
    print()
    print(textwrap.indent(report.strip(), prefix="  "))
    print()
    print("=" * width)


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────

def run() -> None:
    profile = load_profile()
    client = get_client()
    inputs = collect_search_inputs()

    queries = build_search_queries(profile, inputs)
    print(f"\nRunning {len(queries)} job board searches...")
    listings = gather_listings(client, queries)
    print(f"  Found {len(listings)} unique listings.")

    if not listings:
        print("\nNo listings found. Try different search terms or location.")
        return

    print(f"\nScoring {len(listings)} listings against your profile...")
    scored = score_listings(client, profile, listings)

    results = filter_and_rank(scored)
    print(f"  {len(results)} cleared the {MIN_MATCH_PCT}% threshold.")

    missing_pay_count = sum(1 for r in results if not r["base_pay"])
    if missing_pay_count:
        print(f"\nEstimating base pay for {missing_pay_count} listings with no disclosed salary...")
        results = enrich_missing_pay(client, results)

    now = datetime.now()
    report = build_report(inputs, len(listings), results, now)
    filepath = save_report(report, now)

    print_report(report)
    print(f"\nSaved to {filepath}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
