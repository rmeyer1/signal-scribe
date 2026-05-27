from typing import Any

from signal_scribe.profile_contracts import (
    V1Analysis,
    V1Company,
    V1CompanyProfileResponse,
    V1Filing,
    V1FilingSection,
    V1FinancialFact,
    V1SourceReference,
    profile_not_found,
)
from signal_scribe.storage import AnalysisStore, SupabaseStore


ANALYSES_LIMIT = 5
FILINGS_LIMIT = 10
FINANCIAL_FACTS_LIMIT = 50
SECTIONS_LIMIT = 20


class CompanyProfileService:
    def __init__(self, store: AnalysisStore) -> None:
        self._store = store

    async def get_company_profile(self, ticker: str) -> V1CompanyProfileResponse:
        normalized_ticker = ticker.upper()
        if not isinstance(self._store, SupabaseStore):
            return profile_not_found(normalized_ticker)

        client = self._store._client
        company_rows = (
            client.table("companies")
            .select("id,ticker,cik,company_name,exchange,sic,sector,industry")
            .eq("ticker", normalized_ticker)
            .limit(1)
            .execute()
            .data
        )
        if not company_rows:
            return profile_not_found(normalized_ticker)

        company = company_rows[0]
        company_id = company["id"]

        analyses = (
            client.table("filing_analysis")
            .select(
                "filing_id,accession_number,form_type,summary,business_summary,"
                "key_findings,red_flags,catalysts,management_tone,risk_score,"
                "quality_score,source_citations,created_at"
            )
            .eq("company_id", company_id)
            .order("created_at", desc=True)
            .limit(ANALYSES_LIMIT)
            .execute()
            .data
        )
        filings = (
            client.table("filings")
            .select(
                "id,accession_number,form_type,filing_date,report_date,fiscal_year,"
                "fiscal_period,sec_url,primary_document_url"
            )
            .eq("company_id", company_id)
            .order("filing_date", desc=True)
            .limit(FILINGS_LIMIT)
            .execute()
            .data
        )
        financial_facts = (
            client.table("financial_facts")
            .select("metric_name,value,unit,fiscal_year,fiscal_period,accession_number,source")
            .eq("company_id", company_id)
            .order("fiscal_year", desc=True)
            .order("metric_name")
            .limit(FINANCIAL_FACTS_LIMIT)
            .execute()
            .data
        )
        filing_ids = [row["id"] for row in filings if row.get("id")]
        sections = self._fetch_sections(filing_ids) if filing_ids else []
        return build_company_profile_response(
            ticker=normalized_ticker,
            company_row=company,
            analysis_rows=analyses,
            filing_rows=filings,
            financial_fact_rows=financial_facts,
            section_rows=sections,
        )

    def _fetch_sections(self, filing_ids: list[str]) -> list[dict[str, Any]]:
        rows = (
            self._store._client.table("filing_sections")
            .select("filing_id,section_name,section_text,chunk_index")
            .in_("filing_id", filing_ids)
            .order("chunk_index")
            .limit(SECTIONS_LIMIT)
            .execute()
            .data
        )
        if not rows:
            return []

        filing_lookup = {
            row["id"]: row
            for row in (
                self._store._client.table("filings")
                .select("id,accession_number,form_type,filing_date")
                .in_("id", list({row["filing_id"] for row in rows if row.get("filing_id")}))
                .execute()
                .data
            )
        }
        for row in rows:
            filing = filing_lookup.get(row.get("filing_id")) or {}
            row["accession_number"] = filing.get("accession_number")
            row["form_type"] = filing.get("form_type")
            row["filing_date"] = filing.get("filing_date")
        return rows


def build_company_profile_response(
    ticker: str,
    company_row: dict[str, Any],
    analysis_rows: list[dict[str, Any]],
    filing_rows: list[dict[str, Any]],
    financial_fact_rows: list[dict[str, Any]],
    section_rows: list[dict[str, Any]],
) -> V1CompanyProfileResponse:
    return V1CompanyProfileResponse(
        status="available",
        company=_company_from_row(ticker, company_row),
        analyses=[_analysis_from_row(row) for row in analysis_rows],
        filings=[_filing_from_row(row) for row in filing_rows],
        financialFacts=[_financial_fact_from_row(row) for row in financial_fact_rows],
        sections=[_section_from_row(row) for row in section_rows],
    )


def _company_from_row(ticker: str, row: dict[str, Any]) -> V1Company:
    return V1Company(
        ticker=str(row.get("ticker") or ticker).upper(),
        cik=row.get("cik"),
        name=row.get("company_name"),
        exchange=row.get("exchange"),
        sic=row.get("sic"),
        sector=row.get("sector"),
        industry=row.get("industry"),
    )


def _analysis_from_row(row: dict[str, Any]) -> V1Analysis:
    return V1Analysis(
        accessionNumber=row["accession_number"],
        formType=row["form_type"],
        filingId=_optional_str(row.get("filing_id")),
        summary=row.get("summary"),
        businessSummary=row.get("business_summary"),
        keyFindings=row.get("key_findings") or [],
        redFlags=row.get("red_flags") or [],
        catalysts=row.get("catalysts") or [],
        managementTone=row.get("management_tone"),
        riskScore=row.get("risk_score"),
        qualityScore=row.get("quality_score"),
        sourceReferences=[
            _source_reference_from_row(reference)
            for reference in row.get("source_citations") or []
            if isinstance(reference, dict)
        ],
        createdAt=_optional_str(row.get("created_at")),
    )


def _filing_from_row(row: dict[str, Any]) -> V1Filing:
    return V1Filing(
        id=_optional_str(row.get("id")),
        accessionNumber=row["accession_number"],
        formType=row["form_type"],
        filingDate=_optional_str(row.get("filing_date")),
        reportDate=_optional_str(row.get("report_date")),
        fiscalYear=row.get("fiscal_year"),
        fiscalPeriod=row.get("fiscal_period"),
        secUrl=row.get("sec_url"),
        primaryDocumentUrl=row.get("primary_document_url"),
    )


def _financial_fact_from_row(row: dict[str, Any]) -> V1FinancialFact:
    return V1FinancialFact(
        metricName=row["metric_name"],
        value=row.get("value"),
        unit=row.get("unit"),
        fiscalYear=row.get("fiscal_year"),
        fiscalPeriod=row.get("fiscal_period"),
        accessionNumber=row.get("accession_number"),
        source=row.get("source"),
    )


def _section_from_row(row: dict[str, Any]) -> V1FilingSection:
    return V1FilingSection(
        filingId=_optional_str(row.get("filing_id")),
        accessionNumber=row.get("accession_number"),
        formType=row.get("form_type"),
        filingDate=_optional_str(row.get("filing_date")),
        sectionName=row["section_name"],
        sectionText=row["section_text"],
        chunkIndex=row.get("chunk_index") or 0,
    )


def _source_reference_from_row(row: dict[str, Any]) -> V1SourceReference:
    return V1SourceReference(
        section=row.get("section"),
        formType=row.get("form_type") or row.get("formType"),
        accessionNumber=row.get("accession_number") or row.get("accessionNumber"),
        sourceUrl=row.get("source_url") or row.get("sourceUrl"),
        excerpt=row.get("excerpt"),
    )


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None
