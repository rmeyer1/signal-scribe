import asyncio
import re
from datetime import date
from html import unescape
from time import monotonic
from typing import Any

import httpx

from signal_scribe.config import Settings
from signal_scribe.schemas import FilingDocument, FilingMetadata


SEC_WWW = "https://www.sec.gov"
SEC_DATA = "https://data.sec.gov"
TICKER_URL = f"{SEC_WWW}/files/company_tickers.json"
TICKER_EXCHANGE_URL = f"{SEC_WWW}/files/company_tickers_exchange.json"


class SecClientError(RuntimeError):
    pass


class AsyncRateLimiter:
    def __init__(self, requests_per_second: float) -> None:
        self._interval = 1.0 / max(requests_per_second, 0.1)
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    async def wait(self) -> None:
        async with self._lock:
            elapsed = monotonic() - self._last_request
            delay = self._interval - elapsed
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request = monotonic()


class SecClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._limiter = AsyncRateLimiter(settings.sec_requests_per_second)
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": settings.sec_user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "application/json, text/html, text/plain",
            },
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get_json(self, url: str) -> dict[str, Any]:
        await self._limiter.wait()
        response = await self._client.get(url)
        if response.status_code >= 400:
            raise SecClientError(f"SEC request failed {response.status_code}: {url}")
        return response.json()

    async def _get_text(self, url: str) -> str:
        await self._limiter.wait()
        response = await self._client.get(url)
        if response.status_code >= 400:
            raise SecClientError(f"SEC request failed {response.status_code}: {url}")
        return response.text

    async def ticker_to_cik(self, ticker: str) -> tuple[str, str]:
        payload = await self._get_json(TICKER_URL)
        normalized = ticker.upper()
        for item in payload.values():
            if item["ticker"].upper() == normalized:
                return str(item["cik_str"]).zfill(10), item["title"]
        raise SecClientError(f"Unknown ticker: {ticker}")

    async def company_tickers_exchange(self) -> list[dict[str, str]]:
        payload = await self._get_json(TICKER_EXCHANGE_URL)
        fields = payload.get("fields", [])
        rows = payload.get("data", [])
        companies: list[dict[str, str]] = []
        for row in rows:
            item = dict(zip(fields, row, strict=False))
            if not item.get("ticker") or not item.get("cik"):
                continue
            companies.append(
                {
                    "ticker": str(item["ticker"]).upper(),
                    "cik": str(item["cik"]).zfill(10),
                    "company_name": str(item.get("name") or ""),
                    "exchange": str(item.get("exchange") or ""),
                }
            )
        return companies

    async def company_submissions(self, cik: str) -> dict[str, Any]:
        return await self._get_json(f"{SEC_DATA}/submissions/CIK{cik.zfill(10)}.json")

    async def company_facts(self, cik: str) -> dict[str, Any]:
        return await self._get_json(f"{SEC_DATA}/api/xbrl/companyfacts/CIK{cik.zfill(10)}.json")

    async def latest_filings(
        self, cik: str, form_types: list[str] | None = None, limit: int = 10
    ) -> list[FilingMetadata]:
        submissions = await self.company_submissions(cik)
        recent = submissions.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        primary_docs = recent.get("primaryDocument", [])
        fiscal_years = recent.get("fy", [])
        fiscal_periods = recent.get("fp", [])

        accepted_forms = {form.upper() for form in form_types} if form_types else None
        filings: list[FilingMetadata] = []
        for idx, form in enumerate(forms):
            if accepted_forms and form.upper() not in accepted_forms:
                continue
            accession = accessions[idx]
            primary_document = primary_docs[idx] if idx < len(primary_docs) else None
            metadata = FilingMetadata(
                company_cik=cik.zfill(10),
                accession_number=accession,
                form_type=form,
                filing_date=_parse_date(filing_dates[idx] if idx < len(filing_dates) else None),
                report_date=_parse_date(report_dates[idx] if idx < len(report_dates) else None),
                fiscal_year=_parse_int(fiscal_years[idx] if idx < len(fiscal_years) else None),
                fiscal_period=fiscal_periods[idx] if idx < len(fiscal_periods) else None,
                sec_url=_filing_index_url(cik, accession),
                primary_document_url=_primary_document_url(cik, accession, primary_document),
                primary_document=primary_document,
            )
            filings.append(metadata)
            if len(filings) >= limit:
                break
        return filings

    async def filing_document(self, metadata: FilingMetadata) -> FilingDocument:
        if not metadata.primary_document_url:
            raise SecClientError(f"Filing has no primary document: {metadata.accession_number}")
        raw_html = await self._get_text(str(metadata.primary_document_url))
        return FilingDocument(
            metadata=metadata,
            raw_html=raw_html,
            raw_text=html_to_text(raw_html),
        )


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _accession_path(accession_number: str) -> str:
    return accession_number.replace("-", "")


def _filing_index_url(cik: str, accession_number: str) -> str:
    cik_int = str(int(cik))
    return f"{SEC_WWW}/Archives/edgar/data/{cik_int}/{_accession_path(accession_number)}"


def _primary_document_url(cik: str, accession_number: str, primary_document: str | None) -> str | None:
    if not primary_document:
        return None
    return f"{_filing_index_url(cik, accession_number)}/{primary_document}"


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(p|div|tr|h[1-6]|li|table)>", "\n", text)
    text = re.sub(r"(?is)<.*?>", " ", text)
    text = unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
