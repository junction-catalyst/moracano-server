# AI 담당 개인 작업 계획

`docs/spec.md`(팀 공용 기획)와 별개로, AI 분석 파이프라인 구현 관련 계획만 여기 기록한다.

## 현재 작업: 프로소디 피처 추출 스크립트

오디오 파일 → 피치·듀레이션 등 음성 피처 추출 → 잘 나온 것으로 `analyze` 응답 샘플 구성.
브랜치: `feat/prosody-extraction`

### 추출할 피처 9개

| 피처 | 정의 | 용도 |
|---|---|---|
| `avg_pitch` | 평균 F0 | 화자 전반 음높이 |
| `pitch_std` | F0 표준편차 | 억양 기복 크기 |
| `pitch_range` | F0 최댓값−최솟값 | 억양 폭(극단치 포착) |
| `pitch_slope_end` | 발화 끝 구간(마지막 ~200ms) F0 기울기 | Rising Intonation 라벨 근거 |
| `syllable_count` | 검출된 음절 수 | 발화속도 계산용 |
| `avg_syllable_duration` | 음절 평균 길이 | Long Vowel Usage 라벨 근거 |
| `syllable_duration_std` | 음절 길이 표준편차 | 리듬 변동성 1차 지표 |
| `npvi` | 인접 음절 길이차 정규화 평균(Normalized PVI) | 리듬 불규칙성 표준 지표 |
| `speaking_rate` | 음절수 / 발화길이(초) | 발화 속도 보조값 |

### 기술 접근

- **음절 타이밍(ASR 없음, ADR 0001 철학 유지 — 방법은 변경)**: 처음엔 Intensity 피크 탐지(에너지
  기반 syllable nuclei counting)로 계획했으나, 정합성이 약하다는 문제 제기로 **강제정렬(forced
  alignment)**로 전환. 제시어 텍스트를 이미 아니까 전사(ASR)는 여전히 불필요하고, 사전학습 한국어
  wav2vec2 CTC 모델(예: `kresnik/wav2vec2-large-xlsr-korean`) + `torchaudio.functional.forced_align`으로
  "이 텍스트가 오디오의 어느 시점에 있는지"만 계산. 학습/파인튜닝 없음. 서버에 상시 로드된 프로세스로
  띄워서 요청마다 모델 재로딩 없이 실시간성 확보 (Docker, 온디바이스는 3일 스코프엔 과함 — CoreML
  변환 자체는 반나절이지만 CTC 정렬 알고리즘을 Swift로 재구현하는 게 오래 걸림).
- **피치**: `parselmouth`의 `sound.to_pitch()`로 F0 컨투어 추출
- **리듬**: 강제정렬로 얻은 음절 구간 길이 리스트에서 표준편차 + nPVI 계산

## 개발 순서

1. 환경 준비 — `parselmouth`, `scipy`, `numpy` 설치
2. 오디오 로드 + 전처리(모노 변환, 정규화)
3. 음절 분할 — Intensity 피크 탐지로 음절 구간 리스트 산출
4. 피치 추출 — 전체 F0 컨투어 + 음절별 F0 평균
5. 9개 피처 계산 함수 작성 (순수 함수, 입력=음절구간+F0컨투어, 출력=dict)
6. 목 스키마(`mocks/analyze-response-samples.json`)와 동일한 JSON으로 조립
7. 실제 샘플 오디오 여러 개로 돌려보고, 값이 그럴듯하게 나온 것들로 mock 샘플 교체/추가

## Next

- 테스트용 실제 오디오 샘플 확보 (AI-Hub 경북 방언 데이터에서 몇 개 추출)
- 위 7단계 완료 후 `docs/progress.md`에 세션 기록 추가

## Voice Experience(시각화·햅틱)용 syllables 필드

`analyze` 응답의 9개 피처는 발화 전체 요약값이라 음절 단위 시각화(억양 화살표)·햅틱 표현을
못 만든다. 별도로 음절 단위 배열을 `syllables` 필드에 추가해서 백엔드에 넘긴다.

### 햅틱 표현 리서치

처음엔 `●`/`━━━`/`↑` 같은 기호로 표현하려 했으나, 이건 화면 표기일 뿐 실제 진동 재생에 못 쓴다.
실제 서비스들의 저장 방식을 확인:

- **iOS Core Haptics(AHAP)**: 이벤트 배열, 각 이벤트가 `Time`/`EventType`(Transient·Continuous)/
  `HapticIntensity`(0~1)/`HapticSharpness`(0~1)를 가짐. Continuous 이벤트는 시간에 따라 강도가
  변하는 ParameterCurve도 지원(램프).
- **Android VibrationEffect**: `timings`(꺼짐/켜짐 지속시간 배열, ms) + `amplitudes`(구간별 세기,
  0~255) 두 배열.
- **공통점**: 기호가 아니라 시간(duration)+세기(intensity) 수치로 저장. AHAP/Android 둘 다
  플랫폼별로 다운컨버트 가능한 추상 포맷(duration_ms, intensity_start/end, sharpness)으로
  통일하기로 함.

### syllables 스키마

```json
{
  "text": "노",
  "start": 0.61,
  "end": 0.79,
  "pitch_trend": "rising",
  "haptic": {
    "duration_ms": 180,
    "intensity_start": 0.5,
    "intensity_end": 0.9,
    "sharpness": 0.6
  }
}
```

- `text`: 사용자가 실제로 말한 내용이 아니라 제시어(prompt) 텍스트를 음절 수만큼 자른 것 (ADR
  0001, ASR 없음 결정 유지)
- `pitch_trend`: 그 음절 구간 F0 기울기로 rising/falling/flat 판정
- `haptic.intensity_start/end`: 값이 같으면 평탄, end>start면 상승(진동이 점점 세짐)으로 화살표
  방향을 실제 진동 램프로 표현
- 목데이터: `mocks/analyze-response-with-syllables.json`

### 확정 사항

- 플랫폼: iOS 네이티브. Core Haptics 사용 가능하므로 Web Vibration API 제약 없음.
- 프론트 확인 완료: AHAP 포맷 그대로 `CHHapticPattern(dictionary:)`에 넣는 구조로 합의됨.
  → `haptic_pattern` 필드는 위 AHAP 구조(`Version`/`Pattern`/`Event`/`ParameterCurve`) 그대로
  내려주면 되고, 프론트 쪽 별도 파싱 코드 불필요.
