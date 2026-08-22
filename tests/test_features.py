import numpy as np

from moracano_ai.features import build_syllables_with_trend, compute_features


def make_pitch_track():
    times = np.arange(0, 1.0, 0.01)
    f0 = np.full_like(times, 200.0)
    f0[times >= 0.8] = np.linspace(200.0, 260.0, len(f0[times >= 0.8]))  # 마지막 구간 상승
    return times, f0


def test_build_syllables_with_trend_labels_rising_tail():
    aligned = [
        {"text": "뭐", "start": 0.0, "end": 0.2},
        {"text": "노", "start": 0.8, "end": 1.0},
    ]
    times, f0 = make_pitch_track()
    syllables = build_syllables_with_trend(aligned, times, f0)
    assert syllables[0]["pitch_trend"] == "flat"
    assert syllables[1]["pitch_trend"] == "rising"


def test_compute_features_shapes():
    aligned = [
        {"text": "뭐", "start": 0.0, "end": 0.2},
        {"text": "라", "start": 0.2, "end": 0.35},
        {"text": "카", "start": 0.35, "end": 0.6},
        {"text": "노", "start": 0.6, "end": 1.0},
    ]
    times, f0 = make_pitch_track()
    features = compute_features(aligned, times, f0)
    assert features["syllable_count"] == 4
    assert features["avg_duration"] > 0
    assert features["speaking_rate"] > 0
    assert set(features) == {
        "avg_pitch", "pitch_std", "pitch_range", "pitch_slope_end",
        "syllable_count", "avg_duration", "duration_std", "npvi", "speaking_rate",
    }
