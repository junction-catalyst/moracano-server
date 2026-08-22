## 2026-08-22 — AI 모듈 아키텍처 설계 확정

JunctionX Korea 2026 · moracano(경상북도 방언 Dialect Root) 프로젝트의 AI 분석 파이프라인을 처음부터
설계했다. 원래 3갈래(ASR / Prosody Analyzer / Voice Embedding) 아키텍처에서 시작해, 3일 해커톤 스코프에
맞춰 프로소디 단일 갈래로 축소했다.

- **5개 기능 블록으로 정리**: ① 탐색·추천(단어 랭킹, 예시문장 선택) ② Acoustic Speech Analysis(음절
  분할, 피치/길이/리듬 추출) ③ Dialect Root 생성(라벨 생성, Similar Voices, PCA 뿌리 방향) ④ Voice
  Experience(음성재생/억양시각화/햅틱, 순수 렌더링) ⑤ 구조화된 아카이브 & 공개 인프라(Supabase 저장 +
  조회 API/MCP).
- **ASR 제거** (`docs/adr/0001`): 프롬프트 텍스트가 이미 정해져 있으므로 사용자 발화를 전사할 필요 없이,
  음향 에너지/피치 피크로 음절 경계만 직접 탐지하는 방식으로 대체. 사투리→표준어 오보정 리스크도 함께
  해소됨.
- **Voice Embedding 제거** (`docs/adr/0002`): Similar Voices와 PCA 뿌리 방향의 입력을 임베딩 벡터에서
  이미 계산되는 프로소디 특징 벡터(평균피치/피치표준편차/평균길이/길이표준편차)로 대체. 이 시점부터
  파이프라인에 딥러닝 모델이 하나도 남지 않음 — 전부 신호처리(`librosa`/`parselmouth`) + 통계(PCA 1회
  피팅) + 규칙(임계값)으로 구성.
- **역할 분담(AI 1명 + 백엔드 1명)**: AI가 블록1·2·3의 계산 로직(+AI-Hub 전처리)을 함수/FastAPI 서비스로
  만들고, 백엔드는 Supabase 스키마·Storage·CRUD·오케스트레이션을 담당. 경계면은 `analyze` 응답 JSON
  스키마 하나로 고정 — 이것만 먼저 합의하면 두 사람이 즉시 병렬 작업 가능.

### 기능 명세서 (Notion 원본 기준)

| 기능명 | API |
|---|---|
| 1. 방언 Challenge | `/api/challenges/today` |
| 2. 녹음 전 지역 입력 (지도 UX) | (음성 CRUD시 통합) |
| 3-1. 음성 녹음 | `/api/voices` |
| 3-2. 음성 저장 (CRUD) | `/api/voices/{id}` |
| 3-3. 음성 분석 (Pitch, Duration, Rhythm) | `/api/voices/{id}/analyze` |
| 4-1. 뿌리 생성 | (API 없음 — 3-3 응답을 클라이언트에서 규칙 계산) |
| 4-2. 햅틱 표현 | (API 없음 — 3-3 응답을 클라이언트에서 렌더링) |

기능명 앞자리 번호는 위 5블록의 ①②③④에 대응한다: 1→블록①, 3-1/3-2→블록⑤(저장), 3-3→블록②,
4-1→블록③, 4-2→블록④.

### Next

- `POST /api/voices/{id}/analyze` 응답 스키마에 맞는 mock 샘플 3개 작성 (백엔드가 실제 분석 로직 없이
  CRUD/프론트 연동 먼저 끝낼 수 있도록).
- AI-Hub 경상북도 방언 데이터가 시군(포항/안동/대구권 등) 단위로 지역 라벨을 갖고 있는지 확인 —
  Similar Voices/숲 단위 시각화가 이 세분화 여부에 달려 있음.
- 라벨 임계값(Rising Intonation 등)과 PCA 변환행렬을 AI-Hub 레퍼런스 코퍼스로 사전 피팅하는 전처리
  스크립트 작성.
- 충청도 관련 요소는 이 프로젝트 범위에 없음(이전 "경상도 vs 충청도 대결" 버전의 잔재였음, 삭제 확인됨) —
  경북 내부 시군 다양성에만 집중.

## 2026-08-22 — 서버 데이터 실사 + 스코프 조정

팀 GPU 서버에 이미 받아둔 AI-Hub "한국어 방언 발화 데이터(경상도, datasetKey 119)"를 실제로 확인한 결과,
지역 메타데이터가 **광역 단위(부산/대구/울산/경남/경북)까지만** 있고 시군(포항/안동/경주 등) 단위가 없음을
확인했다. 경북 출생 화자 발화량도 현재 다운로드분 기준 약 245시간으로 전체의 일부에 불과.

- **Similar Voices 기능 제거 (팀 결정)**: 기획서(`docs/spec.md`, 결과 예시 섹션)엔 "Similar Voices:
  Yeongdeok, Gyeongju"로 명시돼 있었으나, 시군 단위 데이터가 없어 구현 불가능함을 확인 후 팀 논의를 거쳐
  MVP에서 제외하기로 결정. `mocks/analyze-response-samples.json`,
  `mocks/analyze-response-with-syllables.json`에서 `similar_regions` 필드 삭제.
- **음절 타이밍 방식 재검토**: 에너지 피크 기반 음절 분할은 정합성이 약하다는 문제 제기 → ASR(Whisper)
  대신 **강제정렬(forced alignment)**로 전환 검토 중 (제시어 텍스트를 이미 아니까, 사전학습 한국어
  wav2vec2 CTC 모델 + `torchaudio` 강제정렬로 텍스트-오디오 시간 매핑만 수행, 전사/학습 불필요). 서버에
  이미 있는 MFA 정렬 결과물과 같은 계열의 접근.
- **온디바이스(CoreML) 검토 후 보류**: wav2vec2→CoreML 변환 자체는 반나절~하루면 되지만, CTC 강제정렬
  알고리즘을 Swift로 재구현하고 오디오 전처리를 동일하게 맞추는 작업까지 합치면 2~3일이 걸려 3일
  해커톤 스코프를 넘음. 서버(Docker, 모델 상시 로드) 방식으로 진행하기로 함.
- **Voice Experience용 syllables 필드 추가 확정**: `text`/`start`/`end`/`pitch_trend`/`haptic`(AHAP
  포맷) 구조로 프론트(iOS, Core Haptics)와 합의 완료. `haptic`은 `CHHapticPattern(dictionary:)`에 바로
  넣을 수 있는 AHAP 구조(Version/Pattern/Event/ParameterCurve) 그대로 사용.

### Next

- 강제정렬 파이프라인(wav2vec2 CTC + torchaudio forced_align) 프로토타입 작성, parselmouth 설치.
- 서버에 이미 있는 MFA 결과물(`mfa_work/`)을 레퍼런스 코퍼스 전처리에 재사용할 수 있는지 확인.
- Similar Voices를 완전히 뺄지, 광역 단위(경북 vs 타 시도)로 축소해서 부활시킬지는 추가 논의 여지 있음
  — 지금은 제거 상태로 진행.
