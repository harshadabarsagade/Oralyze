# Changelog

All notable changes to Oralyze are documented here.
Format: [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

---

## [Unreleased]

### P0 — Critical (demo can fail)

- **fix(ci):** Remove duplicate `New.yml` workflow that deployed entire repo root over `static/`, causing non-deterministic GitHub Pages content (`ddf81f4`)
- **fix(repo):** Remove root-level duplicate frontend files (`index.html`, `config.js`, `favicon.ico`, `manifest.webmanifest`, `404.html`, `assets/`, `js/`) — single source of truth is `static/` (`f54fa9b`)
- **fix(audio):** Define `setupVisualizer` and `teardownVisualizer` for real-time waveform capture (`8103f67`)
- **fix(recording):** Restore `startStudentRecording` with live transcript streaming and instant answer submission (`45f4a9a`)
- **fix(demo):** Fix math demo trigger; integrate in-mic animated tick/cross verdicts (`0fc024a`)

### P1 — Judge Notices

- **feat:** Complete prompt pipeline — sends user prompt to Granite, caches by SHA1, multi-provider fallback IBM → OpenRouter → Groq → Gemini → offline bank (`a612f56`)
- **feat(ui):** Smooth sliding pill indicator transition in header navigation (`edd61ed`)
- **feat:** 1-click viva link sharing via Web Share API + anti-cheating tab-switch proctoring (`86067db`)

### P2 — Looks Unfinished

- **feat(brand):** Install new blue soundwave icon; update favicon.ico, all PNG icon sizes (16/32/180/192/512), brand/logo (`c4b0ead`)
- **feat:** Add Cloud Fundamentals question bank (PaaS/IaaS/SaaS/Kubernetes/Serverless) (`86067db`)
- **fix(ui):** Remove "offline demo build" badge from header (`e4bbae7`)

---

## [0.1.0] — 2026-11-22 (Initial Demo Build)

- Flask backend with IBM Granite primary LLM
- 5-state mic UI (idle/speaking/recording/checking/verdict)
- Math Demo Mode (5 offline arithmetic questions)
- Real-time live transcript with interim tail + blinking caret
- Auto-speech synthesis (Watson TTS → Web Speech API fallback)
- Multi-provider LLM: IBM Granite → OpenRouter → Groq → Gemini
- PWA manifest + icon set + `.nojekyll`
- GitHub Pages CI/CD (`static.yml` → deploys `./static`)
- 5 fluency unit tests (all passing)
