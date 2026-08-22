import soundfile as sf
import torch
import torchaudio
from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

# 음절 vocab 317M 모델 + OOV 근사 대체(nearest_syllable). 같은 조건에서 자모 vocab 94M 모델
# (Kkonjeong/wav2vec2-base-korean)보다 onset 오차 중앙값 29ms vs 36ms, 50ms 이내 80% vs 64%로 더 정확.
# 가볍게 가려면 base로 바꾸면 되고 코드 변경은 필요 없음. 비교 수치는 docs/progress.md 2026-08-22 참고
ALIGNER_MODEL = "kresnik/wav2vec2-large-xlsr-korean"
TARGET_SAMPLE_RATE = 16000
# CTC 토큰은 실제 음절 onset보다 한 프레임쯤 늦게 찍힘(MFA 대비 중앙값 +15~21ms), 그만큼 앞당김
ONSET_LAG_SEC = 0.02


def load_aligner(model_name: str = ALIGNER_MODEL) -> tuple[Wav2Vec2ForCTC, Wav2Vec2Processor]:
    processor = Wav2Vec2Processor.from_pretrained(model_name)
    model = Wav2Vec2ForCTC.from_pretrained(model_name)
    model.eval()
    model.to("cuda" if torch.cuda.is_available() else "cpu")
    return model, processor


def load_waveform(path: str) -> tuple[torch.Tensor, int]:
    # torchaudio.load는 최신 버전에서 torchcodec을 요구해 의존성이 무거워지므로 soundfile로 읽음
    data, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    waveform = torch.from_numpy(data.T)  # (channels, samples)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    if sample_rate != TARGET_SAMPLE_RATE:
        waveform = torchaudio.functional.resample(waveform, sample_rate, TARGET_SAMPLE_RATE)
        sample_rate = TARGET_SAMPLE_RATE
    return waveform, sample_rate


CHOSEONG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNGSEONG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONGSEONG = [""] + list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")


def prompt_syllables(prompt: str) -> list[str]:
    # 한글 음절 블록은 유니코드 완성형 1글자 = 1음절이라 공백만 걷어내면 됨
    return [ch for ch in prompt if not ch.isspace()]


def syllable_jamo(ch: str) -> list[str]:
    code = ord(ch) - 0xAC00
    if not 0 <= code < 11172:
        return [ch]
    lead, vowel, tail = code // 588, (code % 588) // 28, code % 28
    return [CHOSEONG[lead], JUNGSEONG[vowel]] + ([JONGSEONG[tail]] if tail else [])


LAX_ONSET = {"ㄲ": "ㄱ", "ㄸ": "ㄷ", "ㅃ": "ㅂ", "ㅆ": "ㅅ", "ㅉ": "ㅈ"}
SIMPLE_VOWEL = {"ㅒ": "ㅐ", "ㅖ": "ㅔ", "ㅙ": "ㅞ", "ㅚ": "ㅞ", "ㅢ": "ㅣ"}


def nearest_syllable(ch: str, vocab: dict) -> str | None:
    # 음절 vocab 모델은 `쫌`·`괜`·`걔`처럼 빠진 완성형이 있어(AI-Hub 실발화의 14%) 발음이 가장 가까운 음절로
    # 대체한다: 된소리→예사소리, 이중모음 단순화, 받침 제거 순. 위치만 찾는 용도라 근사 음절로도 충분
    code = ord(ch) - 0xAC00
    if not 0 <= code < 11172:
        return None
    lead, vowel, tail = CHOSEONG[code // 588], JUNGSEONG[(code % 588) // 28], code % 28
    for lead2 in (lead, LAX_ONSET.get(lead, lead)):
        for vowel2 in (vowel, SIMPLE_VOWEL.get(vowel, vowel)):
            for tail2 in (tail, 0):
                cand = chr(0xAC00 + CHOSEONG.index(lead2) * 588 + JUNGSEONG.index(vowel2) * 28 + tail2)
                if cand in vocab:
                    return cand
    return None


def prompt_tokens(syllables: list[str], vocab: dict) -> list[tuple[int, str]]:
    # 음절 vocab(kresnik 계열)이면 음절 그대로(없으면 근사 음절), 자모 vocab(wav2vec2-base-korean 등)이면
    # 자모로 분해해 (음절 번호, 토큰) 쌍으로 돌려준다. 자모 vocab은 완성형 음절이 전부 표현되므로 OOV가 없음
    if "ㄱ" in vocab:
        return [(i, j) for i, ch in enumerate(syllables) for j in syllable_jamo(ch)]
    return [(i, ch if ch in vocab else nearest_syllable(ch, vocab) or ch) for i, ch in enumerate(syllables)]


def forced_align_syllables(
    waveform: torch.Tensor,
    sample_rate: int,
    prompt: str,
    model: Wav2Vec2ForCTC,
    processor: Wav2Vec2Processor,
) -> list[dict]:
    syllables = prompt_syllables(prompt)
    vocab = processor.tokenizer.get_vocab()
    tokens = prompt_tokens(syllables, vocab)
    unknown = [tok for _, tok in tokens if tok not in vocab]
    if unknown:
        # 모델 vocab에 없는 음절(희귀 사투리 표기 등)이면 강제정렬이 불가능하니 상위에서 처리하게 예외로 알림
        raise ValueError(f"prompt에 vocab 밖 음절 있음: {unknown}")

    device = next(model.parameters()).device
    inputs = processor(waveform.squeeze(0).numpy(), sampling_rate=sample_rate, return_tensors="pt")
    with torch.no_grad():
        logits = model(inputs.input_values.to(device)).logits  # (1, T, C)
    log_probs = torch.log_softmax(logits, dim=-1).cpu()

    blank_id = processor.tokenizer.pad_token_id
    target_ids = torch.tensor([[vocab[tok] for _, tok in tokens]], dtype=torch.int32)

    aligned_tokens, scores = torchaudio.functional.forced_align(log_probs, target_ids, blank=blank_id)
    spans = torchaudio.functional.merge_tokens(aligned_tokens[0], scores[0], blank=blank_id)

    num_frames = logits.shape[1]
    frame_duration = waveform.shape[-1] / sample_rate / num_frames

    if len(spans) != len(tokens):
        raise ValueError(f"정렬된 구간 수({len(spans)})가 토큰 수({len(tokens)})와 다름")

    raw = group_spans(
        syllables,
        tokens,
        [(max(0.0, s.start * frame_duration - ONSET_LAG_SEC), s.end * frame_duration) for s in spans],
    )
    audio_end = waveform.shape[-1] / sample_rate
    return [
        {**seg, "start": round(seg["start"], 3), "end": round(seg["end"], 3)}
        for seg in extend_spans(raw, audio_end)
    ]


def group_spans(syllables: list[str], tokens: list[tuple[int, str]], spans: list[tuple]) -> list[dict]:
    grouped = [{"text": ch, "start": None, "end": None} for ch in syllables]
    for (idx, _), (start, end) in zip(tokens, spans):
        seg = grouped[idx]
        seg["start"] = start if seg["start"] is None else seg["start"]
        seg["end"] = end
    return grouped


def extend_spans(spans: list[dict], audio_end: float) -> list[dict]:
    # CTC는 음절을 1~2프레임(20~40ms)짜리 스파이크로만 내놓아 span 길이가 실제 음절 길이가 아님.
    # AI-Hub 검증(scripts/validate_alignment.py)에서 onset은 MFA와 중앙값 29ms로 맞았으므로
    # 각 음절의 끝을 다음 음절 onset까지 늘려 실제 길이에 가깝게 만든다.
    extended = [{**seg, "end": nxt["start"]} for seg, nxt in zip(spans[:-1], spans[1:])]
    last = spans[-1]
    if extended:
        durations = sorted(seg["end"] - seg["start"] for seg in extended)
        typical = durations[len(durations) // 2]
        last = {**last, "end": min(audio_end, max(last["end"], last["start"] + typical))}
    return extended + [last]
