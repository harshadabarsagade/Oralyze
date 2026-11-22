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

logger = logging.getLogger("granite")

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
