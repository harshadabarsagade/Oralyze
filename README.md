# ORALYZE — AI Voice Viva Examiner

> College minor-project web app built on IBM Cloud Lite services.

Oralyze is an AI-powered voice viva examiner. It generates subject-specific viva questions, speaks them aloud using Watson TTS, listens to student answers via Watson STT, grades conceptual correctness with IBM Granite, and analyzes delivery (speaking pace, filler words, hesitation pauses) using pure algorithmic fluency metrics. Viva scorecards are stored in IBM Cloudant with a teacher review dashboard.

---

## Architecture & Data Flow

```
+-------------------------------------------------------------+
|                       Student Browser                       |
|   (MediaRecorder WebM Audio, Audio Player, Single Page UI)  |
+------------------------------+------------------------------+
                               |
                   POST /api/answer (audio blob)
                               v
+-------------------------------------------------------------+
|                        Oralyze Flask                        |
|                                                             |
|  1. Watson STT REST API -> Transcript + Word Timestamps     |
|  2. Fluency Engine      -> WPM, Fillers, Pauses, Pace Score |
|  3. IBM Granite LLM     -> Rubric Content Score (0-10)      |
|  4. Aggregator          -> Content (70%) + Delivery (30%)   |
|  5. IBM Cloudant        -> Session Scorecard Document       |
+-------------------------------------------------------------+
```

---

## IBM Cloud Setup Instructions (Human Steps)

All services run on **IBM Cloud Lite (Always Free)** plans.

1. **Create IBM Cloud Account**: Sign up at [cloud.ibm.com](https://cloud.ibm.com/). Lite tier provides 40+ free services without credit card requirement.
2. **watsonx.ai**:
   - Create a *watsonx.ai Runtime* instance on the **Lite** plan.
   - Open watsonx.ai, create a new project.
   - Go to `Manage -> General`, copy the **Project ID**.
   - Associate the runtime service to your project.
3. **Speech to Text**:
   - In Catalog, search *Speech to Text* -> select **Lite** plan (500 mins/month free).
   - Copy the service **URL** (e.g. `https://api.us-south.speech-to-text.watson.cloud.ibm.com/instances/<id>`).
4. **Text to Speech**:
   - In Catalog, search *Text to Speech* -> select **Lite** plan (10,000 chars/month free).
   - Copy the service **URL**.
5. **Cloudant NoSQL DB**:
   - In Catalog, search *Cloudant* -> select **Lite** plan (1 GB storage, 20 reads/10 writes per sec).
   - Select Authentication method: *IAM and legacy credentials* or *IAM*.
   - Copy the service **URL** (`https://<account>.cloudantnosqldb.appdomain.cloud`).
   - In the Cloudant dashboard, create a database named `oralyze_scorecards`.
6. **IAM API Key**:
   - In IBM Cloud Console: `Manage -> Access (IAM) -> API keys -> Create`.
   - Copy the generated API key (displayed once). This single key authenticates against all four services via IAM Bearer token.

### Free Tier Quotas & Design Limits

| Service | Lite Quota | Design Implication |
|---|---|---|
| watsonx.ai Granite | 300,000 tokens / month, 2 requests/sec | Prompts kept concise; 1 call per question generation, 1 per answer grading |
| Speech to Text | 500 minutes / month | Recordings capped at 90 seconds in browser UI |
| Text to Speech | 10,000 characters / month | Synthesize once per question; in-memory audio caching |
| Cloudant | 1 GB, 20 reads / 10 writes per sec | One document per complete viva session |

---

## Quickstart (Offline / Mock Mode)

Oralyze is designed to run completely offline with **zero API keys** and zero external network calls out of the box:

```bash
git clone https://github.com/mohitraj8503/oralyze.git
cd oralyze
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open `http://localhost:5000` in your browser.
