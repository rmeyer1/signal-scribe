import csv
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from signal_scribe.config import Settings
from signal_scribe.pipeline import SignalScribePipeline
from signal_scribe.schemas import Company, FilingMetadata
from signal_scribe.sec_client import SecClient
from signal_scribe.storage import SupabaseStore


DEFAULT_FORM_TYPES = ["10-K", "10-Q", "8-K", "S-1", "S-3", "DEF 14A", "20-F", "40-F", "6-K"]


class IngestionService:
    def __init__(self, settings: Settings, store: SupabaseStore) -> None:
        self._settings = settings
        self._store = store
        self._client = store._client

    async def sync_universe_from_sec_exchange(
        self,
        name: str,
        exchange: str,
        limit: int | None = None,
    ) -> dict[str, Any]:
        sec = SecClient(self._settings)
        try:
            rows = await sec.company_tickers_exchange()
        finally:
            await sec.close()

        exchange_normalized = exchange.upper()
        companies = [
            row
            for row in rows
            if row["exchange"].upper() == exchange_normalized or exchange_normalized == "ALL"
        ]
        if limit:
            companies = companies[:limit]
        return self._sync_universe(
            name=name,
            source="sec_company_tickers_exchange",
            source_config={"exchange": exchange},
            companies=companies,
        )

    async def sync_universe_from_csv(self, name: str, csv_path: str) -> dict[str, Any]:
        path = Path(csv_path)
        rows = list(csv.DictReader(path.open("r", encoding="utf-8-sig")))

        sec = SecClient(self._settings)
        try:
            ticker_rows = {row["ticker"].upper(): row for row in await sec.company_tickers_exchange()}
        finally:
            await sec.close()

        companies: list[dict[str, str]] = []
        for row in rows:
            ticker = (row.get("ticker") or row.get("symbol") or row.get("Ticker") or "").upper()
            if not ticker:
                continue
            sec_row = ticker_rows.get(ticker)
            cik = str(row.get("cik") or row.get("CIK") or (sec_row or {}).get("cik") or "").zfill(10)
            if not cik or cik == "0000000000":
                continue
            companies.append(
                {
                    "ticker": ticker,
                    "cik": cik,
                    "company_name": row.get("company_name")
                    or row.get("name")
                    or row.get("Name")
                    or (sec_row or {}).get("company_name")
                    or ticker,
                    "exchange": row.get("exchange")
                    or row.get("Exchange")
                    or (sec_row or {}).get("exchange")
                    or "",
                }
            )

        return self._sync_universe(
            name=name,
            source="csv",
            source_config={"path": str(path)},
            companies=companies,
        )

    async def discover_filings(
        self,
        universe_name: str,
        form_types: list[str],
        limit_per_company: int = 5,
        company_limit: int | None = None,
        filed_after: date | None = None,
    ) -> dict[str, Any]:
        universe = self._get_universe(universe_name)
        run_id = self._create_ingestion_run(universe["id"])
        companies = self._active_universe_companies(universe["id"], limit=company_limit)
        sec = SecClient(self._settings)
        found = discovered = queued = skipped = outside_window = failed = 0

        try:
            for company in companies:
                try:
                    filings = await sec.latest_filings(
                        company["cik"],
                        form_types=form_types,
                        limit=limit_per_company,
                    )
                    for metadata in filings:
                        found += 1
                        if filed_after and (
                            metadata.filing_date is None or metadata.filing_date < filed_after
                        ):
                            outside_window += 1
                            continue
                        discovered += 1
                        if self._filing_or_completed_job_exists(metadata.accession_number):
                            skipped += 1
                            continue
                        self._queue_filing_job(
                            universe_id=universe["id"],
                            run_id=run_id,
                            company=company,
                            metadata=metadata,
                        )
                        queued += 1
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    self._record_discovery_error(
                        run_id,
                        f"{company['ticker']} ({company['cik']}): {type(exc).__name__}: {exc}",
                    )
            self._complete_ingestion_run(run_id, discovered, queued, skipped, failed)
        finally:
            await sec.close()

        return {
            "run_id": run_id,
            "universe": universe_name,
            "companies_checked": len(companies),
            "found": found,
            "discovered": discovered,
            "queued": queued,
            "skipped": skipped,
            "outside_window": outside_window,
            "failed": failed,
        }

    async def process_queued_filings(
        self,
        limit: int = 10,
        universe_name: str | None = None,
    ) -> dict[str, Any]:
        jobs = self._claim_jobs(limit=limit, universe_name=universe_name)
        pipeline = SignalScribePipeline(self._settings, self._store)
        completed = failed = 0

        for job in jobs:
            try:
                company = Company(
                    ticker=job["ticker"],
                    cik=job["cik"],
                    company_name=job.get("company_name") or job["ticker"],
                )
                metadata = FilingMetadata(
                    company_cik=job["cik"],
                    accession_number=job["accession_number"],
                    form_type=job["form_type"],
                    filing_date=job.get("filing_date"),
                    report_date=job.get("report_date"),
                    sec_url=job.get("sec_url"),
                    primary_document_url=job.get("primary_document_url"),
                    primary_document=job.get("primary_document"),
                )
                analysis = await pipeline.process_filing(company, metadata, persist=True)
                self._mark_job_completed(job["id"], str(analysis.id))
                completed += 1
            except Exception as exc:  # noqa: BLE001
                self._mark_job_failed(job, exc)
                failed += 1

        return {"claimed": len(jobs), "completed": completed, "failed": failed}

    def universe_exists(self, universe_name: str) -> bool:
        result = (
            self._client.table("universes")
            .select("id")
            .eq("name", universe_name)
            .limit(1)
            .execute()
        )
        return bool(result.data)

    def _sync_universe(
        self,
        name: str,
        source: str,
        source_config: dict[str, Any],
        companies: list[dict[str, str]],
    ) -> dict[str, Any]:
        companies = _dedupe_companies_by_cik(companies)
        universe_result = (
            self._client.table("universes")
            .upsert(
                {
                    "name": name,
                    "source": source,
                    "source_config": source_config,
                    "refreshed_at": _now_iso(),
                },
                on_conflict="name",
            )
            .execute()
        )
        universe = universe_result.data[0]
        universe_id = universe["id"]
        active_ciks = {company["cik"] for company in companies}

        existing = (
            self._client.table("universe_companies")
            .select("id,cik")
            .eq("universe_id", universe_id)
            .execute()
            .data
        )
        for row in existing:
            if row["cik"] not in active_ciks:
                self._client.table("universe_companies").update(
                    {"active": False, "removed_at": _now_iso()}
                ).eq("id", row["id"]).execute()

        if companies:
            rows = [
                {
                    "universe_id": universe_id,
                    "ticker": company["ticker"].upper(),
                    "cik": company["cik"],
                    "company_name": company["company_name"],
                    "exchange": company.get("exchange"),
                    "active": True,
                    "removed_at": None,
                }
                for company in companies
            ]
            self._client.table("universe_companies").upsert(
                rows,
                on_conflict="universe_id,cik",
            ).execute()

        return {"universe_id": universe_id, "name": name, "companies": len(companies)}

    def _get_universe(self, universe_name: str) -> dict[str, Any]:
        result = self._client.table("universes").select("*").eq("name", universe_name).execute()
        if not result.data:
            raise ValueError(f"Universe does not exist: {universe_name}")
        return result.data[0]

    def _active_universe_companies(self, universe_id: str, limit: int | None) -> list[dict[str, Any]]:
        query = (
            self._client.table("universe_companies")
            .select("*")
            .eq("universe_id", universe_id)
            .eq("active", True)
            .order("ticker")
        )
        if limit:
            query = query.limit(limit)
        return query.execute().data

    def _create_ingestion_run(self, universe_id: str) -> str:
        result = self._client.table("ingestion_runs").insert({"universe_id": universe_id}).execute()
        return result.data[0]["id"]

    def _complete_ingestion_run(
        self,
        run_id: str,
        discovered: int,
        queued: int,
        skipped: int,
        failed: int,
    ) -> None:
        self._client.table("ingestion_runs").update(
            {
                "status": "completed" if failed == 0 else "completed_with_errors",
                "completed_at": _now_iso(),
                "discovered_count": discovered,
                "queued_count": queued,
                "skipped_count": skipped,
                "failed_count": failed,
            }
        ).eq("id", run_id).execute()

    def _record_discovery_error(self, run_id: str, error: str) -> None:
        self._client.table("ingestion_runs").update({"error": error}).eq("id", run_id).execute()

    def _filing_or_completed_job_exists(self, accession_number: str) -> bool:
        filing = (
            self._client.table("filings")
            .select("id")
            .eq("accession_number", accession_number)
            .limit(1)
            .execute()
            .data
        )
        if filing:
            return True
        job = (
            self._client.table("filing_ingestion_jobs")
            .select("id,status")
            .eq("accession_number", accession_number)
            .in_("status", ["queued", "processing", "completed"])
            .limit(1)
            .execute()
            .data
        )
        return bool(job)

    def _queue_filing_job(
        self,
        universe_id: str,
        run_id: str,
        company: dict[str, Any],
        metadata: FilingMetadata,
    ) -> None:
        self._client.table("filing_ingestion_jobs").upsert(
            {
                "universe_id": universe_id,
                "ingestion_run_id": run_id,
                "ticker": company["ticker"],
                "cik": company["cik"],
                "company_name": company.get("company_name"),
                "accession_number": metadata.accession_number,
                "form_type": metadata.form_type,
                "filing_date": metadata.filing_date.isoformat() if metadata.filing_date else None,
                "report_date": metadata.report_date.isoformat() if metadata.report_date else None,
                "sec_url": str(metadata.sec_url) if metadata.sec_url else None,
                "primary_document_url": (
                    str(metadata.primary_document_url) if metadata.primary_document_url else None
                ),
                "primary_document": metadata.primary_document,
                "status": "queued",
                "updated_at": _now_iso(),
            },
            on_conflict="accession_number",
        ).execute()

    def _claim_jobs(self, limit: int, universe_name: str | None) -> list[dict[str, Any]]:
        query = (
            self._client.table("filing_ingestion_jobs")
            .select("*, universes!inner(name)")
            .eq("status", "queued")
            .lt("attempts", 3)
            .order("filing_date")
            .limit(limit)
        )
        if universe_name:
            query = query.eq("universes.name", universe_name)
        jobs = query.execute().data
        for job in jobs:
            self._client.table("filing_ingestion_jobs").update(
                {
                    "status": "processing",
                    "attempts": int(job.get("attempts") or 0) + 1,
                    "locked_at": _now_iso(),
                    "started_at": _now_iso(),
                    "updated_at": _now_iso(),
                }
            ).eq("id", job["id"]).eq("status", "queued").execute()
        return jobs

    def _mark_job_completed(self, job_id: str, analysis_id: str) -> None:
        self._client.table("filing_ingestion_jobs").update(
            {
                "status": "completed",
                "completed_at": _now_iso(),
                "last_error": None,
                "updated_at": _now_iso(),
            }
        ).eq("id", job_id).execute()

    def _mark_job_failed(self, job: dict[str, Any], exc: Exception) -> None:
        attempts = int(job.get("attempts") or 0) + 1
        max_attempts = int(job.get("max_attempts") or 3)
        self._client.table("filing_ingestion_jobs").update(
            {
                "status": "failed" if attempts >= max_attempts else "queued",
                "last_error": f"{type(exc).__name__}: {exc}",
                "attempts": attempts,
                "updated_at": _now_iso(),
            }
        ).eq("id", job["id"]).execute()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _dedupe_companies_by_cik(companies: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: dict[str, dict[str, str]] = {}
    for company in companies:
        cik = company["cik"]
        if cik not in deduped:
            deduped[cik] = company
    return list(deduped.values())
