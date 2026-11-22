/**
 * Oralyze Unified Data Layer (js/api.js)
 * Exposes the exact same async functions in both MODE 1 (Hosted Offline) and MODE 2 (Live API Backend).
 * Callers never need to know which mode is running.
 */
(function() {
  const SESSIONS_STORAGE_KEY = 'oralyze.sessions';
  const VIVAS_STORAGE_KEY = 'oralyze.vivas';

  function getApiBase() {
    const config = window.ORALYZE_CONFIG || {};
    return (config.API_BASE || '').trim().replace(/\/+$/, '');
  }

  function isHostedMode() {
    return !getApiBase();
  }

  function getStoredVivas() {
    try {
      return JSON.parse(localStorage.getItem(VIVAS_STORAGE_KEY) || '{}');
    } catch (e) {
      return {};
    }
  }

  function saveStoredViva(code, viva) {
    try {
      const all = getStoredVivas();
      all[code] = viva;
      localStorage.setItem(VIVAS_STORAGE_KEY, JSON.stringify(all));
    } catch (e) {
      console.warn('[OralyzeApi] Failed to save viva to localStorage', e);
    }
  }

  function getStoredSessions() {
    try {
      return JSON.parse(localStorage.getItem(SESSIONS_STORAGE_KEY) || '[]');
    } catch (e) {
      return [];
    }
  }

  function saveStoredSession(session) {
    try {
      const all = getStoredSessions();
      // Replace if existing or prepend
      const existingIdx = all.findIndex(s => s.session_id === session.session_id || s.code === session.code);
      if (existingIdx >= 0) {
        all[existingIdx] = session;
      } else {
        all.unshift(session);
      }
      localStorage.setItem(SESSIONS_STORAGE_KEY, JSON.stringify(all));
    } catch (e) {
      console.warn('[OralyzeApi] Failed to save session to localStorage', e);
    }
  }

  let bundledQuestionsCache = null;
  async function fetchBundledQuestions() {
    if (bundledQuestionsCache) return bundledQuestionsCache;
    try {
      const res = await fetch('./data/questions.json');
      if (res.ok) {
        bundledQuestionsCache = await res.json();
        return bundledQuestionsCache;
      }
    } catch (e) {
      console.warn('[OralyzeApi] Failed to fetch ./data/questions.json', e);
    }
    // Hardcoded minimal fallback bank if fetch fails
    return [
      {
        id: "q1",
        subject: "DBMS",
        topic: "Indexing and B+ Trees",
        text: "Explain what a B+ tree index is and why it is preferred over a binary search tree in relational databases.",
        bloom: "understand",
        key_points: ["disk block access optimization", "all data in leaf nodes", "leaf nodes linked sequentially", "balanced height"],
        ideal_seconds: 40
      },
      {
        id: "q2",
        subject: "DBMS",
        topic: "Transactions",
        text: "What are ACID properties in database management systems and why are they critical?",
        bloom: "understand",
        key_points: ["Atomicity all or nothing", "Consistency valid state", "Isolation concurrent transactions", "Durability committed data saved"],
        ideal_seconds: 40
      },
      {
        id: "q3",
        subject: "DBMS",
        topic: "Normalization",
        text: "Differentiate between Third Normal Form (3NF) and Boyce-Codd Normal Form (BCNF).",
        bloom: "analyze",
        key_points: ["no transitive dependency in 3NF", "determinant must be superkey in BCNF", "functional dependency preservation"],
        ideal_seconds: 45
      },
      {
        id: "q4",
        subject: "Operating Systems",
        topic: "Deadlocks",
        text: "What are the four necessary conditions for a deadlock to occur in an operating system?",
        bloom: "remember",
        key_points: ["Mutual exclusion", "Hold and wait", "No preemption", "Circular wait"],
        ideal_seconds: 35
      },
      {
        id: "q5",
        subject: "Computer Networks",
        topic: "Transport Layer",
        text: "Compare TCP and UDP in terms of reliability, overhead, and typical real-world use cases.",
        bloom: "analyze",
        key_points: ["TCP is connection oriented and reliable", "UDP is connectionless with lower latency", "3-way handshake in TCP", "UDP for streaming and gaming"],
        ideal_seconds: 40
      }
    ];
  }

  function generateRandomCode() {
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    let code = '';
    for (let i = 0; i < 6; i++) {
      code += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return code;
  }

  /**
   * Preview viva questions from prompt
   */
  async function previewViva(prompt, difficulty = 'medium', language = 'English', count = 5) {
    if (isHostedMode()) {
      const bank = await fetchBundledQuestions();
      const pLow = (prompt || '').toLowerCase();
      let matched = bank.filter(q => {
        const s = (q.subject || '').toLowerCase();
        const t = (q.topic || '').toLowerCase();
        const txt = (q.text || '').toLowerCase();
        return pLow.includes(s) || pLow.includes(t) || s.includes(pLow) || txt.includes(pLow);
      });

      if (matched.length < count) {
        matched = bank.slice(0, count);
      } else {
        matched = matched.slice(0, count);
      }

      return {
        title: `${prompt.slice(0, 25).trim() || 'Engineering'} Viva`,
        subject: prompt.slice(0, 20).trim() || 'Computer Science',
        topic: prompt.slice(0, 30).trim() || 'Technical Viva',
        difficulty,
        language,
        questions: matched.map((q, idx) => ({
          id: `q${idx + 1}`,
          index: idx,
          text: q.text,
          bloom: q.bloom || q.level || 'understand',
          key_points: q.key_points || [],
          ideal_seconds: q.ideal_seconds || 40
        })),
        source: 'browser_offline'
      };
    }

    const res = await fetch(`${getApiBase()}/api/viva/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, difficulty, language, count })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.message || 'Failed to preview viva questions');
    }
    return await res.json();
  }

  /**
   * Create a viva room
   */
  async function createViva(payload) {
    if (isHostedMode()) {
      let questions = payload.questions;
      if (!questions || !questions.length) {
        const preview = await previewViva(payload.prompt || 'Computer Science viva', payload.difficulty, payload.language, payload.count || 5);
        questions = preview.questions;
      }

      const code = generateRandomCode();
      const viva = {
        code,
        title: payload.title || `${payload.subject || 'Technical'} Viva`,
        subject: payload.subject || 'Engineering',
        topic: payload.topic || 'Oral Examination',
        difficulty: payload.difficulty || 'medium',
        language: payload.language || 'English',
        total_questions: questions.length,
        questions: questions.map((q, i) => ({
          id: q.id || `q_${i}`,
          index: i,
          text: q.text,
          bloom: q.bloom || q.level || 'understand',
          level: q.bloom || q.level || 'understand',
          key_points: q.key_points || [],
          ideal_seconds: q.ideal_seconds || 40
        })),
        status: 'waiting',
        created_at: new Date().toISOString()
      };

      saveStoredViva(code, viva);

      return {
        code,
        title: viva.title,
        subject: viva.subject,
        topic: viva.topic,
        total_questions: viva.total_questions,
        questions: viva.questions,
        language: viva.language,
        difficulty: viva.difficulty,
        status: 'waiting'
      };
    }

    const res = await fetch(`${getApiBase()}/api/viva`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || err.message || 'Failed to create viva');
    }
    return await res.json();
  }

  /**
   * Get viva room info by code
   */
  async function getViva(code) {
    const cleanCode = (code || '').toUpperCase().trim();
    if (isHostedMode()) {
      const vivas = getStoredVivas();
      const viva = vivas[cleanCode];
      if (!viva) {
        throw new Error('Viva not found. Please verify the code.');
      }
      return viva;
    }

    const res = await fetch(`${getApiBase()}/api/viva/${cleanCode}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Viva not found');
    }
    return await res.json();
  }

  /**
   * Submit an answer for grading
   */
  async function submitAnswer(code, audioBlob, liveTranscript, questionIndex = 0, wordTimestamps = null, durationSeconds = 30) {
    const cleanCode = (code || '').toUpperCase().trim();
    if (isHostedMode()) {
      const viva = await getViva(cleanCode);
      const question = viva.questions[questionIndex] || viva.questions[0];

      // Grade content in browser
      const contentResult = window.OralyzeGrader.gradeAnswer(question, liveTranscript, viva.language);
      
      // Compute delivery score
      const deliveryResult = window.OralyzeGrader.calculateDeliveryScore(wordTimestamps || liveTranscript.split(' '), durationSeconds);

      const overall = Math.round(((contentResult.score * 10) * 0.7) + (deliveryResult.delivery_score * 0.3));

      const evaluation = {
        question_id: question.id,
        question_text: question.text,
        student_transcript: liveTranscript,
        content_score: contentResult.score,
        delivery_score: deliveryResult.delivery_score,
        overall_score: overall,
        verdict: contentResult.verdict,
        feedback: contentResult.feedback,
        correct_points: contentResult.correct_points,
        missing_points: contentResult.missing_points,
        ideal_answer: contentResult.ideal_answer,
        fluency_metrics: deliveryResult,
        wpm: deliveryResult.wpm,
        filler_ratio: deliveryResult.filler_ratio,
        pause_count: deliveryResult.pause_count
      };

      // Update viva status in localStorage
      viva.answers = viva.answers || [];
      viva.answers.push(evaluation);
      viva.current_question = questionIndex + 1;
      viva.last_score = {
        content: contentResult.score,
        delivery: deliveryResult.delivery_score,
        overall: overall,
        student_transcript: liveTranscript
      };

      if (viva.current_question >= viva.total_questions) {
        viva.status = 'completed';
      } else {
        viva.status = 'in_progress';
      }
      saveStoredViva(cleanCode, viva);

      // If completed, save full session into oralyze.sessions
      if (viva.status === 'completed') {
        const avgContent = Math.round((viva.answers.reduce((acc, a) => acc + a.content_score, 0) / viva.answers.length) * 10) / 10;
        const avgDelivery = Math.round(viva.answers.reduce((acc, a) => acc + a.delivery_score, 0) / viva.answers.length);
        const overallFinal = Math.round(((avgContent * 10) * 0.7) + (avgDelivery * 0.3));

        const sessionRecord = {
          session_id: `offline_${cleanCode}_${Date.now()}`,
          code: cleanCode,
          student_name: viva.student_name || 'Candidate',
          subject: viva.subject,
          topic: viva.topic,
          date: new Date().toISOString(),
          content_score: avgContent,
          delivery_score: avgDelivery,
          overall_score: overallFinal,
          questions: viva.questions,
          answers: viva.answers
        };
        saveStoredSession(sessionRecord);
      }

      return {
        success: true,
        evaluation,
        viva_status: viva.status,
        next_question_index: viva.current_question
      };
    }

    const formData = new FormData();
    if (audioBlob) {
      formData.append('audio', audioBlob, 'answer.wav');
    }
    formData.append('code', cleanCode);
    formData.append('question_index', questionIndex);
    formData.append('transcript', liveTranscript || '');

    const res = await fetch(`${getApiBase()}/api/answer`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Failed to grade answer');
    }
    return await res.json();
  }

  /**
   * Get live viva monitor data for teacher
   */
  async function getLive(code) {
    const cleanCode = (code || '').toUpperCase().trim();
    if (isHostedMode()) {
      const viva = await getViva(cleanCode);
      return {
        code: cleanCode,
        status: viva.status || 'waiting',
        current_question: viva.current_question || 0,
        total_questions: viva.total_questions || (viva.questions ? viva.questions.length : 5),
        student_name: viva.student_name || 'Waiting for candidate...',
        last_score: viva.last_score || null,
        answers: viva.answers || []
      };
    }

    const res = await fetch(`${getApiBase()}/api/viva/${cleanCode}/live`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Failed to poll live room');
    }
    return await res.json();
  }

  /**
   * Get final scorecard by code or session_id
   */
  async function getScorecard(codeOrId) {
    const key = (codeOrId || '').trim();
    if (isHostedMode()) {
      const sessions = getStoredSessions();
      const found = sessions.find(s => s.code === key.toUpperCase() || s.session_id === key);
      if (found) return found;

      // Check in stored vivas
      const vivas = getStoredVivas();
      const viva = vivas[key.toUpperCase()];
      if (viva && viva.answers && viva.answers.length) {
        const avgContent = Math.round((viva.answers.reduce((acc, a) => acc + a.content_score, 0) / viva.answers.length) * 10) / 10;
        const avgDelivery = Math.round(viva.answers.reduce((acc, a) => acc + a.delivery_score, 0) / viva.answers.length);
        return {
          session_id: `local_${key}`,
          code: key.toUpperCase(),
          student_name: viva.student_name || 'Candidate',
          subject: viva.subject,
          topic: viva.topic,
          date: new Date().toISOString(),
          content_score: avgContent,
          delivery_score: avgDelivery,
          overall_score: Math.round(((avgContent * 10) * 0.7) + (avgDelivery * 0.3)),
          questions: viva.questions,
          answers: viva.answers
        };
      }
      throw new Error('Scorecard not found');
    }

    const res = await fetch(`${getApiBase()}/api/scorecard/${key}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Scorecard not found');
    }
    return await res.json();
  }

  /**
   * Get all past sessions for Teacher Dashboard
   */
  async function getDashboard() {
    if (isHostedMode()) {
      const sessions = getStoredSessions();
      if (!sessions || sessions.length === 0) {
        // Seed initial 3 realistic demo records if empty for a polished first look
        const seed = [
          {
            session_id: "demo_101",
            code: "A7K2QX",
            student_name: "Aarav Sharma",
            subject: "DBMS",
            topic: "Indexing & B+ Trees",
            date: "2026-11-20T10:30:00Z",
            content_score: 8.2,
            delivery_score: 88,
            overall_score: 84,
            status: "completed"
          },
          {
            session_id: "demo_102",
            code: "M3P9LT",
            student_name: "Priya Patel",
            subject: "Operating Systems",
            topic: "Deadlocks & Semaphores",
            date: "2026-11-21T14:15:00Z",
            content_score: 7.4,
            delivery_score: 79,
            overall_score: 76,
            status: "completed"
          },
          {
            session_id: "demo_103",
            code: "K8W2NZ",
            student_name: "Rohan Verma",
            subject: "Computer Networks",
            topic: "TCP/IP & Congestion Control",
            date: "2026-11-22T08:45:00Z",
            content_score: 9.0,
            delivery_score: 92,
            overall_score: 91,
            status: "completed"
          }
        ];
        localStorage.setItem(SESSIONS_STORAGE_KEY, JSON.stringify(seed));
        return { records: seed, total: seed.length, source: 'localStorage' };
      }
      return { records: sessions, total: sessions.length, source: 'localStorage' };
    }

    const res = await fetch(`${getApiBase()}/api/dashboard`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Failed to load dashboard records');
    }
    return await res.json();
  }

  // Expose global OralyzeApi
  window.OralyzeApi = {
    getApiBase,
    isHostedMode,
    previewViva,
    createViva,
    getViva,
    submitAnswer,
    getLive,
    getScorecard,
    getDashboard
  };
})();
