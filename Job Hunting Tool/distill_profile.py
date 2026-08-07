"""
distill_profile.py
------------------
One-time setup step. Reads your resume or career data file and condenses
it into a compact profile.json that job_matcher.py reuses on every run.

Re-run any time your resume or data file changes significantly.
The matcher will not run without profile.json present.

Supports any OpenAI-compatible API provider (Anthropic, OpenAI, OpenRouter,
Ollama, etc.). Configure your provider in .env — see README.md for details.
"""

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Provider config ────────────────────────────────────────────────────────
# Set these in your .env file. See README.md for all supported providers.
PROVIDER        = os.getenv("JM_PROVIDER", "anthropic").lower()
MODEL           = os.getenv("JM_MODEL", "claude-sonnet-4-6")
API_KEY         = os.getenv("JM_API_KEY", "")
API_BASE_URL    = os.getenv("JM_API_BASE_URL", "")  # only needed for OpenRouter/Ollama/custom

# ── File paths ─────────────────────────────────────────────────────────────
RESUME_PATH  = Path(__file__).parent / os.getenv("JM_RESUME_FILE", "resume.txt")
PROFILE_PATH = Path(__file__).parent / "profile.json"

DISTILL_PROMPT = """You are condensing a resume or career document into a compact
structured profile for use in automated job matching. The profile will be
compared against job listings by an LLM, so it needs to carry real signal,
not just a list of buzzwords.

Read the full document below and produce ONLY a JSON object with these exact keys:

"target_titles": array of 8-15 job titles this person is realistically
  qualified for right now, spanning close-to-current-role to adjacent stretch
  roles. Use real industry title language.

"seniority": one of "entry", "mid", "senior", "lead", "principal", "director"
  — honest assessment based on years of experience and scope of responsibility
  shown in the document.

"years_experience": integer, total years of relevant professional experience.

"core_competencies": array of 10-20 short phrases, the strongest and most
  differentiated skills and competencies. Write in clear commercial language.

"technical_skills": array of specific tools, languages, platforms, frameworks,
  and certifications by name (e.g. "Python", "AWS", "Figma", "PMP").

"domain_experience": array of 5-10 industries or domains this person has real
  depth in (e.g. "fintech", "healthcare IT", "B2B SaaS", "defense").

"standout_accomplishments": array of 8-15 of the strongest, most quantified
  accomplishments across the whole career, written as one-line achievement
  statements. Pull the biggest numbers and clearest scope. Do not invent
  anything not present in the source document.

"education_credentials": array of strings, degrees and certifications.

"clearance": string describing security clearance if present, otherwise
  empty string.

"differentiators": array of 3-6 short phrases describing what makes this
  candidate unusual or hard to replace compared to a typical candidate for
  similar roles.

Respond with ONLY the JSON object. No markdown fences, no preamble, no
commentary.

RESUME / CAREER DOCUMENT:

{resume}
"""


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

    # OpenAI-compatible: openai, openrouter, ollama, or any other provider
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


# ── LLM call (handles both Anthropic and OpenAI-compatible) ───────────────

def call_llm(client, client_type: str, prompt: str) -> str:
    if client_type == "anthropic":
        message = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    # OpenAI-compatible
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


# ── Helpers ────────────────────────────────────────────────────────────────

def strip_fences(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"```$", "", raw, flags=re.MULTILINE)
    return raw.strip()


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> None:
    if not RESUME_PATH.exists():
        raise SystemExit(
            f"Resume file not found at: {RESUME_PATH}\n"
            f"Set JM_RESUME_FILE in .env to your resume filename, or place "
            f"resume.txt in this directory. See README.md for details."
        )

    if PROFILE_PATH.exists():
        answer = input(
            f"{PROFILE_PATH.name} already exists. Overwrite with a fresh "
            "distillation? [y/N] > "
        ).strip().lower()
        if answer != "y":
            print("Left existing profile.json untouched.")
            return

    print(f"Reading resume from {RESUME_PATH.name}...")
    resume_text = RESUME_PATH.read_text(encoding="utf-8")

    print(f"Distilling profile via {PROVIDER} / {MODEL}...")
    client, client_type = get_client()
    raw = call_llm(client, client_type, DISTILL_PROMPT.format(resume=resume_text))
    raw = strip_fences(raw)

    try:
        profile = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(
            f"Model did not return valid JSON.\n\nRaw output:\n{raw}\n\nError: {e}"
        )

    PROFILE_PATH.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    print(f"\nProfile saved to {PROFILE_PATH.name}")
    print(f"Target titles : {', '.join(profile.get('target_titles', []))}")
    print(f"Seniority     : {profile.get('seniority', '?')}")
    print(f"Years exp.    : {profile.get('years_experience', '?')}")
    print(
        "\nReview profile.json before running job_matcher.py. "
        "Edit any fields that don't look right."
    )


if __name__ == "__main__":
    main()
