import json
from pathlib import Path
from uuid import UUID

from supabase import Client, create_client

from signal_scribe.config import Settings
from signal_scribe.embeddings import vector_to_sql
from signal_scribe.schemas import (
    Company,
    FilingAnalysis,
    FilingDocument,
    FilingSection,
    FinancialMetric,
    SemanticSearchMatch,
)


class AnalysisStore:
    async def save_filing_run(
        self,
        company: Company,
        document: FilingDocument,
        metrics: list[FinancialMetric],
        sections: list[FilingSection],
        analysis: FilingAnalysis,
    ) -> str:
        return await self.save_analysis(analysis)

    async def save_analysis(self, analysis: FilingAnalysis) -> str:
        raise NotImplementedError

    async def search(self, query: str, limit: int = 20) -> list[FilingAnalysis]:
        raise NotImplementedError

    async def semantic_search(
        self,
        query_embedding: list[float],
        limit: int = 10,
        ticker: str | None = None,
        form_type: str | None = None,
    ) -> list[SemanticSearchMatch]:
        raise NotImplementedError


class LocalJsonlStore(AnalysisStore):
    def __init__(self, path: str) -> None:
        self._path = Path(path)

    async def save_analysis(self, analysis: FilingAnalysis) -> str:
        self._path.parent.mkdir(parents=True, exist_ok=True) if self._path.parent != Path(".") else None
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(analysis.model_dump_json() + "\n")
        return str(analysis.id)

    async def search(self, query: str, limit: int = 20) -> list[FilingAnalysis]:
        if not self._path.exists():
            return []
        query_lower = query.lower()
        matches: list[FilingAnalysis] = []
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                analysis = FilingAnalysis.model_validate_json(line)
                haystack = json.dumps(analysis.model_dump(mode="json")).lower()
                if query_lower in haystack:
                    matches.append(analysis)
                if len(matches) >= limit:
                    break
        return matches

    async def semantic_search(
        self,
        query_embedding: list[float],
        limit: int = 10,
        ticker: str | None = None,
        form_type: str | None = None,
    ) -> list[SemanticSearchMatch]:
        return []


class SupabaseStore(AnalysisStore):
    def __init__(self, settings: Settings) -> None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise ValueError("Supabase settings are missing.")
        self._client: Client = create_client(settings.supabase_url, settings.supabase_service_role_key)

    async def save_analysis(self, analysis: FilingAnalysis) -> str:
        payload = _analysis_payload(analysis, company_id=None, filing_id=analysis.filing_id)
        result = (
            self._client.table("filing_analysis")
            .upsert(payload, on_conflict="accession_number")
            .execute()
        )
        row = result.data[0] if result.data else payload
        return row["id"]

    async def save_filing_run(
        self,
        company: Company,
        document: FilingDocument,
        metrics: list[FinancialMetric],
        sections: list[FilingSection],
        analysis: FilingAnalysis,
    ) -> str:
        company_id = self._upsert_company(company)
        filing_id = self._upsert_filing(company_id, document)
        self._replace_financial_facts(company_id, filing_id, metrics)
        self._replace_filing_sections(filing_id, sections)
        analysis.filing_id = UUID(filing_id)
        return self._upsert_analysis(company_id, filing_id, analysis)

    def _upsert_company(self, company: Company) -> str:
        payload = {
            "ticker": company.ticker.upper(),
            "cik": company.cik,
            "company_name": company.company_name,
            "exchange": company.exchange,
            "sic": company.sic,
            "sector": company.sector,
            "industry": company.industry,
        }
        result = self._client.table("companies").upsert(payload, on_conflict="cik").execute()
        return _first_row(result, "companies", {"cik": company.cik})["id"]

    def _upsert_filing(self, company_id: str, document: FilingDocument) -> str:
        metadata = document.metadata
        payload = {
            "company_id": company_id,
            "company_cik": metadata.company_cik,
            "accession_number": metadata.accession_number,
            "form_type": metadata.form_type,
            "filing_date": metadata.filing_date.isoformat() if metadata.filing_date else None,
            "report_date": metadata.report_date.isoformat() if metadata.report_date else None,
            "fiscal_year": metadata.fiscal_year,
            "fiscal_period": metadata.fiscal_period,
            "sec_url": str(metadata.sec_url) if metadata.sec_url else None,
            "primary_document_url": (
                str(metadata.primary_document_url) if metadata.primary_document_url else None
            ),
            "raw_text": document.raw_text,
            "raw_html": document.raw_html,
        }
        result = (
            self._client.table("filings")
            .upsert(payload, on_conflict="accession_number")
            .execute()
        )
        return _first_row(result, "filings", {"accession_number": metadata.accession_number})["id"]

    def _replace_financial_facts(
        self, company_id: str, filing_id: str, metrics: list[FinancialMetric]
    ) -> None:
        self._client.table("financial_facts").delete().eq("filing_id", filing_id).execute()
        if not metrics:
            return
        rows = [
            {
                "company_id": company_id,
                "filing_id": filing_id,
                "metric_name": metric.name,
                "value": metric.value,
                "unit": metric.unit,
                "fiscal_year": metric.fiscal_year,
                "fiscal_period": metric.fiscal_period,
                "accession_number": metric.accession_number,
                "source": metric.source,
            }
            for metric in metrics
        ]
        self._client.table("financial_facts").insert(rows).execute()

    def _replace_filing_sections(self, filing_id: str, sections: list[FilingSection]) -> None:
        self._client.table("filing_sections").delete().eq("filing_id", filing_id).execute()
        if not sections:
            return
        rows = [
            {
                "filing_id": filing_id,
                "section_name": section.section_name,
                "section_text": section.section_text,
                "chunk_index": section.chunk_index,
                "embedding": vector_to_sql(section.embedding) if section.embedding else None,
            }
            for section in sections
        ]
        self._client.table("filing_sections").insert(rows).execute()

    def _upsert_analysis(
        self, company_id: str, filing_id: str, analysis: FilingAnalysis
    ) -> str:
        payload = _analysis_payload(analysis, company_id=company_id, filing_id=filing_id)
        result = (
            self._client.table("filing_analysis")
            .upsert(payload, on_conflict="accession_number")
            .execute()
        )
        return _first_row(result, "filing_analysis", {"accession": analysis.accession_number})["id"]

    async def search(self, query: str, limit: int = 20) -> list[FilingAnalysis]:
        result = (
            self._client.table("filing_analysis")
            .select("*")
            .or_(f"summary.ilike.%{query}%,business_summary.ilike.%{query}%")
            .limit(limit)
            .execute()
        )
        return [_analysis_from_supabase(row) for row in result.data]

    async def semantic_search(
        self,
        query_embedding: list[float],
        limit: int = 10,
        ticker: str | None = None,
        form_type: str | None = None,
    ) -> list[SemanticSearchMatch]:
        result = self._client.rpc(
            "match_filing_sections",
            {
                "query_embedding": vector_to_sql(query_embedding),
                "match_count": limit,
                "filter_ticker": ticker.upper() if ticker else None,
                "filter_form_type": form_type,
            },
        ).execute()
        return [SemanticSearchMatch.model_validate(row) for row in result.data]


def get_store(settings: Settings) -> AnalysisStore:
    if settings.supabase_enabled:
        return SupabaseStore(settings)
    return LocalJsonlStore(settings.local_store_path)


def _analysis_from_supabase(row: dict) -> FilingAnalysis:
    return FilingAnalysis(
        id=row["id"],
        company_ticker=row.get("company_ticker", ""),
        company_cik=row["company_cik"],
        filing_id=row.get("filing_id"),
        accession_number=row["accession_number"],
        form_type=row["form_type"],
        summary=row["summary"],
        business_summary=row.get("business_summary"),
        key_findings=row.get("key_findings") or [],
        red_flags=row.get("red_flags") or [],
        catalysts=row.get("catalysts") or [],
        financial_highlights=row.get("financial_summary") or [],
        management_tone=row.get("management_tone"),
        risk_score=row.get("risk_score"),
        quality_score=row.get("quality_score"),
        source_references=row.get("source_citations") or [],
        raw_model_output=row.get("raw_model_output"),
        created_at=row.get("created_at"),
    )


def _first_row(result, table_name: str, lookup: dict) -> dict:
    if result.data:
        return result.data[0]
    raise RuntimeError(f"Supabase write to {table_name} returned no rows for {lookup}")


def _analysis_payload(
    analysis: FilingAnalysis,
    company_id: str | None,
    filing_id: str | None,
) -> dict:
    return {
        "id": str(analysis.id),
        "company_id": company_id,
        "company_ticker": analysis.company_ticker,
        "company_cik": analysis.company_cik,
        "filing_id": str(filing_id) if filing_id else None,
        "accession_number": analysis.accession_number,
        "form_type": analysis.form_type,
        "summary": analysis.summary,
        "business_summary": analysis.business_summary,
        "key_findings": analysis.key_findings,
        "red_flags": analysis.red_flags,
        "catalysts": analysis.catalysts,
        "financial_summary": [m.model_dump(mode="json") for m in analysis.financial_highlights],
        "management_tone": analysis.management_tone,
        "risk_score": analysis.risk_score,
        "quality_score": analysis.quality_score,
        "source_citations": [r.model_dump(mode="json") for r in analysis.source_references],
        "raw_model_output": analysis.raw_model_output,
    }
