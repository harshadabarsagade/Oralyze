# Contributing to Oralyze

Thank you for your interest! Here's how to contribute.

## Quick Setup

```bash
git clone https://github.com/mohitraj8503/Oralyze.git
cd Oralyze
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
python app.py          # starts on http://localhost:5000
```

## Branch Strategy

- `main` — always deployable; GitHub Pages serves from `./static`
- Feature branches: `feat/<name>`, bug fixes: `fix/<name>`

## Commit Style

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(ui): add dark mode toggle
fix(audio): teardownVisualizer not called on early exit
docs: update README with backend setup
```

## Frontend Files

**All frontend files live in `./static/`.** Never add frontend files to the repo root — the GitHub Pages CI deploys only `./static`.

```
static/
  index.html          ← single-page app (all JS inline)
  config.js           ← set API_BASE here, nothing else
  js/api.js           ← unified data layer (offline + live)
  js/grader.js        ← answer grading logic
  data/questions.json ← bundled question bank
  assets/icons/       ← PWA icon set
  manifest.webmanifest
  favicon.ico
```

## Running Tests

```bash
pytest tests/ -v
```

## Reporting Bugs

Open a GitHub Issue with:
1. Steps to reproduce
2. Browser + OS
3. Console error (F12 → Console)
4. Network payload (F12 → Network → `/api/viva` → Payload)
