from signal_scribe.financials import extract_recent_financial_metrics


def test_extract_recent_financial_metrics_prefers_matching_accession():
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {"val": 100, "fy": 2024, "fp": "FY", "accn": "old", "filed": "2025-01-01"},
                            {"val": 150, "fy": 2025, "fp": "FY", "accn": "new", "filed": "2026-01-01"},
                        ]
                    }
                }
            }
        }
    }

    metrics = extract_recent_financial_metrics(facts, accession_number="new")

    revenue = next(metric for metric in metrics if metric.name == "revenue")
    assert revenue.value == 150
    assert revenue.fiscal_year == 2025
