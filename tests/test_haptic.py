from moracano_ai.haptic import build_ahap_pattern


def test_flat_syllable_has_event_only_no_curve():
    syllables = [{"text": "뭐", "start": 0.0, "end": 0.2, "pitch_trend": "flat"}]
    result = build_ahap_pattern(syllables)
    assert result["Version"] == 1
    assert len(result["Pattern"]) == 1
    assert "Event" in result["Pattern"][0]


def test_rising_syllable_adds_parameter_curve():
    syllables = [{"text": "노", "start": 0.6, "end": 0.8, "pitch_trend": "rising"}]
    result = build_ahap_pattern(syllables)
    assert len(result["Pattern"]) == 2
    assert "ParameterCurve" in result["Pattern"][1]
    points = result["Pattern"][1]["ParameterCurve"]["ParameterCurveControlPoints"]
    assert points[1]["ParameterValue"] > points[0]["ParameterValue"]


def test_falling_syllable_curve_decreases():
    syllables = [{"text": "카", "start": 0.3, "end": 0.6, "pitch_trend": "falling"}]
    result = build_ahap_pattern(syllables)
    points = result["Pattern"][1]["ParameterCurve"]["ParameterCurveControlPoints"]
    assert points[1]["ParameterValue"] < points[0]["ParameterValue"]


def test_event_parameters_within_valid_range():
    syllables = [
        {"text": "뭐", "start": 0.0, "end": 0.18, "pitch_trend": "flat"},
        {"text": "카", "start": 0.18, "end": 0.61, "pitch_trend": "falling"},
    ]
    result = build_ahap_pattern(syllables)
    for item in result["Pattern"]:
        if "Event" in item:
            for param in item["Event"]["EventParameters"]:
                assert 0.0 <= param["ParameterValue"] <= 1.0
