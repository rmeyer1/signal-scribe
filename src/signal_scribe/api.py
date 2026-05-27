from hmac import compare_digest

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from signal_scribe.config import Settings, get_settings
from signal_scribe.embeddings import EmbeddingService
from signal_scribe.pipeline import SignalScribePipeline
from signal_scribe.profile_contracts import V1CompanyProfileResponse, dump_v1_profile
from signal_scribe.profile_service import CompanyProfileService
from signal_scribe.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    SearchResponse,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from signal_scribe.sec_client import SecClient
from signal_scribe.storage import AnalysisStore, get_store

bearer_auth = HTTPBearer(auto_error=False)

app = FastAPI(
    title="Signal Scribe",
    version="0.1.0",
    description="SEC EDGAR financial filings ingestion and analysis agent backend.",
)


def store_dependency(settings: Settings = Depends(get_settings)) -> AnalysisStore:
    return get_store(settings)


def profile_service_dependency(
    store: AnalysisStore = Depends(store_dependency),
) -> CompanyProfileService:
    return CompanyProfileService(store)


def require_v1_bearer_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_auth),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.signal_scribe_api_key:
        raise HTTPException(status_code=503, detail="SignalScribe API auth is not configured")
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not compare_digest(credentials.credentials, settings.signal_scribe_api_key):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/health")
async def health(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    return {
        "ok": True,
        "openai_enabled": settings.openai_enabled,
        "supabase_enabled": settings.supabase_enabled,
    }


@app.get("/companies/{ticker}/latest-filings")
async def latest_filings(
    ticker: str,
    form_types: str = "10-K,10-Q,8-K,S-1",
    limit: int = 10,
    settings: Settings = Depends(get_settings),
):
    sec = SecClient(settings)
    try:
        cik, company_name = await sec.ticker_to_cik(ticker)
        filings = await sec.latest_filings(
            cik,
            form_types=[item.strip() for item in form_types.split(",") if item.strip()],
            limit=limit,
        )
        return {"ticker": ticker.upper(), "company_name": company_name, "cik": cik, "filings": filings}
    finally:
        await sec.close()


@app.get("/v1/companies/{ticker}/profile", response_model=V1CompanyProfileResponse)
async def company_profile(
    ticker: str,
    _: None = Depends(require_v1_bearer_auth),
    service: CompanyProfileService = Depends(profile_service_dependency),
):
    try:
        profile = await service.get_company_profile(ticker)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="Unable to load company profile") from exc
    if profile.status == "not_found":
        return JSONResponse(status_code=404, content=dump_v1_profile(profile))
    return profile


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: AnalyzeRequest,
    settings: Settings = Depends(get_settings),
    store: AnalysisStore = Depends(store_dependency),
) -> AnalyzeResponse:
    pipeline = SignalScribePipeline(settings, store)
    return await pipeline.analyze_latest(
        ticker=request.ticker,
        form_types=request.form_types,
        limit=request.limit,
        persist=request.persist,
    )


@app.get("/search", response_model=SearchResponse)
async def search(
    q: str,
    limit: int = 20,
    store: AnalysisStore = Depends(store_dependency),
) -> SearchResponse:
    return SearchResponse(query=q, matches=await store.search(q, limit=limit))


@app.post("/semantic-search", response_model=SemanticSearchResponse)
async def semantic_search(
    request: SemanticSearchRequest,
    settings: Settings = Depends(get_settings),
    store: AnalysisStore = Depends(store_dependency),
) -> SemanticSearchResponse:
    embedding = await EmbeddingService(settings).embed_query(request.query)
    if embedding is None:
        return SemanticSearchResponse(query=request.query, matches=[])
    matches = await store.semantic_search(
        query_embedding=embedding,
        limit=request.limit,
        ticker=request.ticker,
        form_type=request.form_type,
    )
    return SemanticSearchResponse(query=request.query, matches=matches)
