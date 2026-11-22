"""Oralyze Flask application.

Routes:
- GET  /                  -> Serves frontend static/index.html
- GET  /api/health        -> System health, mock mode flag, missing credentials
- POST /api/start         -> Start viva session, generate questions, return first question + audio
- GET  /api/question      -> Retrieve question by index with base64 audio
- POST /api/answer        -> Transcribe audio blob, grade content & fluency, calculate total
- GET  /api/scorecard/<id>-> Retrieve completed session scorecard
- POST /api/reset/<id>    -> Reset / terminate session

Data flow:
Browser mic -> POST /api/answer -> STT -> Transcript + Word Timings ->
Fluency Engine + Granite Grader -> Combined score (70% Content + 30% Fluency) -> Session cache.
"""
import base64
import logging
import os
import uuid
from flask import Flask, jsonify, request, send_from_directory
from config import Config
from services.fluency import analyze_fluency
from services.granite import generate_questions, grade_answer
from services.speech import synthesize, transcribe
from services import store

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger("oralyze")

app = Flask(__name__, static_folder="static")

# In-memory viva sessions
# session_id -> {
#   "session_id": str,
#   "subject": str,
#   "level": str,
#   "language": str,
#   "total": int,
#   "questions": list[dict],
#   "answers": list[dict],
#   "audio_cache": dict[int, str]  # index -> b64 mp3
# }
SESSIONS: dict[str, dict] = {}


def _get_public_question(q: dict) -> dict:
    """Strip private/grading keys from question object before sending to client."""
    return {
        "text": q.get("text", ""),
        "level": q.get("level", "understand")
    }


def _get_or_synthesize_audio(q_text: str, language: str) -> tuple[str, str]:
    """Synthesize question text to base64 MP3."""
    mp3_bytes = synthesize(q_text, language=language)
    b64 = base64.b64encode(mp3_bytes).decode("ascii")
    return b64, "audio/mp3"


@app.route("/")
def index():
    """Serve single-page application."""
    return send_from_directory("static", "index.html")


@app.route("/dashboard")
def dashboard_view():
    """Serve teacher dashboard page."""
    return send_from_directory("static", "index.html")


@app.route("/api/health", methods=["GET"])
def health_check():
    """System health check and configuration status."""
    missing = Config.missing_keys()
    cloudant_active = store.cloudant_enabled()
    return jsonify({
        "ok": True,
        "mock_mode": Config.MOCK_MODE,
        "cloudant": cloudant_active,
        "missing_keys": missing
    })


@app.route("/api/start", methods=["POST"])
def start_session():
    """Start viva session and return question 0 with synthesized audio."""
    data = request.get_json(silent=True) or {}
    subject = (data.get("subject") or "DBMS").strip()
    level = (data.get("level") or "undergraduate").strip().lower()
    language = (data.get("language") or "en").strip().lower()

    if language not in ("en", "hi"):
        language = "en"

    session_id = uuid.uuid4().hex[:8]
    n_questions = min(Config.MAX_QUESTIONS, 5)

    try:
        questions = generate_questions(subject=subject, level=level, n=n_questions)
    except Exception as e:
        logger.error("[app] Failed to generate questions: %s", e)
        return jsonify({"error": "Failed to generate viva questions"}), 500

    if not questions:
        return jsonify({"error": "No questions available for this subject"}), 400

    q0 = questions[0]
    b64_audio, mime = _get_or_synthesize_audio(q0["text"], language=language)

    SESSIONS[session_id] = {
        "session_id": session_id,
        "subject": subject,
        "level": level,
        "language": language,
        "total": len(questions),
        "questions": questions,
        "answers": [],
        "audio_cache": {0: b64_audio}
    }

    return jsonify({
        "session_id": session_id,
        "total": len(questions),
        "index": 0,
        "question": _get_public_question(q0),
        "audio_b64": b64_audio,
        "audio_mime": mime
    })


@app.route("/api/question", methods=["GET"])
def get_question():
    """Retrieve specific question by index for an ongoing session."""
    session_id = request.args.get("session_id", "").strip()
    raw_index = request.args.get("index", "0").strip()

    if not session_id or session_id not in SESSIONS:
        return jsonify({"error": "Invalid or expired session_id"}), 400

    sess = SESSIONS[session_id]
    try:
        index = int(raw_index)
    except ValueError:
        return jsonify({"error": "Invalid question index"}), 400

    if index < 0 or index >= len(sess["questions"]):
        return jsonify({"error": "Question index out of range"}), 400

    q = sess["questions"][index]
    if index in sess["audio_cache"]:
        b64_audio = sess["audio_cache"][index]
    else:
        b64_audio, _ = _get_or_synthesize_audio(q["text"], language=sess["language"])
        sess["audio_cache"][index] = b64_audio

    return jsonify({
        "session_id": session_id,
        "total": len(sess["questions"]),
        "index": index,
        "question": _get_public_question(q),
        "audio_b64": b64_audio,
        "audio_mime": "audio/mp3"
    })


@app.route("/api/answer", methods=["POST"])
def submit_answer():
    """Accept spoken audio blob, evaluate STT, content correctness and delivery fluency."""
    session_id = request.form.get("session_id", "").strip()
    raw_index = request.form.get("index", "0").strip()
    language = request.form.get("language", "").strip().lower()

    if not session_id or session_id not in SESSIONS:
        return jsonify({"error": "Invalid or expired session_id"}), 400

    sess = SESSIONS[session_id]
    try:
        index = int(raw_index)
    except ValueError:
        return jsonify({"error": "Invalid index"}), 400

    if index < 0 or index >= len(sess["questions"]):
        return jsonify({"error": "Question index out of range"}), 400

    lang = language or sess["language"]
    audio_file = request.files.get("audio")
    audio_bytes = b""
    content_type = "audio/webm"

    if audio_file:
        audio_bytes = audio_file.read()
        content_type = audio_file.content_type or "audio/webm"

    current_q = sess["questions"][index]

    # 1. Watson STT
    try:
        stt_result = transcribe(audio_bytes=audio_bytes, content_type=content_type, language=lang)
    except Exception as e:
        logger.error("[app] STT processing error: %s", e)
        stt_result = {"transcript": "", "words": []}

    transcript = stt_result.get("transcript", "").strip()
    words = stt_result.get("words", [])

    # 2. Content Grading (Granite / Keyword fallback)
    try:
        content_eval = grade_answer(question=current_q, transcript=transcript, language=lang)
    except Exception as e:
        logger.error("[app] Grading error: %s", e)
        content_eval = {
            "score": 5.0,
            "verdict": "partially correct",
            "correct_points": [],
            "missing_points": [],
            "feedback": "Answer recorded.",
            "ideal_answer": ""
        }

    # 3. Delivery Fluency Analytics
    fluency_eval = analyze_fluency(words=words, transcript=transcript, language=lang)

    # 4. Total Combined Score Calculation
    # Content score is 0-10 -> content_pct = content_score * 10
    # Delivery fluency_score is 0-100
    # total = round(0.70 * content_pct + 0.30 * fluency_score, 1)
    content_score = float(content_eval.get("score", 0.0))
    content_pct = round(content_score * 10.0, 1)
    fluency_score = float(fluency_eval.get("fluency_score", 0.0))
    total = round((0.70 * content_pct) + (0.30 * fluency_score), 1)

    has_next = (index + 1) < len(sess["questions"])

    answer_record = {
        "index": index,
        "question_text": current_q.get("text", ""),
        "transcript": transcript,
        "content": content_eval,
        "fluency": fluency_eval,
        "content_pct": content_pct,
        "total": total
    }

    # Replace or append answer record
    existing_idx = None
    for i, a in enumerate(sess["answers"]):
        if a["index"] == index:
            existing_idx = i
            break
    if existing_idx is not None:
        sess["answers"][existing_idx] = answer_record
    else:
        sess["answers"].append(answer_record)

    # Auto-save when finishing last question
    if not has_next:
        _persist_session(sess)

    return jsonify({
        "transcript": transcript,
        "content": content_eval,
        "fluency": fluency_eval,
        "total": total,
        "has_next": has_next,
        "index": index
    })


def _persist_session(sess: dict) -> None:
    """Save finalized session to Cloudant / local JSON store."""
    answers = sess.get("answers", [])
    if not answers:
        return

    n = len(answers)
    avg_content = round(sum(a["content_pct"] for a in answers) / n, 1)
    avg_fluency = round(sum(a["fluency"]["fluency_score"] for a in answers) / n, 1)
    avg_total = round(sum(a["total"] for a in answers) / n, 1)

    doc = {
        "_id": sess["session_id"],
        "session_id": sess["session_id"],
        "subject": sess["subject"],
        "level": sess["level"],
        "language": sess["language"],
        "average_content": avg_content,
        "average_fluency": avg_fluency,
        "average_total": avg_total,
        "answers": answers,
        "questions_count": len(sess["questions"])
    }
    store.save(doc)


@app.route("/api/scorecard/<session_id>", methods=["GET"])
def get_scorecard(session_id: str):
    """Retrieve full scorecard for a session."""
    session_id = session_id.strip()
    sess = SESSIONS.get(session_id)

    if sess and sess.get("answers"):
        answers = sess["answers"]
        n = len(answers)
        avg_content = round(sum(a["content_pct"] for a in answers) / n, 1)
        avg_fluency = round(sum(a["fluency"]["fluency_score"] for a in answers) / n, 1)
        avg_total = round(sum(a["total"] for a in answers) / n, 1)

        return jsonify({
            "session_id": session_id,
            "subject": sess["subject"],
            "level": sess["level"],
            "language": sess["language"],
            "questions": [_get_public_question(q) for q in sess["questions"]],
            "average_total": avg_total,
            "average_content": avg_content,
            "average_fluency": avg_fluency,
            "answers": answers,
            "saved": True
        })

    # If not in memory, check storage
    doc = store.get(session_id)
    if doc:
        return jsonify(doc)

    return jsonify({"error": "Scorecard not found"}), 404


@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    """Retrieve recent viva sessions for dashboard."""
    limit = int(request.args.get("limit", 25))
    sessions = store.recent(limit=limit)
    return jsonify({"sessions": sessions})


@app.route("/api/reset/<session_id>", methods=["POST"])
def reset_session(session_id: str):
    """Clear session from memory."""
    session_id = session_id.strip()
    if session_id in SESSIONS:
        del SESSIONS[session_id]
    return jsonify({"ok": True})


if __name__ == "__main__":
    logger.info("Starting Oralyze on port %s (Mock Mode: %s)", Config.PORT, Config.MOCK_MODE)
    app.run(host="0.0.0.0", port=Config.PORT, debug=False)
