from typing import Any

from signal_scribe.schemas import FinancialMetric


CONCEPT_CANDIDATES = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "debt": ["DebtCurrent", "LongTermDebtCurrent", "LongTermDebtNoncurrent"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "shares": ["CommonStocksIncludingAdditionalPaidInCapital", "EntityCommonStockSharesOutstanding"],
}


def extract_recent_financial_metrics(
    company_facts: dict[str, Any], accession_number: str | None = None
) -> list[FinancialMetric]:
    facts = company_facts.get("facts", {})
    metrics: list[FinancialMetric] = []

    for metric_name, concepts in CONCEPT_CANDIDATES.items():
        for concept in concepts:
            concept_data = facts.get("us-gaap", {}).get(concept) or facts.get("dei", {}).get(concept)
            if not concept_data:
                continue
            unit_name, unit_values = _preferred_unit(concept_data.get("units", {}))
            if not unit_values:
                continue
            fact = _latest_fact(unit_values, accession_number)
            if fact is None:
                continue
            metrics.append(
                FinancialMetric(
                    name=metric_name,
                    value=_to_float(fact.get("val")),
                    unit=unit_name,
                    fiscal_year=fact.get("fy"),
                    fiscal_period=fact.get("fp"),
                    accession_number=fact.get("accn"),
                )
            )
            break

    return metrics


def _preferred_unit(units: dict[str, list[dict[str, Any]]]) -> tuple[str | None, list[dict[str, Any]]]:
    for unit in ("USD", "shares", "USD/shares", "pure"):
        if unit in units:
            return unit, units[unit]
    if not units:
        return None, []
    unit, values = next(iter(units.items()))
    return unit, values


def _latest_fact(
    values: list[dict[str, Any]], accession_number: str | None
) -> dict[str, Any] | None:
    usable = [
        item
        for item in values
        if item.get("val") is not None and (not accession_number or item.get("accn") == accession_number)
    ]
    if not usable and accession_number:
        usable = [item for item in values if item.get("val") is not None]
    if not usable:
        return None
    return sorted(usable, key=lambda item: (item.get("filed") or "", item.get("end") or ""))[-1]


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
