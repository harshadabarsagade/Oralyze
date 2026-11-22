/**
 * Oralyze Keyword-Overlap Grader (Browser Runtime)
 * Matches the exact logic and scoring weights of services/granite.py `_keyword_grade`
 */
(function() {
  const FILLERS = ['um', 'uh', 'like', 'actually', 'basically', 'you know', 'sort of', 'kind of'];

  function normalizeText(text) {
    return (text || '').toLowerCase().replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
  }

  function gradeAnswer(question, transcript, language = 'en') {
    const rawTranscript = (transcript || '').trim();
    const clean = normalizeText(rawTranscript);
    const words = clean ? clean.split(' ') : [];
    const keyPoints = (question.key_points || []).map(kp => (kp || '').trim()).filter(Boolean);

    if (words.length < 2) {
      return {
        score: 0.0,
        verdict: 'incorrect',
        correct_points: [],
        missing_points: keyPoints,
        feedback: 'No spoken response detected. Please answer orally and clearly.',
        ideal_answer: keyPoints.length ? keyPoints.join('. ') + '.' : 'A comprehensive technical explanation covering all core principles.'
      };
    }

    const correctPoints = [];
    const missingPoints = [];

    for (const kp of keyPoints) {
      const kpClean = normalizeText(kp);
      const kpTokens = kpClean.split(' ').filter(t => t.length > 2);
      let matched = false;

      if (clean.includes(kpClean)) {
        matched = true;
      } else if (kpTokens.length > 0) {
        let matchCount = 0;
        for (const token of kpTokens) {
          if (clean.includes(token)) {
            matchCount++;
          }
        }
        if (matchCount / kpTokens.length >= 0.5) {
          matched = true;
        }
      }

      if (matched) {
        correctPoints.push(kp);
      } else {
        missingPoints.push(kp);
      }
    }

    const totalPts = Math.max(keyPoints.length, 1);
    const matchedRatio = correctPoints.length / totalPts;
    const lengthBonus = Math.min(words.length / 30.0, 1.0) * 1.5;
    const rawScore = (matchedRatio * 8.5) + lengthBonus;

    let minFloor = words.length < 5 ? 1.0 : 2.5;
    let score = Math.min(Math.max(rawScore, minFloor), 10.0);
    score = Math.round(score * 10) / 10;

    let verdict = 'partially correct';
    if (score >= 7.5) {
      verdict = 'correct';
    } else if (score < 4.0) {
      verdict = 'incorrect';
    }

    let feedback = '';
    if (verdict === 'correct') {
      feedback = 'Solid explanation covering the essential concepts clearly.';
    } else if (verdict === 'partially correct') {
      const missingHint = missingPoints.slice(0, 2).join(' and ');
      feedback = missingHint ? `Good attempt, but make sure to elaborate on ${missingHint}.` : 'Fair answer, could be more comprehensive.';
    } else {
      feedback = 'The answer missed core technical elements. Review the key concepts.';
    }

    const idealAnswer = keyPoints.length ? keyPoints.join('. ') + '.' : 'A comprehensive technical explanation covering key principles.';

    return {
      score,
      verdict,
      correct_points: correctPoints,
      missing_points: missingPoints,
      feedback,
      ideal_answer: idealAnswer
    };
  }

  function calculateDeliveryScore(wordTimestamps, durationSeconds) {
    if (!wordTimestamps || wordTimestamps.length === 0) {
      return {
        delivery_score: 50,
        wpm: 120,
        filler_ratio: 0,
        filler_count: 0,
        pause_count: 0,
        pace_label: 'moderate'
      };
    }

    const totalWords = wordTimestamps.length;
    const duration = Math.max(durationSeconds || 1, 1);
    const wpm = Math.round((totalWords / duration) * 60);

    let fillerCount = 0;
    for (const item of wordTimestamps) {
      const w = normalizeText(item.word || item);
      if (FILLERS.includes(w)) fillerCount++;
    }
    const fillerRatio = Math.round((fillerCount / Math.max(totalWords, 1)) * 100);

    let pauseCount = 0;
    for (let i = 1; i < wordTimestamps.length; i++) {
      const prevEnd = wordTimestamps[i-1].end;
      const currStart = wordTimestamps[i].start;
      if (prevEnd !== undefined && currStart !== undefined && (currStart - prevEnd) > 0.8) {
        pauseCount++;
      }
    }

    // Pace penalty (ideal 110-165 wpm)
    let paceScore = 100;
    if (wpm < 110) paceScore = Math.max(40, 100 - (110 - wpm) * 0.8);
    else if (wpm > 165) paceScore = Math.max(40, 100 - (wpm - 165) * 0.8);

    const fillerScore = Math.max(30, 100 - (fillerRatio * 6));
    const pauseScore = Math.max(40, 100 - (pauseCount * 8));

    const deliveryScore = Math.round((paceScore * 0.4) + (fillerScore * 0.35) + (pauseScore * 0.25));

    let paceLabel = 'moderate';
    if (wpm < 110) paceLabel = 'hesitant';
    else if (wpm > 165) paceLabel = 'rapid';

    return {
      delivery_score: Math.min(Math.max(deliveryScore, 10), 99),
      wpm,
      filler_ratio: fillerRatio,
      filler_count: fillerCount,
      pause_count: pauseCount,
      pace_label: paceLabel
    };
  }

  window.OralyzeGrader = {
    gradeAnswer,
    calculateDeliveryScore
  };
})();
