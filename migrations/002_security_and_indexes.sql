alter table companies enable row level security;
alter table filings enable row level security;
alter table filing_sections enable row level security;
alter table financial_facts enable row level security;
alter table filing_analysis enable row level security;

create index if not exists filings_company_id_idx on filings (company_id);
create index if not exists filing_sections_filing_id_idx on filing_sections (filing_id);
create index if not exists financial_facts_company_id_idx on financial_facts (company_id);
create index if not exists financial_facts_filing_id_idx on financial_facts (filing_id);
create index if not exists filing_analysis_company_id_idx on filing_analysis (company_id);

create schema if not exists extensions;
alter extension vector set schema extensions;
