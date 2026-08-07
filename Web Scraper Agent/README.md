# Web Scraper Agent

A structured research agent that takes a plain-language goal, searches the web for it across two source types (institutional and social/forum), scores every result against what you actually asked, and produces a ranked markdown report — not a pile of links.

---

## How it works

1. **You answer four questions** about what you're looking for, why, what you'll do with the information, and which sources matter most.
2. **The agent runs two search passes** — one targeting articles, research, and institutional sources, one targeting Reddit, forums, and social media.
3. **Every result is scored 1–5** against your stated goal. Only perfect 5/5 matches survive.
4. **Up to 5 results per source type** make the final report (up to 10 total), ranked best to worst.
5. **A markdown report is saved** to a timestamped folder in `reports/`.

This is tournament-style filtering: many candidates are found, only the best survive.

---

## Supported providers

### LLM providers (for analysis and ranking)
| Provider | Value | Default model |
|----------|-------|---------------|
| Anthropic (Claude) | `anthropic` | `claude-haiku-4-5-20251001` |
| OpenAI (GPT) | `openai` | `gpt-4o-mini` |
| Google (Gemini) | `google` | `gemini-1.5-flash` |

### Search providers (for web search)
| Provider | Value | Notes |
|----------|-------|-------|
| Anthropic built-in | `anthropic` | Requires `LLM_PROVIDER=anthropic`. No extra key. |
| Brave Search | `brave` | Works with any LLM. Free tier: ~$5/month in credits. |
| SerpAPI | `serpapi` | Works with any LLM. Free tier: 100 searches/month. |

You can mix and match: for example, use OpenAI for LLM analysis with Brave Search for retrieval.

---

## Requirements

- Python 3.10 or higher
- `python-dotenv` (always required)
- The SDK for your chosen LLM provider (install only what you need):

```bash
# Anthropic
pip install anthropic python-dotenv

# OpenAI
pip install openai python-dotenv

# Google Gemini
pip install google-generativeai python-dotenv
```

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-username/web-scraper-agent.git
cd web-scraper-agent
```

### 2. Install dependencies

Install `python-dotenv` plus the SDK for your chosen LLM provider:

```bash
pip install python-dotenv anthropic        # if using Anthropic
pip install python-dotenv openai           # if using OpenAI
pip install python-dotenv google-generativeai  # if using Google
```

### 3. Create your `.env` file

Copy the example and fill in your values:

```bash
cp .env.example .env
```

Then open `.env` and set your provider and API key(s). See the [Configuration](#configuration) section below for all available options.

### 4. Run the agent

```bash
python web_scraper_agent.py
```

---

## Configuration

All configuration is done via a `.env` file in the project root. Copy `.env.example` to `.env` and edit it — never commit your `.env` file.

### Full `.env.example`

```env
# ── LLM Provider ─────────────────────────────────────────────────
# Which LLM provider to use for analysis and ranking.
# Options: anthropic | openai | google
LLM_PROVIDER=anthropic

# The model to use. Leave blank to use the provider's recommended default.
# Anthropic defaults: claude-haiku-4-5-20251001
# OpenAI defaults:    gpt-4o-mini
# Google defaults:    gemini-1.5-flash
LLM_MODEL=

# ── LLM API Keys ─────────────────────────────────────────────────
# Only the key matching your LLM_PROVIDER is required.
ANTHROPIC_API_KEY=sk-ant-your-key-here
OPENAI_API_KEY=sk-your-key-here
GOOGLE_API_KEY=your-key-here

# ── Search Provider ───────────────────────────────────────────────
# Which provider to use for web search.
# Options: anthropic | brave | serpapi
#
# anthropic — Uses Claude's built-in web search tool.
#             Requires LLM_PROVIDER=anthropic. No extra key needed.
#
# brave     — Uses the Brave Search API (api.search.brave.com).
#             Works with any LLM provider. Requires BRAVE_API_KEY.
#
# serpapi   — Uses SerpAPI to query Google Search results.
#             Works with any LLM provider. Requires SERPAPI_KEY.
SEARCH_PROVIDER=anthropic

# ── Search API Keys ───────────────────────────────────────────────
# Only required if SEARCH_PROVIDER is brave or serpapi.
BRAVE_API_KEY=your-brave-api-key-here
SERPAPI_KEY=your-serpapi-key-here
```

### Common configurations

**Anthropic only (simplest setup)**
```env
LLM_PROVIDER=anthropic
SEARCH_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

**OpenAI + Brave Search**
```env
LLM_PROVIDER=openai
SEARCH_PROVIDER=brave
OPENAI_API_KEY=sk-your-key-here
BRAVE_API_KEY=your-brave-api-key-here
```

**Google Gemini + SerpAPI**
```env
LLM_PROVIDER=google
SEARCH_PROVIDER=serpapi
GOOGLE_API_KEY=your-key-here
SERPAPI_KEY=your-serpapi-key-here
```

---

## Getting API keys

| Service | Where to get a key |
|---------|-------------------|
| Anthropic | [console.anthropic.com](https://console.anthropic.com) |
| OpenAI | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| Google Gemini | [aistudio.google.com](https://aistudio.google.com) |
| Brave Search | [api.search.brave.com](https://api.search.brave.com) |
| SerpAPI | [serpapi.com](https://serpapi.com) |

---

## Example session

```
Web Scraper Agent
Answer the questions below, or type 'quit' at the first one to exit.

1. What are you looking for? > Pain points solo founders face when pricing their SaaS product
2. Why are you looking for it? > I'm deciding whether to build a pricing strategy tool for founders
3. What are you planning on doing with the information? > Validate the pain point and shape product copy
4. Which sources matter most? > mix of articles and social media

Searching articles, news, and institutional sources...
  Got 14 results.

Searching Reddit, X, Facebook, and forums...
  Got 11 results.

Scoring 14 institutional candidates (5/5 only)...
Scoring 11 social/forum candidates (5/5 only)...

════════════════════════════════════════════════════════════════════════
                         RESEARCH REPORT
════════════════════════════════════════════════════════════════════════

  25 candidates reviewed; 2 bucket(s) produced perfect-5 matches.

  ## Institutional & Articles
  ...

  ## Social Media & Forums
  ...

Saved to reports/2026-06-17_pain-points-solo-founders-face-when-pricing/report.md
```

---

## Output format

Reports are saved to `reports/{date}_{slugified-goal}/report.md`.

Each surviving result includes:

- **Title** and **URL**
- **Score:** 5/5
- **What it says:** 2–3 sentence summary
- **Why it's relevant:** direct tie to your stated goal

Results are split into two sections: `Institutional & Articles` and `Social Media & Forums`, each capped at 5 entries.

---

## Notes on social media coverage

- **Reddit** is well-indexed and reliably surfaced.
- **X (Twitter)** and **Facebook** content is often not publicly crawlable and may be absent or thin in results. This is a platform limitation, not a bug.
- If social results are thin for your topic, try rephrasing question 1 to include words like "forum", "discussion", or "Reddit thread."

---

## Project structure

```
web_scraper_agent.py   # main script — entry point and full agent logic
.env.example           # configuration template (copy to .env)
.gitignore             # excludes .env, reports/, and cache files
README.md              # this file
reports/               # auto-created on first run, gitignored
```

---

## License

MIT — use it however you want.
