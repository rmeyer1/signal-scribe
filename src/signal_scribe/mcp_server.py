from signal_scribe.config import get_settings
from signal_scribe.pipeline import SignalScribePipeline
from signal_scribe.sec_client import SecClient
from signal_scribe.storage import get_store

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Install MCP support with: pip install 'signal-scribe[mcp]'") from exc


mcp = FastMCP("signal-scribe")


@mcp.tool()
async def list_latest_filings(ticker: str, form_types: list[str], limit: int = 10) -> dict:
    """List recent SEC filings for a ticker."""
    settings = get_settings()
    sec = SecClient(settings)
    try:
        cik, company_name = await sec.ticker_to_cik(ticker)
        filings = await sec.latest_filings(cik, form_types=form_types, limit=limit)
        return {
            "ticker": ticker.upper(),
            "company_name": company_name,
            "cik": cik,
            "filings": [filing.model_dump(mode="json") for filing in filings],
        }
    finally:
        await sec.close()


@mcp.tool()
async def analyze_latest_filings(
    ticker: str,
    form_types: list[str],
    limit: int = 1,
    persist: bool = True,
) -> dict:
    """Analyze latest SEC filings and optionally save the structured result."""
    settings = get_settings()
    pipeline = SignalScribePipeline(settings, get_store(settings))
    response = await pipeline.analyze_latest(ticker, form_types, limit, persist=persist)
    return response.model_dump(mode="json")


@mcp.tool()
async def search_saved_analyses(query: str, limit: int = 20) -> dict:
    """Search saved filing analyses by text."""
    settings = get_settings()
    store = get_store(settings)
    results = await store.search(query, limit=limit)
    return {"query": query, "matches": [item.model_dump(mode="json") for item in results]}


if __name__ == "__main__":
    mcp.run()
