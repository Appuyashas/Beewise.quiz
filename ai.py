"""
Beewise AI Module — ai.py
=========================
Handles all AI features:
  - BeeBot study buddy chat
  - AI question generation for admins

Powered by Anthropic Claude API.
Set ANTHROPIC_API_KEY environment variable to enable.
Falls back to Pollinations (free, no key) if no key is set.
"""

import os
import json
import requests

# ── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
AI_MODEL          = "claude-haiku-4-5-20251001"   # fast + cheap
AI_TIMEOUT        = 30
CHAT_TOKENS       = 500
GEN_TOKENS        = 2000

# ── Core: Anthropic API call ──────────────────────────────────────────────────
def _ask_anthropic(system_prompt: str, user_message: str, max_tokens: int) -> tuple:
    """Call Anthropic Claude API. Returns (text, None) or (None, error)."""
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": AI_MODEL,
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
            },
            timeout=AI_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["content"][0]["text"].strip()
        return (text, None) if text else (None, "Empty response — try again.")
    except requests.exceptions.Timeout:
        return None, "AI took too long. Try again in a moment!"
    except requests.exceptions.ConnectionError:
        return None, "Could not reach AI server. Check your internet connection."
    except Exception as e:
        return None, f"AI error: {str(e)}"


# ── Fallback: Pollinations (free, no key) ─────────────────────────────────────
def _ask_pollinations(system_prompt: str, user_message: str, max_tokens: int) -> tuple:
    """Fallback to Pollinations free AI via POST."""
    try:
        resp = requests.post(
            "https://text.pollinations.ai/",
            json={
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "model": "openai",
                "max_tokens": max_tokens,
                "private": True,
            },
            timeout=AI_TIMEOUT,
        )
        resp.raise_for_status()
        text = resp.text.strip()
        return (text, None) if text else (None, "Empty response — try again.")
    except requests.exceptions.Timeout:
        return None, "AI took too long. Try again in a moment!"
    except requests.exceptions.ConnectionError:
        return None, "Could not reach AI server. Check your internet connection."
    except Exception as e:
        return None, f"AI error: {str(e)}"


def ask_ai(system_prompt: str, user_message: str, max_tokens: int = CHAT_TOKENS) -> tuple:
    """Route to Anthropic if key is set, otherwise fall back to Pollinations."""
    if ANTHROPIC_API_KEY:
        return _ask_anthropic(system_prompt, user_message, max_tokens)
    return _ask_pollinations(system_prompt, user_message, max_tokens)


# ── BeeBot Study Buddy ─────────────────────────────────────────────────────────
def beebot_reply(username: str, message: str, weak_cats: list, strong_cats: list,
                 total_games: int) -> tuple:
    """Generate a personalised BeeBot study reply. Returns (reply_text, None) or (None, error)."""
    weak_str   = ", ".join(weak_cats)   if weak_cats   else "None yet"
    strong_str = ", ".join(strong_cats) if strong_cats else "None yet"

    system = f"""You are BeeBot — a friendly, encouraging AI study buddy inside Beewise, \
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
    """Generate MCQ questions. Returns (list_of_dicts, None) or (None, error)."""
    count = min(max(count, 1), 10)

    system = """You are an expert quiz question writer for Beewise, a computer science quiz platform.
Generate multiple-choice questions in EXACT JSON format.

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

    try:
        clean = text.strip()
        # Strip accidental markdown code fences
        if "```" in clean:
            for part in clean.split("```"):
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("["):
                    clean = part
                    break
        # Find first [ ... ] block in case there's any preamble
        start = clean.find("[")
        end   = clean.rfind("]")
        if start != -1 and end != -1:
            clean = clean[start:end+1]

        questions = json.loads(clean)

        if not isinstance(questions, list) or len(questions) == 0:
            return None, "AI returned empty or invalid question list. Try again."

        required = {"question", "opt0", "opt1", "opt2", "opt3"}
        valid = [q for q in questions if required.issubset(q.keys())]

        if not valid:
            return None, "AI questions are missing required fields. Try again."

        return valid, None

    except json.JSONDecodeError as e:
        return None, f"AI returned invalid format. Try a different topic. ({e})"