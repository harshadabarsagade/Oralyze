# ORALYZE — Phase Progress Log & Build Guide

Log of build phases and commit history for Oralyze.

| Phase | Description | Commit Message | Status |
|---|---|---|---|
| **Phase 0** | Scaffold, config template, .gitignore, dependencies, IBM setup docs | `chore: project scaffold, env template and IBM setup docs` | ✅ Completed |
| **Phase 1** | Thread-safe cached IBM IAM Bearer token management with auto-refresh | `feat(auth): cached IBM IAM token provider` | ✅ Completed |
| **Phase 2** | Offline question bank & Granite LLM question generation with fallback | `feat(granite): viva question generation with offline fallback bank` | ✅ Completed |
| **Phase 3** | Rubric-based answer grading prompt & deterministic keyword grader | `feat(granite): rubric-based answer grading with deterministic fallback` | ✅ Completed |
| **Phase 4** | Watson STT with word timestamps/confidence & Watson TTS with Hindi discovery | `feat(speech): Watson STT with word timings and TTS with voice discovery` | ✅ Completed |
| **Phase 5** | Pure fluency engine (WPM, fillers, pauses, confidence) + unit tests | `feat(fluency): pace, filler and pause scoring with unit tests` | ✅ Completed |
| **Phase 6** | Flask routes + responsive single-page frontend (mock mode end-to-end) | `feat(app): end-to-end viva flow in mock mode` | ✅ Completed |
| **Phase 7** | IBM Cloudant persistence REST service with local JSON file fallback | `feat(store): Cloudant persistence with local JSON fallback` | ✅ Completed |
| **Phase 8** | Live mode hardening: token refresh, 2 req/sec rate limiter, timeouts | `fix: live-mode hardening, timeouts and quota-safe caching` | ✅ Completed |
| **Phase 9** | Teacher dashboard, loading indicators, demo badges, print styles | `feat(ui): teacher dashboard, loading states and demo badge` | ✅ Completed |
| **Phase 10** | Comprehensive README, 3-minute demo script, deployment manifests | `docs: README, demo script and deployment config` | ✅ Completed |
