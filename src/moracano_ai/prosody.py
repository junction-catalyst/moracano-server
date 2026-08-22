import numpy as np
import parselmouth


def load_sound(path: str) -> parselmouth.Sound:
    return parselmouth.Sound(path)


def speech_end(samples: np.ndarray, sample_rate: int, after: float, drop_db: float = 20.0) -> float | None:
    # 마지막 음절은 다음 음절 onset이 없어 CTC로는 끝을 못 잡는다. `after`(마지막 음절 onset) 이후 intensity가
    # 피크 대비 drop_db 아래로 떨어지기 직전 시각을 발화 끝으로 본다. AI-Hub 503발화에서 MFA 대비 오차 중앙값
    # 142ms → 45ms(20dB가 부호 편향 0으로 최적, 15dB는 -10ms, 25dB는 +25ms)
    sound = parselmouth.Sound(samples.astype(np.float64), sampling_frequency=sample_rate)
    intensity = sound.to_intensity(minimum_pitch=75.0, time_step=0.005)
    times, values = intensity.xs(), intensity.values[0]
    tail = times >= after
    if not tail.any():
        return None
    loud = tail & (values >= values[tail].max() - drop_db)
    return float(times[loud].max())


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


def segment_track(times: np.ndarray, f0: np.ndarray, start: float, end: float) -> tuple[np.ndarray, np.ndarray]:
    mask = (times >= start) & (times < end) & ~np.isnan(f0)
    return times[mask], f0[mask]


def semitones(f0: np.ndarray, reference: float) -> np.ndarray:
    # Hz 기울기는 목소리가 높은 화자일수록 같은 억양에도 값이 커진다. 발화 중앙값 F0 기준 반음으로 바꾸면
    # 남녀·개인 차이가 빠지고 청각적 크기에 비례한다
    return 12 * np.log2(f0 / reference)


def slope_per_sec(times: np.ndarray, values: np.ndarray) -> float:
    # 끝점 두 개 차이는 F0 프레임 하나의 잡음에 흔들려서 최소제곱 기울기를 쓴다
    if len(values) < 3 or np.ptp(times) <= 0:
        return 0.0
    return float(np.polyfit(times, values, 1)[0])


def glissando_threshold(duration: float) -> float:
    # 't Hart(1976) 글리산도 역치 G = 0.16/T^2 (반음/s): 짧은 구간일수록 가파른 변화여야 음높이 이동으로
    # 들린다. 40ms 이하 구간은 역치가 발산하므로 80ms에서 cap
    return 0.16 / max(duration, 0.08) ** 2


def pitch_trend(times: np.ndarray, segment: np.ndarray, duration: float = 0.0) -> str:
    if len(segment) < 3 or duration <= 0:
        return "flat"
    slope = slope_per_sec(times, segment)
    threshold = glissando_threshold(duration)
    if slope > threshold:
        return "rising"
    if slope < -threshold:
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
