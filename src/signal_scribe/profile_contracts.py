from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class V1ContractModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class V1Company(V1ContractModel):
    ticker: str
    cik: str | None = None
    name: str | None = None
    exchange: str | None = None
    sic: str | None = None
    sector: str | None = None
    industry: str | None = None


class V1SourceReference(V1ContractModel):
    section: str | None = None
    form_type: str | None = Field(default=None, alias="formType")
    accession_number: str | None = Field(default=None, alias="accessionNumber")
    source_url: str | None = Field(default=None, alias="sourceUrl")
    excerpt: str | None = None


class V1Analysis(V1ContractModel):
    accession_number: str = Field(alias="accessionNumber")
    form_type: str = Field(alias="formType")
    filing_id: str | None = Field(default=None, alias="filingId")
    summary: str | None = None
    business_summary: str | None = Field(default=None, alias="businessSummary")
    key_findings: list[str] = Field(default_factory=list, alias="keyFindings")
    red_flags: list[str] = Field(default_factory=list, alias="redFlags")
    catalysts: list[str] = Field(default_factory=list)
    management_tone: str | None = Field(default=None, alias="managementTone")
    risk_score: float | None = Field(default=None, alias="riskScore")
    quality_score: float | None = Field(default=None, alias="qualityScore")
    source_references: list[V1SourceReference] = Field(
        default_factory=list,
        alias="sourceReferences",
    )
    created_at: str | None = Field(default=None, alias="createdAt")


class V1Filing(V1ContractModel):
    id: str | None = None
    accession_number: str = Field(alias="accessionNumber")
    form_type: str = Field(alias="formType")
    filing_date: str | None = Field(default=None, alias="filingDate")
    report_date: str | None = Field(default=None, alias="reportDate")
    fiscal_year: int | None = Field(default=None, alias="fiscalYear")
    fiscal_period: str | None = Field(default=None, alias="fiscalPeriod")
    sec_url: str | None = Field(default=None, alias="secUrl")
    primary_document_url: str | None = Field(default=None, alias="primaryDocumentUrl")


class V1FinancialFact(V1ContractModel):
    metric_name: str = Field(alias="metricName")
    value: float | None = None
    unit: str | None = None
    fiscal_year: int | None = Field(default=None, alias="fiscalYear")
    fiscal_period: str | None = Field(default=None, alias="fiscalPeriod")
    accession_number: str | None = Field(default=None, alias="accessionNumber")
    source: str | None = None


class V1FilingSection(V1ContractModel):
    filing_id: str | None = Field(default=None, alias="filingId")
    accession_number: str | None = Field(default=None, alias="accessionNumber")
    form_type: str | None = Field(default=None, alias="formType")
    filing_date: str | None = Field(default=None, alias="filingDate")
    section_name: str = Field(alias="sectionName")
    section_text: str = Field(alias="sectionText")
    chunk_index: int = Field(default=0, alias="chunkIndex")


class V1CompanyProfileResponse(V1ContractModel):
    status: Literal["available", "not_found"]
    company: V1Company | None = None
    analyses: list[V1Analysis] = Field(default_factory=list)
    filings: list[V1Filing] = Field(default_factory=list)
    financial_facts: list[V1FinancialFact] = Field(
        default_factory=list,
        alias="financialFacts",
    )
    sections: list[V1FilingSection] = Field(default_factory=list)
    message: str | None = None


def profile_not_found(ticker: str) -> V1CompanyProfileResponse:
    return V1CompanyProfileResponse(
        status="not_found",
        message=f"No SignalScribe profile found for ticker {ticker.upper()}",
    )


def dump_v1_profile(response: V1CompanyProfileResponse) -> dict[str, Any]:
    return response.model_dump(by_alias=True, mode="json")
