import os
import random
from pathlib import Path

import anthropic
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024
SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "tutor" / "system_prompt.md"

TAGLINES = [
    "the answer is in you.",
    "no spoilers here.",
    "think out loud.",
    "wrong answers welcome.",
    "stuck is just the start.",
    "you've got this.",
    "let's figure it out.",
    "confusion is the beginning.",
    "every expert was once confused.",
    "the struggle is the lesson.",
    "you already know more than you think.",
    "thinking is the work.",
    "get comfortable being curious.",
    "the best learning feels like discovery.",
    "an investment in knowledge pays the best interest.",
    "the beautiful thing about learning is nobody can take it away from you.",
    "education is not the filling of a pail, but the lighting of a fire.",
    "curiosity is the engine of achievement.",
    "the expert in anything was once a beginner.",
    "learning never exhausts the mind.",
    "wonder is the beginning of wisdom.",
    "a question is the beginning of understanding.",
    "knowledge is power.",
    "you don't have to be great to start, but you have to start to be great.",
]

MICRO_REACTIONS = [
    "you're so close 🔥",
    "that's the right instinct ⚡",
    "now we're cooking 🧠",
    "yes, keep going 🎯",
    "you're thinking like a pro 💡",
    "that click you just felt? that's it 🙌",
]

BREAKTHROUGH_KEYWORDS = [
    "i got it", "i understand", "oh i see", "that makes sense",
    "i figured", "now i get", "oh that's", "makes sense now",
    "i think i understand", "got it", "i see now", "ohh", "ohhh",
    "aha", "oh!", "wait i", "so it's", "so the answer"
]

TYPING_MESSAGES = [
    "thinking... 🧠",
    "cooking up a hint... 💡",
    "no answers, just clues... 🔍",
    "almost there... 🎯",
]

LEVELS = {
    "K-12": {
        "emoji": "🎒",
        "label": "K-12",
        "desc": "Elementary through high school",
        "subjects": ["Math", "Science", "English", "History", "Biology", "Chemistry", "Physics", "Geography", "Art", "Music"],
    },
    "College": {
        "emoji": "🎓",
        "label": "College",
        "desc": "Associates, Bachelor's, Master's, PhD",
        "subjects": ["Calculus", "Statistics", "Economics", "Psychology", "Philosophy", "Computer Science", "Engineering", "Literature", "Political Science", "Sociology"],
    },
    "Professional": {
        "emoji": "💼",
        "label": "Professional",
        "desc": "Real world skills and career growth",
        "subjects": ["Leadership", "Finance", "Marketing", "Data Analysis", "Project Management", "Communication", "Negotiation", "Strategy", "Product Thinking", "Critical Thinking"],
    },
}


def load_system_prompt() -> str:
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "You are Figured, a patient Socratic guide for all learners. "
        "Never give direct answers. Guide learners to discover answers themselves "
        "through questions and hints. Adapt to the learner's level."
    )


def build_session_prompt(base: str, level: str, subject: str) -> str:
    level_context = {
        "K-12": "The learner is a K-12 student. Use age-appropriate language, simple analogies, and lots of encouragement.",
        "College": "The learner is a college student. Match their degree-level depth. Challenge their reasoning and push for deeper understanding.",
        "Professional": "The learner is a working professional. Connect concepts to real-world applications and career relevance.",
    }
    context = level_context.get(level, "")
    return f"{base}\n\n## Session Context\nLevel: {level}\nSubject: {subject}\n{context}\n\nStart by orienting the learner to what you'll work on together, then begin guiding them through the subject using the Socratic method."


def is_breakthrough(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in BREAKTHROUGH_KEYWORDS)


def is_progress(text: str) -> bool:
    progress_words = ["maybe", "i think", "could it be", "is it", "so if", "because", "since", "would"]
    t = text.lower()
    return any(w in t for w in progress_words)


st.set_page_config(
    page_title="Figured",
    page_icon="💡",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;1,300;1,400&display=swap');

html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"], .main {
    background-color: #ffffff !important; color: #1a1a2e !important;
}
[data-testid="stAppViewContainer"] { background-color: #ffffff !important; }
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
#MainMenu, footer, header { visibility: hidden; }
.main > div:first-child { padding-top: 0 !important; }
[data-testid="stAppViewBlockContainer"] { padding-top: 0 !important; }
section[data-testid="stMain"] > div { padding-top: 0 !important; }
.block-container { padding: 0 !important; max-width: 820px !important; margin-top: 0 !important; }

/* Onboarding wrap */
.onboard-wrap {
    display: flex; flex-direction: column; align-items: center;
    padding: 3rem 2rem 4rem 2rem; text-align: center;
}
.onboard-step {
    font-size: 0.78rem; font-weight: 600; color: #9ca3af;
    letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 0.6rem;
}
.onboard-q {
    font-family: 'Syne', sans-serif; font-size: 2rem; font-weight: 700;
    color: #1a1a2e; margin-bottom: 0.4rem; line-height: 1.2;
}
.onboard-sub { font-size: 0.95rem; color: #6b7280; margin-bottom: 2.5rem; font-weight: 300; }

/* Level cards — rendered as HTML, not Streamlit buttons */
.level-grid { display: flex; gap: 1.25rem; justify-content: center; margin-bottom: 2rem; width: 100%; }
.level-card {
    flex: 1; max-width: 240px;
    background: #ffffff; border: 2px solid #e5e7eb; border-radius: 1.25rem;
    padding: 2rem 1.25rem; text-align: center; cursor: pointer;
    transition: all 0.18s ease; min-height: 200px;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
}
.level-card:hover { border-color: #6366f1; background: #f5f3ff; box-shadow: 0 4px 20px rgba(99,102,241,0.12); transform: translateY(-2px); }
.level-card .lc-emoji { font-size: 3rem; margin-bottom: 0.75rem; line-height: 1; }
.level-card .lc-name { font-family: 'Syne', sans-serif; font-weight: 700; font-size: 1.1rem; color: #1a1a2e; margin-bottom: 0.3rem; }
.level-card .lc-desc { font-size: 0.8rem; color: #9ca3af; line-height: 1.4; }

/* Subject chips */
.chip-grid { display: flex; flex-wrap: wrap; gap: 0.6rem; justify-content: center; max-width: 620px; margin-bottom: 1.75rem; }
.chip {
    background: #f9fafb; border: 2px solid #e5e7eb; border-radius: 2rem;
    padding: 0.5rem 1.1rem; font-size: 0.88rem; font-weight: 500; color: #374151;
    cursor: pointer; transition: all 0.15s ease; white-space: nowrap;
}
.chip:hover { border-color: #6366f1; color: #6366f1; background: #f5f3ff; }
.chip.selected { border-color: #6366f1; background: #6366f1; color: white; }

/* Wordmark */
.figured-wordmark-wrap {
    font-family: 'Syne', sans-serif; font-weight: 800; letter-spacing: 0.18em;
    color: #1a1a2e; display: inline-block; line-height: 1.4; margin-bottom: 0.5rem;
}
.figured-i-wrap {
    display: inline-block;
    position: relative;
    color: #6366f1;
    animation: ipulse 2.5s ease-in-out infinite;
}
@keyframes ipulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

/* Preview card */
.preview-card {
    background: #f5f3ff; border: 2px solid #e0e7ff; border-radius: 1.25rem;
    padding: 1.75rem; max-width: 560px; margin: 0 auto 2rem auto; text-align: left;
}
.preview-label { font-size: 0.75rem; font-weight: 600; color: #6366f1; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 0.5rem; }
.preview-title { font-family: 'Syne', sans-serif; font-size: 1.1rem; font-weight: 700; color: #1a1a2e; margin-bottom: 0.75rem; }
.preview-body { font-size: 0.92rem; color: #4b5563; line-height: 1.7; }
.preview-rule { margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #e0e7ff; font-size: 0.82rem; color: #9ca3af; font-style: italic; }

/* Action buttons */
.action-row { display: flex; gap: 1rem; justify-content: center; margin-top: 0.5rem; }
.btn-primary {
    background: #6366f1; color: white; border: none; border-radius: 2rem;
    padding: 0.75rem 2rem; font-family: 'DM Sans', sans-serif; font-weight: 500;
    font-size: 1rem; cursor: pointer; transition: background 0.2s ease, transform 0.1s ease;
}
.btn-primary:hover { background: #4f46e5; transform: translateY(-1px); }
.btn-ghost {
    background: transparent; color: #6b7280; border: 2px solid #e5e7eb; border-radius: 2rem;
    padding: 0.75rem 1.5rem; font-family: 'DM Sans', sans-serif; font-weight: 400;
    font-size: 0.95rem; cursor: pointer; transition: all 0.15s ease;
}
.btn-ghost:hover { border-color: #6366f1; color: #6366f1; }

/* Chat area */
.chat-area { padding: 1.5rem 1.5rem 140px 1.5rem; }
.figured-header { text-align: center; padding: 2rem 0 1.25rem 0; }
.figured-tagline { font-family: 'DM Sans', sans-serif; font-size: 0.9rem; font-weight: 300; color: #9ca3af; letter-spacing: 0.04em; margin-top: 0.5rem; font-style: italic; }
.session-badge { display: inline-block; background: #f5f3ff; border: 1px solid #e0e7ff; border-radius: 2rem; padding: 0.25rem 0.85rem; font-size: 0.78rem; color: #6366f1; font-weight: 500; margin-top: 0.5rem; }
.chat-divider { border: none; border-top: 1px solid #f0f0f5; margin: 0.75rem 0 1.25rem 0; }

.chat-message { display: flex; gap: 0.65rem; margin-bottom: 1rem; align-items: flex-end; }
.chat-message.user { flex-direction: row-reverse; }
.avatar { width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex-shrink: 0; font-size: 0.75rem; }
.avatar.figured { background: #6366f1; color: white; font-family: 'Syne', sans-serif; font-weight: 800; letter-spacing: 0.05em; }
.avatar.user { background: #f3f4f6; color: #374151; font-size: 0.9rem; }
.bubble { max-width: 80%; padding: 0.75rem 1rem; border-radius: 1.1rem; font-size: 0.93rem; line-height: 1.6; }
.bubble.figured { background: #f5f3ff; color: #1a1a2e; border-bottom-left-radius: 0.2rem; }
.bubble.user { background: #6366f1; color: white; border-bottom-right-radius: 0.2rem; }

.typing-bubble { background: #f5f3ff; border-radius: 1.1rem; border-bottom-left-radius: 0.2rem; padding: 0.75rem 1rem; font-size: 0.85rem; color: #6366f1; font-style: italic; display: flex; align-items: center; gap: 0.5rem; }
.typing-dots span { display: inline-block; width: 5px; height: 5px; background: #6366f1; border-radius: 50%; animation: bounce 1.2s infinite; }
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce { 0%, 80%, 100% { transform: translateY(0); opacity: 0.4; } 40% { transform: translateY(-5px); opacity: 1; } }

.micro-reaction { font-size: 0.85rem; font-weight: 500; color: #6366f1; background: #f5f3ff; border-radius: 2rem; padding: 0.3rem 1rem; display: inline-block; animation: fadeIn 0.4s ease; margin-left: 2.5rem; margin-bottom: 0.5rem; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }

.confetti-wrapper { text-align: center; font-size: 1.6rem; letter-spacing: 0.1em; margin-bottom: 0.5rem; animation: pop 0.5s ease; }
@keyframes pop { 0% { transform: scale(0.5); opacity: 0; } 70% { transform: scale(1.15); opacity: 1; } 100% { transform: scale(1); } }

/* Chat input */
.stTextInput > div > div > input {
    border-radius: 2rem !important; border: 2px solid #e5e7eb !important;
    padding: 0.7rem 1.2rem !important; font-family: 'DM Sans', sans-serif !important;
    font-size: 0.93rem !important; background: #ffffff !important; color: #1a1a2e !important;
    box-shadow: none !important; outline: none !important;
}
.stTextInput > div > div > input:focus {
    border-color: #6366f1 !important;
    box-shadow: none !important;
}
/* Remove outer form container borders and shadows */
[data-testid="stForm"] { border: none !important; padding: 0 !important; box-shadow: none !important; background: transparent !important; }
[data-testid="stForm"] > div { border: none !important; box-shadow: none !important; background: transparent !important; }
.stTextInput > div { border: none !important; box-shadow: none !important; background: transparent !important; }
.stTextInput > div > div { border: none !important; box-shadow: none !important; background: transparent !important; }
.stFormSubmitButton > button {
    border-radius: 2rem !important; background: #6366f1 !important; color: white !important;
    border: none !important; padding: 0.7rem 1.5rem !important; font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important; font-size: 0.93rem !important; width: 100% !important;
}
.stFormSubmitButton > button:hover { background: #4f46e5 !important; }

/* Streamlit buttons */
.stButton > button {
    border-radius: 2rem !important; background: #6366f1 !important; color: white !important;
    border: none !important; padding: 0.65rem 1.5rem !important; font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important; font-size: 0.93rem !important;
    transition: background 0.2s ease, transform 0.1s ease;
}
.stButton > button:hover { background: #4f46e5 !important; transform: translateY(-1px); }

/* start over — small subtle */
.chat-controls .stButton > button {
    background: transparent !important; color: #9ca3af !important;
    border: 1px solid #e5e7eb !important; font-size: 0.8rem !important;
    padding: 0.3rem 1rem !important;
}
.chat-controls .stButton > button:hover { color: #6366f1 !important; border-color: #6366f1 !important; transform: none !important; }
</style>
""", unsafe_allow_html=True)


def wordmark_html(size="2.2rem", **kwargs):
    return f"""<span class="figured-wordmark-wrap" style="font-size:{size};">F<span class="figured-i-wrap">I</span>GURED</span>"""


defaults = {
    "screen": "level",
    "level": None,
    "subject": None,
    "custom_subject": "",
    "messages": [],
    "greeted": False,
    "tagline": random.choice(TAGLINES),
    "show_reaction": None,
    "show_confetti": False,
    "last_input": "",
    "lesson_preview": None,
    "message_count": 0,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

if "system_prompt" not in st.session_state:
    st.session_state.system_prompt = load_system_prompt()

if "client" not in st.session_state:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        st.error("ANTHROPIC_API_KEY not found. Add it to your .env file.")
        st.stop()
    st.session_state.client = anthropic.Anthropic(api_key=api_key)


# ══════════════════════════════════════════════════════════════════════════════
# SCREEN 1 — Level selection
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.screen == "level":
    st.markdown(f"""
    <div class="onboard-wrap">
        <div style="text-align:center;margin-bottom:2.5rem;">{wordmark_html("2.4rem")}</div>
        <div class="onboard-step">Step 1 of 3</div>
        <div class="onboard-q">Who are you learning as?</div>
        <div class="onboard-sub">Pick your level. You can always change it.</div>
    </div>
    """, unsafe_allow_html=True)

    cols = st.columns(3)
    for i, (key, info) in enumerate(LEVELS.items()):
        with cols[i]:
            selected = st.session_state.level == key
            border = "#6366f1" if selected else "#e5e7eb"
            bg = "#f5f3ff" if selected else "#ffffff"
            st.markdown(f"""
            <div style="background:{bg};border:2px solid {border};border-radius:1.25rem;
                        padding:2rem 1.25rem;text-align:center;min-height:200px;
                        display:flex;flex-direction:column;align-items:center;
                        justify-content:center;margin-bottom:0.75rem;
                        transition:all 0.18s ease;">
                <div style="font-size:3rem;line-height:1;margin-bottom:0.75rem;">{info['emoji']}</div>
                <div style="font-family:'Syne',sans-serif;font-weight:700;font-size:1.1rem;color:#1a1a2e;margin-bottom:0.3rem;">{info['label']}</div>
                <div style="font-size:0.8rem;color:#9ca3af;line-height:1.4;">{info['desc']}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"Select {key}", key=f"lvl_{key}", use_container_width=True):
                st.session_state.level = key
                st.session_state.screen = "subject"
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# SCREEN 2 — Subject selection
# ══════════════════════════════════════════════════════════════════════════════

elif st.session_state.screen == "subject":
    level = st.session_state.level
    subjects = LEVELS[level]["subjects"]

    st.markdown(f"""
    <div class="onboard-wrap">
        <div style="text-align:center;margin-bottom:2rem;">{wordmark_html("2rem")}</div>
        <div class="onboard-step">Step 2 of 3</div>
        <div class="onboard-q">What do you want to work through?</div>
        <div class="onboard-sub">{level} subjects below, or type your own.</div>
    </div>
    """, unsafe_allow_html=True)

    cols = st.columns(5)
    for i, subj in enumerate(subjects):
        with cols[i % 5]:
            selected = st.session_state.subject == subj
            label = f"✓ {subj}" if selected else subj
            if st.button(label, key=f"subj_{subj}", use_container_width=True):
                if st.session_state.subject == subj:
                    st.session_state.subject = None
                else:
                    st.session_state.subject = subj
                    st.session_state.custom_subject = ""
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    custom = st.text_input(
        "Or type your own subject:",
        value=st.session_state.custom_subject,
        placeholder="e.g. Organic Chemistry, SAT Prep, Public Speaking...",
    )
    if custom:
        st.session_state.custom_subject = custom
        st.session_state.subject = custom

    st.markdown("<br>", unsafe_allow_html=True)

    col_back, col_spacer, col_next = st.columns([1, 2, 1])
    with col_back:
        if st.button("Back", key="back_subj"):
            st.session_state.screen = "level"
            st.session_state.subject = None
            st.rerun()
    with col_next:
        if st.session_state.subject:
            if st.button("Preview my lesson", key="next_preview"):
                preview_prompt = (
                    f"A {level} learner wants to work on {st.session_state.subject}. "
                    f"Write a 2-3 sentence lesson preview that tells them what they'll work through. "
                    f"Be specific, motivating, and Socratic. Do not give answers. "
                    f"Just the sentences, no headers, no bullets."
                )
                with st.spinner("Preparing your lesson..."):
                    try:
                        resp = st.session_state.client.messages.create(
                            model=MODEL, max_tokens=200,
                            messages=[{"role": "user", "content": preview_prompt}],
                        )
                        st.session_state.lesson_preview = resp.content[0].text
                    except Exception:
                        st.session_state.lesson_preview = f"In this session you'll work through {st.session_state.subject} using the Socratic method. Figured guides with questions and hints, never answers. By the end, you'll have figured it out yourself."
                st.session_state.screen = "preview"
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# SCREEN 3 — Lesson preview
# ══════════════════════════════════════════════════════════════════════════════

elif st.session_state.screen == "preview":
    level = st.session_state.level
    subject = st.session_state.subject
    emoji = LEVELS[level]["emoji"]

    st.markdown(f"""
    <div class="onboard-wrap">
        <div style="text-align:center;margin-bottom:2rem;">{wordmark_html("2rem")}</div>
        <div class="onboard-step">Step 3 of 3</div>
        <div class="onboard-q">Here's what we'll work through.</div>
        <div class="onboard-sub">No answers. Just thinking. You've got this.</div>
        <div class="preview-card">
            <div class="preview-label">{emoji} {level} &nbsp;|&nbsp; {subject}</div>
            <div class="preview-title">Your Figured Session</div>
            <div class="preview-body">{st.session_state.lesson_preview}</div>
            <div class="preview-rule">Figured never gives you the answer. It asks the right questions until you find it yourself.</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col_back, col_spacer, col_start = st.columns([1, 2, 1])
    with col_back:
        if st.button("Change subject", key="back_preview"):
            st.session_state.screen = "subject"
            st.rerun()
    with col_start:
        if st.button("Let's go", key="start_session"):
            base = st.session_state.system_prompt
            st.session_state.system_prompt = build_session_prompt(base, level, subject)
            st.session_state.screen = "chat"
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# SCREEN 4 — Chat
# ══════════════════════════════════════════════════════════════════════════════

elif st.session_state.screen == "chat":
    level = st.session_state.level
    subject = st.session_state.subject
    emoji = LEVELS[level]["emoji"]

    if not st.session_state.greeted:
        opener_prompt = (
            f"You are Figured opening a {level} session on {subject}. "
            f"Write a focused 2-3 sentence opener that: "
            f"1) names the subject and frames what makes it worth thinking hard about, "
            f"2) sets the expectation clearly: you will ask questions, not give answers, "
            f"3) ends with ONE sharp, specific opening question that begins the actual work. "
            f"Tone: direct, warm, intellectually alive. No filler. No 'great to meet you'. No 'Here is the opening:' or any preamble."
        )
        try:
            resp = st.session_state.client.messages.create(
                model=MODEL, max_tokens=200,
                messages=[{"role": "user", "content": opener_prompt}],
            )
            opener = resp.content[0].text
        except Exception:
            opener = f"We're working on {subject} today. I won't hand you answers but I'll ask the right questions until you find them yourself. Let's start: what's the first thing you're trying to understand?"

        st.session_state.messages.append({"role": "assistant", "content": opener})
        st.session_state.greeted = True

    st.markdown('<div class="chat-area">', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="figured-header">
        {wordmark_html("2.6rem")}
        <div class="figured-tagline">{st.session_state.tagline}</div>
        <div class="session-badge">{emoji} {level} &nbsp;|&nbsp; {subject}</div>
    </div>
    <hr class="chat-divider">
    """, unsafe_allow_html=True)

    if st.session_state.show_confetti:
        st.markdown('<div class="confetti-wrapper">🎉 ✨ 🔥 💡 🎯 ✨ 🎉</div>', unsafe_allow_html=True)
        st.session_state.show_confetti = False

    for msg in st.session_state.messages:
        role = msg["role"]
        content = msg["content"]
        css_role = "figured" if role == "assistant" else "user"
        avatar = "F" if role == "assistant" else "🧠"
        st.markdown(f"""
        <div class="chat-message {css_role}">
            <div class="avatar {css_role}">{avatar}</div>
            <div class="bubble {css_role}">{content}</div>
        </div>
        """, unsafe_allow_html=True)

    if st.session_state.show_reaction:
        st.markdown(f'<div class="micro-reaction">{st.session_state.show_reaction}</div>', unsafe_allow_html=True)
        st.session_state.show_reaction = None

    user_slot = st.empty()
    typing_slot = st.empty()
    st.markdown('</div>', unsafe_allow_html=True)

    with st.form(key="chat_form", clear_on_submit=True):
        col1, col2 = st.columns([5, 1])
        with col1:
            user_input = st.text_input(
                label="message", placeholder="What are you thinking...",
                label_visibility="collapsed",
            )
        with col2:
            send = st.form_submit_button("Send", use_container_width=True)

    st.markdown('<div class="chat-controls" style="text-align:center;margin-top:0.5rem;">', unsafe_allow_html=True)
    if st.button("start over", key="clear_btn"):
        for k, v in defaults.items():
            st.session_state[k] = v
        st.session_state.system_prompt = load_system_prompt()
        st.session_state.tagline = random.choice(TAGLINES)
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    user_text = user_input.strip() if user_input else ""
    should_respond = send and user_text

    # ── Session limit wall ────────────────────────────────────────────────────
    MESSAGE_LIMIT = 10

    if st.session_state.message_count >= MESSAGE_LIMIT:
        st.markdown("""
        <div style="
            background: #f5f3ff;
            border: 2px solid #e0e7ff;
            border-radius: 1.25rem;
            padding: 2rem;
            text-align: center;
            max-width: 520px;
            margin: 1rem auto;
        ">
            <div style="font-size:2rem;margin-bottom:0.75rem;">🧠</div>
            <div style="font-family:'Syne',sans-serif;font-weight:700;font-size:1.2rem;color:#1a1a2e;margin-bottom:0.5rem;">
                You've hit your free session limit.
            </div>
            <div style="font-size:0.93rem;color:#6b7280;line-height:1.6;margin-bottom:1.25rem;">
                Figured is in early access. You used 10 messages — that means you were actually thinking, which is the whole point.<br><br>
                Want unlimited access? Drop your email and you'll be first to know when full access opens.
            </div>
            <a href="https://forms.gle/5d5EZJCUCkwnGauT6" target="_blank" style="
                background: #6366f1;
                color: white;
                border-radius: 2rem;
                padding: 0.75rem 2rem;
                font-family: 'DM Sans', sans-serif;
                font-weight: 500;
                font-size: 1rem;
                text-decoration: none;
                display: inline-block;
            ">Join the waitlist</a>
        </div>
        """, unsafe_allow_html=True)

    elif should_respond:
        st.session_state.last_input = user_text
        st.session_state.message_count += 1
        breakthrough = is_breakthrough(user_text)
        progress = is_progress(user_text) and not breakthrough

        st.session_state.messages.append({"role": "user", "content": user_text})

        user_slot.markdown(f"""
        <div class="chat-message user">
            <div class="avatar user">🧠</div>
            <div class="bubble user">{user_text}</div>
        </div>
        """, unsafe_allow_html=True)

        typing_msg = random.choice(TYPING_MESSAGES)
        typing_slot.markdown(f"""
        <div class="chat-message figured">
            <div class="avatar figured">F</div>
            <div class="typing-bubble">{typing_msg}&nbsp;<span class="typing-dots"><span></span><span></span><span></span></span></div>
        </div>
        """, unsafe_allow_html=True)

        api_messages = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]

        try:
            response = st.session_state.client.messages.create(
                model=MODEL, max_tokens=MAX_TOKENS,
                system=st.session_state.system_prompt,
                messages=api_messages,
            )
            reply = response.content[0].text
        except anthropic.RateLimitError:
            reply = "Hit a rate limit. Give me a second and try again."
        except anthropic.APIError as e:
            reply = f"Something went wrong: {e}"

        typing_slot.empty()
        user_slot.empty()
        st.session_state.messages.append({"role": "assistant", "content": reply})

        if breakthrough:
            st.session_state.show_confetti = True
            st.session_state.show_reaction = random.choice(MICRO_REACTIONS)
        elif progress:
            st.session_state.show_reaction = random.choice(MICRO_REACTIONS)

        st.rerun()