"""Oralyze Flask application: Live Room Architecture.

Flow:
- Teacher creates viva room -> 6-character code (e.g. A7K2QX) + question generation.
- Teacher opens live monitor -> polls /api/viva/<code>/live every 2s.
- Student joins on phone/tab with 6-character code -> receives questions + audio.
- Student speaks answer -> browser live speech preview + Watson STT word timings.
- Answer evaluated (Granite content + fluency analytics) -> teacher's live monitor updates in real time.
- Final scorecard archived to Cloudant / local JSON store.

API endpoints:
POST /api/viva                 {subject, topic, level, language, count}
GET  /api/viva/<code>          -> viva info + questions
POST /api/viva/<code>/answer   multipart: qid, audio, language, live_transcript
GET  /api/viva/<code>/live     -> live state for teacher polling
GET  /api/viva/<code>/scorecard-> completed scorecard
GET  /api/dashboard            -> past sessions list
GET  /api/health               -> system status
"""
import base64
import datetime
import logging
import random
import string
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

# In-memory room store: code -> room dict
# code: 6 uppercase alphanumeric chars
VIVAS: dict[str, dict] = {}


def _generate_code() -> str:
    """Generate a clean 6-character alphanumeric code avoiding ambiguous chars."""
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(20):
        code = "".join(random.choices(chars, k=6))
        if code not in VIVAS:
            return code
    return uuid.uuid4().hex[:6].upper()


def _get_or_synthesize_audio(text: str, language: str) -> tuple[str, str]:
    """Synthesize question text to base64 MP3."""
    mp3_bytes = synthesize(text, language=language)
    b64 = base64.b64encode(mp3_bytes).decode("ascii")
    return b64, "audio/mp3"


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/join")
def join_redirect():
    return send_from_directory("static", "index.html")


@app.route("/dashboard")
def dashboard_view():
    return send_from_directory("static", "index.html")


@app.route("/api/health", methods=["GET"])
def health_check():
    missing = Config.missing_keys()
    cloudant_active = store.cloudant_enabled()
    return jsonify({
        "ok": True,
        "mock_mode": Config.MOCK_MODE,
        "cloudant": cloudant_active,
        "missing_keys": missing
    })


@app.route("/api/viva", methods=["POST"])
def create_viva():
    """Teacher creates a viva room with subject/topic."""
    data = request.get_json(silent=True) or {}
    subject = (data.get("subject") or "DBMS").strip()
    topic = (data.get("topic") or "").strip()
    level = (data.get("level") or "undergraduate").strip().lower()
    language = (data.get("language") or "en").strip().lower()
    try:
        count = int(data.get("count", 5))
    except (ValueError, TypeError):
        count = 5

    count = max(1, min(count, 10))
    code = _generate_code()

    # Query term combines subject and specific topic
    query = f"{subject}: {topic}" if topic else subject

    try:
        raw_questions = generate_questions(subject=query, level=level, n=count)
    except Exception as e:
        logger.error("[viva] Error generating questions: %s", e)
        return jsonify({"error": "Failed to generate viva questions"}), 500

    questions = []
    audio_cache = {}
    for idx, q in enumerate(raw_questions):
        qid = f"q_{idx}"
        q_item = {
            "id": qid,
            "index": idx,
            "text": q.get("text", ""),
            "level": q.get("level", "understand"),
            "key_points": q.get("key_points", [])
        }
        questions.append(q_item)

    # Pre-synthesize question 0 so student hears it immediately on join
    if questions:
        b64, _ = _get_or_synthesize_audio(questions[0]["text"], language)
        audio_cache[0] = b64

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    room = {
        "code": code,
        "subject": subject,
        "topic": topic,
        "level": level,
        "language": language,
        "total": len(questions),
        "questions": questions,
        "audio_cache": audio_cache,
        "status": "waiting",  # waiting -> answering -> done
        "current_index": 0,
        "student_name": "Student",
        "answers": [],
        "created_at": now_iso
    }
    VIVAS[code] = room

    # Client-safe question representations
    client_questions = [{
        "id": q["id"],
        "index": q["index"],
        "text": q["text"],
        "level": q["level"]
    } for q in questions]

    return jsonify({
        "code": code,
        "subject": subject,
        "topic": topic,
        "level": level,
        "language": language,
        "questions": client_questions,
        "total": len(questions)
    })


@app.route("/api/viva/<code>", methods=["GET"])
def get_viva(code: str):
    """Student joins and fetches viva details by 6-char code."""
    code = code.strip().upper()
    room = VIVAS.get(code)
    if not room:
        return jsonify({"error": "Viva room not found. Check the code."}), 404

    # If student is joining, update status if waiting
    if room["status"] == "waiting":
        room["status"] = "answering"

    curr_idx = room["current_index"]
    q_curr = room["questions"][curr_idx] if curr_idx < len(room["questions"]) else None

    # Fetch/cache audio for current question
    audio_b64 = ""
    if q_curr:
        if curr_idx in room["audio_cache"]:
            audio_b64 = room["audio_cache"][curr_idx]
        else:
            audio_b64, _ = _get_or_synthesize_audio(q_curr["text"], room["language"])
            room["audio_cache"][curr_idx] = audio_b64

    return jsonify({
        "code": room["code"],
        "subject": room["subject"],
        "topic": room["topic"],
        "level": room["level"],
        "language": room["language"],
        "total": room["total"],
        "current_index": curr_idx,
        "question": {
            "id": q_curr["id"],
            "index": q_curr["index"],
            "text": q_curr["text"],
            "level": q_curr["level"]
        } if q_curr else None,
        "audio_b64": audio_b64,
        "created_at": room["created_at"]
    })


@app.route("/api/viva/<code>/answer", methods=["POST"])
def submit_viva_answer(code: str):
    """Student submits an answer. Evaluates STT + Granite + Fluency. Updates room live state."""
    code = code.strip().upper()
    room = VIVAS.get(code)
    if not room:
        return jsonify({"error": "Viva room not found"}), 404

    qid = request.form.get("qid", "").strip()
    language = request.form.get("language", "").strip().lower() or room["language"]
    live_transcript = request.form.get("live_transcript", "").strip()

    # Find corresponding question
    matched_q = None
    for q in room["questions"]:
        if q["id"] == qid or str(q["index"]) == qid:
            matched_q = q
            break

    if not matched_q:
        curr_idx = room["current_index"]
        if curr_idx < len(room["questions"]):
            matched_q = room["questions"][curr_idx]
        else:
            return jsonify({"error": "Question not found"}), 400

    q_idx = matched_q["index"]

    audio_file = request.files.get("audio")
    audio_bytes = b""
    content_type = "audio/webm"
    if audio_file:
        audio_bytes = audio_file.read()
        content_type = audio_file.content_type or "audio/webm"

    # 1. Watson STT (with fallback)
    try:
        stt_result = transcribe(audio_bytes=audio_bytes, content_type=content_type, language=language)
    except Exception as e:
        logger.error("[viva] STT error: %s", e)
        stt_result = {"transcript": "", "words": []}

    transcript = stt_result.get("transcript", "").strip()
    words = stt_result.get("words", [])

    # If STT transcript was empty but browser gave a live transcript, use browser transcript as text fallback
    if not transcript and live_transcript:
        transcript = live_transcript
        if not words:
            # Construct simulated word timestamps from live transcript
            t_words = live_transcript.split()
            cur_t = 0.5
            for w in t_words:
                words.append({
                    "word": w,
                    "start": round(cur_t, 2),
                    "end": round(cur_t + 0.3, 2),
                    "confidence": 0.90
                })
                cur_t += 0.38

    # 2. Content Evaluation (Granite / Keyword fallback)
    try:
        content_eval = grade_answer(question=matched_q, transcript=transcript, language=language)
    except Exception as e:
        logger.error("[viva] Grading error: %s", e)
        content_eval = {
            "score": 5.0,
            "verdict": "partially correct",
            "correct_points": [],
            "missing_points": [],
            "feedback": "Answer recorded.",
            "ideal_answer": ""
        }

    # 3. Delivery Fluency Analytics
    fluency_eval = analyze_fluency(words=words, transcript=transcript, language=language)

    # 4. Total Combined Score
    # Content: 0-10 -> content_pct = score * 10
    # Delivery: 0-100
    # Total: 70% content + 30% delivery
    content_score = float(content_eval.get("score", 0.0))
    content_pct = round(content_score * 10.0, 1)
    fluency_score = float(fluency_eval.get("fluency_score", 0.0))
    total = round((0.70 * content_pct) + (0.30 * fluency_score), 1)

    next_index = q_idx + 1
    is_done = next_index >= room["total"]

    answer_record = {
        "qid": matched_q["id"],
        "index": q_idx,
        "question_text": matched_q["text"],
        "transcript": transcript,
        "content": content_eval,
        "delivery": fluency_eval,
        "content_pct": content_pct,
        "total": total
    }

    # Update room answers
    replaced = False
    for i, a in enumerate(room["answers"]):
        if a["qid"] == matched_q["id"]:
            room["answers"][i] = answer_record
            replaced = True
            break
    if not replaced:
        room["answers"].append(answer_record)

    room["current_index"] = next_index
    if is_done:
        room["status"] = "done"
        _persist_viva_room(room)
    else:
        room["status"] = "answering"

    return jsonify({
        "qid": matched_q["id"],
        "index": q_idx,
        "transcript": transcript,
        "content": content_eval,
        "delivery": fluency_eval,
        "total": total,
        "next_index": next_index,
        "done": is_done
    })


@app.route("/api/viva/<code>/live", methods=["GET"])
def get_viva_live(code: str):
    """Teacher's Live Monitor polls this every 2 seconds."""
    code = code.strip().upper()
    room = VIVAS.get(code)
    if not room:
        return jsonify({"error": "Viva room not found"}), 404

    # Extract clean list of answers for live feed
    clean_answers = []
    for a in room.get("answers", []):
        clean_answers.append({
            "qid": a["qid"],
            "index": a["index"],
            "question_text": a.get("question_text", ""),
            "content": a["content"],
            "delivery": a["delivery"],
            "total": a["total"]
        })

    return jsonify({
        "code": room["code"],
        "subject": room["subject"],
        "topic": room["topic"],
        "status": room["status"],  # "waiting", "answering", "done"
        "current_index": room["current_index"],
        "total": room["total"],
        "answers": clean_answers,
        "student": room.get("student_name", "Student")
    })


@app.route("/api/viva/<code>/scorecard", methods=["GET"])
def get_viva_scorecard(code: str):
    """Retrieve full scorecard for completed viva."""
    code = code.strip().upper()
    room = VIVAS.get(code)

    if room and room.get("answers"):
        answers = room["answers"]
        n = len(answers)
        avg_content = round(sum(a["content_pct"] for a in answers) / n, 1)
        avg_delivery = round(sum(a["delivery"]["fluency_score"] for a in answers) / n, 1)
        avg_total = round(sum(a["total"] for a in answers) / n, 1)

        band = "Excellent" if avg_total >= 85 else ("Good" if avg_total >= 70 else ("Average" if avg_total >= 55 else "Needs work"))

        return jsonify({
            "code": room["code"],
            "subject": room["subject"],
            "topic": room.get("topic", ""),
            "level": room.get("level", "undergraduate"),
            "language": room.get("language", "en"),
            "average_total": avg_total,
            "average_content": avg_content,
            "average_delivery": avg_delivery,
            "band": band,
            "answers": answers,
            "created_at": room["created_at"]
        })

    # Fallback to store
    doc = store.get(code)
    if doc:
        return jsonify(doc)

    return jsonify({"error": "Scorecard not found"}), 404


def _persist_viva_room(room: dict) -> None:
    """Save finalized viva room to Cloudant or local fallback."""
    answers = room.get("answers", [])
    if not answers:
        return

    n = len(answers)
    avg_content = round(sum(a["content_pct"] for a in answers) / n, 1)
    avg_delivery = round(sum(a["delivery"]["fluency_score"] for a in answers) / n, 1)
    avg_total = round(sum(a["total"] for a in answers) / n, 1)

    doc = {
        "_id": room["code"],
        "code": room["code"],
        "session_id": room["code"],
        "subject": room["subject"],
        "topic": room.get("topic", ""),
        "level": room.get("level", "undergraduate"),
        "language": room.get("language", "en"),
        "average_content": avg_content,
        "average_delivery": avg_delivery,
        "average_total": avg_total,
        "answers": answers,
        "questions_count": room["total"],
        "created_at": room["created_at"]
    }
    store.save(doc)


@app.route("/api/dashboard", methods=["GET"])
def get_dashboard():
    """Retrieve sessions for teacher dashboard."""
    limit = int(request.args.get("limit", 25))
    sessions = store.recent(limit=limit)

    clean_sessions = []
    for s in sessions:
        clean_sessions.append({
            "code": s.get("code") or s.get("_id") or s.get("session_id", ""),
            "subject": s.get("subject", "Viva"),
            "topic": s.get("topic", ""),
            "level": s.get("level", "undergraduate"),
            "date": s.get("created_at", ""),
            "avg_content": s.get("average_content", 0),
            "avg_delivery": s.get("average_delivery") or s.get("average_fluency", 0),
            "avg_total": s.get("average_total", 0),
            "count": s.get("questions_count") or len(s.get("answers", []))
        })

    return jsonify({"sessions": clean_sessions})


if __name__ == "__main__":
    logger.info("Starting Oralyze Live Viva on http://localhost:%s (Mock Mode: %s)", Config.PORT, Config.MOCK_MODE)
    app.run(host="0.0.0.0", port=Config.PORT, debug=False)
