import numpy as np

from moracano_ai.prosody import npvi, pitch_trend, segment_f0


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
