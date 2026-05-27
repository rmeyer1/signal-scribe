# Signal Scribe

Signal Scribe is a backend agent for turning SEC EDGAR filings into structured financial intelligence. It follows the architecture from the shared planning chat:

```text
SEC EDGAR ingestion -> structured analysis -> Supabase/local storage -> API/MCP tools
```

The agent does not randomly browse. It fetches official SEC data, analyzes only selected filings, validates source references, and saves auditable JSON for other apps.

## What It Builds

- SEC ticker -> CIK lookup using `https://www.sec.gov/files/company_tickers.json`
- Recent filing discovery using SEC submissions JSON
- Filing document retrieval from SEC Archives
- XBRL company facts extraction for common financial metrics
- OpenAI structured-output analysis when `OPENAI_API_KEY` is configured
- Deterministic dry-run analysis when no OpenAI key is present
- Supabase persistence when Supabase env vars are configured
- Local JSONL persistence as a development fallback
- FastAPI endpoints for other apps
- Optional MCP tools for Agent Builder / ChatGPT connector workflows

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env`:

```bash
SEC_USER_AGENT="Signal Scribe your-email@example.com"
OPENAI_API_KEY="sk-..."
SIGNAL_SCRIBE_API_KEY="server-to-server-shared-secret"
SUPABASE_URL="https://..."
SUPABASE_SERVICE_ROLE_KEY="..."
```

The SEC asks automated clients to declare a User-Agent and stay within fair-access limits. Signal Scribe defaults below the SEC's 10 requests/second ceiling.

## Run The API

```bash
signal-scribe serve --port 8000
```

Endpoints:

```text
GET  /health
GET  /v1/companies/{ticker}/profile
GET  /companies/{ticker}/latest-filings?form_types=10-K,10-Q,8-K,S-1&limit=10
POST /analyze
GET  /search?q=liquidity
POST /semantic-search
```

The `/v1/*` endpoints are the stable product API for downstream services. They require
server-to-server bearer auth:

```bash
curl http://127.0.0.1:8000/v1/companies/AAPL/profile \
  -H "Authorization: Bearer $SIGNAL_SCRIBE_API_KEY"
```

Example:

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H 'content-type: application/json' \
  -d '{"ticker":"AAPL","form_types":["10-K"],"limit":1,"persist":false}'
```

## Run From CLI

```bash
signal-scribe analyze AAPL --form-types 10-K --limit 1 --no-persist
```

Without `OPENAI_API_KEY`, this returns a dry-run heuristic analysis. With `OPENAI_API_KEY`, it uses structured JSON output from the Responses API.

Semantic search over embedded filing sections:

```bash
signal-scribe semantic-search "liquidity risk and debt obligations" --ticker AAPL --limit 5
```

Universe and queue workflow:

```bash
# Create or refresh a universe from SEC ticker/exchange mappings.
signal-scribe sync-universe nasdaq --source sec-exchange --exchange Nasdaq

# Create the universe only when it is missing; existing universes are left untouched.
signal-scribe sync-universe nasdaq --source sec-exchange --exchange Nasdaq --only-if-missing

# For licensed/custom index membership, use a CSV with ticker/symbol and optional cik/name/exchange columns.
signal-scribe sync-universe sp500 --source csv --csv-path ./sp500.csv

# Discover recent filings and enqueue only filings that are not already processed or queued.
signal-scribe discover-filings nasdaq --form-types 10-K,10-Q,8-K,S-1,S-3,DEF\ 14A --limit-per-company 5

# Production discovery can be bounded to recent filing dates to avoid an accidental historical backfill.
signal-scribe discover-filings nasdaq --lookback-days 7

# Process queued filings. This runs SEC fetch, financial fact extraction, OpenAI analysis,
# section extraction, embeddings, and Supabase persistence.
signal-scribe process-queued-filings --universe nasdaq --limit 10
```

These commands are intended to be called by whatever scheduler you choose later. No cron job is created by this repo.

## GitHub Actions

[ingest-filings.yml](.github/workflows/ingest-filings.yml) runs filing discovery and queue processing at:

```text
10:00 AM Eastern
1:00 PM Eastern
4:30 PM Eastern
9:00 PM Eastern
```

GitHub cron is UTC-only, so the workflow schedules both EST and EDT UTC equivalents and gates execution using `America/New_York` local time. The 9 PM run also refreshes universe membership before discovery.
Intraday runs first ensure the configured SEC exchange universe exists, so they can bootstrap a newly configured universe instead of failing discovery.

Required repository secrets:

```text
SEC_USER_AGENT
OPENAI_API_KEY
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
```

Useful repository variables:

```text
SIGNAL_SCRIBE_UNIVERSE=nasdaq
SIGNAL_SCRIBE_UNIVERSE_SOURCE=sec-exchange
SIGNAL_SCRIBE_EXCHANGE=Nasdaq
SIGNAL_SCRIBE_FORM_TYPES=10-K,10-Q,8-K,S-1,S-3,DEF 14A,20-F,40-F,6-K
SIGNAL_SCRIBE_LIMIT_PER_COMPANY=5
SIGNAL_SCRIBE_LOOKBACK_DAYS=7
SIGNAL_SCRIBE_COMPANY_LIMIT=
SIGNAL_SCRIBE_PROCESS_LIMIT=10
SIGNAL_SCRIBE_NIGHTLY_PROCESS_LIMIT=25
```

## Supabase

Run [migrations/001_initial.sql](migrations/001_initial.sql) in Supabase SQL editor or via the Supabase CLI.

The tables are:

- `companies`
- `filings`
- `filing_sections`
- `financial_facts`
- `filing_analysis`
- `universes`
- `universe_companies`
- `ingestion_runs`
- `filing_ingestion_jobs`

Persisted runs now write across the core tables:

- `companies`: one row per ticker/CIK.
- `filings`: filing metadata plus raw SEC text/html.
- `financial_facts`: normalized XBRL-derived metrics for queryable time-series analysis.
- `filing_sections`: extracted filing sections/chunks with OpenAI embeddings for semantic search.
- `filing_analysis`: model-generated summary, findings, risks, citations, and scores linked back to the filing.

Embeddings are generated with `OPENAI_EMBEDDING_MODEL`, defaulting to `text-embedding-3-small`, and stored in `filing_sections.embedding`. The database exposes `match_filing_sections(...)` for semantic section search.

Queue tables:

- `universes`: named groups like `nasdaq`, `sp500`, `russell2000`, or custom watchlists.
- `universe_companies`: active ticker/CIK membership for each universe.
- `ingestion_runs`: one row per discovery pass, with discovered/queued/skipped/failed counts.
- `filing_ingestion_jobs`: durable processing queue with status, attempts, errors, and filing metadata.

## Agent Builder / MCP

Install the optional MCP extra:

```bash
pip install -e ".[mcp]"
python -m signal_scribe.mcp_server
```

Exposed tools:

- `list_latest_filings`
- `analyze_latest_filings`
- `search_saved_analyses`

In Agent Builder, wire the workflow like:

```text
Input ticker/forms
-> list_latest_filings
-> analyze_latest_filings
-> validation/review node
-> save/query via API or MCP response
```

Recommended agent instruction:

```text
You are Signal Scribe, a financial filings analyst.
Use only SEC filing data returned by tools.
Do not invent financial numbers.
Use null for unknown values.
Cite form type, accession number, source URL, and filing section for material claims.
Flag liquidity, dilution, going-concern, related-party, debt, litigation, and revenue-quality risks.
Do not provide personalized investment advice.
Return structured JSON.
```

## Tests

```bash
pytest
```

## Notes

Primary external references used for this scaffold:

- [SEC EDGAR APIs](https://www.sec.gov/edgar/sec-api-documentation)
- [SEC Accessing EDGAR Data](https://www.sec.gov/os/accessing-edgar-data)
- [OpenAI Apps SDK / MCP docs](https://developers.openai.com/apps-sdk)
