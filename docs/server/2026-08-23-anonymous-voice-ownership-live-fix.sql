-- Live Supabase fix for anonymous voice ownership.
--
-- This SQL aligns the live project with the documented MVP flow:
-- signInAnonymously() -> voices.owner_id = auth.uid() -> private Storage path
-- {auth.uid()}/{voice_id}.m4a.
--
-- Note: enabling Anonymous Sign-Ins is an Auth service setting, not a Postgres
-- schema setting. It must be enabled in Supabase Dashboard or via Management API:
-- PATCH /v1/projects/{ref}/config/auth
-- body: {"external_anonymous_users_enabled": true}

begin;

alter table public.voices
  add column if not exists owner_id uuid;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'voices_owner_id_fkey'
      and conrelid = 'public.voices'::regclass
  ) then
    alter table public.voices
      add constraint voices_owner_id_fkey
      foreign key (owner_id) references auth.users(id);
  end if;
end $$;

create index if not exists idx_voices_owner on public.voices(owner_id);

alter table public.voices enable row level security;

revoke all on table public.voices from anon;
revoke all on table public.voices from authenticated;
grant select, insert, update on table public.voices to authenticated;

drop policy if exists "public read voices" on public.voices;
drop policy if exists "public insert voices" on public.voices;
drop policy if exists "public update voice analysis" on public.voices;
drop policy if exists "users read own voices" on public.voices;
drop policy if exists "users read done voices" on public.voices;
drop policy if exists "users read own or done voices" on public.voices;
drop policy if exists "users insert own voices" on public.voices;
drop policy if exists "users update own voice analysis" on public.voices;

create policy "users read own or done voices"
  on public.voices
  for select
  to authenticated
  using (
    (select auth.uid()) = owner_id
    or status = 'done'
  );

create policy "users insert own voices"
  on public.voices
  for insert
  to authenticated
  with check ((select auth.uid()) = owner_id);

create policy "users update own voice analysis"
  on public.voices
  for update
  to authenticated
  using ((select auth.uid()) = owner_id)
  with check (
    (select auth.uid()) = owner_id
    and status in ('pending','processing','done','failed')
  );

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
  on storage.buckets
  for select
  using (id = 'voices');

drop policy if exists "public upload voice objects" on storage.objects;
drop policy if exists "public read voice objects" on storage.objects;
drop policy if exists "authenticated upload own voice objects" on storage.objects;
drop policy if exists "authenticated read own voice objects" on storage.objects;
drop policy if exists "authenticated update own voice objects" on storage.objects;

create policy "authenticated upload own voice objects"
  on storage.objects
  for insert
  to authenticated
  with check (
    bucket_id = 'voices'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  );

create policy "authenticated read own voice objects"
  on storage.objects
  for select
  to authenticated
  using (
    bucket_id = 'voices'
    and (
      owner_id = (select auth.uid()::text)
      or (storage.foldername(name))[1] = (select auth.uid()::text)
    )
  );

create policy "authenticated update own voice objects"
  on storage.objects
  for update
  to authenticated
  using (
    bucket_id = 'voices'
    and (
      owner_id = (select auth.uid()::text)
      or (storage.foldername(name))[1] = (select auth.uid()::text)
    )
  )
  with check (
    bucket_id = 'voices'
    and (storage.foldername(name))[1] = (select auth.uid()::text)
  );

commit;
