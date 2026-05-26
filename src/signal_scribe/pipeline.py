from signal_scribe.analyzer import FilingAnalyzer
from signal_scribe.config import Settings
from signal_scribe.embeddings import EmbeddingService
from signal_scribe.financials import extract_recent_financial_metrics
from signal_scribe.schemas import AnalyzeResponse, Company, FilingAnalysis, FilingMetadata
from signal_scribe.sec_client import SecClient
from signal_scribe.sections import extract_filing_sections
from signal_scribe.storage import AnalysisStore


class SignalScribePipeline:
    def __init__(self, settings: Settings, store: AnalysisStore) -> None:
        self._settings = settings
        self._store = store
        self._analyzer = FilingAnalyzer(settings)
        self._embeddings = EmbeddingService(settings)

    async def analyze_latest(
        self,
        ticker: str,
        form_types: list[str],
        limit: int,
        persist: bool = True,
    ) -> AnalyzeResponse:
        sec = SecClient(self._settings)
        try:
            cik, company_name = await sec.ticker_to_cik(ticker)
            company = Company(ticker=ticker.upper(), cik=cik, company_name=company_name)
            filings = await sec.latest_filings(cik, form_types=form_types, limit=limit)
            company_facts = await sec.company_facts(cik)
            analyses: list[FilingAnalysis] = []
            for metadata in filings:
                analysis = await self._process_filing_with_sec(
                    sec=sec,
                    company=company,
                    metadata=metadata,
                    company_facts=company_facts,
                    persist=persist,
                )
                analyses.append(analysis)
        finally:
            await sec.close()

        return AnalyzeResponse(
            status="saved" if persist else "dry_run",
            analyses=analyses,
        )

    async def process_filing(
        self,
        company: Company,
        metadata: FilingMetadata,
        persist: bool = True,
    ) -> FilingAnalysis:
        sec = SecClient(self._settings)
        try:
            company_facts = await sec.company_facts(company.cik)
            return await self._process_filing_with_sec(
                sec=sec,
                company=company,
                metadata=metadata,
                company_facts=company_facts,
                persist=persist,
            )
        finally:
            await sec.close()

    async def _process_filing_with_sec(
        self,
        sec: SecClient,
        company: Company,
        metadata: FilingMetadata,
        company_facts: dict,
        persist: bool,
    ) -> FilingAnalysis:
        document = await sec.filing_document(metadata)
        metrics = extract_recent_financial_metrics(company_facts, metadata.accession_number)
        sections = extract_filing_sections(document.raw_text, metadata.form_type)
        sections = await self._embeddings.embed_sections(sections)
        analysis = await self._analyzer.analyze(company.ticker, document, metrics)
        if persist:
            await self._store.save_filing_run(
                company=company,
                document=document,
                metrics=metrics,
                sections=sections,
                analysis=analysis,
            )
        return analysis
