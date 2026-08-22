# 임계값은 아직 AI-Hub 레퍼런스 코퍼스로 캘리브레이션 전이라 잠정값(placeholder).
# docs/ai/plan.md Next 항목 완료되면 이 값들을 코퍼스 통계로 교체할 것.
DEFAULT_THRESHOLDS = {
    "rising_slope_hz_per_sec": 30.0,
    "long_vowel_duration_sec": 0.25,
    "high_npvi": 40.0,
}


def generate_labels(features: dict, thresholds: dict = DEFAULT_THRESHOLDS) -> list[str]:
    labels = []
    if features["pitch_slope_end"] > thresholds["rising_slope_hz_per_sec"]:
        labels.append("Rising Intonation")
    if features["avg_duration"] > thresholds["long_vowel_duration_sec"]:
        labels.append("Long Vowel Usage")
    if features["npvi"] > thresholds["high_npvi"]:
        labels.append("Strong Rhythm Variation")
    return labels
