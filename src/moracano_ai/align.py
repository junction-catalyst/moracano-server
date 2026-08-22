import soundfile as sf
import torch
import torchaudio
from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

ALIGNER_MODEL = "kresnik/wav2vec2-large-xlsr-korean"
TARGET_SAMPLE_RATE = 16000


def load_aligner(model_name: str = ALIGNER_MODEL) -> tuple[Wav2Vec2ForCTC, Wav2Vec2Processor]:
    processor = Wav2Vec2Processor.from_pretrained(model_name)
    model = Wav2Vec2ForCTC.from_pretrained(model_name)
    model.eval()
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


def prompt_syllables(prompt: str) -> list[str]:
    # 한글 음절 블록은 유니코드 완성형 1글자 = 1음절이라 공백만 걷어내면 됨
    return [ch for ch in prompt if not ch.isspace()]


def forced_align_syllables(
    waveform: torch.Tensor,
    sample_rate: int,
    prompt: str,
    model: Wav2Vec2ForCTC,
    processor: Wav2Vec2Processor,
) -> list[dict]:
    syllables = prompt_syllables(prompt)
    vocab = processor.tokenizer.get_vocab()
    unknown = [ch for ch in syllables if ch not in vocab]
    if unknown:
        # 모델 vocab에 없는 음절(희귀 사투리 표기 등)이면 강제정렬이 불가능하니 상위에서 처리하게 예외로 알림
        raise ValueError(f"prompt에 vocab 밖 음절 있음: {unknown}")

    inputs = processor(waveform.squeeze(0).numpy(), sampling_rate=sample_rate, return_tensors="pt")
    with torch.no_grad():
        logits = model(inputs.input_values).logits  # (1, T, C)
    log_probs = torch.log_softmax(logits, dim=-1)

    blank_id = processor.tokenizer.pad_token_id
    target_ids = torch.tensor([[vocab[ch] for ch in syllables]], dtype=torch.int32)

    aligned_tokens, scores = torchaudio.functional.forced_align(log_probs, target_ids, blank=blank_id)
    spans = torchaudio.functional.merge_tokens(aligned_tokens[0], scores[0], blank=blank_id)

    num_frames = logits.shape[1]
    frame_duration = waveform.shape[-1] / sample_rate / num_frames

    if len(spans) != len(syllables):
        raise ValueError(f"정렬된 구간 수({len(spans)})가 음절 수({len(syllables)})와 다름")

    return [
        {
            "text": ch,
            "start": round(span.start * frame_duration, 3),
            "end": round(span.end * frame_duration, 3),
        }
        for ch, span in zip(syllables, spans)
    ]
