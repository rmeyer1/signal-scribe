from signal_scribe.analyzer import FilingAnalyzer
from signal_scribe.config import Settings
from signal_scribe.schemas import FilingDocument, FilingMetadata


def test_heuristic_analysis_flags_risk_language():
    analyzer = FilingAnalyzer(Settings(openai_api_key=None))
    document = FilingDocument(
        metadata=FilingMetadata(
            company_cik="0000320193",
            accession_number="0000320193-26-000001",
            form_type="10-K",
        ),
        raw_text=(
            "The company reported operating results for the year. "
            "Management identified a material weakness in internal controls. "
            "There is substantial doubt about the company's ability to continue as a going concern."
        ),
    )

    analysis = analyzer._heuristic_analysis("AAPL", document, [])

    assert analysis.company_ticker == "AAPL"
    assert any("Going-concern" in item for item in analysis.red_flags)
    assert any("Material weakness" in item for item in analysis.red_flags)
