# Oralyze — 3-Minute Live Demo Script

**Project:** Oralyze (AI Voice Viva Examiner)  
**Team:** Catylitic Coders (Mohit Raj + teammates)  
**Target Submission:** IBM Cloud / watsonx.ai College Showcase

---

## ⏱️ Timeline & Stage Directions

### 0:00 – 0:30 | The Hook: "Sab CRUD app hain"
- **Speaker:** "Good morning judges / professors. Look at every other minor project submitted this semester: an attendance tracker, an expense manager, an online grocery store. *Sab CRUD apps hain* — simple forms that save rows to a database.
- We built **Oralyze**: an AI voice viva examiner powered by IBM Cloud. It speaks questions out loud, listens to student speech, evaluates deep conceptual understanding using **IBM Granite**, and scores speaking delivery — pace, filler words, hesitation pauses — in real time."

### 0:30 – 1:15 | Question 1: The Strong Technical Answer
- Open `http://localhost:5000` (or the deployed live URL).
- Point to the **Offline Mock / IBM Cloud** status badge in the header.
- Select `DBMS`, click **Start Viva Exam**.
- Hit **🔊 Replay Question** so the examiner hears Watson TTS articulate the viva question.
- Click the **Microphone** button and deliver a confident answer:
  > *"ACID stands for Atomicity, Consistency, Isolation, and Durability. Atomicity ensures all operations succeed or rollback. Isolation separates concurrent transactions, and durability guarantees committed data survives crashes."*
- Click **Submit Answer**.
- **Point to the Result:**
  - Content Score: **9.0 - 10 / 10** (*Correct*)
  - Delivery Fluency: **85 - 95 / 100** (*Excellent*, ~140 wpm, 0 fillers)
  - Show the examiner feedback and word timing chips.

### 1:15 – 2:00 | Question 2: The Hesitant / Flawed Answer
- Click **Next Question**.
- On Question 2, click **Microphone** and intentionally give a hesitant, filler-heavy answer:
  > *"Umm... like... indexing is basically... uhh... sorting pointers in B-trees... matlab... you know, to make search faster."*
- Click **Submit Answer**.
- **Highlight the Contrast:**
  - Notice the **Content vs Delivery split**:
  - The student gets partial credit for technical concepts (~5.0/10), but **delivery drops** to ~60/100 due to detected filler words (*umm, uhh, matlab, you know*) and hesitation gaps.
  - Show the actionable hint generated: *"4 filler words detected. Try pausing silently instead of vocalizing fillers."*

### 2:00 – 2:30 | Scorecard & Teacher Review Dashboard
- Complete or skip to the **Final Scorecard**.
- Show the **Content Average vs Delivery Average** banner and per-question breakdown.
- Click **🖨️ Print / Save PDF** to demonstrate instant university-grade report generation.
- Click the **Teacher Dashboard** tab.
- Show past student examination records retrieved from **IBM Cloudant** with side-by-side progress bars comparing technical competence vs verbal delivery.

### 2:30 – 3:00 | The Closer
- **Speaker:**
  > *"Traditional viva exams take hours of faculty time and are prone to subjective bias. Oralyze standardizes oral testing across the entire department.*
  > 
  > ***IBM Granite ne padha, Watson ne suna aur bola, aur Cloudant ne yaad rakha.***
  > 
  > *Thank you. We are ready for your questions!"*
