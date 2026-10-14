-- Blacklist Records — Supabase setup.
-- Supabase → SQL Editor → New query → επικόλλησε όλο το αρχείο → Run.
-- ΠΡΙΝ το τρέξεις: άλλαξε το email στο τέλος με το δικό σου.

-- ---------- table ----------
create table if not exists public.demos (
  id         uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  artist     text not null check (char_length(artist) between 1 and 100),
  email      text not null check (char_length(email) between 3 and 200),
  title      text not null check (char_length(title) between 1 and 150),
  genre      text check (char_length(genre) <= 60),
  bpm        int  check (bpm between 40 and 250),
  music_key  text check (char_length(music_key) <= 20),
  instagram  text check (char_length(instagram) <= 200),
  link       text check (char_length(link) <= 500),
  message    text check (char_length(message) <= 2000),
  file_path  text check (char_length(file_path) <= 300),
  status     text not null default 'new' check (status in ('new', 'listened', 'shortlist', 'signed', 'rejected')),
  rating     int  check (rating between 1 and 5),
  notes      text,
  check (file_path is not null or link is not null)
);
create index if not exists demos_created_at on public.demos (created_at desc);

-- ---------- admins ----------
create table if not exists public.admins (email text primary key);
alter table public.admins enable row level security; -- no policies: not readable from the website

create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.admins where lower(email) = lower(auth.jwt() ->> 'email'));
$$;

-- ---------- row level security ----------
alter table public.demos enable row level security;

drop policy if exists "anyone can submit" on public.demos;
create policy "anyone can submit" on public.demos for insert to anon, authenticated
  with check (status = 'new' and rating is null and notes is null);

drop policy if exists "admins read" on public.demos;
create policy "admins read" on public.demos for select to authenticated using (public.is_admin());

drop policy if exists "admins update" on public.demos;
create policy "admins update" on public.demos for update to authenticated
  using (public.is_admin()) with check (public.is_admin());

drop policy if exists "admins delete" on public.demos;
create policy "admins delete" on public.demos for delete to authenticated using (public.is_admin());

-- ---------- storage (private bucket, 50 MB per file, audio only) ----------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('demos', 'demos', false, 52428800,
        array['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/x-wav', 'audio/wave', 'audio/aiff', 'audio/x-aiff',
              'audio/flac', 'audio/x-flac', 'audio/mp4', 'audio/x-m4a', 'audio/aac'])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "anyone can upload demo" on storage.objects;
create policy "anyone can upload demo" on storage.objects for insert to anon, authenticated
  with check (bucket_id = 'demos' and (storage.foldername(name))[1] = 'uploads');

drop policy if exists "admins read demo files" on storage.objects;
create policy "admins read demo files" on storage.objects for select to authenticated
  using (bucket_id = 'demos' and public.is_admin());

drop policy if exists "admins delete demo files" on storage.objects;
create policy "admins delete demo files" on storage.objects for delete to authenticated
  using (bucket_id = 'demos' and public.is_admin());

-- ---------- ΒΑΛΕ ΤΟ ΔΙΚΟ ΣΟΥ EMAIL ----------
insert into public.admins (email) values ('to-email-sou@example.com') on conflict do nothing;
