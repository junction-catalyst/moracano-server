def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def syllable_intensity(duration: float, avg_duration: float) -> float:
    ratio = duration / avg_duration if avg_duration > 0 else 1.0
    return round(clamp(0.3 + 0.4 * ratio), 2)


def syllable_sharpness(trend: str) -> float:
    return {"flat": 0.3, "rising": 0.6, "falling": 0.5}.get(trend, 0.3)


def trend_intensity_end(intensity: float, trend: str) -> float | None:
    # flat이면 세기 변화(ParameterCurve) 없이 고정 강도 이벤트만 재생
    if trend == "rising":
        return round(clamp(intensity * 1.3), 2)
    if trend == "falling":
        return round(clamp(intensity * 0.7), 2)
    return None


def build_ahap_pattern(syllables_with_trend: list[dict]) -> dict:
    durations = [s["end"] - s["start"] for s in syllables_with_trend]
    avg_duration = sum(durations) / len(durations) if durations else 0.0

    pattern = []
    for s in syllables_with_trend:
        duration = s["end"] - s["start"]
        intensity = syllable_intensity(duration, avg_duration)
        sharpness = syllable_sharpness(s["pitch_trend"])

        pattern.append(
            {
                "Event": {
                    "EventType": "HapticContinuous",
                    "Time": s["start"],
                    "EventDuration": round(duration, 3),
                    "EventParameters": [
                        {"ParameterID": "HapticIntensity", "ParameterValue": intensity},
                        {"ParameterID": "HapticSharpness", "ParameterValue": sharpness},
                    ],
                }
            }
        )

        end_intensity = trend_intensity_end(intensity, s["pitch_trend"])
        if end_intensity is not None:
            pattern.append(
                {
                    "ParameterCurve": {
                        "ParameterID": "HapticIntensityControl",
                        "Time": s["start"],
                        "ParameterCurveControlPoints": [
                            {"Time": s["start"], "ParameterValue": intensity},
                            {"Time": s["end"], "ParameterValue": end_intensity},
                        ],
                    }
                }
            )

    return {"Version": 1, "Pattern": pattern}
