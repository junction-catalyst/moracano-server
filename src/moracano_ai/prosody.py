import numpy as np
import parselmouth


def load_sound(path: str) -> parselmouth.Sound:
    return parselmouth.Sound(path)


def pitch_contour(sound: parselmouth.Sound) -> tuple[np.ndarray, np.ndarray]:
    # 2-pass 추정(de Looze & Hirst 2008): 넓은 범위로 한 번 뽑아 화자의 q25/q75를 구한 뒤 그 화자에 맞는
    # floor/ceiling으로 다시 추출. 기본 75~600Hz 고정 범위에서는 AI-Hub 실발화의 35%에서 옥타브 점프가 섞였음
    first = sound.to_pitch(pitch_floor=60.0, pitch_ceiling=700.0)
    voiced = first.selected_array["frequency"]
    voiced = voiced[voiced > 0]
    if len(voiced) >= 5:
        q25, q75 = np.percentile(voiced, [25, 75])
        pitch = sound.to_pitch(pitch_floor=max(50.0, 0.75 * q25), pitch_ceiling=min(700.0, 1.5 * q75))
    else:
        pitch = first
    times = pitch.xs()
    f0 = pitch.selected_array["frequency"]
    f0 = np.where(f0 == 0, np.nan, f0)  # 0Hz는 무성구간(parselmouth 표기), 통계 계산에서 제외
    return times, f0


def segment_f0(times: np.ndarray, f0: np.ndarray, start: float, end: float) -> np.ndarray:
    mask = (times >= start) & (times < end)
    values = f0[mask]
    return values[~np.isnan(values)]


def pitch_trend(segment: np.ndarray, threshold_hz_per_sec: float = 15.0, duration: float = 0.0) -> str:
    if len(segment) < 2 or duration <= 0:
        return "flat"
    slope = (segment[-1] - segment[0]) / duration
    if slope > threshold_hz_per_sec:
        return "rising"
    if slope < -threshold_hz_per_sec:
        return "falling"
    return "flat"


def npvi(durations: list[float]) -> float:
    # Normalized Pairwise Variability Index — 인접 구간 길이차의 정규화 평균, 리듬 불규칙성 지표
    if len(durations) < 2:
        return 0.0
    diffs = []
    for a, b in zip(durations[:-1], durations[1:]):
        denom = (a + b) / 2
        if denom > 0:
            diffs.append(abs(a - b) / denom)
    return round(100 * float(np.mean(diffs)), 2) if diffs else 0.0
