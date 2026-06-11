# Figured

> I guide — you discover.

Figured is a Socratic AI tutor for all learners. It never gives direct answers — it guides you to find them yourself through questions, hints, and encouragement. Built for K-12 students, college learners, and adults.

## How it works

Figured uses the Socratic method: instead of answering your question, it asks you one back. Each question nudges you one step closer to the answer. You do the thinking — Figured makes sure you get there.

## Project structure

```
figured/
├── tutor/
│   ├── tutor.py          # Terminal chat interface
│   └── system_prompt.md  # Socratic tutor instructions
├── app/
│   └── app.py            # Streamlit web UI
├── requirements.txt
├── .env                  # API keys (not committed)
└── README.md
```

## Getting started

**1. Clone the repo**
```bash
git clone https://github.com/yourusername/figured.git
cd figured
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Add your API key**

Create a `.env` file in the root:
```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

**4. Run the terminal version**
```bash
cd tutor
python tutor.py
```

**5. Run the web app**
```bash
cd app
streamlit run app.py
```

## Tech stack

- [Anthropic Claude](https://anthropic.com) — AI backbone
- [Streamlit](https://streamlit.io) — web interface
- Python 3.10+

## License

MIT
