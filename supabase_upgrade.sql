-- Run once in Supabase SQL Editor. Existing tables and user data are preserved.
create table if not exists public.biu_market_bars (
  symbol text not null,
  frequency text not null,
  bar_time timestamptz not null,
  open double precision not null,
  high double precision not null,
  low double precision not null,
  close double precision not null,
  volume double precision not null default 0,
  amount double precision not null default 0,
  source text not null,
  is_closed boolean not null default true,
  updated_at timestamptz not null default now(),
  primary key(symbol, frequency, bar_time)
);
create index if not exists biu_market_bars_lookup on public.biu_market_bars(symbol, frequency, bar_time desc);

create table if not exists public.biu_analysis_cache (
  cache_key text primary key,
  category text not null,
  symbol text,
  strategy_version text,
  data_end_date date,
  payload jsonb not null,
  updated_at timestamptz not null default now()
);
create index if not exists biu_analysis_lookup on public.biu_analysis_cache(category, symbol, data_end_date desc);

alter table public.biu_market_bars enable row level security;
alter table public.biu_analysis_cache enable row level security;
-- The app uses the server-only Secret/service-role key. Do not add anonymous policies.
