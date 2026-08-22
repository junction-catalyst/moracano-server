# TODO: AI-Hub 레퍼런스 코퍼스로 PCA를 1회 피팅해서 나온 고정 변환행렬로 교체할 것 (docs/ai/plan.md 참고).
# 지금은 코퍼스 준비 전이라, avg_pitch/npvi 두 값을 각각 -1~1로 정규화해 좌표처럼 쓰는 임시 구현.
PLACEHOLDER_PITCH_RANGE = (100.0, 300.0)
PLACEHOLDER_NPVI_RANGE = (0.0, 80.0)


def normalize(value: float, lo: float, hi: float) -> float:
    if hi == lo:
        return 0.0
    return max(-1.0, min(1.0, 2 * (value - lo) / (hi - lo) - 1))


def placeholder_pca_coord(features: dict) -> list[float]:
    x = normalize(features["avg_pitch"], *PLACEHOLDER_PITCH_RANGE)
    y = normalize(features["npvi"], *PLACEHOLDER_NPVI_RANGE)
    return [round(x, 3), round(y, 3)]
