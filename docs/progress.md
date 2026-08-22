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

- ~~`POST /api/voices/{id}/analyze` 응답 스키마에 맞는 mock 샘플 3개 작성~~ → 완료, `mocks/analyze-response-samples.json`.
- ~~AI-Hub 경상북도 방언 데이터가 시군 단위로 지역 라벨을 갖고 있는지 확인~~ → 완료(`speaker.birthplace` 등
  필드로 시군 필터링 가능), 아래 규명.
- 라벨 임계값(Rising Intonation 등)과 PCA 변환행렬을 AI-Hub 레퍼런스 코퍼스로 사전 피팅하는 전처리
  스크립트 작성.
- 충청도 관련 요소는 이 프로젝트 범위에 없음(이전 "경상도 vs 충청도 대결" 버전의 잔재였음, 삭제 확인됨) —
  경북 내부 시군 다양성에만 집중.

## 2026-08-22 — Supabase 프로젝트 생성 및 초기 스키마 적용

Supabase 프로젝트(`junction`, ref `nuofcxkxoaahnofytckg`, region `ap-northeast-2`)를 생성하고, 확정된
API 명세(Challenge/Voice/Analysis/Dialect Root/Archive·Map/Lexicon 6도메인)에 맞춰 초기 스키마를
Management API로 직접 적용했다.

- **스키마 파일**: `docs/schema.sql`. 테이블 8개 — `regions`, `challenges`, `voices`, `lemmas`,
  `variants`, `utterances`, `utterance_variants`, `exposures`.
- **`voices` 테이블에 분석 결과를 직접 저장**한다(별도 `prosody_features` 테이블 없음) —
  `mocks/analyze-response-samples.json`과 동일 필드(`avg_pitch`, `pitch_std`, `avg_duration`,
  `duration_std`, `labels`, `similar_regions`, `pca_x`/`pca_y`, `status`). `POST /voices/{id}/analyze`가
  이 행을 UPDATE하는 구조로 API 명세와 1:1 대응.
- **RLS**: 공개 데이터(`regions`/`challenges`/`lemmas`/`variants`/`utterances`)는 읽기 전용 공개 정책.
  `voices`/`exposures`는 익명 INSERT 허용(무로그인 설계). 분석 결과 UPDATE는 별도 정책 없음 —
  Python 서버가 `sb_secret_...`(service_role 계열) 키로 RLS를 우회해 직접 쓴다.
- **`regions` 시딩 완료**: 경상북도 23개 시군(포항·경주·김천·안동·구미·영주·영천·상주·문경·경산·
  군위·의성·청송·영양·영덕·청도·고령·성주·칠곡·예천·봉화·울진·울릉) 전체 삽입, count 23 확인.
- **키 3종 정리**: `SUPABASE_PUBLISHABLE_KEY`(iOS 앱에 그대로 심는 공개 키), `SUPABASE_SECRET_KEY`
  (서버 전용, RLS 우회), `SUPABASE_ACCESS_TOKEN`(Management API용 `sbp_...` — **계정 전체 프로젝트에
  접근 가능**하므로 스키마 변경 등 1회성 작업에만 쓰고 상시 보관하지 않는 게 안전). 전부 `.env`에만
  존재, `.gitignore`로 추적 제외 확인.

### Next

- ⚠️ **mock 샘플의 `region: "대구"`가 실제 `regions` 시딩과 불일치** — 대구는 광역시라 경북 23개
  시군에 포함되지 않음. mock을 경북 시군으로 교체하거나, "인접 문화권" 참고 데이터로 별도 처리할지
  결정 필요.
- Storage 버킷(`voices`) 생성 + 업로드 정책 설정 — 아직 미적용.
- AI-Hub 라벨로 `lemmas`/`variants`/`utterances` 실데이터 적재 (현재는 스키마만 있고 데이터는 비어있음).
- 라벨 임계값·PCA 변환행렬 사전 피팅 스크립트 작성 (이전 항목에서 이월).
