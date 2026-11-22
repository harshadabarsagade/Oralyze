from services.llm import call_llm
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
    """Call LLM dispatcher or fallback to IBM watsonx.ai text chat API for Granite."""
    # First attempt dispatcher across configured providers (IBM, OpenRouter, Groq, Gemini)
    try:
        output, provider_name = call_llm(messages, max_tokens=max_tokens, temperature=temperature)
        if output and output.strip():
            logger.info("[granite] Chat response successfully received from provider=%s", provider_name)
            return output
    except Exception as e:
        logger.warning("[granite] LLM dispatcher call failed: %s; trying direct watsonx if configured", e)

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

    has_llm_key = bool(
        (Config.IBM_API_KEY and not Config.MOCK_MODE) or
        os.getenv("GROQ_API_KEY") or
        os.getenv("GEMINI_API_KEY") or
        os.getenv("OPENROUTER_API_KEY")
    )
    if not has_llm_key:
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
    """Create structured viva result from offline question bank tailored to the exact topic."""
    p_low = prompt.lower()
    subject = "Computer Science"

    if "javascript" in p_low or "js" in p_low or "ecmascript" in p_low:
        subject = "JavaScript"
    elif "html" in p_low or "css" in p_low or "web" in p_low or "frontend" in p_low:
        subject = "HTML and CSS"
    elif "math" in p_low or "arithmetic" in p_low or "algebra" in p_low or "addition" in p_low:
        subject = "Mathematics"
    elif "dbms" in p_low or "database" in p_low or "sql" in p_low or "rdbms" in p_low:
        subject = "DBMS"
    elif "operating system" in p_low or re.search(r"\bos\b", p_low):
        subject = "Operating Systems"
    elif "network" in p_low or "tcp" in p_low or "udp" in p_low or "osi" in p_low:
        subject = "Computer Networks"
    elif "data structure" in p_low or "dsa" in p_low or "algorithm" in p_low or "graph" in p_low:
        subject = "Data Structures"
    elif "cloud" in p_low or "paas" in p_low or "iaas" in p_low or "saas" in p_low:
        subject = "Cloud Computing"
    elif "python" in p_low:
        subject = "Python"

    questions = get_bank_questions(subject, n=count)
    return {
        "title": f"{subject} Oral Exam",
        "subject": subject,
        "topic": prompt[:40],
        "difficulty": difficulty,
        "language": language,
        "questions": questions,
        "source": "fallback"
    }


def generate_questions(subject: str, level: str = "undergraduate", n: int = 5) -> list[dict]:
    """Compatibility wrapper for question generation."""
    res, _ = preview_viva_from_prompt(f"{subject} {level} viva exam", count=n)
    return res.get("questions", get_bank_questions(subject, n))


def _words_match(w1: str, w2: str) -> bool:
    """Fuzzy/prefix match two words allowing for plural, tense, and form variations."""
    import difflib
    if w1 == w2:
        return True
    if len(w1) >= 4 and len(w2) >= 4:
        if w1.startswith(w2[:4]) or w2.startswith(w1[:4]):
            ratio = difflib.SequenceMatcher(None, w1, w2).ratio()
            return ratio >= 0.70
    return False


def _keyword_grade(question: dict, transcript: str) -> dict:
    """Deterministic strict keyword-based grading fallback adhering to academic viva rubrics.

    Rules:
    - Max score: 10.0, Min score: 0.0
    - Wrong, irrelevant, nonsense, or empty answers receive 0.0 marks and verdict 'incorrect'
    - NO leniency bonus (speaking length does not award points)
    - NO minimum score floor
    - Key points evaluated individually for genuine conceptual understanding
    - Exact arithmetic questions checked for correct numerical value
    """
    stop_words = {
        'a', 'an', 'the', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
        'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
        'do', 'does', 'did', 'can', 'could', 'shall', 'should', 'will', 'would', 'may',
        'might', 'must', 'it', 'its', 'that', 'this', 'these', 'those', 'what', 'which',
        'who', 'whom', 'why', 'how', 'from', 'up', 'about', 'into', 'over', 'after',
        'each', 'other', 'allows', 'using', 'means', 'used', 'between', 'like', 'also'
    }

    key_points = [str(kp).strip() for kp in question.get("key_points", []) if str(kp).strip()]
    text_clean = (transcript or "").strip()
    words = re.findall(r"[a-zA-Z0-9]+", text_clean.lower())
    q_text = question.get("text", "")

    # 1. Exact arithmetic check (e.g. "What is 2 + 2?", "What is 7 + 8?")
    math_match = re.search(r"(\d+)\s*([\+\-\*\/×÷])\s*(\d+)", q_text)
    if math_match:
        a, op, b = int(math_match.group(1)), math_match.group(2), int(math_match.group(3))
        if op == '+':
            expected_val = a + b
        elif op in ('-', '−'):
            expected_val = a - b
        elif op in ('*', '×'):
            expected_val = a * b
        else:
            expected_val = a // b if b != 0 else 0

        expected_str = str(expected_val)
        num_word_map = {
            0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
            6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
            12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen", 16: "sixteen",
            17: "seventeen", 18: "eighteen", 19: "nineteen", 20: "twenty", 42: "forty-two"
        }
        expected_words = {expected_str, num_word_map.get(expected_val, "")}
        has_correct = any(w in expected_words for w in words)
        nums_in_transcript = [w for w in words if w.isdigit()]

        if has_correct and (not nums_in_transcript or expected_str in nums_in_transcript):
            return {
                "score": 10.0,
                "verdict": "correct",
                "correct_points": [expected_str],
                "missing_points": [],
                "incorrect_statements": [],
                "irrelevant_content": [],
                "feedback": f"Correct numerical calculation: {expected_str}.",
                "ideal_answer": f"The exact answer is {expected_str}."
            }
        else:
            incorrect_st = [f"Provided '{text_clean}' instead of '{expected_str}'"] if text_clean else []
            return {
                "score": 0.0,
                "verdict": "incorrect",
                "correct_points": [],
                "missing_points": [expected_str],
                "incorrect_statements": incorrect_st,
                "irrelevant_content": [],
                "feedback": f"Incorrect answer. Expected {expected_str}.",
                "ideal_answer": f"The correct answer is {expected_str}."
            }

    # 2. Empty / very short response
    if not words or len(words) < 2:
        return {
            "score": 0.0,
            "verdict": "incorrect",
            "correct_points": [],
            "missing_points": key_points,
            "incorrect_statements": [],
            "irrelevant_content": [],
            "feedback": "Answer was too brief or inaudible to demonstrate understanding.",
            "ideal_answer": f"Key concepts that should be explained: {', '.join(key_points)}."
        }

    content_words = [w for w in words if w not in stop_words]
    if not content_words:
        return {
            "score": 0.0,
            "verdict": "incorrect",
            "correct_points": [],
            "missing_points": key_points,
            "incorrect_statements": [],
            "irrelevant_content": [text_clean],
            "feedback": "Answer contained no substantive technical content.",
            "ideal_answer": f"Expected key concepts: {', '.join(key_points)}."
        }

    # 3. Off-topic & Relevance Filter
    q_content = [w for w in re.findall(r"[a-zA-Z0-9]+", q_text.lower()) if w not in stop_words]
    kp_content = [w for kp in key_points for w in re.findall(r"[a-zA-Z0-9]+", kp.lower()) if w not in stop_words]
    domain_words = set(q_content + kp_content)

    has_domain_overlap = any(any(_words_match(cw, dw) for dw in domain_words) for cw in content_words)
    if not has_domain_overlap:
        return {
            "score": 0.0,
            "verdict": "incorrect",
            "correct_points": [],
            "missing_points": key_points,
            "incorrect_statements": [],
            "irrelevant_content": [text_clean],
            "feedback": "The answer is completely unrelated to the question asked.",
            "ideal_answer": f"Key concepts that should be explained: {', '.join(key_points)}."
        }

    # 4. Evaluate each key concept individually
    correct_points = []
    missing_points = []

    for kp in key_points:
        kp_words = [w for w in re.findall(r"[a-zA-Z0-9]+", kp.lower()) if w not in stop_words]
        if not kp_words:
            continue
        matched_kp_words = sum(1 for kw in kp_words if any(_words_match(cw, kw) for cw in content_words))

        if len(kp_words) == 1 and matched_kp_words == 1:
            correct_points.append(kp)
        elif len(kp_words) > 1 and (matched_kp_words >= 2 or (matched_kp_words / len(kp_words)) >= 0.5):
            correct_points.append(kp)
        else:
            missing_points.append(kp)

    # 5. Acronym / False definition check (e.g. "API means Apple Pie Ice cream")
    if not correct_points:
        return {
            "score": 0.0,
            "verdict": "incorrect",
            "correct_points": [],
            "missing_points": key_points,
            "incorrect_statements": [f"Factually incorrect definition: '{text_clean}'"],
            "irrelevant_content": [],
            "feedback": "The answer did not address the actual technical concepts of the question.",
            "ideal_answer": f"A correct explanation should cover: {', '.join(key_points)}."
        }

    # 6. Strict scoring without leniency bonus
    total_pts = max(len(key_points), 1)
    ratio = len(correct_points) / total_pts

    if ratio >= 0.70:
        score = round(8.0 + (ratio - 0.70) * 6.6, 1)
        verdict = "correct"
        feedback = "Solid explanation covering the essential concepts clearly."
    elif ratio >= 0.30:
        score = round(4.5 + (ratio - 0.30) * 8.0, 1)
        verdict = "partially_correct"
        missing_hint = ", ".join(missing_points[:2])
        feedback = f"Identified some essential points, but missed: {missing_hint}."
    else:
        score = round(ratio * 9.0, 1)
        verdict = "partially_correct" if score >= 2.0 else "incorrect"
        feedback = "Answer demonstrated minimal conceptual understanding. Review the core definitions."

    score = min(max(score, 0.0), 10.0)
    return {
        "score": score,
        "verdict": verdict,
        "correct_points": correct_points,
        "missing_points": missing_points,
        "incorrect_statements": [],
        "irrelevant_content": [],
        "feedback": feedback,
        "ideal_answer": f"Key concepts that should be explained: {', '.join(key_points)}."
    }


def grade_answer(question: dict, transcript: str, language: str = "en") -> dict:
    """Grade viva answer using LLM rubric prompt with deterministic strict fallback."""
    words = (transcript or "").strip().split()
    if len(words) < 2:
        return _keyword_grade(question, transcript)

    has_llm_key = bool(
        (Config.IBM_API_KEY and not Config.MOCK_MODE) or
        os.getenv("GROQ_API_KEY") or
        os.getenv("GEMINI_API_KEY") or
        os.getenv("OPENROUTER_API_KEY")
    )
    if not has_llm_key:
        return _keyword_grade(question, transcript)

    prompt = f"""You are a strict academic oral viva examiner grading a student's spoken answer.

Question: {question.get('text', '')}
Expected Key Points: {json.dumps(question.get('key_points', []))}
Student's Spoken Transcript: "{transcript}"
Language: {language}

STRICT EVALUATION RULES:
1. If the answer is completely wrong, irrelevant, or nonsense (e.g. "banana is a fruit" or "API means Apple Pie Ice cream"), score MUST be 0.0 and verdict MUST be "incorrect".
2. DO NOT give marks simply for repeating a single keyword out of context.
3. DO NOT award any leniency bonus for length or speaking time.
4. Partial credit (2.0 to 7.0) is ONLY allowed if the student demonstrates genuine partial understanding of the expected concepts.
5. High marks (7.5 to 10.0) with verdict "correct" require accurate explanation of the core concepts.
6. Maximum content score is 10.0. Minimum is 0.0.

Respond ONLY with a valid JSON object matching this schema, with no markdown fences, no formatting:
{{
  "score": <float between 0.0 and 10.0>,
  "verdict": "<correct|partially_correct|incorrect>",
  "correct_points": ["<points the student mentioned correctly>"],
  "missing_points": ["<key points the student omitted>"],
  "incorrect_statements": ["<incorrect or contradictory claims made>"],
  "irrelevant_content": ["<off-topic text if any>"],
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
            if score >= 7.5:
                verdict = "correct"
            elif score >= 2.5:
                verdict = "partially_correct"
            else:
                verdict = "incorrect"

            return {
                "score": score,
                "verdict": verdict,
                "correct_points": [str(p) for p in parsed.get("correct_points", [])],
                "missing_points": [str(p) for p in parsed.get("missing_points", [])],
                "incorrect_statements": [str(s) for s in parsed.get("incorrect_statements", [])],
                "irrelevant_content": [str(i) for i in parsed.get("irrelevant_content", [])],
                "feedback": str(parsed.get("feedback", "")).strip() or "Evaluation completed.",
                "ideal_answer": str(parsed.get("ideal_answer", "")).strip() or "Review key definitions."
            }
    except Exception as e:
        logger.warning("[granite] Answer grading failed via LLM, falling back to strict keyword grader: %s", e)

    return _keyword_grade(question, transcript)
