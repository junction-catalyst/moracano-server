from moracano_ai.labels import generate_labels


def base_features(**overrides):
    features = {
        "pitch_slope_end": 0.0,
        "avg_duration": 0.15,
        "npvi": 10.0,
    }
    features.update(overrides)
    return features


def test_no_labels_when_all_flat():
    assert generate_labels(base_features()) == []


def test_rising_intonation_label():
    labels = generate_labels(base_features(pitch_slope_end=50.0))
    assert "Rising Intonation" in labels


def test_long_vowel_usage_label():
    labels = generate_labels(base_features(avg_duration=0.3))
    assert "Long Vowel Usage" in labels


def test_strong_rhythm_variation_label():
    labels = generate_labels(base_features(npvi=60.0))
    assert "Strong Rhythm Variation" in labels


def test_multiple_labels_combine():
    labels = generate_labels(base_features(pitch_slope_end=50.0, npvi=60.0))
    assert set(labels) == {"Rising Intonation", "Strong Rhythm Variation"}
