"""
Distill Profile
----------------
One-time (or run-when-the-data-bank-changes) step. Reads the full master
data bank and condenses it into a compact profile.json that the job matcher
reuses on every run, so we're not feeding 1400 lines of accomplishments
into every single job-listing scoring call.

Run this manually whenever NATHAN_BIENVENU_MASTER_DATA_BANK.txt changes.
The matcher will refuse to run without a profile.json present.
"""

import json
import os
import re
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-6"
DATA_BANK_PATH = Path(__file__).parent / "NATHAN_BIENVENU_MASTER_DATA_BANK.txt"
PROFILE_PATH = Path(__file__).parent / "profile.json"

DISTILL_PROMPT = """You are condensing a long career data bank into a compact
structured profile for use in automated job matching. The profile will be
compared against job listings by an LLM, so it needs to carry real signal,
not just a list of buzzwords.

Read the full data bank below and produce ONLY a JSON object with these
exact keys:

"target_titles": array of 8-15 job titles this person is realistically
  qualified for right now, spanning the range from close-to-current-role
  to adjacent stretch roles. Use real industry title language, not internal
  military/defense phrasing.

"seniority": one of "entry", "mid", "senior", "lead", "principal", "director"
  — best honest assessment based on years of experience and scope of
  responsibility shown in the data bank.

"years_experience": integer, total years of relevant professional experience.

"core_competencies": array of 10-20 short phrases, the strongest and most
  differentiated skills/competencies, written in commercial/industry
  language (apply the sector translation table where it exists in the
  source). Prioritize breadth across domains over depth in one.

"technical_skills": array of specific tools, languages, platforms,
  frameworks, certifications by name (e.g. "Python", "AWS", "SysML",
  "Part 107 sUAS").

"domain_experience": array of 5-10 industries/domains this person has
  real depth in (e.g. "defense/aerospace", "digital engineering",
  "AI product development").

"standout_accomplishments": array of 8-15 of the single strongest,
  most quantified accomplishments across the whole career, written as
  one-line achievement statements in commercial language. Pull the
  biggest numbers and clearest scope. Do not invent anything not
  present in the source.

"education_credentials": array of strings, degrees and certifications.

"clearance": string describing security clearance status if present in
  the source, otherwise empty string.

"differentiators": array of 3-6 short phrases describing what makes this
  candidate unusual or hard to replace compared to a typical candidate
  for similar roles (e.g. cross-domain translation ability, rare
  combination of operational + technical + AI product experience).

Respond with ONLY the JSON object. No markdown fences, no preamble, no
commentary.

DATA BANK:

{data_bank}
"""


def get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit(
            "ANTHROPIC_API_KEY not found. Add it to your .env file and try again."
        )
    return anthropic.Anthropic(api_key=api_key)


def strip_fences(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw)
    raw = re.sub(r"```$", "", raw)
    return raw.strip()


def distill(client: anthropic.Anthropic, data_bank_text: str) -> dict:
    prompt = DISTILL_PROMPT.format(data_bank=data_bank_text)

    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = strip_fences(message.content[0].text)

    try:
        profile = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(
            f"Claude did not return valid JSON. Raw output:\n\n{raw}\n\nError: {e}"
        )

    return profile


def main() -> None:
    if not DATA_BANK_PATH.exists():
        raise SystemExit(
            f"Data bank not found at {DATA_BANK_PATH}. "
            "Place NATHAN_BIENVENU_MASTER_DATA_BANK.txt next to this script."
        )

    if PROFILE_PATH.exists():
        answer = input(
            f"{PROFILE_PATH.name} already exists. Overwrite with a fresh "
            "distillation? [y/N] > "
        ).strip().lower()
        if answer != "y":
            print("Left existing profile.json untouched.")
            return

    print("Reading data bank...")
    data_bank_text = DATA_BANK_PATH.read_text(encoding="utf-8")

    print("Distilling into compact profile (one Claude call)...")
    client = get_client()
    profile = distill(client, data_bank_text)

    PROFILE_PATH.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    print(f"\nSaved profile to {PROFILE_PATH}")
    print(f"\nTarget titles: {', '.join(profile.get('target_titles', []))}")
    print(f"Seniority: {profile.get('seniority', '?')}")
    print(f"Years experience: {profile.get('years_experience', '?')}")


if __name__ == "__main__":
    main()
