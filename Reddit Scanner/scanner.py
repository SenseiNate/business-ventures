import os
import textwrap
import time
from datetime import datetime
from pathlib import Path

import anthropic
import requests
from dotenv import load_dotenv

load_dotenv()

REPORTS_DIR = Path("reports")

SUBREDDITS = [
    # Parents
    "Parenting",
    "Mommit",
    "daddit",
    "ParentingADHD",
    "homeschool",
    # Teachers by level
    "Teachers",
    "ElementaryTeachers",
    "HighSchoolTeachers",
    "SpecialEducation",
    # Learning disabilities
    "ADHD",
    "Dyslexia",
    "autism",
    "learningdisabilities",
    "giftedkids",
    # Homework and studying
    "HomeworkHelp",
    "GetStudying",
    "learnmath",
    # Subjects
    "math",
    "science",
    "writing",
    "history",
    # Electives
    "learnprogramming",
    "languagelearning",
    # General education
    "education",
    "EdTech",
]


def fetch_posts(subreddit: str) -> list[dict[str, str]]:
    url = f"https://api.pullpush.io/reddit/search/submission/?subreddit={subreddit}&size=10&sort=desc"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    data = response.json()
    posts = []
    for item in data["data"]:
        posts.append(
            {
                "title": item.get("title", "").strip(),
                "selftext": item.get("selftext", "").strip(),
            }
        )
    return posts


def format_posts_for_prompt(posts: list[dict[str, str]]) -> str:
    blocks = []
    for i, post in enumerate(posts, start=1):
        body = post["selftext"] or "(no body text)"
        blocks.append(
            f"Post {i}\nTitle: {post['title']}\nBody: {body}"
        )
    return "\n\n---\n\n".join(blocks)


def analyze_with_claude(subreddit: str, posts_text: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": (
                    f"You are analyzing Reddit posts from r/{subreddit} to find product opportunities for Figured, a Socratic AI tutor for all learners.\n\n"
                    "Review the posts below and identify the top 5 pain points across all of them.\n"
                    "For each pain point, provide:\n"
                    "1. Pain point name (short label)\n"
                    "2. Description (1-2 sentences)\n"
                    "3. Emotional intensity (1-10)\n"
                    "4. Failed solutions mentioned (list any, or say 'None mentioned')\n"
                    "5. Potential product angle for Figured (1-2 sentences)\n\n"
                    "Base your analysis only on what appears in the posts. Do not invent details.\n"
                    "Format the output clearly with numbered sections and line breaks.\n\n"
                    f"Posts:\n\n{posts_text}"
                ),
            }
        ],
    )

    return message.content[0].text


def save_report(subreddit: str, analysis: str, now: datetime) -> Path:
    subreddit_dir = REPORTS_DIR / subreddit
    subreddit_dir.mkdir(parents=True, exist_ok=True)
    filepath = subreddit_dir / f"{now:%Y-%m-%d_%H-%M-%S}.md"
    content = f"# r/{subreddit} Pain Point Analysis\n**Date:** {now:%B %d, %Y %I:%M %p}\n\n{analysis}\n"
    filepath.write_text(content, encoding="utf-8")
    return filepath


def print_progress(subreddit: str, post_count: int, analysis: str) -> None:
    width = 72
    print()
    print("=" * width)
    print(f" r/{subreddit} Pain Point Scanner".center(width))
    print("=" * width)
    print(f"\nAnalyzed {post_count} posts\n")
    print("-" * width)
    print()
    print(textwrap.indent(analysis.strip(), prefix="  "))
    print()
    print("-" * width)


def main() -> None:
    now = datetime.now()
    total = len(SUBREDDITS)
    completed = []
    failed = []

    print(f"\nStarting scan of {total} subreddits...")
    print(f"Reports will be saved to: {REPORTS_DIR}/\n")

    for i, subreddit in enumerate(SUBREDDITS, start=1):
        print(f"[{i}/{total}] Scanning r/{subreddit}...")

        try:
            posts = fetch_posts(subreddit)

            if not posts:
                print(f"  No posts found, skipping.")
                failed.append(subreddit)
                continue

            posts_text = format_posts_for_prompt(posts)
            analysis = analyze_with_claude(subreddit, posts_text)
            filepath = save_report(subreddit, analysis, now)
            print_progress(subreddit, len(posts), analysis)
            print(f"  Saved to {filepath}")
            completed.append(subreddit)

        except Exception as e:
            print(f"  Failed: {e}")
            failed.append(subreddit)

        time.sleep(2)

    print(f"\n{'=' * 72}")
    print(f"SCAN COMPLETE")
    print(f"{'=' * 72}")
    print(f"Completed: {len(completed)}/{total} subreddits")
    print(f"Reports saved to: {REPORTS_DIR}/")
    if failed:
        print(f"Failed: {', '.join(failed)}")
    print()


if __name__ == "__main__":
    main()