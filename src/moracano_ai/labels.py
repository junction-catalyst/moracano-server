# AI-Hub 경상도 실발화 600개(10대~60대 이상, scripts/validate_alignment.py 시드 0·1, large 정렬 모델)의
# 분포에서 잡은 값. 상위 25%(npvi, 음절 길이)·상위 10%(끝 기울기, 18%가 0이라 p75는 의미 없음)를
# "두드러짐"으로 본다. npvi는 정렬 모델에 따라 분포가 달라지므로(base 모델이면 p75가 75) 모델을 바꾸면
# 같이 다시 잡을 것. 대화체 기준이라 제시어 낭독 데이터가 쌓이면 재캘리브레이션. docs/progress.md 참고
DEFAULT_THRESHOLDS = {
    "rising_slope_hz_per_sec": 150.0,
    "long_vowel_duration_sec": 0.23,
    "high_npvi": 58.0,
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
