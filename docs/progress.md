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

## 2026-08-22 — Supabase 프로젝트 생성 및 스키마 적용 (위 스코프 조정 반영)

Supabase 프로젝트(`junction`, ref `nuofcxkxoaahnofytckg`, region `ap-northeast-2`)를 생성하고,
`mocks/backend-final-record.json`·`mocks/ai-service-contract.json` 계약에 맞춰 스키마를 Management API로
직접 적용했다. 최초 적용본은 그 직전 세션(위 "서버 데이터 실사" 항목)과 별개로 진행되고 있었어서
`similar_regions`/`pca_x`·`pca_y` 형태로 만들었다가, origin/dev를 머지하며 위 변경사항(Similar Voices
제거, syllables·haptic_pattern 추가)을 뒤늦게 확인하고 즉시 재수정했다.

- **스키마 파일**: `docs/schema.sql` (v2). 테이블 8개 — `regions`, `challenges`, `voices`, `lemmas`,
  `variants`, `utterances`, `utterance_variants`, `exposures`.
- **`voices`가 `backend-final-record.json`과 1:1 대응**: `avg_pitch`/`pitch_std`/`avg_duration`/
  `duration_std`/`labels`/`pca_coord`(numeric[])/`syllables`(jsonb)/`haptic_pattern`(jsonb, AHAP 그대로).
  `similar_regions`는 넣지 않음. `POST /voices/{id}/analyze`가 이 행을 UPDATE.
- **지역 필드 이원화**: `voices.region_code`만 `regions`(경북 23개 시군, 사용자가 지도 UX에서 직접
  선택)를 참조하는 FK다. `lemmas`/`variants`/`utterances.region_code`는 **FK 없는 자유 텍스트**로 바꿨다
  — AI-Hub 원본이 시군이 아니라 광역 단위(경북/경남/부산/대구/울산)까지만 주기 때문에, 23개 시군 코드와
  매칭이 안 된다. `sub_region` 컬럼은 세 테이블 모두에서 제거(항상 NULL이 될 게 뻔해서).
- **RLS**: 공개 데이터는 읽기 전용 공개. `voices`/`exposures`는 익명 INSERT 허용(무로그인 설계). 분석
  결과 UPDATE는 별도 정책 없음 — Python 서버가 `sb_secret_...`(service_role 계열) 키로 RLS를 우회.
- **`regions` 시딩 완료**: 경상북도 23개 시군 전체 삽입, count 23 확인. 이 테이블은 스키마 재작업 중에도
  건드리지 않았다.
- **키 3종 정리**: `SUPABASE_PUBLISHABLE_KEY`(iOS 앱에 그대로 심는 공개 키), `SUPABASE_SECRET_KEY`
  (서버 전용, RLS 우회), `SUPABASE_ACCESS_TOKEN`(Management API `sbp_...` — **계정의 다른 프로젝트에도
  접근 가능**함을 실제 확인함, 1회성 스키마 작업에만 쓰고 상시 보관하지 않는 게 안전). 전부 `.env`에만
  존재, `.gitignore`로 추적 제외 확인.

### Next

- ⚠️ **"개발 확정안"(Notion) 문서의 Challenge 선정 SQL이 무효화됨** — `count(distinct sub_region)`으로
  "여러 시군에서 다르게 말한 문장"을 고르는 쿼리를 제안했었는데, AI-Hub에 시군 라벨이 없어 그대로 못 씀.
  광역 단위 필터로 축소하거나, Challenge 50개를 수작업 큐레이션으로 전환할지 결정 필요 — Notion 갱신 필요.
- Storage 버킷(`voices`) 생성 + 업로드 정책 설정 — 아직 미적용.
- AI-Hub 라벨/강제정렬 파이프라인 출력으로 `lemmas`/`variants`/`utterances`/`voices` 실데이터 적재
  (현재는 스키마만 있고 데이터는 비어있음, `regions` 제외).
- 라벨 임계값·PCA 변환행렬 사전 피팅 스크립트 작성 (이전 항목에서 이월).

## 2026-08-22 — Supabase Storage + 온디바이스 분석으로 스코프 재조정

AI 모델/분석 로직을 iOS 로컬 온디바이스에서 실행하기로 하면서 별도 FastAPI/Python 분석 서버를 MVP
범위에서 제거했다. 음성 파일과 분석 결과는 Supabase만 사용한다.

- **Storage 결정**: Supabase Storage private `voices` bucket 사용. 데모 데이터는 10개 내외라 Free Plan
  한도(파일 저장 1GB, egress 10GB) 안에서 충분하다. 업로드 파일은 m4a/aac, 파일 크기는 2MB 이하로 제한.
- **데이터 흐름 변경**: iOS가 Anonymous Auth session 확보 → `voices` row 생성 →
  `{owner_id}/{voice_id}.m4a` 업로드 → 온디바이스 분석 → 같은 `voices` row에 `avg_pitch`/`pitch_std`/
  `avg_duration`/`duration_std`/`labels`/`pca_coord`/`syllables`/`haptic_pattern` update.
- **API 변경**: `POST /voices/{id}/analyze` 자체 서버 API는 MVP에서 제거. 분석 트리거는 iOS 로컬 함수가
  담당하고, 프론트는 Supabase row를 직접 조회한다.
- **RLS 변경**: 소셜 로그인 없이 Supabase Anonymous Auth를 사용한다. iOS는 `auth.uid()`를
  `voices.owner_id`에 저장하고, `voices` row와 Storage object는 owner 기준으로만 읽고 쓴다.
- **Storage metadata 조회 정책 추가**: publishable key로 `/storage/v1/bucket/voices` 확인 시
  `NoSuchBucket`처럼 보이지 않도록 `storage.buckets`의 `voices` row에만 select policy를 추가했다.
  bucket 자체는 계속 private이다.
- **계약 파일 변경**: `mocks/ai-service-contract.json`을 `mocks/on-device-analysis-contract.json`으로
  변경하고, `mocks/backend-final-record.json` 설명도 온디바이스 분석 기준으로 수정했다.

### Next

- iOS에서 Anonymous Auth session 생성, `voices` row insert, Storage upload, 분석 결과 update,
  `createSignedUrl` 기반 presigned URL 방식 재생을 한 번에 검증.
- Supabase Dashboard에서 `voices` bucket이 private인지, 2MB 제한과 MIME 제한이 적용됐는지 확인.
- 노출된 Management API access token은 작업 후 revoke/rotate.

## 2026-08-22 — Anonymous Auth 기반 사용자 녹음 소유권 반영

소셜 로그인/계정 UI를 만들기엔 MVP 범위가 과하므로, Supabase Anonymous Auth를 lightweight user
boundary로 쓰는 방향으로 스키마 계약을 바꿨다. 사용자는 로그인 플로우가 없지만,
DB/RLS 입장에서는 `auth.uid()`가 생기므로 사용자 녹음 row와 private Storage object를 본인 것만
접근하게 제한할 수 있다.

- **이슈/브랜치**: GitHub issue #1 기준 `feat/1-anonymous-voice-ownership` 브랜치에서 작업.
- **`voices.owner_id` 추가**: `auth.users(id)`를 참조하는 nullable 컬럼으로 추가했다. 기존
  healthcheck row가 있을 수 있어 즉시 `not null`로 잠그지 않고, 새 INSERT 정책에서
  `auth.uid() = owner_id`를 강제한다.
- **voices RLS 축소**: 기존 `public read/insert/update voices` 정책을 제거하고,
  `users read own voices`, `users insert own voices`, `users update own voice analysis` 정책으로 교체했다.
- **Storage RLS 축소**: `voices` bucket object는 `{auth.uid()}/{voice_id}.m4a` path에만 upload 가능하고,
  read/createSignedUrl은 object `owner_id`가 현재 `auth.uid()`와 같을 때만 가능하다.
- **계약 문서 반영**: `docs/ai/plan.md`와 `mocks/backend-final-record.json`에 `owner_id`와
  `{owner_id}/{voice_id}.m4a` object path를 반영했다.

### Next

- Supabase Dashboard에서 Anonymous Sign-Ins를 enable해야 한다.
- iOS에서 `signInAnonymously()` → `owner_id = session.user.id` → row insert → Storage upload →
  on-device update → `createSignedUrl` 재생 플로우를 실기기/시뮬레이터에서 확인한다.

## 2026-08-23 — 지역 확장형 seed 적재 구조 반영

포항/경주/안동/구미처럼 시군 단위 seed 데이터를 추가해도 표제어와 출처 지역 의미가 섞이지 않도록
lexicon 구조를 분리했다.

- **`dialect_regions` 추가**: AI-Hub/seed 데이터 출처 지역을 관리한다. `GB` 같은 광역 태그와
  `포항`/`경주` 같은 시군 태그를 함께 담을 수 있고, `level`은 `province` 또는 `city`로 제한한다.
- **`lemmas` 전역화**: `lemmas.region_code`를 제거했다. `lemmas.standard_form`은 표준어 표제어 자체만
  의미하며, 지역성은 `variants.region_code`와 `utterances.region_code`가 담당한다.
- **출처 지역 FK**: `variants.region_code`, `utterances.region_code`는 `dialect_regions(code)`를
  참조한다. `voices.region_code`는 기존대로 사용자가 앱에서 고른 `regions(code)`를 참조한다.
- **원문발화 중복 방지**: `utterances(source, region_code, dialect_text, standard_text)` unique index를
  추가했다. 같은 CSV를 다시 돌려도 같은 원문발화가 중복 삽입되지 않는다.
- **CSV seed 자동화**: `scripts/seed_challenge_sentences.py`를 추가했다. CSV의 `eojeol_list`에서
  `is_dialect=true`만 뽑아 `lemmas`/`variants`/`utterance_variants`를 만든다.

### 검증

- 라이브 Supabase에 `dialect_regions` 생성, 기존 `GB` 데이터 등록, FK와 unique index 적용 완료.
- 기존 seed 데이터 count 유지: `challenges=116`, `utterances=116`, `lemmas=27`, `variants=29`,
  `utterance_variants=116`, `dialect_regions=1`.
- publishable key로 `dialect_regions` 조회 확인.
- Supabase security advisor: lint 없음.
