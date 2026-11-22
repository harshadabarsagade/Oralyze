"""IBM Granite LLM service wrapper.

Handles viva question generation from teacher natural-language prompts and rubric-based answer grading.
Provides deterministic local offline fallbacks when in MOCK_MODE or on network error.
"""
import hashlib
import json
import logging
import os
import re
import time
import requests
from config import Config
from services.ibm_auth import get_token, IAMAuthError

logger = logging.getLogger("granite")

# Rate limiting for IBM watsonx Lite plan (2 req/sec)
_last_granite_call_time = 0.0

# In-memory prompt preview cache: sha1 -> (timestamp, preview_result)
_prompt_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 600  # 10 minutes

# Path to offline question bank
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions.json")

# In-memory question bank cache
_question_bank: dict | None = None


def _rate_limit_granite():
    """Ensure at least 550ms between requests to respect IBM Lite 2 req/sec rate limit."""
    global _last_granite_call_time
    now = time.time()
    elapsed = now - _last_granite_call_time
    if elapsed < 0.55:
        time.sleep(0.55 - elapsed)
    _last_granite_call_time = time.time()


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
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # Look for { ... } object first
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(cleaned[first_brace:last_brace + 1])
        except Exception:
            pass

    # Look for [ ... ] array
    first_bracket = cleaned.find("[")
    last_bracket = cleaned.rfind("]")
    if first_bracket != -1 and last_bracket > first_bracket:
        try:
            return json.loads(cleaned[first_bracket:last_bracket + 1])
        except Exception:
            pass

    return None


def chat(messages: list[dict], max_tokens: int = 1200, temperature: float = 0.4, top_p: float = 0.9) -> str:
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
        "temperature": temperature,
        "top_p": top_p
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
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
    for k, questions in bank.items():
        if k == key or k in key or key in k:
            matches = questions
            break

    if not matches:
        matches = bank.get("default", [])

    selected = matches[:n]
    if len(selected) < n and bank.get("default"):
        for q in bank["default"]:
            if len(selected) >= n:
                break
            if q not in selected:
                selected.append(q)

    # Normalize fields
    normalized = []
    for idx, q in enumerate(selected[:n]):
        normalized.append({
            "id": f"q{idx+1}",
            "text": q.get("text", ""),
            "bloom": q.get("level", q.get("bloom", "understand")),
            "key_points": q.get("key_points", []),
            "ideal_seconds": 45
        })
    return normalized


def sanitize_prompt(raw_prompt: str) -> str:
    """Sanitize teacher prompt before sending to model.
    
    Collapse whitespace, strip backticks, {{ }}, control chars, and system:/assistant: prefixes.
    Truncate at 500 chars.
    """
    if not raw_prompt:
        return ""
    # Strip prefixes
    text = re.sub(r"^(?:system|assistant|user)\s*:\s*", "", raw_prompt.strip(), flags=re.IGNORECASE)
    # Strip backticks and curly braces
    text = re.sub(r"[`{}]+", "", text)
    # Strip control characters
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text[:500]


def _similarity(s1: str, s2: str) -> float:
    """Word overlap ratio between two question strings."""
    w1 = set(re.findall(r"\w+", s1.lower()))
    w2 = set(re.findall(r"\w+", s2.lower()))
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / max(len(w1), len(w2))


def preview_viva_from_prompt(
    prompt: str,
    difficulty: str = "medium",
    language: str = "English",
    count: int = 5
) -> tuple[dict, int]:
    """Generate or retrieve cached viva questions from teacher prompt.
    
    Returns (result_dict, status_code).
    """
    cleaned = sanitize_prompt(prompt)
    if len(cleaned) < 10:
        return {
            "error": "need_more_detail",
            "message": "Tell me the subject and the topic."
        }, 422

    # Clamp count 3-7
    target_count = max(3, min(int(count or 5), 7))
    difficulty = difficulty.lower() if difficulty in ("easy", "medium", "hard") else "medium"
    language = "Hindi" if "hindi" in str(language).lower() else "English"

    cache_key = hashlib.sha1(f"{cleaned}|{difficulty}|{language}|{target_count}".encode("utf-8")).hexdigest()
    now = time.time()
    if cache_key in _prompt_cache:
        cached_time, cached_val = _prompt_cache[cache_key]
        if now - cached_time < CACHE_TTL:
            logger.info("[granite] Returning cached preview for prompt: %s...", cleaned[:30])
            return cached_val, 200

    if Config.MOCK_MODE or not Config.IBM_API_KEY:
        fallback_res = _make_fallback_result(cleaned, difficulty, language, target_count)
        fallback_res["source"] = "fallback"
        _prompt_cache[cache_key] = (now, fallback_res)
        return fallback_res, 200

    # System prompt specified verbatim in B2
    system_prompt = """You are an examiner at an Indian engineering college. You write oral viva questions that a student answers out loud in 30 to 60 seconds.

You always answer with a single JSON object and nothing else. No explanation, no markdown, no code fences.

JSON shape:
{
  "title": "<short viva title, max 6 words>",
  "subject": "<subject name, max 4 words>",
  "topic": "<topic or chapter, max 6 words>",
  "difficulty": "easy|medium|hard",
  "questions": [
    {
      "text": "<the question, one or two sentences, spoken style>",
      "bloom": "remember|understand|apply|analyse",
      "key_points": ["<point an ideal answer must contain>", "<point>", "<point>"],
      "ideal_seconds": <integer 20-60>
    }
  ]
}

Hard rules:
- Produce exactly the number of questions requested.
- Never write yes/no questions, never multiple choice, never "define X" alone.
- At least half the questions must be apply or analyse level, not recall.
- key_points: 2 to 5 short phrases, each under 12 words.
- Use plain English that a student can understand when heard once, out loud.
- No two questions may test the same idea.
- If the request mentions a language other than English, write the question text in that language but keep the JSON keys in English."""

    user_message = f"""Write a viva from this teacher's request:

<prompt>{cleaned}</prompt>

Settings: difficulty={difficulty}, number of questions={target_count}, language={language}.
Return only the JSON object."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    parsed = None
    for attempt in range(2):
        try:
            raw_res = chat(messages, max_tokens=1200, temperature=0.4, top_p=0.9)
            parsed = _extract_json(raw_res)
            if isinstance(parsed, dict) and "questions" in parsed and isinstance(parsed["questions"], list):
                break
        except Exception as e:
            logger.warning("[granite] attempt %d generation failed: %s", attempt + 1, e)

        # Retry once with JSON repair message
        if attempt == 0:
            messages.append({"role": "assistant", "content": raw_res if 'raw_res' in locals() else ""})
            messages.append({
                "role": "user",
                "content": "Your previous reply was not valid JSON. Reply again with only the JSON object, no other text."
            })

    # Validate parsed JSON according to Section B5
    validated_questions = []
    if isinstance(parsed, dict):
        raw_qs = parsed.get("questions", [])
        for item in raw_qs:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            bloom = str(item.get("bloom", item.get("level", "understand"))).lower()
            if bloom not in ("remember", "understand", "apply", "analyse", "analyze"):
                bloom = "understand"
            if bloom == "analyze":
                bloom = "analyse"

            # Check: text 20-220 chars, has ? or imperative verb
            if len(text) < 20 or len(text) > 260:
                continue

            kps = [str(k).strip() for k in item.get("key_points", []) if str(k).strip()]
            if len(kps) < 2:
                continue

            ideal_sec = int(item.get("ideal_seconds", 40))
            ideal_sec = max(15, min(ideal_sec, 90))

            # Deduplicate: if shares >70% words with existing question
            is_dup = False
            for existing in validated_questions:
                if _similarity(text, existing["text"]) > 0.70:
                    is_dup = True
                    break
            if is_dup:
                continue

            validated_questions.append({
                "id": f"q{len(validated_questions)+1}",
                "text": text,
                "bloom": bloom,
                "key_points": kps[:5],
                "ideal_seconds": ideal_sec
            })

    # If valid questions count is acceptable (allow target_count-1, never fewer than 3)
    if len(validated_questions) >= min(3, target_count - 1):
        res = {
            "title": str(parsed.get("title", f"{cleaned[:20]} Viva")).strip()[:40],
            "subject": str(parsed.get("subject", "Engineering")).strip()[:30],
            "topic": str(parsed.get("topic", "Viva Voce")).strip()[:40],
            "difficulty": difficulty,
            "language": language,
            "questions": validated_questions[:target_count],
            "source": "granite"
        }
        _prompt_cache[cache_key] = (now, res)
        return res, 200

    # Fallback to local question bank if model generation fails
    logger.warning("[granite] Validation failed or insufficient questions generated. Using offline bank.")
    fallback_res = _make_fallback_result(cleaned, difficulty, language, target_count)
    fallback_res["source"] = "fallback"
    _prompt_cache[cache_key] = (now, fallback_res)
    return fallback_res, 200


def _make_fallback_result(prompt: str, difficulty: str, language: str, count: int) -> dict:
    """Create structured viva result from offline question bank."""
    # Detect subject in prompt
    p_low = prompt.lower()
    subject = "Computer Science"
    if "dbms" in p_low or "database" in p_low or "sql" in p_low:
        subject = "DBMS"
    elif "os" in p_low or "operating system" in p_low:
        subject = "Operating Systems"
    elif "network" in p_low or "tcp" in p_low or "udp" in p_low:
        subject = "Computer Networks"
    elif "data structure" in p_low or "tree" in p_low or "graph" in p_low:
        subject = "Data Structures"

    questions = get_bank_questions(subject, n=count)
    return {
        "title": f"{subject} Oral Exam",
        "subject": subject,
        "topic": prompt[:30],
        "difficulty": difficulty,
        "language": language,
        "questions": questions,
        "source": "fallback"
    }


def generate_questions(subject: str, level: str = "undergraduate", n: int = 5) -> list[dict]:
    """Compatibility wrapper for question generation."""
    res, _ = preview_viva_from_prompt(f"{subject} {level} viva exam", count=n)
    return res.get("questions", get_bank_questions(subject, n))


def _keyword_grade(question: dict, transcript: str) -> dict:
    """Deterministic keyword-based grading fallback when offline or on API failure."""
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
    length_bonus = min(len(words) / 30.0, 1.0) * 1.5

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
    """Grade viva answer using IBM Granite rubric prompt with deterministic keyword fallback."""
    if Config.MOCK_MODE or not Config.IBM_API_KEY:
        return _keyword_grade(question, transcript)

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
