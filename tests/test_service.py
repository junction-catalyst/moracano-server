from fastapi.testclient import TestClient

from moracano_ai.service import app

# lifespan을 타지 않는 클라이언트: 모델 로드 없이 입력 검증 경로만 확인
client = TestClient(app)


def test_healthz():
    assert client.get("/healthz").json() == {"status": "ok"}


def test_prompt_without_hangul_is_422():
    response = client.post("/analyze", files={"audio": ("a.wav", b"RIFF")}, data={"prompt": "?!"})
    assert response.status_code == 422
    assert "한글 음절" in response.json()["detail"]


def test_unreadable_audio_is_415():
    response = client.post("/analyze", files={"audio": ("a.m4a", b"\x00" * 512)}, data={"prompt": "뭐라카노"})
    assert response.status_code == 415
    assert "PCM WAV" in response.json()["detail"]
