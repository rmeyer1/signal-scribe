import asyncio
import json

import typer

from signal_scribe.config import get_settings
from signal_scribe.embeddings import EmbeddingService
from signal_scribe.ingestion import DEFAULT_FORM_TYPES, IngestionService
from signal_scribe.pipeline import SignalScribePipeline
from signal_scribe.storage import SupabaseStore, get_store

app = typer.Typer(help="Signal Scribe SEC filings agent CLI.")


@app.command()
def analyze(
    ticker: str,
    form_types: str = "10-K,10-Q,8-K,S-1",
    limit: int = 1,
    persist: bool = True,
) -> None:
    """Analyze latest SEC filings for a ticker."""
    settings = get_settings()
    store = get_store(settings)
    pipeline = SignalScribePipeline(settings, store)
    response = asyncio.run(
        pipeline.analyze_latest(
            ticker=ticker,
            form_types=[item.strip() for item in form_types.split(",") if item.strip()],
            limit=limit,
            persist=persist,
        )
    )
    typer.echo(json.dumps(response.model_dump(mode="json"), indent=2))


@app.command()
def sync_universe(
    name: str,
    source: str = typer.Option("sec-exchange", help="sec-exchange or csv"),
    exchange: str = typer.Option("Nasdaq", help="Exchange for sec-exchange source, or ALL."),
    csv_path: str | None = typer.Option(None, help="CSV with ticker/symbol and optional cik/name."),
    limit: int | None = typer.Option(None, help="Limit companies for test universes."),
    only_if_missing: bool = typer.Option(
        False,
        "--only-if-missing",
        help="Skip refresh when the universe already exists.",
    ),
) -> None:
    """Create or refresh a universe of companies."""
    settings = get_settings()
    store = _require_supabase_store()
    service = IngestionService(settings, store)
    if only_if_missing and service.universe_exists(name):
        typer.echo(json.dumps({"name": name, "status": "exists"}, indent=2))
        return

    if source == "sec-exchange":
        result = asyncio.run(service.sync_universe_from_sec_exchange(name, exchange, limit=limit))
    elif source == "csv":
        if not csv_path:
            raise typer.BadParameter("--csv-path is required when --source csv")
        result = asyncio.run(service.sync_universe_from_csv(name, csv_path))
    else:
        raise typer.BadParameter("--source must be sec-exchange or csv")
    typer.echo(json.dumps(result, indent=2))


@app.command()
def discover_filings(
    universe: str,
    form_types: str = ",".join(DEFAULT_FORM_TYPES),
    limit_per_company: int = 5,
    company_limit: int | None = None,
) -> None:
    """Discover new SEC filings for a universe and enqueue unprocessed filings."""
    settings = get_settings()
    service = IngestionService(settings, _require_supabase_store())
    result = asyncio.run(
        service.discover_filings(
            universe_name=universe,
            form_types=[item.strip() for item in form_types.split(",") if item.strip()],
            limit_per_company=limit_per_company,
            company_limit=company_limit,
        )
    )
    typer.echo(json.dumps(result, indent=2))


@app.command()
def process_queued_filings(
    limit: int = 10,
    universe: str | None = None,
) -> None:
    """Process queued filing ingestion jobs."""
    settings = get_settings()
    service = IngestionService(settings, _require_supabase_store())
    result = asyncio.run(service.process_queued_filings(limit=limit, universe_name=universe))
    typer.echo(json.dumps(result, indent=2))


@app.command()
def semantic_search(
    query: str,
    limit: int = 10,
    ticker: str | None = None,
    form_type: str | None = None,
) -> None:
    """Search filing section chunks semantically."""
    settings = get_settings()
    store = get_store(settings)

    async def run() -> dict:
        embedding = await EmbeddingService(settings).embed_query(query)
        if embedding is None:
            return {"query": query, "matches": []}
        matches = await store.semantic_search(
            query_embedding=embedding,
            limit=limit,
            ticker=ticker,
            form_type=form_type,
        )
        return {"query": query, "matches": [match.model_dump(mode="json") for match in matches]}

    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the HTTP API."""
    import uvicorn

    uvicorn.run("signal_scribe.api:app", host=host, port=port, reload=True)


def _require_supabase_store() -> SupabaseStore:
    store = get_store(get_settings())
    if not isinstance(store, SupabaseStore):
        raise typer.BadParameter("Supabase URL and service role key are required for queue commands.")
    return store


if __name__ == "__main__":
    app()
