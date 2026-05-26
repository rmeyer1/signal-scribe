create extension if not exists "uuid-ossp";
create extension if not exists vector;

create table if not exists companies (
  id uuid primary key default uuid_generate_v4(),
  ticker text not null unique,
  cik text not null unique,
  company_name text not null,
  exchange text,
  sic text,
  sector text,
  industry text,
  created_at timestamptz not null default now()
);

create table if not exists filings (
  id uuid primary key default uuid_generate_v4(),
  company_id uuid references companies(id) on delete cascade,
  company_cik text not null,
  accession_number text not null unique,
  form_type text not null,
  filing_date date,
  report_date date,
  fiscal_year int,
  fiscal_period text,
  sec_url text,
  primary_document_url text,
  raw_text text,
  raw_html text,
  created_at timestamptz not null default now()
);

create table if not exists filing_sections (
  id uuid primary key default uuid_generate_v4(),
  filing_id uuid references filings(id) on delete cascade,
  section_name text not null,
  section_text text not null,
  chunk_index int not null default 0,
  embedding vector(1536),
  created_at timestamptz not null default now()
);

create table if not exists financial_facts (
  id uuid primary key default uuid_generate_v4(),
  company_id uuid references companies(id) on delete cascade,
  filing_id uuid references filings(id) on delete cascade,
  metric_name text not null,
  value numeric,
  unit text,
  fiscal_year int,
  fiscal_period text,
  accession_number text,
  source text not null default 'sec_xbrl',
  created_at timestamptz not null default now()
);

create table if not exists filing_analysis (
  id uuid primary key default uuid_generate_v4(),
  company_id uuid references companies(id) on delete set null,
  filing_id uuid references filings(id) on delete set null,
  company_ticker text,
  company_cik text not null,
  accession_number text not null unique,
  form_type text not null,
  summary text not null,
  business_summary text,
  key_findings jsonb not null default '[]'::jsonb,
  red_flags jsonb not null default '[]'::jsonb,
  catalysts jsonb not null default '[]'::jsonb,
  financial_summary jsonb not null default '[]'::jsonb,
  management_tone text,
  risk_score numeric,
  quality_score numeric,
  source_citations jsonb not null default '[]'::jsonb,
  raw_model_output jsonb,
  created_at timestamptz not null default now()
);

create index if not exists filing_analysis_summary_idx
  on filing_analysis using gin (to_tsvector('english', summary || ' ' || coalesce(business_summary, '')));

create index if not exists filing_analysis_risk_idx on filing_analysis (risk_score desc);
create index if not exists filings_company_form_idx on filings (company_cik, form_type, filing_date desc);
