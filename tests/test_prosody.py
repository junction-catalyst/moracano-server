import numpy as np

from moracano_ai.prosody import npvi, pitch_trend, segment_f0, speech_end


def test_speech_end_finds_where_tone_stops():
    sr = 16000
    t = np.arange(0, 1.0, 1 / sr)
    samples = np.where(t < 0.6, 0.5 * np.sin(2 * np.pi * 200 * t), 0.0)
    end = speech_end(samples.astype(np.float32), sr, after=0.3)
    assert 0.55 <= end <= 0.65


def test_speech_end_none_when_after_exceeds_audio():
    samples = np.zeros(16000, dtype=np.float32)
    assert speech_end(samples, 16000, after=5.0) is None


def test_segment_f0_filters_by_time_and_drops_nan():
    times = np.array([0.0, 0.1, 0.2, 0.3, 0.4])
    f0 = np.array([100.0, np.nan, 110.0, 120.0, 130.0])
    result = segment_f0(times, f0, 0.1, 0.4)
    assert list(result) == [110.0, 120.0]


def test_pitch_trend_rising():
    segment = np.array([100.0, 150.0])
    assert pitch_trend(segment, duration=0.2) == "rising"


def test_pitch_trend_falling():
    segment = np.array([150.0, 100.0])
    assert pitch_trend(segment, duration=0.2) == "falling"


def test_pitch_trend_flat_when_too_short():
    assert pitch_trend(np.array([100.0]), duration=0.2) == "flat"
    assert pitch_trend(np.array([]), duration=0.2) == "flat"


def test_npvi_zero_for_single_segment():
    assert npvi([0.2]) == 0.0


def test_npvi_higher_for_irregular_durations():
    regular = npvi([0.2, 0.2, 0.2, 0.2])
    irregular = npvi([0.1, 0.3, 0.15, 0.35])
    assert irregular > regular
    assert regular == 0.0
