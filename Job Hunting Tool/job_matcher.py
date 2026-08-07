"""
job_matcher.py
--------------
Searches job boards for open roles and scores each listing against your
distilled profile using LLM comparison — not keyword matching. Filters to
your configured match threshold, estimates pay where it isn't disclosed,
and writes a ranked markdown report.

Run distill_profile.py first to generate profile.json.

Supports any OpenAI-compatible API provider. Note: built-in web search
(used for job sourcing and pay estimation) requires the Anthropic provider
with a model that supports the web_search tool. With other providers the
tool falls back to prompt-only mode, which relies on the model's training
data rather than live search — results will be less fresh.

See README.md for full setup and configuration details.
"""

import json
import os
import re
import textwrap
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Provider config ────────────────────────────────────────────────────────
PROVIDER        = os.getenv("JM_PROVIDER", "anthropic").lower()
MODEL           = os.getenv("JM_MODEL", "claude-sonnet-4-6")
API_KEY         = os.getenv("JM_API_KEY", "")
API_BASE_URL    = os.getenv("JM_API_BASE_URL", "")
WEB_SEARCH_TOOL = os.getenv("JM_WEB_SEARCH_TOOL", "web_search_20250305")

# ── Matcher config ─────────────────────────────────────────────────────────
MIN_MATCH_PCT   = int(os.getenv("JM_MIN_MATCH_PCT", "60"))
MAX_SEARCHES    = int(os.getenv("JM_MAX_SEARCHES", "8"))

# ── File paths ─────────────────────────────────────────────────────────────
REPORTS_DIR  = Path(__file__).parent / "reports"
PROFILE_PATH = Path(__file__).parent / "profile.json"


# ── Client factory ─────────────────────────────────────────────────────────

def get_client():
    if not API_KEY:
        raise SystemExit(
            "JM_API_KEY not set. Add it to your .env file. See README.md."
        )

    if PROVIDER == "anthropic":
        try:
            import anthropic
        except ImportError:
            raise SystemExit("anthropic package not installed. Run: pip install anthropic")
        return anthropic.Anthropic(api_key=API_KEY), "anthropic"

    try:
        from openai import OpenAI
    except ImportError:
        raise SystemExit("openai package not installed. Run: pip install openai")

    kwargs = {"api_key": API_KEY}
    if API_BASE_URL:
        kwargs["base_url"] = API_BASE_URL
    elif PROVIDER == "openrouter":
        kwargs["base_url"] = "https://openrouter.ai/api/v1"
    elif PROVIDER == "ollama":
        kwargs["base_url"] = "http://localhost:11434/v1"

    return OpenAI(**kwargs), "openai"


# ── LLM call helpers ───────────────────────────────────────────────────────

def call_llm(client, client_type: str, prompt: str) -> str:
    """Plain text completion, no tool use."""
    if client_type == "anthropic":
        import anthropic as _anthropic
        message = client.messages.create(
            model=MODEL,
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def call_llm_with_search(client, client_type: str, prompt: str) -> str:
    """Text completion with Anthropic web_search tool loop.
    Falls back to plain call for non-Anthropic providers with a notice."""
    if client_type != "anthropic":
        return call_llm(client, client_type, prompt)

    import anthropic as _anthropic

    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        tools=[{"type": WEB_SEARCH_TOOL, "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )

    text_blocks = [b.text for b in message.content if b.type == "text"]
    raw = "\n".join(text_blocks)

    if message.stop_reason == "tool_use":
        conversation = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": message.content},
        ]
        for _ in range(3):
            follow_up = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                tools=[{"type": WEB_SEARCH_TOOL, "name": "web_search"}],
                messages=conversation,
            )
            if follow_up.stop_reason != "tool_use":
                text_blocks = [b.text for b in follow_up.content if b.type == "text"]
                raw = "\n".join(text_blocks)
                break
            conversation.append({"role": "assistant", "content": follow_up.content})

    return raw


# ── Utilities ──────────────────────────────────────────────────────────────

def strip_fences(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"```$", "", raw, flags=re.MULTILINE)
    return raw.strip()


def load_profile() -> dict:
    if not PROFILE_PATH.exists():
        raise SystemExit(
            "profile.json not found. Run distill_profile.py first to build it "
            "from your resume. See README.md."
        )
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


# ── Step 1: collect search inputs ─────────────────────────────────────────

def collect_search_inputs() -> dict:
    print("\nJob Matcher\n")

    pay_min = input(
        "Minimum target base pay (e.g. 80000), or blank to skip > "
    ).strip()
    location_mode = (
        input("Location preference [onsite/hybrid/remote/any] > ").strip().lower()
        or "any"
    )
    location_area = ""
    if location_mode in ("onsite", "hybrid"):
        location_area = input("City or region for onsite/hybrid roles > ").strip()
    extra_focus = input(
        "Specific titles, industries, or keywords to prioritize? "
        "(optional, blank to use full profile) > "
    ).strip()

    return {
        "pay_min": pay_min,
        "location_mode": location_mode,
        "location_area": location_area,
        "extra_focus": extra_focus,
    }


# ── Step 2: build queries and gather listings ──────────────────────────────

def build_search_queries(profile: dict, inputs: dict) -> list[str]:
    titles = list(profile.get("target_titles", []))
    if inputs["extra_focus"]:
        titles = [inputs["extra_focus"]] + titles

    location_clause = ""
    if inputs["location_mode"] == "remote":
        location_clause = "remote"
    elif inputs["location_mode"] in ("onsite", "hybrid") and inputs["location_area"]:
        location_clause = inputs["location_area"]

    year = datetime.now().year
    boards = [
        "site:linkedin.com/jobs",
        "site:indeed.com",
        "site:greenhouse.io",
        "site:lever.co",
    ]

    queries = []
    i = 0
    while len(queries) < MAX_SEARCHES and titles:
        title = titles[i % len(titles)]
        board = boards[i % len(boards)]
        q = f"{board} {title} {location_clause} job opening {year}".strip()
        if q not in queries:
            queries.append(q)
        i += 1
        if i > MAX_SEARCHES * 3:
            break

    return queries[:MAX_SEARCHES]


def gather_listings(client, client_type: str, queries: list[str]) -> list[dict]:
    all_listings = []

    for q in queries:
        prompt = (
            "Search the web for this query:\n\n"
            f'"{q}"\n\n'
            "After searching, respond with ONLY a JSON array of job listings. "
            "Each item must have these exact keys:\n"
            '"company", "title", "url", "location",\n'
            '"base_pay" (string — base salary figure or range ONLY, exactly '
            "as stated. Do NOT include bonus, equity, or signing bonus here. "
            'Empty string if not stated),\n'
            '"extra_comp" (string — any bonus, equity, commission, or '
            "relocation details mentioned, or empty string),\n"
            '"snippet" (1-3 sentences on role responsibilities and requirements).\n\n'
            "Include only actual job postings, not articles or advice pages. "
            "Empty array if none found. Respond with ONLY the JSON array."
        )

        raw = strip_fences(call_llm_with_search(client, client_type, prompt))

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
                "company":    str(item.get("company", "")).strip(),
                "title":      str(item.get("title", "")).strip(),
                "url":        str(item.get("url", "")).strip(),
                "location":   str(item.get("location", "")).strip(),
                "base_pay":   str(item.get("base_pay", "")).strip(),
                "extra_comp": str(item.get("extra_comp", "")).strip(),
                "snippet":    str(item.get("snippet", "")).strip(),
            }
            if listing["company"] and listing["title"]:
                all_listings.append(listing)

    return _dedupe(all_listings)


def _dedupe(listings: list[dict]) -> list[dict]:
    """Dedupe by (company, title, url). Multiple queries commonly surface
    the same posting — same company+title at a different URL is kept since
    it may be a distinct opening."""
    seen, out = set(), []
    for l in listings:
        key = (l["company"].lower(), l["title"].lower(), l["url"])
        if key not in seen:
            seen.add(key)
            out.append(l)
    return out


# ── Step 3: score listings against profile ─────────────────────────────────

def _format_profile(profile: dict) -> str:
    return json.dumps(profile, indent=2)


def _format_listings(listings: list[dict]) -> str:
    blocks = []
    for i, l in enumerate(listings, start=1):
        blocks.append(
            f"Listing {i}\n"
            f"Company: {l['company']}\n"
            f"Title: {l['title']}\n"
            f"Location: {l['location']}\n"
            f"Base pay (empty if not disclosed): {l['base_pay']}\n"
            f"Extra comp (bonus/equity/relo, empty if none): {l['extra_comp']}\n"
            f"URL: {l['url']}\n"
            f"Details: {l['snippet']}"
        )
    return "\n\n---\n\n".join(blocks)


def score_listings(client, client_type: str, profile: dict, listings: list[dict]) -> list[dict]:
    prompt = (
        "You are scoring job listings against a candidate profile for fit. "
        "Judge based on actual substance — not literal keyword overlap. "
        "Titles and skills are phrased inconsistently across companies; "
        "assess whether the candidate's real experience and competencies "
        "would make them a strong, qualified applicant for each role.\n\n"
        f"CANDIDATE PROFILE:\n{_format_profile(profile)}\n\n"
        f"JOB LISTINGS:\n\n{_format_listings(listings)}\n\n"
        "Return ONLY a JSON array. Each item must have:\n"
        '"company", "title", "location", "url",\n'
        '"base_pay" (copy through exactly as given, or empty string),\n'
        '"extra_comp" (copy through exactly as given, or empty string),\n'
        '"match_pct" (integer 0-100, your honest fit assessment),\n'
        '"reasoning" (1-2 sentences on why, citing specific overlaps or gaps).\n\n'
        "Do not invent or estimate pay figures here — copy them through unchanged.\n\n"
        "Score honestly. Do not inflate. A generic title with no real skill overlap "
        "should score low. Strong competency match should score high even if the "
        "title wording differs.\n\n"
        "On education: treat degree requirements as a pass/fail checkbox. "
        "Do not penalise for degree subject matter unless a specific discipline "
        "is explicitly non-negotiable in the listing (e.g. 'JD required'). "
        "Years of experience and demonstrated competencies drive the score.\n\n"
        "On seniority: if a listing explicitly targets junior/entry level "
        "(e.g. '1-2 years required', 'new grad') and the candidate is "
        "significantly more senior, score it down accordingly.\n\n"
        "Respond with ONLY the JSON array, no other text."
    )

    raw = strip_fences(call_llm(client, client_type, prompt))

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
        results.append({
            "company":    str(item.get("company", "")).strip(),
            "title":      str(item.get("title", "")).strip(),
            "location":   str(item.get("location", "")).strip(),
            "url":        str(item.get("url", "")).strip(),
            "base_pay":   str(item.get("base_pay", "")).strip(),
            "extra_comp": str(item.get("extra_comp", "")).strip(),
            "match_pct":  max(0, min(100, pct)),
            "reasoning":  str(item.get("reasoning", "")).strip(),
        })
    return results


# ── Step 4: filter and rank ────────────────────────────────────────────────

def filter_and_rank(scored: list[dict]) -> list[dict]:
    kept = [s for s in scored if s["match_pct"] >= MIN_MATCH_PCT]
    kept.sort(key=lambda s: s["match_pct"], reverse=True)
    return kept


# ── Step 5: pay enrichment for listings with no disclosed base ─────────────

def enrich_missing_pay(client, client_type: str, results: list[dict]) -> list[dict]:
    """Single batched lookup for kept listings with no disclosed base pay.
    Uses web search when available (Anthropic), falls back to model knowledge
    for other providers. Always labeled estimated vs. stated in the report."""
    needs_estimate = [r for r in results if not r["base_pay"]]

    for r in results:
        r["pay_is_estimate"] = False

    if not needs_estimate:
        return results

    roles_text = "\n".join(
        f"{i}. {r['title']} at {r['company']}, "
        f"location: {r['location'] or 'not specified'}"
        for i, r in enumerate(needs_estimate, start=1)
    )

    prompt = (
        "For each numbered role below, research and estimate a realistic "
        "typical BASE salary range (not total comp) for that title at that "
        "company in that location, at the appropriate seniority level. Use "
        "company-specific data where you have it, otherwise use market data "
        "for similar roles.\n\n"
        f"{roles_text}\n\n"
        "Respond with ONLY a JSON array with exactly one object per role, "
        "in the same order, no skipping. Each object needs:\n"
        '"role_number" (integer matching the number above),\n'
        '"estimated_range" (e.g. "$90,000 - $120,000"),\n'
        '"basis" (3-8 words on what the estimate is based on).\n'
        "If you cannot form a reasonable estimate for a role, still include "
        "its object with empty strings for estimated_range and basis.\n"
        "Respond with ONLY the JSON array, no other text."
    )

    estimates = []
    try:
        raw = strip_fences(call_llm_with_search(client, client_type, prompt))
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            estimates = parsed
    except Exception as e:
        print(f"  Pay estimation call failed: {e}")
        return results

    estimates_by_number = {}
    for est in estimates:
        if not isinstance(est, dict):
            continue
        try:
            num = int(est.get("role_number", -1))
        except (ValueError, TypeError):
            continue
        estimates_by_number[num] = est

    matched = 0
    for i, r in enumerate(needs_estimate, start=1):
        est = estimates_by_number.get(i)
        if not est:
            continue
        est_range = str(est.get("estimated_range", "")).strip()
        basis = str(est.get("basis", "")).strip()
        if est_range:
            r["base_pay"] = est_range
            r["pay_is_estimate"] = True
            r["pay_basis"] = basis
            matched += 1

    if estimates and matched == 0:
        print("  Pay estimates returned but could not be matched — leaving pay as not found.")

    return results


# ── Step 6: report ─────────────────────────────────────────────────────────

def _pay_display(r: dict) -> str:
    if not r["base_pay"]:
        return "Not found"
    if r.get("pay_is_estimate"):
        basis = r.get("pay_basis", "")
        suffix = f" (est. — {basis})" if basis else " (estimated)"
        return f"{r['base_pay']}{suffix}"
    return r["base_pay"]


def build_report(inputs: dict, total_found: int, results: list[dict], now: datetime) -> str:
    lines = []
    lines.append("# Job Match Report")
    lines.append("")
    lines.append(f"**Date:** {now:%B %d, %Y %I:%M %p}")

    loc = inputs["location_mode"]
    if inputs["location_area"]:
        loc += f" ({inputs['location_area']})"
    pay = f"${int(inputs['pay_min']):,}" if inputs["pay_min"].isdigit() else inputs["pay_min"] or "none"
    lines.append(f"**Filters:** min pay {pay} | location {loc}")
    lines.append("")
    lines.append(
        "> Sourced via web search only. No direct ATS scraping; listing "
        "freshness is best-effort — confirm a role is still open before "
        "applying. Pay marked **(estimated)** is a market estimate, not a "
        "figure stated in the listing."
    )
    lines.append("")
    lines.append(
        f"**{total_found} listings reviewed. "
        f"{len(results)} scored {MIN_MATCH_PCT}% or higher.**"
    )
    lines.append("")

    if not results:
        lines.append(
            "No listings cleared the match threshold. Try broadening your "
            "location, lowering the pay floor, or adding more target titles "
            "to profile.json."
        )
        return "\n".join(lines)

    # Summary table
    lines.append("| # | Match | Company | Title | Pay | Location | Apply | Extra Comp |")
    lines.append("|---|-------|---------|-------|-----|----------|-------|------------|")
    for i, r in enumerate(results, start=1):
        lines.append(
            f"| {i} | {r['match_pct']}% | {r['company']} | {r['title']} | "
            f"{_pay_display(r)} | {r['location'] or '—'} | "
            f"[Link]({r['url']}) | {r['extra_comp'] or '—'} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")

    # Detail sections
    for i, r in enumerate(results, start=1):
        lines.append(f"## {i}. {r['title']} — {r['company']}")
        lines.append(f"**Match:** {r['match_pct']}%  ")
        lines.append(f"**Pay:** {_pay_display(r)}  ")
        if r["extra_comp"]:
            lines.append(f"**Extra comp:** {r['extra_comp']}  ")
        lines.append(f"**Location:** {r['location'] or 'not specified'}  ")
        lines.append(f"**Apply:** {r['url']}  ")
        lines.append(f"**Why:** {r['reasoning']}")
        lines.append("")

    return "\n".join(lines)


def save_report(report: str, now: datetime) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = REPORTS_DIR / f"{now:%Y-%m-%d_%H%M}_job-matches.md"
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


# ── Main ──────────────────────────────────────────────────────────────────

def run() -> None:
    profile = load_profile()
    client, client_type = get_client()

    if client_type != "anthropic":
        print(
            f"\n[Note] Provider '{PROVIDER}' does not support live web search. "
            "Job sourcing will rely on the model's training data. Results may "
            "be less fresh than with the Anthropic provider."
        )

    inputs = collect_search_inputs()

    queries = build_search_queries(profile, inputs)
    print(f"\nRunning {len(queries)} searches...")
    listings = gather_listings(client, client_type, queries)
    print(f"  Found {len(listings)} unique listings.")

    if not listings:
        print("\nNo listings found. Try broadening your search inputs.")
        return

    print(f"\nScoring {len(listings)} listings against your profile...")
    scored = score_listings(client, client_type, profile, listings)

    results = filter_and_rank(scored)
    print(f"  {len(results)} cleared the {MIN_MATCH_PCT}% threshold.")

    missing_pay = sum(1 for r in results if not r["base_pay"])
    if missing_pay:
        print(f"\nEstimating pay for {missing_pay} listings with no disclosed salary...")
        results = enrich_missing_pay(client, client_type, results)

    now = datetime.now()
    report = build_report(inputs, len(listings), results, now)
    filepath = save_report(report, now)

    print_report(report)
    print(f"\nSaved to {filepath}")


if __name__ == "__main__":
    run()
