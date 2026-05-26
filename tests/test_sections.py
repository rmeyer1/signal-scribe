from signal_scribe.sections import extract_filing_sections


def test_extract_filing_sections_finds_and_chunks_major_items():
    text = "\n".join(
        [
            "Item 1. Business",
            "Business overview. " * 80,
            "Item 1A. Risk Factors",
            "Risk factor detail. " * 80,
            "Item 7. Management's Discussion and Analysis",
            "Management commentary. " * 80,
        ]
    )

    sections = extract_filing_sections(text, "10-K")

    names = {section.section_name for section in sections}
    assert "business" in names
    assert "risk_factors" in names
    assert "mda" in names
    assert all(section.section_text for section in sections)


def test_extract_filing_sections_falls_back_to_full_filing_chunks():
    text = "No recognizable headings. " * 200

    sections = extract_filing_sections(text, "8-K")

    assert sections
    assert sections[0].section_name == "full_filing"


def test_filing_section_accepts_embedding_values():
    section = extract_filing_sections("No recognizable headings. " * 200, "8-K")[0]
    section.embedding = [0.1, 0.2, 0.3]

    assert section.embedding == [0.1, 0.2, 0.3]


def test_extract_8k_sections_with_unicode_spacing():
    text = (
        "FORM 8-K Item\u20098.01. Other Events. "
        + "Other event detail. " * 80
        + " Item\u20099.01. Financial Statements and Exhibits. "
        + "Exhibit detail. " * 80
    )

    sections = extract_filing_sections(text, "8-K")

    names = {section.section_name for section in sections}
    assert "other_events" in names
    assert "financial_statements_exhibits" in names


def test_extract_proxy_sections():
    text = (
        "Proxy Summary. " + "Summary detail. " * 80
        + " Election of Directors. " + "Director detail. " * 80
        + " Executive Compensation. " + "Comp detail. " * 80
    )

    names = {section.section_name for section in extract_filing_sections(text, "DEF 14A")}

    assert "proxy_summary" in names
    assert "directors" in names
    assert "executive_compensation" in names


def test_extract_foreign_issuer_sections():
    text_20f = (
        "Item 3. Key Information. " + "Risk detail. " * 80
        + " Item 5. Operating and Financial Review and Prospects. " + "Review detail. " * 80
    )
    text_6k = "Report of Foreign Private Issuer. " + "Issuer detail. " * 80

    names_20f = {section.section_name for section in extract_filing_sections(text_20f, "20-F")}
    names_6k = {section.section_name for section in extract_filing_sections(text_6k, "6-K")}

    assert "key_information" in names_20f
    assert "operating_financial_review" in names_20f
    assert "report_foreign_private_issuer" in names_6k


def test_extract_s_form_sections():
    text = (
        "Risk Factors. " + "Risk detail. " * 80
        + " Use of Proceeds. " + "Use detail. " * 80
        + " Dilution. " + "Dilution detail. " * 120
    )

    names = {section.section_name for section in extract_filing_sections(text, "S-1")}

    assert "risk_factors" in names
    assert "use_of_proceeds" in names
    assert "dilution" in names
