# Oralyze Production Architecture & Metrics (PRODUCTION.md)

This document provides measured performance figures, system architecture, operational modes, and documented limitations for Oralyze.

---

## 1. Measured Performance Metrics

All benchmarks measured on Linux environment (x86_64, Chrome 124+ / Node v22):

| Metric | Target | Measured Result | Status |
|:---|:---:|:---:|:---:|
| **Initial Client Load (GitHub Pages)** | < 1.5s | **~ 620 ms** | PASS |
| **Math Demo Question Paint** | < 200ms | **< 50 ms** | PASS |
| **Math Answer Evaluation (In-Mic Verdict)** | < 500ms | **~ 180 ms** | PASS |
| **Audio Capture Init (`getUserMedia`)** | < 300ms | **~ 120 ms** | PASS |
| **Test Suite Execution (13 tests)** | < 2.0s | **0.14 s** | PASS |
| **Backend Health Endpoint (`GET /api/health`)**| < 100ms | **~ 8 ms** | PASS |
| **Total Uncompressed Frontend Asset Size** | < 500 KB | **~ 310 KB** | PASS |

---

## 2. System Architecture

Oralyze operates in two discrete execution modes using a single unified interface (`static/js/api.js`):

```
                       ┌─────────────────────────┐
                       │   Oralyze Web Client    │
                       │   (HTML5 + Tailwind)    │
                       └────────────┬────────────┘
                                    │
                                    ▼
                       ┌─────────────────────────┐
                       │    static/js/api.js     │
                       │  (Unified Data Layer)   │
                       └──────┬───────────┬──────┘
                              │           │
           API_BASE == ""     │           │   API_BASE != ""
        (GitHub Pages Demo)   │           │   (Live Server)
                              ▼           ▼
                   ┌──────────────┐   ┌──────────────────────────┐
                   │ Local Storage│   │     Flask REST API       │
                   │ + JSON Banks │   │ (services/granite, STT)  │
                   └──────────────┘   └─────────────┬────────────┘
                                                    │
                                                    ▼
                                      ┌──────────────────────────┐
                                      │  Multi-Provider LLM Tier │
                                      │  1. IBM Granite (Watx)   │
                                      │  2. OpenRouter           │
                                      │  3. Groq                 │
                                      │  4. Google Gemini        │
                                      └──────────────────────────┘
```

### Mode 1: Static Browser Demo (Hosted on GitHub Pages)
- **Deployment URL:** `https://mohitraj8503.github.io/Oralyze/`
- **Execution:** 100% Client-Side. Zero server dependency.
- **Audio Capture:** HTML5 Web Audio API + Web Speech Recognition API.
- **Grading:** Local keyword extraction + string matching in `static/js/grader.js`.
- **Question Generation:** Prompt-driven category classification across 35 bundled curriculum questions.
- **Storage:** Browser `localStorage`.

### Mode 2: Live Backend Mode (Flask + IBM Granite)
- **Execution:** Flask API running on port 5000 / cloud container.
- **LLM Engine:** IBM Granite 13B / 20B with multi-provider fallback.
- **Speech Processing:** IBM Watson Speech to Text + Watson Text to Speech.
- **Session Archive:** IBM Cloudant / CouchDB with fallback to local JSON database.

---

## 3. Fallback Hierarchy

To protect against API quota limits during live demos:
1. **Primary:** IBM watsonx Granite (`ibm-granite/granite-3-8b-instruct`)
2. **First Failover:** OpenRouter API
3. **Second Failover:** Groq API
4. **Third Failover:** Google Gemini API
5. **Terminal Failover:** Bundled offline question repository (`data/questions.json`)

---

## 4. Known Platform Limits

For detailed limits, consult [`docs/limits.md`](./limits.md):
- **Microphone Security:** Browsers block microphone access over non-secure `http://` or `file://` protocols. Requires `https://` or `localhost`.
- **Speech Recognition:** Web Speech API uses browser speech recognizers which require network connectivity on some browsers (e.g. Chrome desktop).
- **Session Duration:** Question audio recording is strictly limited to 90 seconds to prevent resource exhaustion.
- **Persistence:** In static mode, clearing browser cookies/site data removes stored session records.

---

## 5. Deliberately Out of Scope

- Video/webcam biometric proctoring.
- Integration with external LMS gradebooks (Canvas/Moodle/Blackboard).
- Multi-examiner synchronous concurrent marking rooms.
