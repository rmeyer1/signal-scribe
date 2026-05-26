from datetime import UTC, date, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl


SupportedForm = Literal["10-K", "10-Q", "8-K", "S-1", "S-3", "DEF 14A", "20-F", "40-F", "6-K"]


class Company(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    ticker: str
    cik: str
    company_name: str
    exchange: str | None = None
    sic: str | None = None
    sector: str | None = None
    industry: str | None = None


class FilingMetadata(BaseModel):
    company_cik: str
    accession_number: str
    form_type: str
    filing_date: date | None = None
    report_date: date | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    sec_url: HttpUrl | None = None
    primary_document_url: HttpUrl | None = None
    primary_document: str | None = None


class FilingDocument(BaseModel):
    metadata: FilingMetadata
    raw_text: str
    raw_html: str | None = None


class FilingSection(BaseModel):
    id: UUID | None = None
    filing_id: UUID | None = None
    section_name: str
    section_text: str
    chunk_index: int = 0
    embedding: list[float] | None = None


class SourceReference(BaseModel):
    section: str | None = None
    form_type: str
    accession_number: str
    source_url: str | None = None
    excerpt: str | None = None


class FinancialMetric(BaseModel):
    name: str
    value: float | None = None
    unit: str | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    accession_number: str | None = None
    source: str = "sec_xbrl"


class FilingAnalysis(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    company_ticker: str
    company_cik: str
    filing_id: UUID | None = None
    accession_number: str
    form_type: str
    summary: str
    business_summary: str | None = None
    key_findings: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    catalysts: list[str] = Field(default_factory=list)
    financial_highlights: list[FinancialMetric] = Field(default_factory=list)
    management_tone: str | None = None
    risk_score: float | None = Field(default=None, ge=0, le=100)
    quality_score: float | None = Field(default=None, ge=0, le=100)
    source_references: list[SourceReference] = Field(default_factory=list)
    raw_model_output: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AnalyzeRequest(BaseModel):
    ticker: str
    form_types: list[str] = Field(default_factory=lambda: ["10-K", "10-Q", "8-K", "S-1"])
    limit: int = Field(default=1, ge=1, le=25)
    persist: bool = True


class AnalyzeResponse(BaseModel):
    status: Literal["saved", "dry_run", "skipped_duplicate", "needs_review"]
    analyses: list[FilingAnalysis]


class SearchResponse(BaseModel):
    query: str
    matches: list[FilingAnalysis]


class SemanticSearchRequest(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=50)
    ticker: str | None = None
    form_type: str | None = None


class SemanticSearchMatch(BaseModel):
    section_id: UUID
    filing_id: UUID
    company_ticker: str
    company_name: str | None = None
    accession_number: str
    form_type: str
    filing_date: date | None = None
    section_name: str
    chunk_index: int
    section_text: str
    similarity: float


class SemanticSearchResponse(BaseModel):
    query: str
    matches: list[SemanticSearchMatch]
