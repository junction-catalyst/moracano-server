import pytest

from moracano_ai.align import (
    extend_spans,
    group_spans,
    nearest_syllable,
    prompt_syllables,
    prompt_tokens,
    syllable_jamo,
)


def test_prompt_syllables_drops_whitespace():
    assert prompt_syllables("뭐라 카노") == ["뭐", "라", "카", "노"]


def test_syllable_jamo_decomposes_with_optional_coda():
    assert syllable_jamo("뭐") == ["ㅁ", "ㅝ"]
    assert syllable_jamo("쫌") == ["ㅉ", "ㅗ", "ㅁ"]
    assert syllable_jamo("값") == ["ㄱ", "ㅏ", "ㅄ"]


def test_prompt_tokens_uses_syllables_for_syllable_vocab_and_jamo_otherwise():
    syllable_vocab = {"뭐": 0, "라": 1}
    assert prompt_tokens(["뭐", "라"], syllable_vocab) == [(0, "뭐"), (1, "라")]
    jamo_vocab = {"ㄱ": 0}
    assert prompt_tokens(["뭐", "라"], jamo_vocab) == [(0, "ㅁ"), (0, "ㅝ"), (1, "ㄹ"), (1, "ㅏ")]


def test_nearest_syllable_relaxes_onset_vowel_then_coda():
    vocab = {"좀": 0, "조": 1, "괘": 2, "개": 3}
    assert nearest_syllable("쫌", vocab) == "좀"
    assert nearest_syllable("쫌", {"쪼": 0}) == "쪼"
    assert nearest_syllable("괜", vocab) == "괘"
    assert nearest_syllable("걔", vocab) == "개"
    assert nearest_syllable("걍", vocab) is None


def test_prompt_tokens_substitutes_oov_syllable_but_keeps_index():
    assert prompt_tokens(["쫌", "더"], {"좀": 0, "더": 1}) == [(0, "좀"), (1, "더")]


def test_group_spans_merges_jamo_spans_into_syllables():
    tokens = [(0, "ㅁ"), (0, "ㅝ"), (1, "ㄹ"), (1, "ㅏ")]
    spans = [(0.10, 0.12), (0.14, 0.16), (0.30, 0.32), (0.36, 0.38)]
    assert group_spans(["뭐", "라"], tokens, spans) == [
        {"text": "뭐", "start": 0.10, "end": 0.16},
        {"text": "라", "start": 0.30, "end": 0.38},
    ]


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


def test_extend_spans_prefers_speech_end_for_last_syllable():
    spans = [
        {"text": "뭐", "start": 0.10, "end": 0.12},
        {"text": "노", "start": 0.30, "end": 0.32},
    ]
    assert extend_spans(spans, audio_end=1.0, speech_end_time=0.75)[-1]["end"] == 0.75
    assert extend_spans(spans, audio_end=0.60, speech_end_time=0.75)[-1]["end"] == 0.60
    # 발화 끝이 마지막 onset보다 앞이면(추정 실패) 중앙값 길이 규칙으로 되돌아감
    assert extend_spans(spans, audio_end=1.0, speech_end_time=0.25)[-1]["end"] == pytest.approx(0.50)
