alter table filing_analysis
  add column if not exists filing_id uuid references filings(id) on delete set null;

alter table filing_sections
  add column if not exists chunk_index int not null default 0;

create index if not exists filing_analysis_filing_id_idx on filing_analysis (filing_id);
create index if not exists companies_ticker_idx on companies (ticker);
create index if not exists companies_cik_idx on companies (cik);
create index if not exists financial_facts_metric_idx on financial_facts (metric_name);
create index if not exists filing_sections_section_name_idx on filing_sections (section_name);
