"""Fluency Analytics Service.

PURE functions implementing the fluency scoring algorithm:
- Pace (Words Per Minute / WPM)
- Filler word & phrase detection (including Hindi/English colloquial markers)
- Pause detection and hesitation analysis
- Confidence score aggregation
- Dynamic actionable feedback hints

Zero dependencies on Flask, requests, or external globals.
"""
import re

FILLERS = {
    "um", "umm", "uh", "uhh", "hmm", "erm", "er", "ah", "aah",
    "matlab", "means", "like", "actually", "basically", "so", "okay", "right"
}

PHRASE_FILLERS = [
    "you know", "i mean", "kind of", "sort of", "that is", "you see"
]

PAUSE_THRESHOLD = 0.8  # seconds


def analyze_fluency(words: list[dict], transcript: str = "", language: str = "en") -> dict:
    """Analyze spoken answer delivery and compute fluency metrics.
    
    words format: [{"word": str, "start": float, "end": float, "confidence": float}]
    """
    n_words = len(words)
    clean_transcript = (transcript or " ".join([w.get("word", "") for w in words])).lower()

    if n_words < 2:
        return {
            "wpm": 0.0,
            "duration": 0.0,
            "filler_count": 0,
            "filler_ratio": 0.0,
            "pause_count": 0,
            "pause_total": 0.0,
            "longest_pause": 0.0,
            "confidence": 0.0,
            "pace_score": 0.0,
            "filler_score": 100.0,
            "pause_score": 100.0,
            "fluency_score": 0.0,
            "band": "Needs work",
            "hints": ["Spoken response was too short to evaluate fluency. Try speaking for at least 15-20 seconds."]
        }

    # 1. Speaking Duration & Pace (WPM)
    duration = max(0.0, words[-1]["end"] - words[0]["start"])
    if duration > 0:
        wpm = round(n_words / (duration / 60.0), 1)
    else:
        wpm = 0.0

    # 2. Filler words and phrases
    # Normalize individual tokens (strip punctuation)
    token_fillers = 0
    for w in words:
        clean_w = re.sub(r"[^\w]", "", w.get("word", "").lower())
        if clean_w in FILLERS:
            token_fillers += 1

    phrase_fillers = 0
    for phrase in PHRASE_FILLERS:
        phrase_fillers += len(re.findall(r"\b" + re.escape(phrase) + r"\b", clean_transcript))

    filler_count = token_fillers + phrase_fillers
    filler_ratio = round((filler_count / max(n_words, 1)) * 100.0, 1)

    # 3. Gaps and Hesitation Pauses
    gaps = []
    for i in range(n_words - 1):
        gap = round(words[i + 1]["start"] - words[i]["end"], 2)
        if gap > 0:
            gaps.append(gap)

    pauses = [g for g in gaps if g >= PAUSE_THRESHOLD]
    pause_count = len(pauses)
    pause_total = round(sum(pauses), 2)
    longest_pause = round(max(pauses or [0.0]), 2)

    # 4. Average Word Confidence
    confidences = [w.get("confidence", 0.9) for w in words]
    avg_conf = round((sum(confidences) / max(len(confidences), 1)) * 100.0, 1)

    # 5. Component Scoring
    # Pace score: optimal 110 - 165 WPM
    if 110.0 <= wpm <= 165.0:
        pace_score = 100.0
    else:
        delta = abs(wpm - (110.0 if wpm < 110.0 else 165.0))
        pace_score = max(0.0, round(100.0 - (delta * 1.2), 1))

    # Filler score
    filler_score = max(0.0, round(100.0 - (filler_ratio * 6.0), 1))

    # Pause score
    pause_penalty = (pause_count * 8.0) + (max(0.0, longest_pause - 0.8) * 10.0)
    pause_score = max(0.0, round(100.0 - pause_penalty, 1))

    # Combined Fluency Score (0-100)
    fluency_score = round((0.40 * pace_score) + (0.40 * filler_score) + (0.20 * pause_score))

    # Qualitative Performance Band
    if fluency_score >= 85:
        band = "Excellent"
    elif fluency_score >= 70:
        band = "Good"
    elif fluency_score >= 55:
        band = "Average"
    else:
        band = "Needs work"

    # Actionable Human Feedback Hints
    hints = []
    if wpm > 165.0:
        hints.append(f"You spoke at {wpm} wpm — slow down slightly so the examiner can follow your technical logic.")
    elif wpm < 110.0 and wpm > 0:
        hints.append(f"You spoke at {wpm} wpm — try to maintain a slightly more energetic, confident pace.")

    if filler_count > 3:
        hints.append(f"{filler_count} filler words detected ({filler_ratio}%). Try taking a silent breath instead of vocalizing fillers like 'umm' or 'actually'.")

    if pause_count >= 3:
        hints.append(f"{pause_count} hesitation pauses detected (longest was {longest_pause}s). Structuring your thoughts before speaking helps reduce dead air.")

    if not hints:
        hints.append("Great delivery! Your speaking pace, clarity, and transitions were well controlled.")

    return {
        "wpm": wpm,
        "duration": round(duration, 1),
        "filler_count": filler_count,
        "filler_ratio": filler_ratio,
        "pause_count": pause_count,
        "pause_total": pause_total,
        "longest_pause": longest_pause,
        "confidence": avg_conf,
        "pace_score": pace_score,
        "filler_score": filler_score,
        "pause_score": pause_score,
        "fluency_score": fluency_score,
        "band": band,
        "hints": hints
    }
