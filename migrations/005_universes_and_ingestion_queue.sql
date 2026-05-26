create table if not exists universes (
  id uuid primary key default uuid_generate_v4(),
  name text not null unique,
  source text not null,
  source_config jsonb not null default '{}'::jsonb,
  refreshed_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists universe_companies (
  id uuid primary key default uuid_generate_v4(),
  universe_id uuid not null references universes(id) on delete cascade,
  ticker text not null,
  cik text not null,
  company_name text not null,
  exchange text,
  active boolean not null default true,
  added_at timestamptz not null default now(),
  removed_at timestamptz,
  unique (universe_id, cik)
);

create table if not exists ingestion_runs (
  id uuid primary key default uuid_generate_v4(),
  universe_id uuid references universes(id) on delete set null,
  status text not null default 'running',
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  discovered_count int not null default 0,
  queued_count int not null default 0,
  skipped_count int not null default 0,
  failed_count int not null default 0,
  error text
);

create table if not exists filing_ingestion_jobs (
  id uuid primary key default uuid_generate_v4(),
  universe_id uuid references universes(id) on delete set null,
  ingestion_run_id uuid references ingestion_runs(id) on delete set null,
  ticker text not null,
  cik text not null,
  company_name text,
  accession_number text not null unique,
  form_type text not null,
  filing_date date,
  report_date date,
  sec_url text,
  primary_document_url text,
  primary_document text,
  status text not null default 'queued'
    check (status in ('queued', 'processing', 'completed', 'failed', 'skipped')),
  attempts int not null default 0,
  max_attempts int not null default 3,
  last_error text,
  locked_at timestamptz,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table universes enable row level security;
alter table universe_companies enable row level security;
alter table ingestion_runs enable row level security;
alter table filing_ingestion_jobs enable row level security;

create index if not exists universe_companies_universe_active_idx
  on universe_companies (universe_id, active, ticker);
create index if not exists filing_ingestion_jobs_status_idx
  on filing_ingestion_jobs (status, created_at);
create index if not exists filing_ingestion_jobs_universe_idx
  on filing_ingestion_jobs (universe_id, status);
create index if not exists ingestion_runs_universe_started_idx
  on ingestion_runs (universe_id, started_at desc);
