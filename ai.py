"""
Beewise AI Module
=================
Priority order:
  1. Anthropic Claude  — set ANTHROPIC_API_KEY  (best quality)
  2. Groq              — set GROQ_API_KEY        (free, very fast)
  3. Pollinations      — no key needed           (free fallback)
"""

import os, json, requests

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY", "")
TIMEOUT           = 25
CHAT_TOKENS       = 500
GEN_TOKENS        = 2000

# ── 1. Anthropic ──────────────────────────────────────────────────────────────
def _anthropic(system, user, max_tokens):
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001",
                  "max_tokens": max_tokens,
                  "system": system,
                  "messages": [{"role": "user", "content": user}]},
            timeout=TIMEOUT)
        r.raise_for_status()
        text = r.json()["content"][0]["text"].strip()
        return (text, None) if text else (None, "Empty response.")
    except requests.exceptions.Timeout:
        return None, "AI is taking too long. Try again!"
    except Exception as e:
        return None, f"Anthropic error: {e}"

# ── 2. Groq (free tier — llama3) ─────────────────────────────────────────────
def _groq(system, user, max_tokens):
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": "llama3-8b-8192",
                  "max_tokens": max_tokens,
                  "messages": [{"role": "system", "content": system},
                                {"role": "user",   "content": user}]},
            timeout=TIMEOUT)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip()
        return (text, None) if text else (None, "Empty response.")
    except requests.exceptions.Timeout:
        return None, "AI is taking too long. Try again!"
    except Exception as e:
        return None, f"Groq error: {e}"

# ── 3. Pollinations (no key needed) ──────────────────────────────────────────
def _pollinations(system, user, max_tokens):
    try:
        r = requests.post(
            "https://text.pollinations.ai/",
            json={"model": "openai",
                  "max_tokens": max_tokens,
                  "private": True,
                  "messages": [{"role": "system", "content": system},
                                {"role": "user",   "content": user}]},
            timeout=TIMEOUT)
        r.raise_for_status()
        text = r.text.strip()
        return (text, None) if text else (None, "Empty response.")
    except requests.exceptions.Timeout:
        return None, "AI took too long. Try again in a moment!"
    except Exception as e:
        return None, f"AI error: {e}"

# ── Router ────────────────────────────────────────────────────────────────────
def ask_ai(system, user, max_tokens=CHAT_TOKENS):
    if ANTHROPIC_API_KEY:
        return _anthropic(system, user, max_tokens)
    if GROQ_API_KEY:
        return _groq(system, user, max_tokens)
    return _pollinations(system, user, max_tokens)

# ── BeeBot ────────────────────────────────────────────────────────────────────
def beebot_reply(username, message, weak_cats, strong_cats, total_games):
    weak_str   = ", ".join(weak_cats)   if weak_cats   else "none yet"
    strong_str = ", ".join(strong_cats) if strong_cats else "none yet"
    system = f"""You are BeeBot, a friendly AI study buddy inside Beewise — a quiz platform \
covering HTML, CSS, Python, SQL, Flask, and Computer Science.

Student: {username} | Games played: {total_games}
Weak topics (below 70%): {weak_str}
Strong topics (70%+): {strong_str}

Rules:
- Be warm, encouraging, and concise (2-3 short paragraphs max)
- Use bee emojis occasionally 🐝🍯✨
- Give clear examples for weak topics
- End with a short tip or motivation
- If asked off-topic, gently guide back to studying
- Never say what AI model you are"""
    return ask_ai(system, message, CHAT_TOKENS)

# ── Question Generator ────────────────────────────────────────────────────────
def generate_questions(topic, category, count=5):
    count = min(max(int(count), 1), 10)
    system = """You are an expert quiz writer for Beewise, a CS quiz platform.
Return ONLY a valid JSON array — no markdown, no backticks, no explanation.
Each object must have: "question", "opt0" (correct), "opt1", "opt2", "opt3".
Make all 4 options plausible. Questions must be clear and educational."""

    user = f"""Generate exactly {count} multiple-choice questions about: {topic}
Category: {category}

Return ONLY this JSON (no other text):
[{{"question":"...","opt0":"correct answer","opt1":"wrong","opt2":"wrong","opt3":"wrong"}}]"""

    text, err = ask_ai(system, user, GEN_TOKENS)
    if err:
        return None, err
    try:
        # Strip markdown fences if present
        clean = text.strip()
        if "```" in clean:
            parts = clean.split("```")
            for p in parts:
                p = p.strip().lstrip("json").strip()
                if p.startswith("["): clean = p; break
        start, end = clean.find("["), clean.rfind("]")
        if start != -1 and end != -1:
            clean = clean[start:end+1]
        qs = json.loads(clean)
        required = {"question","opt0","opt1","opt2","opt3"}
        valid = [q for q in qs if required.issubset(q.keys())]
        if not valid:
            return None, "AI returned invalid format. Try a different topic."
        return valid, None
    except json.JSONDecodeError as e:
        return None, f"AI returned invalid JSON. Try again. ({e})"