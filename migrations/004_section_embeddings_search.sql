create index if not exists filing_sections_embedding_hnsw_idx
  on filing_sections
  using hnsw (embedding extensions.vector_cosine_ops)
  where embedding is not null;

create or replace function match_filing_sections(
  query_embedding text,
  match_count int default 10,
  filter_ticker text default null,
  filter_form_type text default null
)
returns table (
  section_id uuid,
  filing_id uuid,
  company_ticker text,
  company_name text,
  accession_number text,
  form_type text,
  filing_date date,
  section_name text,
  chunk_index int,
  section_text text,
  similarity double precision
)
language sql
stable
as $$
  select
    fs.id as section_id,
    f.id as filing_id,
    c.ticker as company_ticker,
    c.company_name,
    f.accession_number,
    f.form_type,
    f.filing_date,
    fs.section_name,
    fs.chunk_index,
    fs.section_text,
    1 - (fs.embedding <=> query_embedding::extensions.vector) as similarity
  from filing_sections fs
  join filings f on f.id = fs.filing_id
  left join companies c on c.id = f.company_id
  where fs.embedding is not null
    and (filter_ticker is null or c.ticker = upper(filter_ticker))
    and (filter_form_type is null or f.form_type = filter_form_type)
  order by fs.embedding <=> query_embedding::extensions.vector
  limit match_count;
$$;
