"""Unit tests for fluency analytics mathematical calculations."""
import pytest
from services.fluency import analyze_fluency


def _make_words(count: int, duration_sec: float, fillers: list[str] = None, pauses: list[float] = None) -> list[dict]:
    """Helper to generate word timeline dicts."""
    fillers = fillers or []
    pauses = pauses or []

    words = []
    current_time = 0.0
    slot_time = duration_sec / max(count, 1)

    for i in range(count):
        word_text = fillers[i] if i < len(fillers) else f"term{i}"
        start = round(current_time, 2)
        end = round(start + (slot_time * 0.7), 2)
        words.append({
            "word": word_text,
            "start": start,
            "end": end,
            "confidence": 0.95
        })
        gap = pauses[i] if i < len(pauses) else 0.1
        current_time = end + gap

    return words


def test_clean_delivery_scores_high():
    """Clean speaker around 140 WPM, 0 fillers, no hesitation pauses -> fluency >= 85."""
    # 70 words with target duration ~30 seconds -> ~140 WPM
    words = _make_words(count=70, duration_sec=32.0)
    transcript = " ".join([w["word"] for w in words])
    res = analyze_fluency(words, transcript)

    assert 120.0 <= res["wpm"] <= 160.0
    assert res["filler_count"] == 0
    assert res["pause_count"] == 0
    assert res["pace_score"] == 100.0
    assert res["filler_score"] == 100.0
    assert res["pause_score"] == 100.0
    assert res["fluency_score"] >= 85
    assert res["band"] == "Excellent"


def test_fast_speaker_pace_penalty():
    """Speaker at >165 WPM incurs pace score reduction."""
    # 100 words in 30 seconds = 200 WPM
    words = _make_words(count=100, duration_sec=30.0)
    transcript = " ".join([w["word"] for w in words])
    res = analyze_fluency(words, transcript)

    assert res["wpm"] > 165.0
    assert res["pace_score"] < 100.0
    assert any("slow down" in hint.lower() for hint in res["hints"])


def test_slow_speaker_pace_penalty():
    """Speaker at <110 WPM incurs pace score reduction."""
    # 30 words in 30 seconds = 60 WPM
    words = _make_words(count=30, duration_sec=30.0)
    transcript = " ".join([w["word"] for w in words])
    res = analyze_fluency(words, transcript)

    assert res["wpm"] < 110.0
    assert res["pace_score"] < 100.0
    assert any("pace" in hint.lower() for hint in res["hints"])


def test_heavy_fillers_penalty():
    """Frequent fillers significantly reduce filler_score and fluency_score."""
    # 50 words with 10 fillers = 20% filler ratio
    fillers = ["um", "uh", "like", "actually", "basically", "so", "you know", "right", "uhh", "matlab"]
    words = _make_words(count=50, duration_sec=25.0, fillers=fillers)
    transcript = " ".join([w["word"] for w in words])
    res = analyze_fluency(words, transcript)

    assert res["filler_count"] >= 8
    assert res["filler_score"] < 60.0
    assert res["fluency_score"] < 85


def test_hesitation_pauses_penalty():
    """Multiple pauses >= 0.8s reduce pause_score."""
    pauses = [1.2, 0.9, 1.5, 0.2]
    words = _make_words(count=20, duration_sec=20.0, pauses=pauses)
    transcript = " ".join([w["word"] for w in words])
    res = analyze_fluency(words, transcript)

    assert res["pause_count"] >= 3
    assert res["longest_pause"] >= 1.5
    assert res["pause_score"] < 70.0
