from signal_scribe.profile_contracts import dump_v1_profile
from signal_scribe.profile_service import build_company_profile_response


def test_build_company_profile_response_maps_storage_rows_to_v1_contract():
    response = build_company_profile_response(
        ticker="aapl",
        company_row={
            "ticker": "AAPL",
            "cik": "0000320193",
            "company_name": "Apple Inc.",
            "exchange": "Nasdaq",
            "sic": "3571",
            "sector": "Technology",
            "industry": "Consumer Electronics",
        },
        analysis_rows=[
            {
                "filing_id": "filing-1",
                "accession_number": "0000320193-26-000001",
                "form_type": "10-K",
                "summary": "Annual filing summary",
                "business_summary": "Makes devices and services.",
                "key_findings": ["Revenue grew"],
                "red_flags": ["Margin pressure"],
                "catalysts": ["New product cycle"],
                "management_tone": "measured",
                "risk_score": 35,
                "quality_score": 82,
                "source_citations": [
                    {
                        "section": "business",
                        "form_type": "10-K",
                        "accession_number": "0000320193-26-000001",
                        "source_url": "https://www.sec.gov/example",
                        "excerpt": "Company description",
                    }
                ],
                "created_at": "2026-05-27T10:00:00+00:00",
            }
        ],
        filing_rows=[
            {
                "id": "filing-1",
                "accession_number": "0000320193-26-000001",
                "form_type": "10-K",
                "filing_date": "2026-05-20",
                "report_date": "2026-03-31",
                "fiscal_year": 2026,
                "fiscal_period": "FY",
                "sec_url": "https://www.sec.gov/Archives/example",
                "primary_document_url": "https://www.sec.gov/Archives/example/aapl.htm",
            }
        ],
        financial_fact_rows=[
            {
                "metric_name": "Revenue",
                "value": 100.5,
                "unit": "USD",
                "fiscal_year": 2026,
                "fiscal_period": "FY",
                "accession_number": "0000320193-26-000001",
                "source": "sec_xbrl",
            }
        ],
        section_rows=[
            {
                "filing_id": "filing-1",
                "accession_number": "0000320193-26-000001",
                "form_type": "10-K",
                "filing_date": "2026-05-20",
                "section_name": "risk_factors",
                "section_text": "Risk factor text",
                "chunk_index": 0,
            }
        ],
    )

    payload = dump_v1_profile(response)

    assert payload["status"] == "available"
    assert payload["company"]["name"] == "Apple Inc."
    assert payload["analyses"][0]["businessSummary"] == "Makes devices and services."
    assert payload["analyses"][0]["sourceReferences"][0]["sourceUrl"].startswith("https://")
    assert payload["filings"][0]["accessionNumber"] == "0000320193-26-000001"
    assert payload["financialFacts"][0]["metricName"] == "Revenue"
    assert payload["sections"][0]["sectionName"] == "risk_factors"
