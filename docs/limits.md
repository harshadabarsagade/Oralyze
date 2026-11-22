# Oralyze — Known Limits & Out of Scope

## Demo Mode (GitHub Pages)

| Limit | Detail |
|-------|--------|
| No live AI questions | Questions come from the bundled `data/questions.json` bank |
| No audio grading | Transcript is compared to keyword lists; no IBM Speech-to-Text |
| No persistence | Sessions stored in `localStorage` only; cleared on private/incognito |
| Microphone | Requires HTTPS + user gesture; file:// protocol blocked by browsers |
| Math Demo only | The 100% offline demo uses 5 arithmetic questions only |

## Live Backend Mode (Flask + IBM Granite)

| Limit | Detail |
|-------|--------|
| IBM API keys required | `IBM_API_KEY`, `IBM_PROJECT_ID` must be set in `.env` |
| Quota fallback chain | IBM → OpenRouter → Groq → Gemini → offline bank |
| No real-time streaming | Questions generated on demand; latency ≈ 1–4s per request |
| No multi-user scaling | Single-process Flask; not production-load-tested |
| Audio grading | Requires `IBM_STT_API_KEY` + `IBM_STT_URL`; without it, falls back to Web Speech API transcript |
| Session storage | In-memory + JSON file; lost on server restart |

## Out of Scope (v0.1)

- Real-time collaborative viva (multiple examiners)
- Video proctoring
- LMS integration (Canvas, Moodle)
- Mobile native app
- Automated marking submission to grade books
