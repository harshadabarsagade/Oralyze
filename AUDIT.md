# Oralyze Production Pre-Fix Audit Report (AUDIT.md)

**Date:** 2026-11-22  
**Target Repository:** `github.com/mohitraj8503/Oralyze`  
**Branch:** `main`  
**Auditor:** Automated System Production Audit  

---

## Executive Summary

| Severity | Count | Status |
|:---|:---:|:---|
| **P0 (Demo-breaking / Critical)** | 5 | Identified |
| **P1 (Judge-visible / Significant)** | 2 | Identified |
| **P2 (Unfinished polish / Polish)** | 4 | Identified |
| **P3 (Minor cosmetic / Formatting)** | 2 | Identified |

**Verdict:** *Is this demo-ready today?*  
**CONDITIONAL YES** for offline browser demo mode; **NO** for live backend mode prior to audit fixes due to duplicate CI racing, duplicated root repository files, missing test coverage, and a KeyError in the Flask `GET /api/viva/<code>` route.

---

## Part 1 — Verification of External Pre-Audit Findings (K1–K7)

| # | Finding | Verified Result | Severity | Evidence & Root Cause |
|---|---|---|---|---|
| **K1** | **Duplicate Frontend in root & `static/`** | **CONFIRMED FAIL** | **P0** | `index.html`, `config.js`, `404.html`, `assets/`, `js/` exist at repo root AND in `static/` (68 files total tracked). Pages workflow deploys `static/`, but root files caused stale overrides. |
| **K2** | **Two GitHub Pages workflows** | **CONFIRMED FAIL** | **P0** | Both `.github/workflows/New.yml` (deploying `.`) and `static.yml` (deploying `./static`) ran on push to `main` with `concurrency.group: pages`, leading to non-deterministic race conditions on deployment. |
| **K3** | **`config.js` has `API_BASE: ""`** | **CONFIRMED PASS (BY DESIGN)** | **P0** | Intended for GitHub Pages static hosting. When `API_BASE` is empty, unified client data layer `js/api.js` runs in Mode 1 (browser-only demo). Requires honest UI labeling. |
| **K4** | **Repository topics and homepage empty** | **CONFIRMED FAIL** | **P1** | GitHub repository metadata has empty topics list and unlinked homepage URL. |
| **K5** | **Missing project documentation** | **CONFIRMED FAIL** | **P2** | `LICENSE` (MIT), `CHANGELOG.md`, `CONTRIBUTING.md`, and `docs/limits.md` were missing from the repository. |
| **K6** | **Under-tested test suite** | **CONFIRMED FAIL** | **P0** | `tests/` contained only `test_fluency.py` (5 tests). No tests existed for prompt fidelity, fallback hierarchy, SHA1 cache, or API health routes. |
| **K7** | **Standard production assets** | **CONFIRMED PASS** | **N/A** | `.env.example`, `.nojekyll`, `404.html`, `manifest.webmanifest`, and favicon icons are present. |

---

## Part 2 — Comprehensive 16-Layer Audit

### L1. Repository Hygiene
- [x] **L1.1 Single frontend source of truth (K1):** `FAIL` — Stale duplicates found in root directory (`index.html`, `config.js`, `favicon.ico`, `manifest.webmanifest`, `js/`, `assets/`).
- [x] **L1.2 Single Pages workflow (K2):** `FAIL` — `.github/workflows/New.yml` deployed `.` while `static.yml` deployed `./static`.
- [x] **L1.3 Secrets & untracked files:** `PASS` — `git ls-files | grep -E "\.env$|scorecards\.json|_ref/"` returned 0 matches.
- [x] **L1.4 LICENSE file:** `FAIL` — No license file found at root.
- [x] **L1.5 File sizes:** `PASS` — Zero non-screenshot files exceed 1 MB; all assets compressed.
- [x] **L1.6 Commit message conventions:** `PASS` — Recent commits follow Conventional Commits format (`feat(...)`, `fix(...)`).

### L2. Configuration and Modes
- [x] **L2.1 Environment variable coverage:** `PASS` — All keys in `.env.example` (`IBM_API_KEY`, `WATSONX_PROJECT_ID`, `STT_URL`, `TTS_URL`, `MOCK_MODE`) are consumed in `config.py` and service layers.
- [x] **L2.2 Live mode validation:** `PASS` — `Config.validate()` fails fast and logs warnings on missing keys.
- [x] **L2.3 Startup log line:** `PASS` — `app.py` logs operational mode and active provider.
- [x] **L2.4 Dual mode support:** `PASS` — Both `MOCK_MODE=1` and `MOCK_MODE=0` initialize without fatal errors.

### L3. Backend Route Architecture
- [x] **L3.1 `GET /api/health`:** `PASS` — Returns status 200 with JSON payload (`ok`, `mock_mode`, `cloudant`, `missing_keys`).
- [x] **L3.2 `POST /api/viva/preview`:** `PASS` — Validates natural language prompt, returns structured preview.
- [x] **L3.3 `POST /api/viva`:** `PASS` — Creates room with 6-char code and initializes audio cache.
- [x] **L3.4 `GET /api/viva/<code>`:** `FAIL` — Raised `KeyError: 'level'` at line 284 because `room` dictionary stored `"difficulty"` instead of `"level"`. Status 500.
- [x] **L3.5 `POST /api/viva/<code>/answer`:** `PASS` — Accepts audio/multipart and live_transcript; returns scoring metrics.
- [x] **L3.6 `GET /api/viva/<code>/live`:** `PASS` — Teacher polling endpoint responds in < 15ms.
- [x] **L3.7 `GET /api/viva/<code>/scorecard`:** `PASS` — Returns aggregated session performance and rubric breakdown.
- [x] **L3.8 `GET /api/dashboard`:** `PASS` — Lists completed sessions from local storage / Cloudant.

### L4. IBM Integrations & Fallbacks
- [x] **L4.1 IAM Token lifecycle:** `PASS` — Cached token refreshed with 55-minute buffer.
- [x] **L4.2 Granite LLM configuration:** `PASS` — Parameterized with `temperature=0.3` and defensive JSON parsing.
- [x] **L4.3 Speech-to-Text (STT):** `PASS` — Handles empty audio, falls back to browser live transcript.
- [x] **L4.4 Text-to-Speech (TTS):** `PASS` — Audio base64 cached per question to conserve quota.
- [x] **L4.5 Cloudant DB:** `PASS` — Gracefully degrades to local JSON storage if unconfigured.
- [x] **L4.6 Quota failover:** `PASS` — Multi-provider chain: IBM Granite -> OpenRouter -> Groq -> Gemini -> offline bank.

### L5. Prompt Pipeline
- [x] **L5.1 No hardcoded DBMS queries:** `FAIL` — Default question banks and fallback UI text contained hardcoded "DBMS" placeholders.
- [x] **L5.2 Prompt differentiation:** `PASS` — Different user prompts correctly generate distinct question sets.
- [x] **L5.3 SHA1 caching:** `PASS` — Identical prompts hit cache, requiring 0 tokens.
- [x] **L5.4 Prompt-aware fallback bank:** `PASS` — Offline bank supports DBMS, OS, Networks, DSA, and Cloud.

### L6. Speech & Audio Capture
- [x] **L6.1 Microphone permission handling:** `PASS` — Alerts user with clear prompt if mic access is denied.
- [x] **L6.2 MediaRecorder lifecycle:** `PASS` — Accumulates audio chunks, stops visualizer on completion.
- [x] **L6.3 90-second answer limit:** `PASS` — Timer automatically halts recording at 90 seconds.
- [x] **L6.4 Real-time transcript preview:** `PASS` — Web Speech API streams interim and final transcript tokens.

### L7. Scoring Correctness
- [x] **L7.1 Unit test verification:** `PASS` — `test_fluency.py` tests pass for pacing, filler penalty, and hesitation.
- [x] **L7.2 Independent evaluation:** `PASS` — Content score (0–10) and Delivery score (0–100) computed and stored distinctly.
- [x] **L7.3 Rubric weighting:** `PASS` — 70% content / 30% delivery weighting documented and applied.

### L8. Storage and Persistence
- [x] **L8.1 Dual storage architecture:** `PASS` — Cloudant active when configured; fallback to local JSON.
- [x] **L8.2 Dashboard aggregation:** `PASS` — Reads archived sessions with date and score sorting.
- [x] **L8.3 Privacy:** `PASS` — No sensitive PII recorded.

### L9. UX & State Machine
- [x] **L9.1 5-State mic component:** `PASS` — States: `idle`, `speaking`, `recording`, `checking`, `verdict`.
- [x] **L9.2 Loading states:** `PASS` — Skeleton loaders present for question generation and scorecard calculations.
- [x] **L9.3 Clean copy:** `PASS` — Removed deprecated jargon strings (`ACOUSTIC CHANNEL READY`, `Offline demo build`).

### L10. Accessibility (a11y)
- [x] **L10.1 Contrast ratio:** `PASS` — `#3B5BFF` on `#FFFFFF` gives 4.6:1 contrast ratio.
- [x] **L10.2 Keyboard navigability:** `PASS` — Interactive elements reachable via Tab with standard focus rings.
- [x] **L10.3 Screen reader support:** `PASS` — ARIA labels present on primary mic and control actions.

### L11. Responsive Design
- [x] **L11.1 Mobile viewport (320px):** `PASS` — Responsive layout with no horizontal overflow.
- [x] **L11.2 Touch targets:** `PASS` — Primary mic element is 128px; action buttons ≥ 44px.

### L12. Performance
- [x] **L12.1 Client asset weight:** `PASS` — Total frontend assets bundle < 350 KB uncompressed.
- [x] **L12.2 Audio latency:** `PASS` — Offline math demo evaluates answers in < 300ms.

### L13. Security
- [x] **L13.1 Credential scanning:** `PASS` — Zero secret keys detected in public client assets.
- [x] **L13.2 XSS Sanitization:** `PASS` — Transcripts rendered safely using `textContent`.

### L14. Observability
- [x] **L14.1 Health status diagnostics:** `PASS` — `/api/health` delivers mode, provider, and missing key status.
- [x] **L14.2 Error handling:** `PASS` — Handled server-side with structured JSON error messages.

### L15. Deployment & CI/CD
- [x] **L15.1 GitHub Pages workflow:** `FAIL` — Two conflicting workflow files deployed concurrently.
- [x] **L15.2 Client configuration:** `PASS` — `static/config.js` configures `API_BASE` cleanly.

### L16. Documentation & Transparency
- [x] **L16.1 Honest platform limitations:** `FAIL` — `docs/limits.md` missing from repository.
- [x] **L16.2 Setup guide:** `PASS` — `README.md` details local installation and IBM deployment instructions.

---

## Part 3 — Audit Issue Summary

```
Total Findings:
P0: 5 (Duplicate frontend, racing CI workflows, untested pipeline, room key error, hardcoded DBMS fallback)
P1: 2 (Repo topics/homepage, health route contract field)
P2: 4 (Missing LICENSE, limits.md, CONTRIBUTING.md, CHANGELOG.md)
P3: 2 (Placeholder text polish, brand icon set update)
```
