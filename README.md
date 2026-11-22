# ORALYZE — AI Voice Viva Examiner

> College minor-project web app built for the IBM Cloud & watsonx.ai submission.  
> **Team:** Catylitic Coders (Mohit Raj + teammates)

Oralyze transforms viva examinations using voice, generative AI, and speech analytics. It generates viva questions for technical subjects, **speaks** them aloud with Watson Text to Speech, **listens** to student answers through Watson Speech to Text, **evaluates conceptual understanding** using IBM Granite, and **scores verbal delivery** (speaking pace, filler words, hesitation pauses) with a pure algorithmic fluency engine — archiving full scorecards to IBM Cloudant with a teacher dashboard.

---

## 🏛️ System Architecture

```
+--------------------------------------------------------------------------+
|                              Student Browser                             |
|       (MediaRecorder WebM Audio, Audio Playback, Single-Page UI)         |
+------------------------------------+-------------------------------------+
                                     |
                         POST /api/answer (audio blob)
                                     v
+--------------------------------------------------------------------------+
|                              Oralyze Flask                               |
|                                                                          |
|  1. Watson Speech to Text   -> Transcript + Word Timestamps & Confidence |
|  2. Fluency Engine (Pure)   -> WPM, Filler Ratio, Hesitation Pauses      |
|  3. IBM Granite (watsonx)   -> Rubric Content Score (0-10) + Feedback    |
|  4. Aggregator              -> 70% Content + 30% Delivery Fluency        |
|  5. IBM Cloudant NoSQL      -> Complete Session Scorecard Document       |
+------------------------------------+-------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|                         Teacher Review Dashboard                         |
|           Class records, Content vs Fluency comparative bars             |
+--------------------------------------------------------------------------+
```

---

## 🚀 Key Features

- **Split Scoring (Content vs Delivery):** Evaluates *what* was said (technical knowledge) separately from *how* it was said (communication confidence).
- **Zero-Dependency Core:** Implemented using pure Python REST requests without heavy SDKs (`requests` + `flask`).
- **Resilient Offline Mock Mode:** `MOCK_MODE=1` guarantees a 100% functional live viva demo without an internet connection or API keys.
- **Microphone Safety:** Automatically caps audio recordings at 90 seconds to stay well within free tier limits.
- **Dynamic Hindi Voice Discovery:** Automatically inspects Watson TTS voices at runtime to discover regional voices without hardcoded assumptions.
- **Teacher Dashboard & Printable PDF:** Track class attempts and print standardized scorecards with browser print styling.

---

## 📋 IBM Cloud Lite Setup (Human Steps)

Oralyze is designed to run entirely on **IBM Cloud Lite (Always Free)** services:

1. **Sign up for IBM Cloud**: Create a free account at [cloud.ibm.com](https://cloud.ibm.com/).
2. **watsonx.ai**:
   - Create a *watsonx.ai Runtime* instance on the **Lite** plan.
   - Open watsonx.ai, create a new project.
   - Go to `Manage -> General` and copy your **Project ID**.
   - Associate the runtime instance with the project.
3. **Watson Speech to Text (STT)**:
   - In Catalog, create a *Speech to Text* instance on the **Lite** plan (500 minutes / month).
   - Copy the service **URL**.
4. **Watson Text to Speech (TTS)**:
   - In Catalog, create a *Text to Speech* instance on the **Lite** plan (10,000 characters / month).
   - Copy the service **URL**.
5. **IBM Cloudant NoSQL DB**:
   - In Catalog, create a *Cloudant* instance on the **Lite** plan (1 GB storage, 20 reads / 10 writes per sec).
   - Copy the service **URL** and create a database named `oralyze_scorecards`.
6. **IAM API Key**:
   - Go to `Manage -> Access (IAM) -> API keys -> Create`.
   - Copy the API Key. This single key authenticates against all four services via IBM IAM tokens.

### Free Tier Quotas & Design Limits

| Service | Lite Quota | Design Guard in Oralyze |
|---|---|---|
| watsonx.ai Granite | 300,000 tokens / month, 2 req/sec | Prompts kept concise; rate limiter enforces >= 550ms between calls |
| Speech to Text | 500 minutes / month | Recordings hard-capped at 90 seconds in browser UI |
| Text to Speech | 10,000 characters / month | Synthesizes each question once; in-memory audio caching |
| Cloudant | 1 GB, 20 reads / 10 writes per sec | One document per viva session, not per answer |

---

## ⚙️ Environment Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

| Variable | Description | Default / Example |
|---|---|---|
| `MOCK_MODE` | Set `1` for offline demo mode, `0` for live IBM calls | `1` |
| `IBM_API_KEY` | Unified IBM Cloud IAM API Key | `your_api_key` |
| `WATSONX_URL` | watsonx.ai endpoint | `https://us-south.ml.cloud.ibm.com` |
| `WATSONX_PROJECT_ID` | watsonx.ai Project ID | `your_project_id` |
| `GRANITE_MODEL_ID` | Model identifier | `ibm/granite-3-3-8b-instruct` |
| `STT_URL` | Watson Speech to Text instance URL | `https://api.us-south.speech-to-text...` |
| `TTS_URL` | Watson Text to Speech instance URL | `https://api.us-south.text-to-speech...` |
| `CLOUDANT_URL` | IBM Cloudant URL | `https://<account>.cloudantnosqldb...` |
| `CLOUDANT_DB` | Cloudant database name | `oralyze_scorecards` |
| `PORT` | Local web server port | `5000` |
| `MAX_QUESTIONS` | Maximum viva questions per session | `5` |

---

## 🏃 Quickstart

### 1. Install Dependencies
```bash
git clone https://github.com/mohitraj8503/oralyze.git
cd oralyze
python3 -m pip install -r requirements.txt
```

### 2. Run Tests
```bash
pytest -q
```

### 3. Launch Application
```bash
python3 app.py
```
Open **`http://localhost:5000`** in your browser.

> **Note on Mobile / Remote Testing:** Web browsers require **HTTPS** (or `localhost`) to access microphone hardware (`navigator.mediaDevices.getUserMedia`). For mobile access across a local network, tunnel via ngrok or deploy to Render/Railway with HTTPS.

---

## 📂 Project Structure

```
oralyze/
├── app.py                  # Flask application: REST routes, viva state machine
├── config.py               # Central environment configuration & MOCK_MODE flag
├── requirements.txt        # Minimal dependencies (flask, requests, dotenv, pytest)
├── Procfile                # Heroku / Render / Railway entrypoint
├── manifest.yml            # IBM Cloud Foundry deployment manifest
├── DEMO.md                 # 3-minute oral presentation script
├── BUILD_GUIDE.md          # Chronological phase implementation log
├── services/
│   ├── ibm_auth.py         # Thread-safe cached IAM token provider
│   ├── granite.py          # Granite LLM question generator & rubric answer grader
│   ├── speech.py           # Watson STT & TTS with dynamic Hindi voice discovery
│   ├── fluency.py          # Pure algorithmic delivery metrics (WPM, fillers, pauses)
│   └── store.py            # IBM Cloudant persistence with local JSON fallback
├── data/
│   ├── questions.json      # Offline fallback question bank
│   └── scorecards.json     # Local storage fallback (git-ignored)
├── static/
│   └── index.html          # Responsive single-page UI (dark theme, modern cards)
└── tests/
    └── test_fluency.py     # Unit tests verifying mathematical fluency scoring
```

---

## 🛡️ Limitations

1. **Ambient Noise:** Background classroom noise can affect Watson STT word confidence. Use a headset microphone in noisy environments.
2. **Spoken Dialects:** In Hindi/Hinglish mode, colloquial technical terms mixed with English code-switching are best handled with `hi-IN_BroadbandModel`.
3. **Lite Rate Limits:** Free accounts are limited to 2 watsonx requests per second; sequential question evaluation with built-in pacing prevents 429 errors.
