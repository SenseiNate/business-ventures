# Job Hunting Tool

Forked from Web Scraper Agent. Takes a personal data bank (accomplishments,
skills, experience, education, credentials) and an LLM-distilled profile
built from it, then searches job boards and company career pages for open
roles, scores each one against the profile using LLM comparison (not
keyword matching), and writes a ranked report.

Phase 1 of a two-phase pipeline. Phase 2 (auto-tailored application
materials per matched role) is a separate tool, not built yet.

## Files

- `distill_profile.py` — one-time (or run-when-the-data-bank-changes) step.
  Condenses the full master data bank into `profile.json`, a compact
  structured profile the matcher reuses on every run.
- `job_matcher.py` — the matcher itself. Searches LinkedIn, Indeed,
  Greenhouse, and Lever for roles matching your target titles, location,
  and pay floor. Scores each listing 0-100% against your profile, keeps
  only 60%+ matches, fills in market-estimated pay where the listing
  doesn't disclose a base salary, and writes a ranked markdown report.
- `profile.json` — the distilled candidate profile used for matching.
- `NATHAN_BIENVENU_MASTER_DATA_BANK.txt` — the full source data bank
  `distill_profile.py` was built from.
- `requirements.txt` — `anthropic`, `python-dotenv`.

## Setup

1. `pip install -r requirements.txt`
2. Add `ANTHROPIC_API_KEY` to a `.env` file in this folder (never committed,
   see `.gitignore`).
3. Run `python3 distill_profile.py` once to build `profile.json` from the
   data bank. Re-run only when the data bank changes.
4. Run `python3 job_matcher.py` for each search. Answers a few prompts
   (pay floor, location mode, optional title focus), then writes a
   timestamped report to `reports/` (not committed).

## How matching works

Each listing is scored 0-100% against the candidate profile based on
actual substance overlap, not literal keyword matching, since titles and
required skills are phrased inconsistently across companies. Education
requirements are treated as a pass/fail credential check, not a fit
factor: years of experience and demonstrated competencies drive the
score, not degree subject matter, unless a listing is explicitly
non-negotiable about one exact discipline.

## Pay handling

Listings that disclose a base salary keep that figure. Listings that
don't get a single batched market-rate estimate after scoring (not
per-listing, to keep cost down), always labeled "(estimated, basis)" in
the report so estimated and stated pay are never visually confused.
Bonus, equity, and relocation details are tracked separately from base
pay under "Extra Details."

## Known limitations

Sourcing is web_search only. No direct ATS scraping, no guaranteed
real-time open/closed verification per company. Best effort on listing
freshness, confirm a posting is still live before applying. Pay
estimates are a market starting point for judgment, not a fact; if
several estimates from the same company come back identical, treat that
as a signal to sanity-check rather than trust outright.
