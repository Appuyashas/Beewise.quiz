"""
QuizBee AI Module — ai.py
=========================
Handles all AI features for QuizBee:
  - BeeBot study buddy chat
  - AI question generation for admins

Powered by Pollinations AI — 100% free, no signup, no API key needed.
"""

import urllib.parse
import requests
import json


# ── Config ────────────────────────────────────────────────────────────────────
AI_PROVIDER = "pollinations"   # free, no key needed
AI_TIMEOUT  = 30               # seconds before giving up
CHAT_TOKENS = 400              # max response length for BeeBot chat
GEN_TOKENS  = 2000             # max response length for question generation


# ── Core AI call ──────────────────────────────────────────────────────────────
def ask_ai(system_prompt: str, user_message: str, max_tokens: int = CHAT_TOKENS):
    """
    Send a prompt to the AI and get a response.
    Returns: (text, None) on success  |  (None, error_string) on failure
    """
    try:
        prompt  = f"{system_prompt}\n\nUser: {user_message}\nBeeBot:"
        encoded = urllib.parse.quote(prompt)
        url     = f"https://text.pollinations.ai/{encoded}"
        resp    = requests.get(url, timeout=AI_TIMEOUT)
        resp.raise_for_status()
        text = resp.text.strip()
        if text:
            return text, None
        return None, "Empty response — please try again."
    except requests.exceptions.Timeout:
        return None, "AI took too long to respond. Try again in a moment!"
    except requests.exceptions.ConnectionError:
        return None, "Could not reach AI server. Check your internet connection."
    except Exception as e:
        return None, f"AI error: {str(e)}"


# ── BeeBot Study Buddy ─────────────────────────────────────────────────────────
def beebot_reply(username: str, message: str, weak_cats: list, strong_cats: list,
                 total_games: int) -> tuple:
    """
    Generate a BeeBot study buddy response personalised to the student.
    Returns: (reply_text, None) or (None, error_string)
    """
    weak_str   = ", ".join(weak_cats)   if weak_cats   else "None yet"
    strong_str = ", ".join(strong_cats) if strong_cats else "None yet"

    system = f"""You are BeeBot — a friendly, encouraging AI study buddy inside QuizBee, \
a quiz platform covering HTML, CSS, Python, SQL, Flask, and General Computer Science.

Student profile:
- Name: {username}
- Total games played: {total_games}
- Weak categories (below 70%): {weak_str}
- Strong categories (70%+): {strong_str}

Your personality rules:
- Friendly, warm, encouraging — like a helpful older classmate
- Use bee emojis occasionally 🐝🍯✨ but don't overdo it
- Give clear, simple explanations suitable for students
- If they ask about a weak category, be extra encouraging and give good examples
- Keep answers concise — 2 to 4 short paragraphs max
- If they ask something off-topic, gently guide them back to studying
- End with a short tip or motivation when relevant
- NEVER mention you are an AI model or what company made you"""

    return ask_ai(system, message, max_tokens=CHAT_TOKENS)


# ── AI Question Generator ──────────────────────────────────────────────────────
def generate_questions(topic: str, category: str, count: int = 5) -> tuple:
    """
    Generate multiple-choice quiz questions on a given topic.
    Returns: (list_of_question_dicts, None) or (None, error_string)
    """
    count = min(max(count, 1), 10)  # clamp between 1 and 10

    system = """You are an expert quiz question writer for QuizBee, a computer science quiz platform.
Your job is to generate multiple-choice questions in EXACT JSON format.

Strict rules:
- Return ONLY a valid JSON array — no explanation, no markdown, no backticks
- Each question has exactly these keys: "question", "opt0", "opt1", "opt2", "opt3"
- opt0 is ALWAYS the correct answer (the system shuffles automatically)
- All 4 options must be plausible — not obviously wrong
- Questions must be clear, unambiguous, and educational
- Suitable for undergraduate IT/CS students"""

    user = f"""Generate exactly {count} multiple-choice questions about: {topic}
Category: {category}

Return ONLY this JSON format, nothing else:
[
  {{
    "question": "Question text here?",
    "opt0": "Correct answer",
    "opt1": "Wrong option 1",
    "opt2": "Wrong option 2",
    "opt3": "Wrong option 3"
  }}
]"""

    text, err = ask_ai(system, user, max_tokens=GEN_TOKENS)
    if err:
        return None, err

    # Parse the JSON from the response
    try:
        clean = text.strip()
        # Strip accidental markdown code fences
        if "```" in clean:
            parts = clean.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("["):
                    clean = part
                    break

        questions = json.loads(clean)

        if not isinstance(questions, list) or len(questions) == 0:
            return None, "AI returned empty or invalid question list. Try again."

        # Validate each question has required keys
        required = {"question", "opt0", "opt1", "opt2", "opt3"}
        valid = [q for q in questions if required.issubset(q.keys())]

        if not valid:
            return None, "AI questions are missing required fields. Try again."

        return valid, None

    except json.JSONDecodeError as e:
        return None, f"AI returned invalid format. Try a different topic. ({e})"