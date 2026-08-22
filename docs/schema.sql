-- moracano initial schema
-- Domains: Challenge / Voice / Analysis / Dialect Root / Archive·Map / Lexicon
-- See docs/spec.md and Notion "개발 확정안" for design rationale.

create extension if not exists pgcrypto;

-- ── Archive·Map ──────────────────────────────────────────────
create table if not exists regions (
  code text primary key,       -- '포항'
  name text not null           -- '포항시'
);

-- ── Challenge ────────────────────────────────────────────────
create table if not exists challenges (
  id             bigserial primary key,
  prompt_text    text not null,
  syllable_count smallint not null,   -- ASR 없이 음절 분할의 유일한 기준값
  variant_count  int,
  region_count   int,
  active_date    date,
  created_at     timestamptz not null default now()
);

-- ── Voice + Analysis (결과는 voices 행에 직접 기록) ──────────
create table if not exists voices (
  id             uuid primary key default gen_random_uuid(),
  challenge_id   bigint references challenges(id),
  region_code    text references regions(code),   -- 사용자가 지도 UX에서 직접 선택
  sub_region     text,
  audio_path     text,
  status         text not null default 'pending'
                 check (status in ('pending','processing','done','failed')),
  -- POST /voices/{id}/analyze 응답 필드 (mocks/analyze-response-samples.json과 동일 스키마)
  avg_pitch        numeric,
  pitch_std        numeric,
  avg_duration     numeric,
  duration_std     numeric,
  labels           text[] default '{}',
  similar_regions  text[] default '{}',
  pca_x            numeric,
  pca_y            numeric,
  created_at     timestamptz not null default now()
);

-- ── Lexicon ──────────────────────────────────────────────────
create table if not exists lemmas (
  id            bigserial primary key,
  standard_form text not null unique,   -- AI-Hub eojeolList.standard로 묶은 표제어
  gloss         text,
  region_code   text references regions(code),
  aihub_count   int default 0,
  user_count    int default 0
);

create table if not exists variants (
  id           bigserial primary key,
  lemma_id     bigint references lemmas(id) on delete cascade,
  surface      text not null,           -- 실제 방언 표면형 ("뿌리 갈래")
  region_code  text references regions(code),
  sub_region   text,
  aihub_count  int default 0,
  user_count   int default 0,
  unique (lemma_id, surface, region_code)
);

create table if not exists utterances (
  id              bigserial primary key,
  source          text not null check (source in ('aihub','user')),
  region_code     text references regions(code),
  sub_region      text,
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
-- 공개 데이터(challenges/lemmas/variants/utterances/regions)는 읽기 전용 공개.
-- voices는 익명 제출을 허용(무로그인 설계)하되, 분석 결과 UPDATE는 secret key(서버)만 수행 —
-- service_role 계열 키는 RLS를 우회하므로 별도 UPDATE 정책이 필요 없다.
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
