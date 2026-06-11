#!/usr/bin/env python3
"""
Figured — Socratic AI Tutor (Terminal Interface)
"""

import os
import sys
from pathlib import Path
import anthropic
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.md"
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

COLORS = {
    "tutor": "\033[94m",   # blue
    "user": "\033[92m",    # green
    "system": "\033[93m",  # yellow
    "error": "\033[91m",   # red
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def c(color: str, text: str) -> str:
    """Wrap text in a terminal color code."""
    return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"


def load_system_prompt() -> str:
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    print(c("system", f"⚠  system_prompt.md not found at {SYSTEM_PROMPT_PATH}. Using fallback."))
    return (
        "You are Figured, a patient Socratic guide for all learners. "
        "Never give direct answers. Guide learners to discover answers themselves "
        "through questions and hints. Adapt to the learner's level."
    )


def print_banner():
    print()
    print(c("bold", "━" * 58))
    print(c("bold", "   💡  Figured"))
    print(c("dim",  "   I guide — you discover. No free answers here! 😄"))
    print(c("bold", "━" * 58))
    print(c("dim",  "   Commands:  'quit' or 'exit' to end  |  'clear' to reset"))
    print(c("bold", "━" * 58))
    print()


def print_tutor(text: str):
    print(f"\n{c('tutor', c('bold', '  Figured │'))} ", end="")
    words = text.split()
    line = ""
    for word in words:
        if len(line) + len(word) + 1 > 70:
            print(line)
            print("           ", end="")
            line = word
        else:
            line = word if not line else f"{line} {word}"
    if line:
        print(line)
    print()


def get_user_input() -> str:
    try:
        raw = input(c("user", c("bold", "    You │ ")) + " ").strip()
        return raw
    except (EOFError, KeyboardInterrupt):
        return "quit"


# ── Core loop ─────────────────────────────────────────────────────────────────

def chat(client: anthropic.Anthropic, system: str):
    history: list[dict] = []

    print_tutor(
        "Hi there! I'm Figured. I won't give you answers directly — "
        "but I'll help you think through anything step by step. "
        "What are you working on today?"
    )

    while True:
        user_input = get_user_input()

        if not user_input:
            continue

        if user_input.lower() in {"quit", "exit"}:
            print(c("system", "\n  👋  Great session! Keep thinking — see you next time.\n"))
            break

        if user_input.lower() == "clear":
            history.clear()
            os.system("clear" if os.name == "posix" else "cls")
            print_banner()
            print_tutor("Fresh start! What would you like to work on?")
            continue

        history.append({"role": "user", "content": user_input})

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=history,
            )

            reply = response.content[0].text
            history.append({"role": "assistant", "content": reply})
            print_tutor(reply)

        except anthropic.AuthenticationError:
            print(c("error", "\n  ✗  Invalid API key. Check your .env file.\n"))
            sys.exit(1)
        except anthropic.RateLimitError:
            print(c("error", "\n  ✗  Rate limit hit. Wait a moment and try again.\n"))
        except anthropic.APIError as e:
            print(c("error", f"\n  ✗  API error: {e}\n"))


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(c("error", "\n  ✗  ANTHROPIC_API_KEY not found. Add it to your .env file.\n"))
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    system = load_system_prompt()

    print_banner()
    chat(client, system)


if __name__ == "__main__":
    main()