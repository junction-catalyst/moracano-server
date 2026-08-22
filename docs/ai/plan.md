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

- **음절 분할(ASR 없음, ADR 0001 결정 유지)**: Intensity(에너지) 엔벨로프 피크 탐지 — 고전적
  syllable nuclei counting(de Jong & Wempe) 방식을 `parselmouth` + `scipy` peak-picking으로 구현
- **피치**: `parselmouth`의 `sound.to_pitch()`로 F0 컨투어 추출
- **리듬**: 검출된 음절 구간 길이 리스트에서 표준편차 + nPVI 계산

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
