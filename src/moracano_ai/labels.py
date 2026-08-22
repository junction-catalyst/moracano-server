# AI-Hub 경상도 실발화 600개(10대~60대 이상, scripts/validate_alignment.py 시드 0·1)의 분포에서 잡은 값.
# 상위 25%(npvi, 음절 길이)·상위 10%(끝 기울기, 28%가 0이라 p75는 의미 없음)를 "두드러짐"으로 본다.
# 대화체 발화 기준이라 제시어 낭독 데이터가 쌓이면 다시 맞출 것. 수치는 docs/progress.md 2026-08-22 참고
DEFAULT_THRESHOLDS = {
    "rising_slope_hz_per_sec": 120.0,
    "long_vowel_duration_sec": 0.224,
    "high_npvi": 75.0,
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
