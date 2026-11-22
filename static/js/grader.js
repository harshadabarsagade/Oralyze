/**
 * Oralyze Keyword-Overlap Grader (Browser Runtime)
 * Matches the strict logic and scoring weights of services/granite.py `_keyword_grade`
 */
(function() {
  const FILLERS = ['um', 'uh', 'like', 'actually', 'basically', 'you know', 'sort of', 'kind of'];

  const STOP_WORDS = new Set([
    'a', 'an', 'the', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
    'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
    'do', 'does', 'did', 'can', 'could', 'shall', 'should', 'will', 'would', 'may',
    'might', 'must', 'it', 'its', 'that', 'this', 'these', 'those', 'what', 'which',
    'who', 'whom', 'why', 'how', 'from', 'up', 'about', 'into', 'over', 'after',
    'each', 'other', 'allows', 'using', 'means', 'used', 'between', 'like', 'also'
  ]);

  function normalizeText(text) {
    return (text || '').toLowerCase().replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
  }

  function wordsMatch(w1, w2) {
    if (w1 === w2) return true;
    if (w1.length >= 4 && w2.length >= 4) {
      if (w1.startsWith(w2.slice(0, 4)) || w2.startsWith(w1.slice(0, 4))) {
        // Simple character similarity
        let common = 0;
        const minLen = Math.min(w1.length, w2.length);
        for (let i = 0; i < minLen; i++) {
          if (w1[i] === w2[i]) common++;
        }
        return (common / Math.max(w1.length, w2.length)) >= 0.70;
      }
    }
    return false;
  }

  function gradeAnswer(question, transcript, language = 'en') {
    const rawTranscript = (transcript || '').trim();
    const clean = normalizeText(rawTranscript);
    const words = clean ? clean.split(' ').filter(Boolean) : [];
    const keyPoints = (question.key_points || []).map(kp => (kp || '').trim()).filter(Boolean);
    const qText = question.text || '';

    // 1. Math / exact arithmetic check
    const mathMatch = qText.match(/(\d+)\s*([\+\-\*\/×÷])\s*(\d+)/);
    if (mathMatch) {
      const a = parseInt(mathMatch[1], 10);
      const op = mathMatch[2];
      const b = parseInt(mathMatch[3], 10);
      let expectedVal = 0;
      if (op === '+') expectedVal = a + b;
      else if (op === '-' || op === '−') expectedVal = a - b;
      else if (op === '*' || op === '×') expectedVal = a * b;
      else expectedVal = b !== 0 ? Math.floor(a / b) : 0;

      const expectedStr = String(expectedVal);
      const numMap = {
        0: 'zero', 1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five',
        6: 'six', 7: 'seven', 8: 'eight', 9: 'nine', 10: 'ten', 11: 'eleven',
        12: 'twelve', 13: 'thirteen', 14: 'fourteen', 15: 'fifteen', 16: 'sixteen',
        17: 'seventeen', 18: 'eighteen', 19: 'nineteen', 20: 'twenty', 42: 'forty two'
      };
      const expectedWords = [expectedStr, numMap[expectedVal] || ''];
      const hasCorrect = words.some(w => expectedWords.includes(w));
      const digitsInTranscript = words.filter(w => /^\d+$/.test(w));

      if (hasCorrect && (digitsInTranscript.length === 0 || digitsInTranscript.includes(expectedStr))) {
        return {
          score: 10.0,
          verdict: 'correct',
          correct_points: [expectedStr],
          missing_points: [],
          incorrect_statements: [],
          irrelevant_content: [],
          feedback: `Correct numerical calculation: ${expectedStr}.`,
          ideal_answer: `The exact answer is ${expectedStr}.`
        };
      } else {
        return {
          score: 0.0,
          verdict: 'incorrect',
          correct_points: [],
          missing_points: [expectedStr],
          incorrect_statements: rawTranscript ? [`Provided '${rawTranscript}' instead of '${expectedStr}'`] : [],
          irrelevant_content: [],
          feedback: `Incorrect answer. Expected ${expectedStr}.`,
          ideal_answer: `The correct answer is ${expectedStr}.`
        };
      }
    }

    // 2. Empty or very short response
    if (words.length < 2) {
      return {
        score: 0.0,
        verdict: 'incorrect',
        correct_points: [],
        missing_points: keyPoints,
        incorrect_statements: [],
        irrelevant_content: [],
        feedback: 'No substantive spoken response detected. Please answer clearly.',
        ideal_answer: keyPoints.length ? keyPoints.join('. ') + '.' : 'A comprehensive technical explanation covering all core principles.'
      };
    }

    const contentWords = words.filter(w => !STOP_WORDS.has(w));
    if (contentWords.length === 0) {
      return {
        score: 0.0,
        verdict: 'incorrect',
        correct_points: [],
        missing_points: keyPoints,
        incorrect_statements: [],
        irrelevant_content: [rawTranscript],
        feedback: 'Answer contained no substantive technical content.',
        ideal_answer: keyPoints.length ? keyPoints.join('. ') + '.' : 'A comprehensive technical explanation covering key principles.'
      };
    }

    // 3. Relevance & Domain Filter
    const qContent = normalizeText(qText).split(' ').filter(w => !STOP_WORDS.has(w) && w.length > 1);
    const kpContent = keyPoints.flatMap(kp => normalizeText(kp).split(' ').filter(w => !STOP_WORDS.has(w) && w.length > 1));
    const domainWords = new Set([...qContent, ...kpContent]);

    const hasDomainOverlap = contentWords.some(cw => {
      for (const dw of domainWords) {
        if (wordsMatch(cw, dw)) return true;
      }
      return false;
    });

    if (!hasDomainOverlap) {
      return {
        score: 0.0,
        verdict: 'incorrect',
        correct_points: [],
        missing_points: keyPoints,
        incorrect_statements: [],
        irrelevant_content: [rawTranscript],
        feedback: 'The answer is completely unrelated to the question asked.',
        ideal_answer: keyPoints.length ? keyPoints.join('. ') + '.' : 'A comprehensive technical explanation covering key principles.'
      };
    }

    // 4. Individual Key Concept Evaluation
    const correctPoints = [];
    const missingPoints = [];

    for (const kp of keyPoints) {
      const kpWords = normalizeText(kp).split(' ').filter(w => !STOP_WORDS.has(w) && w.length > 1);
      if (kpWords.length === 0) continue;

      let matchedKpWords = 0;
      for (const kw of kpWords) {
        if (contentWords.some(cw => wordsMatch(cw, kw))) {
          matchedKpWords++;
        }
      }

      if (kpWords.length === 1 && matchedKpWords === 1) {
        correctPoints.push(kp);
      } else if (kpWords.length > 1 && (matchedKpWords >= 2 || (matchedKpWords / kpWords.length) >= 0.5)) {
        correctPoints.push(kp);
      } else {
        missingPoints.push(kp);
      }
    }

    // 5. Acronym / False definition check
    if (correctPoints.length === 0) {
      return {
        score: 0.0,
        verdict: 'incorrect',
        correct_points: [],
        missing_points: keyPoints,
        incorrect_statements: [`Factually incorrect or unsupported definition: '${rawTranscript}'`],
        irrelevant_content: [],
        feedback: 'The answer did not address the actual technical concepts of the question.',
        ideal_answer: keyPoints.length ? keyPoints.join('. ') + '.' : 'A comprehensive technical explanation covering key principles.'
      };
    }

    // 6. Strict Rubric Scoring (No Leniency Bonus, No Min Floor)
    const totalPts = Math.max(keyPoints.length, 1);
    const ratio = correctPoints.length / totalPts;
    let score = 0.0;
    let verdict = 'incorrect';
    let feedback = '';

    if (ratio >= 0.70) {
      score = Math.round((8.0 + (ratio - 0.70) * 6.6) * 10) / 10;
      verdict = 'correct';
      feedback = 'Solid explanation covering the essential concepts clearly.';
    } else if (ratio >= 0.30) {
      score = Math.round((4.5 + (ratio - 0.30) * 8.0) * 10) / 10;
      verdict = 'partially_correct';
      const missingHint = missingPoints.slice(0, 2).join(' and ');
      feedback = missingHint ? `Identified some essential points, but missed: ${missingHint}.` : 'Fair answer, could be more comprehensive.';
    } else {
      score = Math.round((ratio * 9.0) * 10) / 10;
      verdict = score >= 2.0 ? 'partially_correct' : 'incorrect';
      feedback = 'Answer demonstrated minimal conceptual understanding. Review the core definitions.';
    }

    score = Math.min(Math.max(score, 0.0), 10.0);

    return {
      score,
      verdict,
      correct_points: correctPoints,
      missing_points: missingPoints,
      incorrect_statements: [],
      irrelevant_content: [],
      feedback,
      ideal_answer: keyPoints.length ? keyPoints.join('. ') + '.' : 'A comprehensive technical explanation covering key principles.'
    };
  }

  function calculateDeliveryScore(wordTimestamps, durationSeconds) {
    if (!wordTimestamps || wordTimestamps.length === 0) {
      return {
        delivery_score: 0,
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
