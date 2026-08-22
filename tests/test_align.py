import pytest

from moracano_ai.align import extend_spans, prompt_syllables


def test_prompt_syllables_drops_whitespace():
    assert prompt_syllables("뭐라 카노") == ["뭐", "라", "카", "노"]


def test_extend_spans_fills_gaps_to_next_onset():
    spans = [
        {"text": "뭐", "start": 0.10, "end": 0.12},
        {"text": "라", "start": 0.30, "end": 0.32},
        {"text": "카", "start": 0.45, "end": 0.47},
    ]
    out = extend_spans(spans, audio_end=1.0)
    assert [s["end"] for s in out[:-1]] == [0.30, 0.45]


def test_extend_spans_last_syllable_uses_typical_duration_capped_by_audio_end():
    spans = [
        {"text": "뭐", "start": 0.10, "end": 0.12},
        {"text": "라", "start": 0.30, "end": 0.32},
        {"text": "카", "start": 0.45, "end": 0.47},
    ]
    # 앞 음절들의 보정 길이 [0.20, 0.15] 중 상위 중앙값 0.20을 마지막 음절에 적용
    assert extend_spans(spans, audio_end=1.0)[-1]["end"] == pytest.approx(0.65)
    assert extend_spans(spans, audio_end=0.50)[-1]["end"] == 0.50


def test_extend_spans_single_syllable_unchanged():
    spans = [{"text": "뭐", "start": 0.10, "end": 0.12}]
    assert extend_spans(spans, audio_end=1.0) == spans
