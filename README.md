# ORALYZE — Live AI Voice Viva Examiner

> **College Minor-Project Web Application for IBM Cloud & watsonx.ai Submission**  
> **Team:** Catylitic Coders (Mohit Raj + teammates)

---

## ⚠️ IMPORTANT RUNTIME INSTRUCTION

> **`python app.py` then open http://localhost:5000 — never open `index.html` directly as `file://`!**  
> Direct `file://` execution breaks relative REST API endpoints (`/api/...`) and browser microphone security (`getUserMedia` requires `localhost` or `https://`).

---

## 🎙️ Product Overview

**Oralyze** is an interactive, live AI voice viva examination room:
1. **Teacher sets the viva** on their laptop: enters subject (e.g. `DBMS`) and topic (`Indexing & B+ Trees`), chooses questions count (3, 5, or 7), and generates a 6-character viva room code (`A7K2QX`).
2. **Student joins on phone or second tab**: enters the 6-character code, listens to the spoken viva question (via Watson TTS), and speaks their answer.
3. **Live words on screen**: as the student speaks, their transcript materializes **live on screen** in real time via speech synthesis/recognition.
4. **Instant score update**: Watson STT generates word-level timestamps, **IBM Granite** grades conceptual depth (0–10), and the fluency engine scores delivery (pace, filler words, hesitation pauses).
5. **Teacher's screen updates live**: the teacher's live monitor polls and displays the student's question progress and score cards **without a page refresh**.
6. **Class Archive**: scorecards are persisted to **IBM Cloudant NoSQL DB** with a teacher review dashboard.

---

## 🏛️ Live Viva Architecture

```
+-----------------------------------------------------------------------------------------+
|                                    TEACHER LAPTOP                                       |
|  POST /api/viva -> Room Created (Code: A7K2QX) -> Polls /api/viva/<code>/live (2s loop) |
+-------------------------------------------+---------------------------------------------+
                                            ^
                                            | Real-Time Live Feed Updates
                                            v
+-----------------------------------------------------------------------------------------+
|                                  ORALYZE FLASK BACKEND                                  |
|   1. IBM Granite LLM (watsonx.ai) : viva question generation & rubric answer grading    |
|   2. Watson Speech to Text (STT)  : audio bytes -> transcript + word timings/confidence |
|   3. Watson Text to Speech (TTS)  : question text -> synthesized audio bytes            |
|   4. Fluency Analytics Service    : pure math (WPM, filler detection, pause analysis)   |
|   5. IBM Cloudant NoSQL DB        : session scorecard archival                          |
+-------------------------------------------+---------------------------------------------+
                                            ^
                                            | Audio Blob & Live Transcript
                                            v
+-----------------------------------------------------------------------------------------+
|                                  STUDENT PHONE / TAB                                    |
|   Joins via A7K2QX -> Web Audio visualizer + Live interim transcript -> Submit Answer  |
+-----------------------------------------------------------------------------------------+
```

---

## 📋 IBM Cloud Lite Setup

All services run under **IBM Cloud Lite (Always Free)** tiers:

1. **Sign up**: Create an account on [cloud.ibm.com](https://cloud.ibm.com/).
2. **watsonx.ai**:
   - Provision a *watsonx.ai Runtime* instance on the **Lite** plan.
   - Create a project, copy **Project ID** from `Manage -> General`.
3. **Watson Speech to Text (STT)**:
   - Create *Speech to Text* on **Lite** plan (500 free minutes/month). Copy service URL.
4. **Watson Text to Speech (TTS)**:
   - Create *Text to Speech* on **Lite** plan (10,000 free chars/month). Copy service URL.
5. **IBM Cloudant**:
   - Create *Cloudant* on **Lite** plan (1 GB, 20 reads / 10 writes per sec). Copy URL and create db `oralyze_scorecards`.
6. **Unified IAM API Key**:
   - Create an API key in `Manage -> Access (IAM) -> API keys`. This single key powers all four services.

### Free Quotas & Design Limits

| Service | Lite Quota | Architectural Safeguard |
|---|---|---|
| watsonx.ai Granite | 300,000 tokens / month, 2 req/sec | Concise prompts; 550ms rate limiter prevents 429 errors |
| Speech to Text | 500 minutes / month | Recordings capped at 90 seconds in UI |
| Text to Speech | 10,000 characters / month | In-memory audio caching per question |
| Cloudant | 1 GB, 20 reads / 10 writes per sec | One document per viva session, not per question |

---

## 🏃 Quickstart

### 1. Install & Setup
```bash
git clone https://github.com/mohitraj8503/oralyze.git
cd oralyze
python3 -m pip install -r requirements.txt
cp .env.example .env
```

### 2. Verify Scoring Maths
```bash
pytest -q
```

### 3. Start Live Server
```bash
python3 app.py
```
Open **`http://localhost:5000`** in your browser.

> **Live Demo Recommendation:** Open **two browser tabs** on your laptop (or open on phone over LAN):
> - Tab 1 (Teacher): Click **I'm a teacher** -> Set topic -> click **Create viva** (leaves the live monitor running).
> - Tab 2 (Student): Open in a narrow window (phone size) -> Click **I'm a student** -> Type the 6-character code -> Speak your answer.
> - Watch Tab 1 automatically update its question feed with scores in real time!
