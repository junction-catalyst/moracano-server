# AI 담당 개인 작업 계획

`docs/spec.md`(팀 공용 기획)와 별개로, AI 분석 파이프라인 구현 관련 계획만 여기 기록한다.

## 현재 작업: iOS 온디바이스 프로소디 분석

iOS 로컬 녹음 파일 → 피치·듀레이션 등 음성 피처 추출 → Supabase `voices` row에 분석 결과 저장.
별도 FastAPI/Python 분석 서버는 MVP 범위에서 제거한다. 사용자는 소셜 로그인 없이
Supabase Anonymous Auth의 `auth.uid()`로 구분한다.

### 추출할 피처 9개

| 피처 | 정의 | 용도 |
|---|---|---|
| `avg_pitch` | 평균 F0 | 화자 전반 음높이 |
| `pitch_std` | F0 표준편차 | 억양 기복 크기 |
| `pitch_range` | F0 최댓값−최솟값 | 억양 폭(극단치 포착) |
| `pitch_slope_end` | 발화 끝 구간(마지막 ~200ms) F0 기울기, 발화 중앙값 기준 반음/s(최소제곱) | Rising Intonation 라벨 근거 |
| `syllable_count` | 검출된 음절 수 | 발화속도 계산용 |
| `avg_syllable_duration` | 음절 평균 길이 | Long Vowel Usage 라벨 근거 |
| `syllable_duration_std` | 음절 길이 표준편차 | 리듬 변동성 1차 지표 |
| `npvi` | 인접 음절 길이차 정규화 평균(Normalized PVI) | 리듬 불규칙성 표준 지표 |
| `speaking_rate` | 음절수 / 발화길이(초) | 발화 속도 보조값 |

### 기술 접근

- **음절 타이밍(ASR 없음)**: 제시어 텍스트를 이미 아니까 전사하지 않는다. MVP는 iOS 로컬 분석으로
  음절 단위 timing을 만들고, 정밀 강제정렬은 후순위로 둔다.
- **피치**: iOS에서 추출 가능한 F0/주파수 contour를 사용한다. 실패 시 데모용 보정값을 둔다.
- **리듬**: 음절 구간 길이 리스트에서 표준편차 + nPVI 계산.
- **저장**: 오디오는 Supabase Storage private `voices` bucket의 `{auth.uid()}/{voice_id}.m4a` path에
  올리고, 분석 결과는 Supabase `voices` row에 직접 update한다.

## 개발 순서

1. 최초 실행 시 `signInAnonymously()`로 anonymous user/session 확보
2. `owner_id = auth.uid()`로 `voices` row 생성
3. iOS 녹음 파일을 m4a/aac로 저장하고 Supabase Storage `voices` bucket의
   `{owner_id}/{voice_id}.m4a`에 업로드
4. 오디오 로드 + 전처리(모노 변환, 정규화)
5. 제시어 기준 음절 배열 생성
6. 피치 추출 — 전체 F0 컨투어 + 음절별 F0 평균
7. 9개 피처 계산 함수 작성 (순수 함수, 입력=음절구간+F0컨투어, 출력=dict)
8. 목 스키마(`mocks/on-device-analysis-contract.json`)와 동일한 JSON으로 조립
9. `voices` row에 `status='done'`, 분석 필드, `syllables`, `haptic_pattern` update

## Next

- Supabase Anonymous Auth 활성화 후 `auth.uid()` 기반 row/object RLS 확인
- Supabase Storage `voices` private bucket 업로드/`createSignedUrl` 재생 확인
- iOS에서 `voices` row insert → Storage upload → 분석 결과 update → 결과 조회 플로우 확인
- 실제 샘플 오디오 10개 내외로 값이 그럴듯하게 나오는지 확인
- 위 3단계 완료 후 `docs/progress.md`에 세션 기록 추가

## 저장 계약: 온디바이스 분석 출력 vs 최종 레코드

Supabase `voices` row가 이미 가진 값과 iOS 온디바이스 분석이 계산하는 값을 분리한다.

| 필드 | 소유 | 비고 |
|---|---|---|
| `voice_id` | Supabase | `voices.id`에서 발급 |
| `owner_id` | Supabase Auth | Anonymous Auth의 `auth.uid()`. 로그인 UI 없는 사용자 구분 |
| `region` | iOS 사용자 입력 | 녹음 전 사용자가 고른 값 |
| `prompt` | Supabase Challenge | 녹음 전 이미 정해짐. 온디바이스 분석 입력으로 사용 |
| `audio_path` | iOS Storage upload | `{owner_id}/{voice_id}.m4a` 같은 `voices` bucket 내부 object path |
| `status` | iOS | pending/done/failed |
| `avg_pitch`~`syllables`,`haptic_pattern` | iOS 온디바이스 분석 | 실제 분석 산출물 |

→ `mocks/on-device-analysis-contract.json`(iOS 온디바이스 분석 출력) /
`mocks/backend-final-record.json`(Supabase row와 분석 결과를 합친 최종 형태)
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
- 목데이터: `mocks/on-device-analysis-contract.json`(iOS 온디바이스 분석 출력) /
  `mocks/backend-final-record.json`(voice_id·region·prompt·status 등 백엔드 소유 필드까지 합친 최종
  레코드)

## 온디바이스(CoreML) 파이프라인

배포가 서버가 아니라 iOS 온디바이스로 바뀌면서 정렬 모델을 `Kkonjeong/wav2vec2-base-korean`(94M, 자모 vocab)로
바꿨다. Python 파이프라인은 그대로 **기준 구현 + 서버 폴백**이고, Swift 구현은 아래 명세와 파이터 픽스처로
수치 검증한다. 상수는 `src/moracano_ai/spec.py`(→ `artifacts/coreml/alignment_spec.json`)가 단일 출처.

### 모델 크기와 양자화 결정 (AI-Hub 300발화, MFA 대비 + fp32 대비 경로 안정성)

| 변형 | mlpackage | onset 중앙값 / ≤50ms | 음절 시작 프레임 fp32와 동일 | 라벨 동일 |
|---|---|---|---|---|
| fp16 | 189 MB | 36ms / 64% | 99.8% | 100% |
| **int8 (채널별, 출하)** | **99 MB** | 36ms / 65% | 98.6% | 99.3% |
| 6bit 팔레타이즈 g16 | ~73 MB | 36ms / 64% | 92.6% | 93.0% |
| 4bit 팔레타이즈 g16 | ~52 MB | 36ms / 65% | 84.7% | 88.0% |
| int4 block32 | ~52 MB | 36ms / 64% | 88.1% | 89.3% |

MFA 오차만으로는 4bit까지 구분이 안 되고, fp32와 같은 경로를 내는지(음절 시작 프레임 동일 ≥ 95%, 라벨 동일
≥ 97%)가 변별 기준이다. int8만 통과. 특징추출 conv 7개와 `lm_head`는 항상 fp16(합쳐 9MB).
EnumeratedShapes용 0 패딩은 라벨 동일 85%로 떨어져 **RangeDim(0.5~15초) 입력**을 쓴다. 입력 정규화 생략은 88.6%로 탈락.

### 산출물 (`scripts/export_coreml.py`, 격리 환경에서 실행, `artifacts/coreml/` git 제외)

`KoreanJamoCTC_fp16.mlpackage`(189MB), `KoreanJamoCTC_int8.mlpackage`(99MB), `vocab.json`(blank `[PAD]`=53),
`alignment_spec.json`, `sha256sums.txt`. 모델 입력 `audio (1, L)` float32 원시 샘플(정규화는 모델 안에 포함),
출력 `log_probs (1, T, 56)` fp32. traced vs eager 로그확률 차이 0.

### Swift 쪽 알고리즘 명세 (`alignment_spec.json`과 같음)

1. 녹음 → 16kHz 모노 Float32, 0.5~15초, 제시어당 최소 길이 `(2 * 자모수 + 1) * 0.02초`(CTC 실행 가능 조건).
2. 제시어: 한글 완성형만 남김 → 자모 분해(초성 19 / 중성 21 / 종성 27, 호환 자모) → `(음절 번호, 토큰 id)`.
3. CoreML 추론 → `log_probs (T, 56)`. `T`는 conv kernel [10,3,3,3,3,2,2] / stride [5,2,2,2,2,2,2]의 fold.
   **frame_duration = 샘플수 / 16000 / T** (4초에서 20.09ms, 고정 20ms 아님).
4. CTC 강제정렬: 상태 2L+1(짝수 = blank 53, 홀수 s = 토큰 (s+1)/2), alpha[0] = {blank, 첫 토큰}, 전이
   s / s-1 / s-2(홀수이고 토큰이 직전 토큰과 다를 때), 마지막 프레임은 argmax(마지막 토큰, 마지막 blank), 역추적.
   연속 같은 라벨을 하나의 span으로 합치고 blank는 버림(끝 프레임 exclusive). T < 토큰수 + 인접 중복이면 실패.
5. 음절 구간: 토큰 span을 음절 번호로 묶음(첫 토큰 시작, 마지막 토큰 끝) → 시작에서 0.02초 뺌(0 하한) → 각 음절
   끝 = 다음 음절 시작 → 마지막 음절 끝 = `speech_end`(없으면 앞 음절 보정 길이의 상위 중앙값) → 소수 3자리 반올림.
6. `speech_end`: Praat intensity(최소 피치 75Hz → 창 6.4/75 = 85.3ms Kaiser β 20.24, 5ms 간격, dB)에서 마지막
   음절 onset 이후 구간 피크보다 20dB 아래로 떨어지기 직전 시각.
7. F0: 1차 60~700Hz → 유성 프레임 q25/q75 → 2차 floor max(50, 0.75 q25), ceiling min(700, 1.5 q75)
   (유성 5프레임 미만이면 1차 유지). Swift는 YIN 계열 10ms hop으로 구현, Praat와 프레임별로는 다르므로
   허용오차는 중앙값/유성 일치/기울기 부호 기준.
8. 반음 = 12·log2(f0 / 발화 중앙값 F0), 구간 [첫 음절 시작, 마지막 음절 끝). 기울기는 최소제곱(프레임 3개 미만이면 0).
   음절 trend: 역치 0.16 / max(T, 0.08)² 반음/s. 끝 기울기: 마지막 0.2초. 표준편차는 모집단(ddof 0).
9. 라벨 임계값 rising 25 반음/s, long vowel 0.23s, npvi 76. 햅틱: intensity clamp(0.3 + 0.4·길이/평균길이),
   sharpness flat 0.3 / rising 0.6 / falling 0.5, 끝 intensity ×1.3 / ×0.7(flat은 ParameterCurve 없음).

### 파이터 픽스처 (`scripts/export_parity_fixtures.py`, `scripts/compare_parity.py`)

AI-Hub 발화 40개(young/old, 3~12음절) + `tests/fixtures/sample.wav`. 발화마다 `.wav`(16k PCM16)와 `.json`:
토큰, `frame_argmax`, 토큰 프레임 span, 음절 구간(보정 전/후), `speech_end`, intensity/F0 트랙, 피치 floor/ceiling,
음절별 반음 기울기·역치·trend, 피처, 라벨, 햅틱. Swift 테스트 타깃이 같은 스키마로 JSON을 쓰면
`uv run python scripts/compare_parity.py artifacts/parity/py_fp32 <swift_dir>`가 항목별 PASS/FAIL을 낸다.
허용오차는 `spec.py`의 `PARITY_TOLERANCES`. AI-Hub 오디오는 재배포 금지라 `artifacts/parity/`는 git 제외
(서버 `/data/aihub/mfa_work/corpus/` 원본, 팀 내부 공유만), `tests/fixtures/parity/sample.*`만 커밋.

파이터가 깨지기 쉬운 순서: (1) F0 추적기(Praat AC vs YIN, 유성 경계·노년층 creaky), (2) intensity 창 정의
(85ms Kaiser, 43ms RMS 아님), (3) 프레임 타이밍(공식 vs 고정 20ms), (4) 반열림 구간과 모집단 표준편차,
(5) fp16/ANE 드리프트로 경계 1프레임 뒤집힘(int8 변형도 fp32 대비 음절 시작 1.4%가 바뀜).
