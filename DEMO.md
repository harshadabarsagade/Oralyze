# Oralyze — 90-Second "Aura Farming" Live Demo Choreography

**Project:** Oralyze (Live AI Voice Viva Examination Room)  
**Team:** Catylitic Coders (Mohit Raj + teammates)

---

## ⏱️ Step-by-Step Stage Script

### 0:00 – 0:15 | The Contrast Setup
- **On Screen:** Laptop displaying `http://localhost:5000` (Oralyze landing page).
- **You Say:**
  > *"Class ke baaki saare projects CRUD apps hain — attendance, expenses, e-commerce. Humne banaya hai **Oralyze**: ek real-time AI voice viva room. Teacher yahan topic daalega, student phone se viva dega, aur live marks aayenge."*

### 0:15 – 0:35 | Teacher Creates Room
- Click **I'm a teacher**.
- Enter Subject: `DBMS`, Topic: `Indexing & B+ Trees`, select `3 Questions`.
- Click **Create viva**.
- Point to the generated 6-character room code (e.g. `HWXAUQ`) on screen.
- **You Say:**
  > *"Teacher ka kaam khatam — do field, ek button. Room code generate ho gaya."*

### 0:35 – 1:00 | Student Joins Live
- Turn slightly or hold up your phone (or a narrow side-by-side browser tab).
- Open `http://localhost:5000` -> Click **I'm a student**.
- Type the 6-character code into the boxes.
- Click **Join viva**.
- The laptop/phone audio articulates the question aloud.
- Click the **Microphone** and answer confidently:
  > *"Indexing in relational databases uses balanced trees like B+ trees to keep lookups logarithmic as records grow. Internal nodes store search keys while leaf nodes store data pointers."*
- **Key Moment:** Point to the screen while talking — the live words appear **in real time** as you speak. Let the room watch for 4-5 seconds.
- Click **Submit answer**.

### 1:00 – 1:20 | Real-Time Live Monitor Update
- Point back at the teacher's screen:
  > *"Teacher ko page refresh nahi karna pada. Question 1 turant mark ho gaya: Content 7.5, Delivery 88, Total 78%."*
- Click **Next question** on student tab.
- Deliberately give a hesitant, filler-heavy second answer:
  > *"Umm... like... indexing is basically... uhh... sorting pointers in B-trees... matlab... you know, to make search faster."*
- Submit and show: Content dropped to ~5.0, but **Delivery dropped** to ~60 due to detected fillers (*umm, uhh, matlab, you know*).
- **You Say:**
  > *"Marks do cheez se aate hain — kya bola, aur kaise bola. Hum dono ko alag score karte hain."*

### 1:20 – 1:30 | The Closer
- Switch teacher tab to the **Dashboard**:
  > *"Ek student nahi — poora batch. Granite ne padha, Watson ne suna aur bola, Cloudant ne yaad rakha. Chaar IBM Cloud services, zero rupaye."*

---

## 💡 Five Questions Judges Will Ask (Quick Answers)

1. **"Is this just a ChatGPT wrapper?"**  
   *Answer:* "No. We use three independent IBM services: Granite for reasoning/grading, Watson STT for speech timings, and Watson TTS for speech synthesis. The fluency analytics engine is our own pure mathematical algorithm calculated from word timestamps, with zero LLM involvement."

2. **"What if the student reads from notes or lies?"**  
   *Answer:* "Granite evaluates rubric coverage. Reading from notes also significantly alters pause and filler rhythm, penalizing the delivery score. Full visual proctoring is out of scope and we state that upfront."

3. **"What are the cost and limits?"**  
   *Answer:* "100% on IBM Cloud Lite (free forever): 300k Granite tokens, 500 STT minutes, 10k TTS characters, and 1 GB Cloudant. At 2 inference requests/second and 10 Cloudant writes/second it caps out, which is why we enforce request pacing."

4. **"Why not OpenAI Whisper?"**  
   *Answer:* "This submission is dedicated to IBM Cloud services. Furthermore, Watson STT returns native word-level timestamps and confidence intervals out-of-the-box, which are essential for our fluency analytics."

5. **"How accurate is the grading?"**  
   *Answer:* "We don't claim arbitrary accuracy percentages. We show the exact rubric, missing points, and verbatim transcripts so the examiner has full audit transparency."
