"""IBM Granite LLM service wrapper.

Handles viva question generation and rubric-based answer grading.
Provides deterministic local offline fallbacks when in MOCK_MODE or on network error.
"""
import json
import logging
import os
import re
import requests
from config import Config
from services.ibm_auth import get_token, IAMAuthError

import time

logger = logging.getLogger("granite")

# watsonx.ai rate limit is 2 req/sec on Lite plan.
# Ensure minimum spacing between sequential Granite calls.
_last_granite_call_time = 0.0


def _rate_limit_granite():
    """Ensure at least 550ms between requests to respect IBM Lite 2 req/sec rate limit."""
    global _last_granite_call_time
    now = time.time()
    elapsed = now - _last_granite_call_time
    if elapsed < 0.55:
        time.sleep(0.55 - elapsed)
    _last_granite_call_time = time.time()

# Path to offline question bank
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions.json")

# In-memory question bank cache
_question_bank: dict | None = None


def load_question_bank() -> dict:
    """Load local questions.json file."""
    global _question_bank
    if _question_bank is None:
        try:
            with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
                _question_bank = json.load(f)
        except Exception as e:
            logger.warning("[granite] Failed to load offline questions.json: %s", e)
            _question_bank = {
                "default": [
                    {
                        "text": "What is the difference between synchronous and asynchronous operations?",
                        "level": "understand",
                        "key_points": ["blocking", "non-blocking", "event loop", "callback", "concurrency"]
                    }
                ]
            }
    return _question_bank


def _extract_json(text: str) -> dict | list | None:
    """Extract valid JSON from LLM response text, handling markdown fences and prose."""
    if not text:
        return None
    # Strip markdown code blocks
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)

    # First attempt direct parse
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # Look for [ ... ] or { ... } within response
    array_match = re.search(r"(\[.*\])", cleaned, re.DOTALL)
    if array_match:
        try:
            return json.loads(array_match.group(1))
        except Exception:
            pass

    obj_match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
    if obj_match:
        try:
            return json.loads(obj_match.group(1))
        except Exception:
            pass

    return None


def chat(messages: list[dict], max_tokens: int = 700, temperature: float = 0.3) -> str:
    """Call IBM watsonx.ai text chat API for Granite.
    
    API Contract:
    POST {WATSONX_URL}/ml/v1/text/chat?version=2023-05-29
    Authorization: Bearer <token>
    {"model_id": "ibm/granite-3-3-8b-instruct", "project_id": "<PROJECT_ID>", ...}
    """
    _rate_limit_granite()
    token = get_token()
    url = f"{Config.WATSONX_URL}/ml/v1/text/chat?version=2023-05-29"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {
        "model_id": Config.GRANITE_MODEL_ID,
        "project_id": Config.WATSONX_PROJECT_ID,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    if resp.status_code != 200:
        raise RuntimeError(f"Granite API error (HTTP {resp.status_code}): {resp.text}")

    data = resp.json()
    choices = data.get("choices", [])
    if not choices or "message" not in choices[0]:
        raise RuntimeError(f"Malformed Granite response: {data}")

    return choices[0]["message"].get("content", "")


def get_bank_questions(subject: str, n: int = 5) -> list[dict]:
    """Retrieve up to n questions from the local question bank."""
    bank = load_question_bank()
    key = subject.lower().strip()

    matches = []
    # Match exact key or substring
    for k, questions in bank.items():
        if k == key or k in key or key in k:
            matches = questions
            break

    if not matches:
        matches = bank.get("default", [])

    # Return up to n questions
    selected = matches[:n]
    if len(selected) < n and bank.get("default"):
        for q in bank["default"]:
            if len(selected) >= n:
                break
            if q not in selected:
                selected.append(q)

    return selected[:n]


def generate_questions(subject: str, level: str = "undergraduate", n: int = 5) -> list[dict]:
    """Generate viva questions for a subject using IBM Granite with bank fallback."""
    if Config.MOCK_MODE:
        return get_bank_questions(subject, n)

    prompt = f"""You are an expert college viva examiner. Generate exactly {n} viva questions for {subject} at the {level} level.
Each question must test conceptual understanding suitable for an oral exam.
You MUST output ONLY a valid JSON array of objects with no markdown fences, no explanatory text.
JSON structure:
[
  {{
    "text": "Clear question here",
    "level": "remember|understand|apply|analyze|evaluate",
    "key_points": ["keyword1", "keyword2", "keyword3"]
  }}
]
"""

    try:
        raw_response = chat([{"role": "user", "content": prompt}], max_tokens=700, temperature=0.3)
        parsed = _extract_json(raw_response)
        if isinstance(parsed, list) and len(parsed) >= 1:
            validated = []
            for item in parsed:
                if isinstance(item, dict) and "text" in item:
                    validated.append({
                        "text": str(item["text"]).strip(),
                        "level": str(item.get("level", "understand")).lower(),
                        "key_points": [str(kp).strip() for kp in item.get("key_points", []) if kp]
                    })
            if len(validated) >= 1:
                return validated[:n]
    except Exception as e:
        logger.warning("[granite] Question generation failed via Granite, falling back to bank: %s", e)

    return get_bank_questions(subject, n)


def _keyword_grade(question: dict, transcript: str) -> dict:
    """Deterministic keyword-based grading fallback when offline or on API failure.
    
    Scores answer based on overlap of required key points in the student's spoken transcript.
    """
    key_points = [kp.lower().strip() for kp in question.get("key_points", []) if kp]
    text_clean = (transcript or "").lower()
    words = text_clean.split()

    if not words or len(words) < 2:
        return {
            "score": 1.5,
            "verdict": "incorrect",
            "correct_points": [],
            "missing_points": key_points[:3],
            "feedback": "Answer was too brief or inaudible to demonstrate understanding.",
            "ideal_answer": f"A comprehensive answer should cover: {', '.join(key_points)}."
        }

    correct_points = []
    missing_points = []

    for kp in key_points:
        kp_words = kp.split()
        if kp in text_clean or any(kw in text_clean for kw in kp_words if len(kw) > 3):
            correct_points.append(kp)
        else:
            missing_points.append(kp)

    total_pts = max(len(key_points), 1)
    matched_ratio = len(correct_points) / total_pts

    # Length factor (speaking in depth adds credibility up to a threshold)
    length_bonus = min(len(words) / 30.0, 1.0) * 1.5

    # Compute raw score 0 to 10
    raw_score = (matched_ratio * 8.5) + length_bonus
    score = round(min(max(raw_score, 1.0 if len(words) < 5 else 2.5), 10.0), 1)

    if score >= 7.5:
        verdict = "correct"
        feedback = "Good conceptual explanation covering the key principles accurately."
    elif score >= 5.0:
        verdict = "partially correct"
        feedback = "Identified several essential points, but missed some key details."
    else:
        verdict = "incorrect"
        feedback = "The answer did not adequately address the core concepts of the question."

    return {
        "score": score,
        "verdict": verdict,
        "correct_points": correct_points,
        "missing_points": missing_points,
        "feedback": feedback,
        "ideal_answer": f"Key concepts that should be explained: {', '.join(key_points)}."
    }


def grade_answer(question: dict, transcript: str, language: str = "en") -> dict:
    """Grade viva answer using IBM Granite rubric prompt with deterministic keyword fallback.
    
    Returns:
    {
      "score": float (0-10),
      "verdict": "correct"|"partially correct"|"incorrect",
      "correct_points": list[str],
      "missing_points": list[str],
      "feedback": str,
      "ideal_answer": str
    }
    """
    if Config.MOCK_MODE or not Config.IBM_API_KEY:
        return _keyword_grade(question, transcript)

    # Empty or trivial transcript check
    words = (transcript or "").strip().split()
    if len(words) < 2:
        return _keyword_grade(question, transcript)

    prompt = f"""You are an expert oral viva examiner grading a student's spoken answer.

Question: {question.get('text', '')}
Expected Key Points: {json.dumps(question.get('key_points', []))}
Student's Spoken Transcript: "{transcript}"
Language: {language}

Evaluate the student's answer fairly based on conceptual understanding. Spoken answers may have colloquial phrasing.
Respond ONLY with a valid JSON object matching this schema, with no markdown fences, no formatting:
{{
  "score": <float between 0.0 and 10.0>,
  "verdict": "<correct|partially correct|incorrect>",
  "correct_points": ["<points the student mentioned correctly>"],
  "missing_points": ["<key points the student omitted or got wrong>"],
  "feedback": "<2-3 sentence constructive critique for the student>",
  "ideal_answer": "<concise 2-sentence reference answer>"
}}
"""

    try:
        raw_res = chat([{"role": "user", "content": prompt}], max_tokens=600, temperature=0.2)
        parsed = _extract_json(raw_res)
        if isinstance(parsed, dict) and "score" in parsed:
            score = float(parsed.get("score", 0.0))
            score = max(0.0, min(10.0, round(score, 1)))
            verdict = str(parsed.get("verdict", "partially correct")).lower()
            if verdict not in ("correct", "partially correct", "incorrect"):
                verdict = "correct" if score >= 7.5 else ("partially correct" if score >= 5.0 else "incorrect")

            return {
                "score": score,
                "verdict": verdict,
                "correct_points": [str(p) for p in parsed.get("correct_points", [])],
                "missing_points": [str(p) for p in parsed.get("missing_points", [])],
                "feedback": str(parsed.get("feedback", "")).strip() or "Good effort.",
                "ideal_answer": str(parsed.get("ideal_answer", "")).strip() or "Review key definitions."
            }
    except Exception as e:
        logger.warning("[granite] Answer grading failed via Granite, falling back to keyword grader: %s", e)

    return _keyword_grade(question, transcript)
