import tempfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, HTTPException, UploadFile
from soundfile import LibsndfileError

from moracano_ai.align import forced_align_syllables, load_aligner, load_waveform, normalize_prompt
from moracano_ai.direction import placeholder_pca_coord
from moracano_ai.features import build_syllables_with_trend, compute_features
from moracano_ai.haptic import build_ahap_pattern
from moracano_ai.labels import generate_labels
from moracano_ai.prosody import load_sound, pitch_contour

_aligner: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 모델을 프로세스 시작 시 한 번만 로드 — 요청마다 재로딩하면 실시간성 요건을 못 맞춤
    model, processor = load_aligner()
    _aligner["model"] = model
    _aligner["processor"] = processor
    yield
    _aligner.clear()


app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/analyze")
async def analyze(audio: UploadFile, prompt: str = Form(...)) -> dict:
    syllable_text = normalize_prompt(prompt)
    if not syllable_text:
        raise HTTPException(status_code=422, detail="prompt에 한글 음절이 없음")

    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        tmp.write(await audio.read())
        tmp.flush()

        try:
            waveform, sample_rate = load_waveform(tmp.name)
        except LibsndfileError as e:
            raise HTTPException(status_code=415, detail=f"오디오를 읽을 수 없음(PCM WAV/FLAC만 지원): {e}") from e
        try:
            aligned = forced_align_syllables(
                waveform, sample_rate, syllable_text, _aligner["model"], _aligner["processor"]
            )
        except (ValueError, RuntimeError) as e:
            # vocab 밖 음절(근사 대체 실패), 음절 수보다 짧은 오디오 등 입력 문제는 4xx로 돌려 백엔드가 failed 처리
            raise HTTPException(status_code=422, detail=f"정렬 실패: {e}") from e

        sound = load_sound(tmp.name)
        times, f0 = pitch_contour(sound)

        syllables = build_syllables_with_trend(aligned, times, f0)
        features = compute_features(aligned, times, f0)

    return {
        **features,
        "labels": generate_labels(features),
        "pca_coord": placeholder_pca_coord(features),
        "syllables": syllables,
        "haptic_pattern": build_ahap_pattern(syllables),
    }
