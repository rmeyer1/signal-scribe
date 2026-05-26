import re

from signal_scribe.schemas import FilingSection


MAX_CHUNK_CHARS = 8_000
CHUNK_OVERLAP_CHARS = 500
MIN_SECTION_CHARS = 500

FORM_10K_PATTERNS = [
    ("business", r"\bitem\s+1\s*[.:]\s*business\b"),
    ("risk_factors", r"\bitem\s+1a\s*[.:]\s*risk\s+factors\b"),
    ("properties", r"\bitem\s+2\s*[.:]\s*properties\b"),
    ("legal_proceedings", r"\bitem\s+3\s*[.:]\s*legal\s+proceedings\b"),
    ("mda", r"\bitem\s+7\s*[.:]\s*management.?s\s+discussion\s+and\s+analysis\b"),
    ("financial_statements", r"\bitem\s+8\s*[.:]\s*financial\s+statements\b"),
    ("controls", r"\bitem\s+9a\s*[.:]\s*controls\s+and\s+procedures\b"),
]

FORM_10Q_PATTERNS = [
    ("10q_financial_statements", r"\bitem\s+1\s*[.:]\s*financial\s+statements\b"),
    ("10q_mda", r"\bitem\s+2\s*[.:]\s*management.?s\s+discussion\s+and\s+analysis\b"),
    ("risk_factors", r"\bitem\s+1a\s*[.:]\s*risk\s+factors\b"),
    ("10q_controls", r"\bitem\s+4\s*[.:]\s*controls\s+and\s+procedures\b"),
]

FORM_8K_PATTERNS = [
    ("material_agreement", r"\bitem\s+1\.01\s*[.:]?\s*entry\s+into\s+a\s+material"),
    ("termination_agreement", r"\bitem\s+1\.02\s*[.:]?\s*termination\s+of\s+a\s+material"),
    ("bankruptcy_receivership", r"\bitem\s+1\.03\s*[.:]?\s*bankruptcy\s+or\s+receivership"),
    ("mine_safety", r"\bitem\s+1\.04\s*[.:]?\s*mine\s+safety"),
    ("cybersecurity", r"\bitem\s+1\.05\s*[.:]?\s*material\s+cybersecurity"),
    ("results_operations", r"\bitem\s+2\.02\s*[.:]?\s*results\s+of\s+operations"),
    ("financial_obligation", r"\bitem\s+2\.03\s*[.:]?\s*creation\s+of\s+a\s+direct\s+financial"),
    ("accelerating_obligation", r"\bitem\s+2\.04\s*[.:]?\s*triggering\s+events"),
    ("exit_disposal", r"\bitem\s+2\.05\s*[.:]?\s*costs\s+associated\s+with\s+exit"),
    ("material_impairments", r"\bitem\s+2\.06\s*[.:]?\s*material\s+impairments"),
    ("delisting", r"\bitem\s+3\.01\s*[.:]?\s*notice\s+of\s+delisting"),
    ("unregistered_sales", r"\bitem\s+3\.02\s*[.:]?\s*unregistered\s+sales"),
    ("shareholder_rights", r"\bitem\s+3\.03\s*[.:]?\s*material\s+modification"),
    ("auditor_change", r"\bitem\s+4\.01\s*[.:]?\s*changes\s+in\s+registrant"),
    ("nonreliance_financials", r"\bitem\s+4\.02\s*[.:]?\s*non-reliance|nonreliance"),
    ("director_officer_changes", r"\bitem\s+5\.02\s*[.:]?\s*departure\s+of\s+directors"),
    ("bylaws", r"\bitem\s+5\.03\s*[.:]?\s*amendments\s+to\s+articles"),
    ("shareholder_votes", r"\bitem\s+5\.07\s*[.:]?\s*submission\s+of\s+matters"),
    ("reg_fd", r"\bitem\s+7\.01\s*[.:]?\s*regulation\s+fd"),
    ("other_events", r"\bitem\s+8\.01\s*[.:]?\s*other\s+events"),
    ("financial_statements_exhibits", r"\bitem\s+9\.01\s*[.:]?\s*financial\s+statements\s+and\s+exhibits"),
]

PROSPECTUS_PATTERNS = [
    ("business", r"\bbusiness\b"),
    ("risk_factors", r"\brisk\s+factors\b"),
    ("use_of_proceeds", r"\buse\s+of\s+proceeds\b"),
    ("dilution", r"(?:^|\s)dilution\s*[.:]"),
    ("capitalization", r"\bcapitalization\b"),
    ("management", r"\bmanagement\b"),
    ("executive_compensation", r"\bexecutive\s+compensation\b"),
    ("principal_stockholders", r"\bprincipal\s+(?:and\s+selling\s+)?stockholders\b"),
    ("description_of_securities", r"\bdescription\s+of\s+(?:capital\s+stock|securities)\b"),
    ("plan_of_distribution", r"\bplan\s+of\s+distribution\b"),
    ("underwriting", r"\bunderwriting\b"),
    ("legal_proceedings", r"\blegal\s+proceedings\b"),
    ("mda", r"\bmanagement.?s\s+discussion\s+and\s+analysis\b"),
    ("financial_statements", r"\bfinancial\s+statements\b"),
]

PROXY_PATTERNS = [
    ("proxy_summary", r"\bproxy\s+summary\b"),
    ("voting_matters", r"\b(?:proposal|item)\s+1\b"),
    ("directors", r"\belection\s+of\s+directors\b"),
    ("corporate_governance", r"\bcorporate\s+governance\b"),
    ("executive_compensation", r"\bexecutive\s+compensation\b"),
    ("pay_vs_performance", r"\bpay\s+versus\s+performance\b"),
    ("security_ownership", r"\bsecurity\s+ownership\b"),
    ("audit_matters", r"\baudit\s+(?:committee|matters|fees)\b"),
    ("related_party_transactions", r"\brelated\s+(?:person|party)\s+transactions\b"),
]

FORM_20F_PATTERNS = [
    ("key_information", r"\bitem\s+3\s*[.:]\s*key\s+information\b"),
    ("company_information", r"\bitem\s+4\s*[.:]\s*information\s+on\s+the\s+company\b"),
    ("operating_financial_review", r"\bitem\s+5\s*[.:]\s*operating\s+and\s+financial\s+review\b"),
    ("directors_management", r"\bitem\s+6\s*[.:]\s*directors"),
    ("major_shareholders", r"\bitem\s+7\s*[.:]\s*major\s+shareholders"),
    ("financial_information", r"\bitem\s+8\s*[.:]\s*financial\s+information\b"),
    ("controls", r"\bitem\s+15\s*[.:]\s*controls\s+and\s+procedures\b"),
]

FORM_40F_PATTERNS = [
    ("annual_information_form", r"\bannual\s+information\s+form\b"),
    ("management_discussion", r"\bmanagement.?s\s+discussion\s+and\s+analysis\b"),
    ("financial_statements", r"\bfinancial\s+statements\b"),
    ("controls", r"\bdisclosure\s+controls\s+and\s+procedures\b"),
    ("mine_safety", r"\bmine\s+safety\s+disclosure\b"),
]

FORM_6K_PATTERNS = [
    ("report_foreign_private_issuer", r"\breport\s+of\s+foreign\s+private\s+issuer\b"),
    ("press_release", r"\bpress\s+release\b"),
    ("financial_results", r"\bfinancial\s+(?:results|statements|information)\b"),
    ("mda", r"\bmanagement.?s\s+discussion\s+and\s+analysis\b"),
    ("exhibits", r"\bexhibit(?:s)?\b"),
]


def extract_filing_sections(text: str, form_type: str) -> list[FilingSection]:
    normalized = normalize_section_text(text)
    if not normalized:
        return []

    matches = _section_matches(normalized, form_type)
    sections: list[FilingSection] = []
    used_names: set[str] = set()
    for index, (name, start) in enumerate(matches):
        end = matches[index + 1][1] if index + 1 < len(matches) else len(normalized)
        section_text = normalized[start:end].strip()
        if name in used_names or len(section_text) < MIN_SECTION_CHARS:
            continue
        sections.extend(_chunk_section(name, section_text))
        used_names.add(name)

    if sections:
        return sections

    return _chunk_section("full_filing", normalized)


def _section_matches(text: str, form_type: str) -> list[tuple[str, int]]:
    patterns = _patterns_for_form(form_type)

    found: list[tuple[str, int]] = []
    for name, pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            found.append((name, match.start()))

    return sorted(found, key=lambda item: item[1])


def _patterns_for_form(form_type: str) -> list[tuple[str, str]]:
    normalized = form_type.upper()
    if normalized == "10-K":
        return FORM_10K_PATTERNS
    if normalized == "10-Q":
        return FORM_10Q_PATTERNS
    if normalized == "8-K":
        return FORM_8K_PATTERNS
    if normalized == "DEF 14A":
        return PROXY_PATTERNS
    if normalized == "20-F":
        return FORM_20F_PATTERNS
    if normalized == "40-F":
        return FORM_40F_PATTERNS
    if normalized == "6-K":
        return FORM_6K_PATTERNS
    if normalized.startswith("S-"):
        return PROSPECTUS_PATTERNS
    return (
        FORM_10K_PATTERNS
        + FORM_10Q_PATTERNS
        + FORM_8K_PATTERNS
        + PROSPECTUS_PATTERNS
        + PROXY_PATTERNS
        + FORM_20F_PATTERNS
        + FORM_40F_PATTERNS
        + FORM_6K_PATTERNS
    )


def normalize_section_text(text: str) -> str:
    normalized = text.replace("\xa0", " ")
    normalized = re.sub(r"[\u2000-\u200b\u202f\u205f\u3000\ufeff]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"(?i)\bitem\s+(\d+)\s*\.\s*(\d+)", r"Item \1.\2", normalized)
    normalized = re.sub(r"(?i)\bitem\s+(\d+)\s*([a-z])\b", r"Item \1\2", normalized)
    return normalized.strip()


def _chunk_section(section_name: str, text: str) -> list[FilingSection]:
    chunks: list[FilingSection] = []
    start = 0
    chunk_index = 0
    while start < len(text):
        end = min(start + MAX_CHUNK_CHARS, len(text))
        if end < len(text):
            sentence_break = max(text.rfind(". ", start, end), text.rfind("\n", start, end))
            if sentence_break > start + MAX_CHUNK_CHARS // 2:
                end = sentence_break + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(
                FilingSection(
                    section_name=section_name,
                    section_text=chunk,
                    chunk_index=chunk_index,
                )
            )
            chunk_index += 1
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP_CHARS, start + 1)
    return chunks
