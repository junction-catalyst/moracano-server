-- moracano schema (v4)
-- 계약 원본: mocks/on-device-analysis-contract.json (iOS 온디바이스 분석 출력),
-- mocks/backend-final-record.json (voices 테이블 + 분석 출력을 합친 최종 레코드),
-- docs/ai/plan.md.
--
-- v1 대비 변경 (2026-08-22, 팀 실데이터 확인 반영):
--   - similar_regions 제거 (AI-Hub가 시군 단위 지역 라벨을 주지 않아 Similar Voices 기능 자체가
--     MVP에서 빠짐 — docs/progress.md "2026-08-22 — 서버 데이터 실사 + 스코프 조정" 참고)
--   - pca_x/pca_y → pca_coord numeric[] (계약의 [x, y] 배열 형태 그대로)
--   - syllables jsonb, haptic_pattern jsonb 추가 (강제정렬 음절 타이밍 + AHAP 햅틱 패턴)
--   - seed 데이터의 출처 지역은 dialect_regions로 분리. voices.region_code는 사용자가 앱에서 직접
--     고른 시군(regions)을 참조하고, variants/utterances.region_code는 AI-Hub/seed 출처 지역
--     dialect_regions를 참조한다.

create extension if not exists pgcrypto;

-- ── Archive·Map ──────────────────────────────────────────────
-- 사용자가 지도 UX에서 직접 선택하는 경북 23개 시군. AI-Hub 유래 데이터는 이 정밀도를 갖지 않는다.
create table if not exists regions (
  code text primary key,       -- '포항'
  name text not null           -- '포항시'
);

-- AI-Hub/seed 데이터의 출처 지역. 광역 태그(GB)와 향후 시군 단위 태그를 함께 담는다.
create table if not exists dialect_regions (
  code        text primary key,       -- 'GB', '포항', '경주'
  name        text not null,          -- '경북', '포항시', '경주시'
  level       text not null check (level in ('province','city')),
  parent_code text references dialect_regions(code),
  created_at  timestamptz not null default now()
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
-- backend-final-record.json과 1:1 대응. iOS는 Supabase Anonymous Auth의 auth.uid()를
-- owner_id에 넣고, Storage 업로드 후 온디바이스 분석 결과를 직접 UPDATE한다.
create table if not exists voices (
  id             uuid primary key default gen_random_uuid(),
  owner_id       uuid references auth.users(id),
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

alter table voices add column if not exists owner_id uuid references auth.users(id);

-- ── Lexicon ──────────────────────────────────────────────────
-- lemmas는 표준어 표제어 전역 사전이다. 지역성은 variants/utterances가 담당한다.
create table if not exists lemmas (
  id            bigserial primary key,
  standard_form text not null unique,   -- AI-Hub eojeolList.standard로 묶은 표제어
  gloss         text,
  aihub_count   int default 0,
  user_count    int default 0
);

create table if not exists variants (
  id           bigserial primary key,
  lemma_id     bigint references lemmas(id) on delete cascade,
  surface      text not null,           -- 실제 방언 표면형 ("뿌리 갈래")
  region_code  text references dialect_regions(code), -- 방언 표현 출처 지역
  aihub_count  int default 0,
  user_count   int default 0,
  unique (lemma_id, surface, region_code)
);

create table if not exists utterances (
  id              bigserial primary key,
  source          text not null check (source in ('aihub','user','synthetic')),
  region_code     text references dialect_regions(code), -- 원문/예시 발화 출처 지역
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
create index if not exists idx_voices_owner       on voices(owner_id);
create index if not exists idx_dialect_regions_parent on dialect_regions(parent_code);
create index if not exists idx_variants_lemma     on variants(lemma_id);
create index if not exists idx_variants_region    on variants(region_code);
create index if not exists idx_utterances_region  on utterances(region_code);
create index if not exists idx_utterance_variants_utterance on utterance_variants(utterance_id);
create index if not exists idx_exposures_utterance on exposures(utterance_id);
create unique index if not exists uq_utterances_source_region_text
  on utterances(source, region_code, dialect_text, standard_text);

-- ── RLS ──────────────────────────────────────────────────────
-- 공개 데이터는 읽기 전용 공개. 사용자 녹음은 Supabase Anonymous Auth로 사용자를 만들고
-- auth.uid() = voices.owner_id 조건으로 본인 row만 INSERT/SELECT/UPDATE한다.
alter table regions            enable row level security;
alter table dialect_regions    enable row level security;
alter table challenges         enable row level security;
alter table voices             enable row level security;
alter table lemmas             enable row level security;
alter table variants           enable row level security;
alter table utterances         enable row level security;
alter table utterance_variants enable row level security;
alter table exposures          enable row level security;

create policy "public read regions"    on regions    for select using (true);
create policy "public read dialect regions" on dialect_regions for select using (true);
create policy "public read challenges" on challenges for select using (true);
create policy "public read lemmas"     on lemmas     for select using (true);
create policy "public read variants"   on variants   for select using (true);
create policy "public read utterances" on utterances for select using (true);
create policy "public read uv"         on utterance_variants for select using (true);

drop policy if exists "public read voices" on voices;
drop policy if exists "public insert voices" on voices;
drop policy if exists "public update voice analysis" on voices;

drop policy if exists "users read own voices" on voices;
create policy "users read own voices"
  on voices for select
  to authenticated
  using ((select auth.uid()) = owner_id);

drop policy if exists "users insert own voices" on voices;
create policy "users insert own voices"
  on voices for insert
  to authenticated
  with check ((select auth.uid()) = owner_id);

drop policy if exists "users update own voice analysis" on voices;
create policy "users update own voice analysis"
  on voices for update
  to authenticated
  using ((select auth.uid()) = owner_id)
  with check (
    (select auth.uid()) = owner_id
    and status in ('pending','processing','done','failed')
  );

create policy "public read exposures"   on exposures for select using (true);
create policy "public insert exposures" on exposures for insert with check (true);

-- ── Storage ──────────────────────────────────────────────────
-- Supabase Storage private bucket. iOS uploads m4a/aac audio to {auth.uid()}/{voice_id}.m4a,
-- and replay uses short-lived presigned-style URLs via createSignedUrl.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'voices',
  'voices',
  false,
  2097152,
  array['audio/mp4', 'audio/m4a', 'audio/x-m4a', 'audio/aac', 'audio/mpeg', 'audio/wav']
)
on conflict (id) do update
set public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types,
    updated_at = now();

drop policy if exists "public read voices bucket metadata" on storage.buckets;
create policy "public read voices bucket metadata"
  on storage.buckets for select
  using (id = 'voices');

drop policy if exists "public upload voice objects" on storage.objects;
drop policy if exists "authenticated upload own voice objects" on storage.objects;
create policy "authenticated upload own voice objects"
  on storage.objects for insert
  to authenticated
  with check (
    bucket_id = 'voices'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  );

drop policy if exists "public read voice objects" on storage.objects;
drop policy if exists "authenticated read own voice objects" on storage.objects;
create policy "authenticated read own voice objects"
  on storage.objects for select
  to authenticated
  using (
    bucket_id = 'voices'
    and owner_id = (select auth.uid()::text)
  );
