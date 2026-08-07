# Job Matcher

An AI-powered CLI tool that searches job boards for open roles and scores each listing against your resume using LLM comparison — not keyword matching. Filters to your configured match threshold, estimates pay where it isn't disclosed, and writes a ranked markdown report you can act on.

Works with Anthropic, OpenAI, OpenRouter, Ollama, or any OpenAI-compatible provider.

---

## How it works

1. **Distill** — `distill_profile.py` reads your resume once and condenses it into a compact `profile.json`. This runs once (or whenever your resume changes significantly) and saves an API call on every subsequent search.
2. **Search** — `job_matcher.py` builds targeted queries from your profile and searches LinkedIn, Indeed, Greenhouse, and Lever for open roles matching your titles, location, and pay preferences.
3. **Score** — Each listing is scored 0–100% against your profile based on actual competency and experience overlap, not keyword frequency. Listings below your configured threshold are dropped.
4. **Enrich** — For listings that don't disclose a base salary, a single batched call estimates a typical market range, clearly labeled as estimated vs. stated.
5. **Report** — A ranked markdown report is saved to `reports/`, with company, title, pay, location, a direct apply link, and a one-line explanation of the match score for each result.

> **Note on web search:** Live job sourcing uses Anthropic's built-in web search tool, available when `JM_PROVIDER=anthropic`. Other providers fall back to the model's training data — results will be less fresh but the rest of the pipeline works identically.

---

## Requirements

- Python 3.10+
- An API key for your chosen provider
- Your resume as a plain text file (`.txt` recommended; convert PDF or DOCX to text first)

---

## Installation

```bash
git clone https://github.com/SenseiNate/business-ventures.git
cd "business-ventures/Job Hunting Tool"
pip install -r requirements.txt
```

If you're using a non-Anthropic provider, also install the OpenAI package:

```bash
pip install openai
```

---

## Setup

### 1. Configure your environment

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

```env
JM_PROVIDER=anthropic
JM_API_KEY=your_api_key_here
JM_MODEL=claude-sonnet-4-6
JM_RESUME_FILE=resume.txt
JM_MIN_MATCH_PCT=60
JM_MAX_SEARCHES=8
```

See [Provider configuration](#provider-configuration) below for provider-specific settings.

### 2. Add your resume

Place your resume in this directory as a plain text file. The filename should match `JM_RESUME_FILE` in your `.env` (default: `resume.txt`).

Plain text works best. If you only have a PDF or DOCX, paste the content into a `.txt` file — formatting doesn't matter, content does.

### 3. Distill your profile

```bash
python3 distill_profile.py
```

This makes one API call and writes `profile.json`. Open it and review the output — check that `target_titles`, `seniority`, and `years_experience` look right. Edit any fields directly if they need adjustment.

Re-run this step any time your resume changes significantly.

### 4. Run the matcher

```bash
python3 job_matcher.py
```

You'll be prompted for:

- **Minimum target pay** — base salary floor (e.g. `80000`), or blank to skip
- **Location preference** — `onsite`, `hybrid`, `remote`, or `any`
- **City/region** — if onsite or hybrid, the area to search in
- **Optional focus** — specific titles or keywords to prioritize, or blank to use your full profile

Results are printed to the terminal and saved to `reports/` as a timestamped markdown file.

---

## Provider configuration

Set `JM_PROVIDER` and `JM_API_KEY` in `.env`. The `JM_API_BASE_URL` field is only needed for non-Anthropic providers.

| Provider | `JM_PROVIDER` | `JM_API_BASE_URL` | Live web search |
|---|---|---|---|
| Anthropic | `anthropic` | _(leave blank)_ | ✅ Yes |
| OpenAI | `openai` | _(leave blank)_ | ❌ No |
| OpenRouter | `openrouter` | _(leave blank, set automatically)_ | ❌ No |
| Ollama (local) | `ollama` | _(leave blank, set automatically)_ | ❌ No |
| Custom / self-hosted | any string | your endpoint URL | ❌ No |

**Example — OpenAI:**
```env
JM_PROVIDER=openai
JM_API_KEY=sk-...
JM_MODEL=gpt-4o
```

**Example — OpenRouter:**
```env
JM_PROVIDER=openrouter
JM_API_KEY=sk-or-...
JM_MODEL=anthropic/claude-sonnet-4-6
```

**Example — Ollama (local):**
```env
JM_PROVIDER=ollama
JM_API_KEY=ollama
JM_MODEL=llama3
```

---

## Configuration reference

All settings live in `.env`. Defaults are shown.

| Variable | Default | Description |
|---|---|---|
| `JM_PROVIDER` | `anthropic` | LLM provider |
| `JM_API_KEY` | _(required)_ | API key for your provider |
| `JM_MODEL` | `claude-sonnet-4-6` | Model name |
| `JM_API_BASE_URL` | _(blank)_ | Custom API endpoint (OpenRouter/Ollama/custom) |
| `JM_RESUME_FILE` | `resume.txt` | Resume filename in this directory |
| `JM_MIN_MATCH_PCT` | `60` | Minimum match score to appear in the report |
| `JM_MAX_SEARCHES` | `8` | Number of job board searches per run |

---

## Customizing your profile

After running `distill_profile.py`, open `profile.json` and adjust any fields:

- **`target_titles`** — add or remove job titles to broaden or narrow what gets searched
- **`seniority`** — corrects how the matcher judges role level fit
- **`years_experience`** — used for seniority mismatch detection
- **`core_competencies`** — the skills that get weighted in scoring
- **`differentiators`** — what makes you unusual; weighted in scoring reasoning

You can also hand-write `profile.json` from scratch if you prefer not to use the distillation step.

---

## Understanding the report

Each result shows:

- **Match %** — LLM-assessed fit based on competency and experience overlap, not keywords
- **Pay** — base salary as stated in the listing, or a market estimate labeled **(estimated)** if not disclosed
- **Extra comp** — bonus, equity, commission, or relocation details if mentioned, kept separate from base pay
- **Apply link** — direct link to the listing
- **Why** — one or two sentences explaining the match score, including any gaps

Pay figures marked **(estimated)** are market-rate lookups, not stated figures. Confirm compensation before relying on them.

---

## Limitations

- **Sourcing is web search only.** No direct ATS API access. Listings may be stale — always confirm a role is still open before applying.
- **Live search requires the Anthropic provider.** Other providers use training data for sourcing, which may not reflect current openings.
- **Pay estimation is imperfect.** When the same company appears multiple times, estimates may converge on a single range rather than accounting for role-level differences. Treat as a starting point, not a fact.
- **Match scores are LLM judgments.** They're calibrated for substance over keywords but aren't deterministic. Run the tool a few times to build intuition for what your scores mean in practice.

---

## Files

| File | Purpose |
|---|---|
| `distill_profile.py` | One-time profile distillation from your resume |
| `job_matcher.py` | Main search, score, and report tool |
| `.env.example` | Template for your `.env` configuration |
| `.gitignore` | Keeps credentials, resume, and reports out of git |
| `requirements.txt` | Python dependencies |
| `resume.txt` | _(you create this)_ Your resume in plain text |
| `profile.json` | _(generated)_ Distilled candidate profile |
| `reports/` | _(generated)_ Timestamped markdown reports |

---

## License

MIT
