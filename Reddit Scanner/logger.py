import os
from datetime import date
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

LOGS_DIR = Path("logs")


def get_brain_dump() -> str:
    print("What did you do today?")
    print("Type or paste your brain dump, then press Enter on an empty line to finish.\n")

    lines = []
    while True:
        line = input()
        if not line.strip():
            break
        lines.append(line)

    brain_dump = "\n".join(lines).strip()
    if not brain_dump:
        raise ValueError("No input provided.")

    return brain_dump


def format_with_claude(brain_dump: str, today: date) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Clean up and format the following daily brain dump into a clear "
                    f"markdown log entry for {today:%B %d, %Y}. Use headings, bullet "
                    f"points, and complete sentences where helpful. Keep all important "
                    f"details from the original — do not invent anything new.\n\n"
                    f"Brain dump:\n{brain_dump}"
                ),
            }
        ],
    )

    return message.content[0].text


def save_log(content: str, today: date) -> Path:
    LOGS_DIR.mkdir(exist_ok=True)
    filepath = LOGS_DIR / f"{today:%Y-%m-%d}.md"
    filepath.write_text(content, encoding="utf-8")
    return filepath


def main() -> None:
    today = date.today()
    brain_dump = get_brain_dump()
    print("\nSending to Claude...\n")
    formatted = format_with_claude(brain_dump, today)
    filepath = save_log(formatted, today)
    print(f"Saved to {filepath}")


if __name__ == "__main__":
    main()