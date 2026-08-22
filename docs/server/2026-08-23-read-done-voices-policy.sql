-- Allow authenticated app users, including anonymous-auth users, to read their
-- own voice rows and completed voice analysis rows created by other users.
--
-- This replaces the narrower "users read own voices" policy to avoid multiple
-- permissive SELECT policies on the same table/role/action.

drop policy if exists "users read own voices" on public.voices;
drop policy if exists "users read done voices" on public.voices;
drop policy if exists "users read own or done voices" on public.voices;
create policy "users read own or done voices"
  on public.voices
  for select
  to authenticated
  using (
    (select auth.uid()) = owner_id
    or status = 'done'
  );
