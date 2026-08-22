import numpy as np

from moracano_ai.prosody import npvi, pitch_trend, segment_f0


def build_syllables_with_trend(
    aligned: list[dict], times: np.ndarray, f0: np.ndarray
) -> list[dict]:
    result = []
    for seg in aligned:
        values = segment_f0(times, f0, seg["start"], seg["end"])
        duration = seg["end"] - seg["start"]
        result.append({**seg, "pitch_trend": pitch_trend(values, duration=duration)})
    return result


def compute_features(aligned: list[dict], times: np.ndarray, f0: np.ndarray) -> dict:
    utt_start, utt_end = aligned[0]["start"], aligned[-1]["end"]
    utt_values = segment_f0(times, f0, utt_start, utt_end)

    durations = [seg["end"] - seg["start"] for seg in aligned]
    total_duration = utt_end - utt_start

    tail_window = 0.2
    tail_values = segment_f0(times, f0, max(utt_end - tail_window, utt_start), utt_end)
    pitch_slope_end = 0.0
    if len(tail_values) >= 2:
        pitch_slope_end = round(float((tail_values[-1] - tail_values[0]) / tail_window), 2)

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
