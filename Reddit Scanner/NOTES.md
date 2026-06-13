# Reddit Scanner — Setup Notes

A simple walkthrough of everything we did to set up this project. Follow these steps in order if you ever need to start over.

---

## What this project is (so far)

A Python project that will talk to **Claude** (Anthropic) and eventually **Reddit**. Right now we have:

- A place to store secret API keys (`.env`)
- Protection so those secrets never get uploaded to GitHub (`.gitignore`)
- A small test script that proves Claude is working (`test_claude.py`)

---

## Step 1 — Create the `.env` file

**What:** A file named `.env` in the project root (same folder as your Python files).

**Contents:**

```
ANTHROPIC_API_KEY=
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
```

**Why:** API keys and passwords should never be hard-coded inside your Python files. The `.env` file holds them locally on your machine. Each line is `NAME=value`.

**What each key is for:**

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Lets your code talk to Claude via Anthropic's API |
| `REDDIT_CLIENT_ID` | Reddit app ID (for when we add Reddit features) |
| `REDDIT_CLIENT_SECRET` | Reddit app secret (for when we add Reddit features) |

---

## Step 2 — Create the `.gitignore` file

**What:** A file named `.gitignore` in the project root.

**Why:** Git tracks every file you add. If you accidentally commit `.env`, your API keys go public on GitHub. The `.gitignore` tells Git to **ignore** certain files forever.

**The most important line:**

```
.env
```

That single line means `.env` will never be committed, even if you run `git add .`.

We also added standard Python ignores (`__pycache__/`, virtualenv folders, build artifacts, etc.) so junk files stay out of the repo too.

---

## Step 3 — Fill in your API keys

**What:** Open `.env` and paste your real values after the `=` signs:

```
ANTHROPIC_API_KEY=sk-ant-api03-...your-key-here...
REDDIT_CLIENT_ID=your-reddit-client-id
REDDIT_CLIENT_SECRET=your-reddit-client-secret
```

**Where to get them:**

- **Anthropic key:** [console.anthropic.com](https://console.anthropic.com/) → API Keys → Create Key
- **Reddit credentials:** [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) → create an app → copy Client ID and Secret

**Important:** Only edit `.env` on your machine. Never paste real keys into chat, email, or code files. If a key leaks, revoke it and create a new one.

---

## Step 4 — Install Python packages

**What:** Install the two libraries the test script needs.

Open a terminal in the project folder and run:

```powershell
pip install anthropic python-dotenv
```

If `pip` is not found, try:

```powershell
py -m pip install anthropic python-dotenv
```

**What each package does:**

| Package | Purpose |
|---|---|
| `anthropic` | Official Python SDK for calling Claude |
| `python-dotenv` | Reads your `.env` file and loads the values into environment variables |

You only need to install these once per machine (or once per virtual environment if you use one).

---

## Step 5 — Create `test_claude.py`

**What:** A Python script that sends a test message to Claude and prints the reply.

**What the script does, line by line:**

1. **`load_dotenv()`** — Reads `.env` and makes `ANTHROPIC_API_KEY` available to Python.
2. **`anthropic.Anthropic(...)`** — Creates a client using your API key.
3. **`client.messages.create(...)`** — Sends a short "hello" message to Claude.
4. **`print(message.content[0].text)`** — Prints Claude's reply to the terminal.

**Run it:**

```powershell
python test_claude.py
```

Or, if `python` is not found:

```powershell
py test_claude.py
```

**Expected result:** Claude replies with a short hello message. If you see that, your API key and setup are working.

---

## Step 6 — Set the Claude model

**What:** We set the model to `claude-sonnet-4-5` in `test_claude.py`:

```python
model="claude-sonnet-4-5",
```

**Why:** The model name tells Anthropic which version of Claude to use. Sonnet is a good balance of speed and quality for development and testing.

If Anthropic releases newer models, you can change this string to switch versions.

---

## Quick checklist (start from scratch)

1. Create project folder
2. Create `.env` with the three placeholder variables
3. Create `.gitignore` with `.env` listed first
4. Paste your real API keys into `.env`
5. Run `pip install anthropic python-dotenv`
6. Create `test_claude.py`
7. Run `python test_claude.py` and confirm you get a reply from Claude

---

## What's still to do

- [ ] Add Reddit Client ID and Secret to `.env`
- [ ] Build the actual Reddit scanner logic
- [ ] (Optional) Add a `requirements.txt` so `pip install -r requirements.txt` installs everything in one command
- [ ] (Optional) Add a `.env.example` file (same keys, empty values) so collaborators know what variables they need without seeing your real keys

---

## Files in this project

| File | Purpose |
|---|---|
| `.env` | Your secret API keys (never commit this) |
| `.gitignore` | Tells Git what to ignore |
| `test_claude.py` | Test script — confirms Claude API works |
| `NOTES.md` | This file |
| `reddit_scanner.txt` | Original project notes/idea file |
