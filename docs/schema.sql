-- moracano schema (v2)
-- 계약 원본: mocks/ai-service-contract.json (AI 서비스 순수 입출력), mocks/backend-final-record.json
-- (voices 테이블 + AI 출력을 합친 최종 레코드), docs/ai/plan.md.
--
-- v1 대비 변경 (2026-08-22, 팀 실데이터 확인 반영):
--   - similar_regions 제거 (AI-Hub가 시군 단위 지역 라벨을 주지 않아 Similar Voices 기능 자체가
--     MVP에서 빠짐 — docs/progress.md "2026-08-22 — 서버 데이터 실사 + 스코프 조정" 참고)
--   - pca_x/pca_y → pca_coord numeric[] (계약의 [x, y] 배열 형태 그대로)
--   - syllables jsonb, haptic_pattern jsonb 추가 (강제정렬 음절 타이밍 + AHAP 햅틱 패턴)
--   - lemmas/variants/utterances.region_code에서 regions FK 제거: AI-Hub는 광역 단위(경북/경남/
--     부산/대구/울산)까지만 제공하고 시군 단위가 없어, 23개 시군 코드와 매칭되지 않음. 자유 텍스트로
--     남겨두고 voices.region_code(사용자가 앱에서 직접 고른 시군)만 regions를 참조.

create extension if not exists pgcrypto;

-- ── Archive·Map ──────────────────────────────────────────────
-- 사용자가 지도 UX에서 직접 선택하는 경북 23개 시군. AI-Hub 유래 데이터는 이 정밀도를 갖지 않는다.
create table if not exists regions (
  code text primary key,       -- '포항'
  name text not null           -- '포항시'
);

-- ── Challenge ────────────────────────────────────────────────
create table if not exists challenges (
  id             bigserial primary key,
  prompt_text    text not null,
  syllable_count smallint not null,   -- ASR 없이 강제정렬 입력 산정의 기준값
  variant_count  int,
  region_count   int,
  active_date    date,
  created_at     timestamptz not null default now()
);

-- ── Voice + Analysis (결과는 voices 행에 직접 기록) ──────────
-- backend-final-record.json과 1:1 대응. voice_id/region/prompt/status는 백엔드 소유,
-- avg_pitch ~ haptic_pattern은 AI 서비스 출력을 그대로 UPDATE.
create table if not exists voices (
  id             uuid primary key default gen_random_uuid(),
  challenge_id   bigint references challenges(id),
  region_code    text references regions(code),   -- 사용자 자기 신고 지역
  audio_path     text,
  status         text not null default 'pending'
                 check (status in ('pending','processing','done','failed')),
  avg_pitch      numeric,
  pitch_std      numeric,
  avg_duration   numeric,
  duration_std   numeric,
  labels         text[] default '{}',
  pca_coord      numeric[],           -- [x, y]
  syllables      jsonb,               -- [{text,start,end,pitch_trend}, ...]
  haptic_pattern jsonb,               -- AHAP 그대로 (Version/Pattern/...), CHHapticPattern에 직결
  created_at     timestamptz not null default now()
);

-- ── Lexicon ──────────────────────────────────────────────────
-- region_code는 AI-Hub 원 데이터의 광역 단위 태그(예: '경북')를 위한 자유 텍스트 — FK 없음.
create table if not exists lemmas (
  id            bigserial primary key,
  standard_form text not null unique,   -- AI-Hub eojeolList.standard로 묶은 표제어
  gloss         text,
  region_code   text,
  aihub_count   int default 0,
  user_count    int default 0
);

create table if not exists variants (
  id           bigserial primary key,
  lemma_id     bigint references lemmas(id) on delete cascade,
  surface      text not null,           -- 실제 방언 표면형 ("뿌리 갈래")
  region_code  text,
  aihub_count  int default 0,
  user_count   int default 0,
  unique (lemma_id, surface, region_code)
);

create table if not exists utterances (
  id              bigserial primary key,
  source          text not null check (source in ('aihub','user')),
  region_code     text,
  dialect_text    text not null,
  standard_text   text not null,
  syllable_count  int,
  dialect_density numeric,
  created_at      timestamptz not null default now()
);

create table if not exists utterance_variants (
  utterance_id bigint references utterances(id) on delete cascade,
  variant_id   bigint references variants(id) on delete cascade,
  primary key (variant_id, utterance_id)
);

create table if not exists exposures (
  user_key     text not null,          -- 브라우저/앱에 저장한 익명 키
  utterance_id bigint references utterances(id) on delete cascade,
  shown_at     timestamptz not null default now(),
  primary key (user_key, utterance_id)
);

-- ── indexes ──────────────────────────────────────────────────
create index if not exists idx_voices_challenge   on voices(challenge_id);
create index if not exists idx_voices_region      on voices(region_code);
create index if not exists idx_variants_lemma     on variants(lemma_id);
create index if not exists idx_utterances_region  on utterances(region_code);

-- ── RLS ──────────────────────────────────────────────────────
-- 공개 데이터는 읽기 전용 공개. voices/exposures는 익명 INSERT 허용(무로그인 설계).
-- 분석 결과 UPDATE는 별도 정책 없음 — Python 서버가 secret key(service_role 계열)로 RLS 우회.
alter table regions            enable row level security;
alter table challenges         enable row level security;
alter table voices             enable row level security;
alter table lemmas             enable row level security;
alter table variants           enable row level security;
alter table utterances         enable row level security;
alter table utterance_variants enable row level security;
alter table exposures          enable row level security;

create policy "public read regions"    on regions    for select using (true);
create policy "public read challenges" on challenges for select using (true);
create policy "public read lemmas"     on lemmas     for select using (true);
create policy "public read variants"   on variants   for select using (true);
create policy "public read utterances" on utterances for select using (true);
create policy "public read uv"         on utterance_variants for select using (true);

create policy "public read voices"   on voices for select using (true);
create policy "public insert voices" on voices for insert with check (true);

create policy "public read exposures"   on exposures for select using (true);
create policy "public insert exposures" on exposures for insert with check (true);
