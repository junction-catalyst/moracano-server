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

1. 환경 준비 — `parselmouth`, `scipy`, `numpy`, `torchaudio`, 한국어 wav2vec2 CTC 모델 설치
2. 오디오 로드 + 전처리(모노 변환, 정규화)
3. 음절 분할 — 강제정렬(forced alignment)로 제시어 텍스트를 오디오에 정렬해 음절 구간 리스트 산출
4. 피치 추출 — 전체 F0 컨투어 + 음절별 F0 평균
5. 9개 피처 계산 함수 작성 (순수 함수, 입력=음절구간+F0컨투어, 출력=dict)
6. 목 스키마(`mocks/ai-service-contract.json`)와 동일한 JSON으로 조립
7. 실제 샘플 오디오 여러 개로 돌려보고, 값이 그럴듯하게 나온 것들로 mock 샘플 교체/추가

## Next

- 테스트용 실제 오디오 샘플 확보 (AI-Hub 경북 방언 데이터에서 몇 개 추출)
- 위 7단계 완료 후 `docs/progress.md`에 세션 기록 추가

## 백엔드 전달 계약: AI 서비스 출력 vs 최종 레코드

백엔드로 넘기는 정보 중 일부는 AI가 계산하지만, 일부는 백엔드가 이미 알고 있는 값(사용자 입력·업로드
시점에 정해짐)이라 AI가 다시 만들 필요가 없다. 이걸 섞어서 문서화하면 헷갈리므로 둘로 분리한다.

| 필드 | 소유 | 비고 |
|---|---|---|
| `voice_id` | 백엔드 | `POST /api/voices`에서 이미 발급, URL 경로에도 있음 |
| `region` | 백엔드(사용자 입력) | 녹음 전 사용자가 고른 값 |
| `prompt` | 백엔드(추천 블록) | 녹음 전 이미 정해짐. 단, AI에는 **강제정렬 입력**으로 전달돼야 함 |
| `status` | 백엔드(job 상태) | pending/done/failed |
| `avg_pitch`~`syllables`,`haptic_pattern` | **AI 계산** | 실제 AI 산출물 |

→ `mocks/ai-service-contract.json`(AI 마이크로서비스의 순수 입출력) /
`mocks/backend-final-record.json`(위 필드까지 합쳐 Supabase에 저장 후 프론트로 서빙하는 최종 형태)
두 파일로 분리.

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

### 확정 사항

- 플랫폼: iOS 네이티브. Core Haptics 사용 가능하므로 Web Vibration API 제약 없음.
- 프론트 확인 완료: AHAP 포맷 그대로 `CHHapticPattern(dictionary:)`에 넣는 구조로 합의됨.

### syllables / haptic_pattern 스키마 (AHAP 네이티브로 통일)

시각화용 `syllables`(텍스트·타이밍·트렌드)와 햅틱용 `haptic_pattern`(AHAP 그대로)을 분리한다 —
Core Haptics는 텍스트/트렌드를 몰라도 되고, 화면 렌더러는 AHAP 구조를 몰라도 되게.

```json
{
  "syllables": [
    { "text": "뭐", "start": 0.00, "end": 0.18, "pitch_trend": "flat" },
    { "text": "라", "start": 0.18, "end": 0.34, "pitch_trend": "flat" },
    { "text": "카", "start": 0.34, "end": 0.61, "pitch_trend": "falling" },
    { "text": "노", "start": 0.61, "end": 0.79, "pitch_trend": "rising" }
  ],
  "haptic_pattern": {
    "Version": 1,
    "Pattern": [
      { "Event": { "EventType": "HapticContinuous", "Time": 0.00, "EventDuration": 0.18,
          "EventParameters": [
            {"ParameterID": "HapticIntensity", "ParameterValue": 0.4},
            {"ParameterID": "HapticSharpness", "ParameterValue": 0.3}
          ] } },
      { "Event": { "EventType": "HapticContinuous", "Time": 0.18, "EventDuration": 0.16,
          "EventParameters": [
            {"ParameterID": "HapticIntensity", "ParameterValue": 0.4},
            {"ParameterID": "HapticSharpness", "ParameterValue": 0.3}
          ] } },
      { "Event": { "EventType": "HapticContinuous", "Time": 0.34, "EventDuration": 0.27,
          "EventParameters": [
            {"ParameterID": "HapticIntensity", "ParameterValue": 0.7},
            {"ParameterID": "HapticSharpness", "ParameterValue": 0.5}
          ] } },
      { "ParameterCurve": { "ParameterID": "HapticIntensityControl", "Time": 0.34,
          "ParameterCurveControlPoints": [
            {"Time": 0.34, "ParameterValue": 0.7},
            {"Time": 0.61, "ParameterValue": 0.5}
          ] } },
      { "Event": { "EventType": "HapticContinuous", "Time": 0.61, "EventDuration": 0.18,
          "EventParameters": [
            {"ParameterID": "HapticIntensity", "ParameterValue": 0.5},
            {"ParameterID": "HapticSharpness", "ParameterValue": 0.6}
          ] } },
      { "ParameterCurve": { "ParameterID": "HapticIntensityControl", "Time": 0.61,
          "ParameterCurveControlPoints": [
            {"Time": 0.61, "ParameterValue": 0.5},
            {"Time": 0.79, "ParameterValue": 0.9}
          ] } }
    ]
  }
}
```

- `syllables[].text`: 사용자가 실제로 말한 내용이 아니라 제시어(prompt) 텍스트를 음절 수만큼 자른
  것 (ADR 0001 철학 유지, 타이밍은 강제정렬로 계산)
- `syllables[].pitch_trend`: 그 음절 구간 F0 기울기로 rising/falling/flat 판정 — 화면 화살표 렌더링용
- `haptic_pattern`: 음절 하나당 `Event` 1개(Continuous, 그 음절의 평균 intensity/sharpness) +
  트렌드가 flat이 아니면 `ParameterCurve` 1개 추가(rising/falling을 실제 진동 세기 램프로 표현).
  프론트는 이 객체를 그대로 `CHHapticPattern(dictionary:)`에 넘기면 끝, 별도 파싱 불필요.
- 목데이터: `mocks/ai-service-contract.json`(AI 서비스 순수 입출력) /
  `mocks/backend-final-record.json`(voice_id·region·prompt·status 등 백엔드 소유 필드까지 합친 최종
  레코드)
