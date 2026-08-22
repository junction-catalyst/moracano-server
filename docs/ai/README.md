# AI 분석 파이프라인

`src/moracano_ai`는 온디바이스 분석 로직의 파이썬 레퍼런스 구현이자 검증 도구다. 실제 서비스는 iOS에서 Core ML로 돌아가고, 이 코드는 그 정답지 역할 + AI-Hub 데이터로 알고리즘을 검증하는 용도로 쓴다. 서버로 배포하지 않는다.

align.py가 강제정렬을 한다. 제시어를 이미 아니까 ASR로 전사할 필요가 없고, 그 텍스트가 오디오 어디에 있는지만 wav2vec2 CTC로 찾는다. prosody.py는 피치 추출이랑 발화 끝 지점(intensity 기반)을 잡는다. features.py랑 labels.py가 피치/길이/리듬 9개 피처를 계산하고 그걸로 라벨(Rising Intonation 등)을 판정한다. haptic.py는 음절별 억양을 Apple AHAP 포맷으로 바꿔서 `CHHapticPattern(dictionary:)`에 바로 꽂을 수 있게 만든다. service.py는 이 파이프라인을 FastAPI로 감싼 로컬 검증용이고 배포 안 한다.

scripts 밑에는 검증용 스크립트들이 있다. validate_alignment.py는 AI-Hub 실발화로 강제정렬 결과를 MFA 정렬이랑 비교한다. calibrate_thresholds.py는 실측 분포로 라벨 임계값을 다시 잡고, export_coreml.py는 정렬 모델을 CoreML로 변환한다. export_parity_fixtures.py/compare_parity.py는 파이썬 출력이랑 스위프트 온디바이스 출력이 같은 값을 내는지 대조하는 용도다.

## 검증 데이터셋

AI-Hub 경상도 방언 실발화 600개(young/old 각 300)로 검증했다. TTS 아니고 실제 녹음이고, 정답은 같은 코퍼스에 이미 있던 MFA 정렬을 썼다. AI-Hub 데이터는 재배포 금지라 오디오는 이 레포에 없고 팀 서버에만 있다.

## 성능

large(317M, 서버용): onset 오차 중앙값 29ms, 50ms 이내 80%, 100ms 이내 94%, GPU 정렬 지연 26ms.
base(94M, 온디바이스 기본값): 36ms / 64% / 91% / 19ms.

CoreML 양자화는 int8(99MB)이 fp16(189MB) 대비 정확도 손실이 거의 없어서(음절 시작 프레임 일치율 98.6%, 라벨 일치율 99.3%) 최종 채택했다. 라벨 분포는 599발화 실측 기준 Rising Intonation 11%, Long Vowel Usage 26%, Strong Rhythm Variation 26%.

실험별 자세한 수치와 왜 이렇게 결정했는지는 `docs/ai/progress.md`에 세션별로 남겨뒀고, 지금 계약이랑 알고리즘 명세는 `docs/ai/plan.md`에 있다.

## 실행

```
uv sync
uv run pytest tests/
```
