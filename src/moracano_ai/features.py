import numpy as np

from moracano_ai.prosody import npvi, pitch_trend, segment_f0, segment_track, semitones, slope_per_sec

TAIL_WINDOW_SEC = 0.2


def semitone_track(aligned: list[dict], times: np.ndarray, f0: np.ndarray) -> np.ndarray:
    utt_values = segment_f0(times, f0, aligned[0]["start"], aligned[-1]["end"])
    reference = float(np.median(utt_values)) if len(utt_values) else 1.0
    return semitones(f0, reference)


def build_syllables_with_trend(
    aligned: list[dict], times: np.ndarray, f0: np.ndarray
) -> list[dict]:
    st = semitone_track(aligned, times, f0)
    result = []
    for seg in aligned:
        seg_times, values = segment_track(times, st, seg["start"], seg["end"])
        duration = seg["end"] - seg["start"]
        result.append({**seg, "pitch_trend": pitch_trend(seg_times, values, duration=duration)})
    return result


def compute_features(aligned: list[dict], times: np.ndarray, f0: np.ndarray) -> dict:
    utt_start, utt_end = aligned[0]["start"], aligned[-1]["end"]
    utt_values = segment_f0(times, f0, utt_start, utt_end)

    durations = [seg["end"] - seg["start"] for seg in aligned]
    total_duration = utt_end - utt_start

    st = semitone_track(aligned, times, f0)
    tail_times, tail_values = segment_track(times, st, max(utt_end - TAIL_WINDOW_SEC, utt_start), utt_end)
    pitch_slope_end = round(slope_per_sec(tail_times, tail_values), 2)  # 반음/s

    return {
        "avg_pitch": round(float(np.mean(utt_values)), 2) if len(utt_values) else 0.0,
        "pitch_std": round(float(np.std(utt_values)), 2) if len(utt_values) else 0.0,
        "pitch_range": round(float(np.ptp(utt_values)), 2) if len(utt_values) else 0.0,
        "pitch_slope_end": pitch_slope_end,
        "syllable_count": len(aligned),
        "avg_duration": round(float(np.mean(durations)), 3),
        "duration_std": round(float(np.std(durations)), 3),
        "npvi": npvi(durations),
        "speaking_rate": round(len(aligned) / total_duration, 2) if total_duration > 0 else 0.0,
    }
