-- Blacklist Records — Supabase setup.
-- Supabase → SQL Editor → New query → επικόλλησε όλο το αρχείο → Run.
-- ΠΡΙΝ το τρέξεις: άλλαξε το email στο τέλος με το δικό σου.

-- ---------- table ----------
create table if not exists public.demos (
  id         uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  artist     text not null check (char_length(artist) between 1 and 100),
  email      text check (char_length(email) between 3 and 200),
  title      text check (char_length(title) between 1 and 150),
  feat       text check (char_length(feat) <= 150),
  submission_id uuid,
  track_no   int  check (track_no between 1 and 10),
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
revoke execute on function public.is_admin() from public, anon;
grant execute on function public.is_admin() to authenticated;

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
        array['audio/*', 'video/*'])
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

-- ---------- traffic & visitors (anonymous, no IP) ----------
create table if not exists public.visits (
  id         bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  visitor    text check (char_length(visitor) <= 40),
  path       text check (char_length(path) <= 200),
  source     text check (char_length(source) <= 100),
  device     text check (device in ('mobile', 'tablet', 'desktop')),
  tz         text check (char_length(tz) <= 60),
  lang       text check (char_length(lang) <= 20),
  last_seen  timestamptz
);
create index if not exists visits_created_at on public.visits (created_at desc);
alter table public.visits enable row level security;
drop policy if exists "anyone can log a visit" on public.visits;
create policy "anyone can log a visit" on public.visits for insert to anon, authenticated with check (true);
drop policy if exists "admins read visits" on public.visits;
create policy "admins read visits" on public.visits for select to authenticated using (public.is_admin());

create or replace function public.start_visit(p_visitor text, p_path text, p_source text, p_device text, p_tz text, p_lang text)
returns bigint language sql security definer set search_path = public as $$
  insert into public.visits (visitor, path, source, device, tz, lang, last_seen)
  values (left(p_visitor, 40), left(p_path, 200), left(p_source, 100),
          case when p_device in ('mobile', 'tablet', 'desktop') then p_device end,
          left(p_tz, 60), left(p_lang, 20), now())
  returning id;
$$;

create or replace function public.ping_visit(p_id bigint, p_visitor text) returns void
language sql security definer set search_path = public as $$
  update public.visits set last_seen = now()
  where id = p_id and visitor is not distinct from p_visitor and created_at > now() - interval '6 hours';
$$;

revoke execute on function public.start_visit(text, text, text, text, text, text) from public;
revoke execute on function public.ping_visit(bigint, text) from public;
grant execute on function public.start_visit(text, text, text, text, text, text) to anon, authenticated;
grant execute on function public.ping_visit(bigint, text) to anon, authenticated;

create or replace function public.traffic_stats(days int default 30) returns json
language plpgsql stable security definer set search_path = public as $$
declare
  since timestamptz := date_trunc('day', now() at time zone 'Europe/Athens') at time zone 'Europe/Athens' - make_interval(days => days - 1);
  today timestamptz := date_trunc('day', now() at time zone 'Europe/Athens') at time zone 'Europe/Athens';
begin
  if not public.is_admin() then raise exception 'not allowed'; end if;
  return json_build_object(
    'live', (select count(distinct visitor) from visits where last_seen > now() - interval '45 seconds'),
    'avg_seconds', (select coalesce(round(avg(extract(epoch from (last_seen - created_at)))), 0) from visits
                    where created_at >= since and last_seen is not null),
    'visitors', (select count(distinct visitor) from visits where created_at >= since),
    'views', (select count(*) from visits where created_at >= since),
    'today', (select count(distinct visitor) from visits where created_at >= today),
    'submissions', (select count(distinct coalesce(submission_id, id)) from demos where created_at >= since),
    'tracks', (select count(*) from demos where created_at >= since and file_path is not null),
    'daily', (select coalesce(json_agg(json_build_object('day', d::date, 'visitors', coalesce(v.n, 0), 'views', coalesce(v.p, 0)) order by d), '[]')
              from generate_series(since at time zone 'Europe/Athens', today at time zone 'Europe/Athens', interval '1 day') d
              left join (select date_trunc('day', created_at at time zone 'Europe/Athens') k, count(distinct visitor) n, count(*) p
                         from visits where created_at >= since group by 1) v on v.k = d),
    'sources', (select coalesce(json_agg(x), '[]') from (select source as name, count(distinct visitor) as n from visits
                where created_at >= since group by 1 order by 2 desc limit 8) x),
    'devices', (select coalesce(json_agg(x), '[]') from (select device as name, count(distinct visitor) as n from visits
                where created_at >= since group by 1 order by 2 desc) x),
    'places', (select coalesce(json_agg(x), '[]') from (select tz as name, count(distinct visitor) as n from visits
               where created_at >= since group by 1 order by 2 desc limit 8) x)
  );
end $$;
revoke execute on function public.traffic_stats(int) from public, anon;
grant execute on function public.traffic_stats(int) to authenticated;

-- ---------- ΒΑΛΕ ΤΟ ΔΙΚΟ ΣΟΥ EMAIL ----------
insert into public.admins (email) values ('to-email-sou@example.com') on conflict do nothing;
