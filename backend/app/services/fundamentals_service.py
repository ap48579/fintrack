"""Parses SEC EDGAR's XBRL company-facts JSON into clean quarterly summaries.

Known simplification: SEC company facts only contain standalone-quarter figures for
income-statement items (Revenue, NetIncome) when a 10-Q explicitly tags them — fiscal Q4
is reported only as part of the 10-K's full-year total, so it has no standalone entry and
is simply absent from the quarterly trend rather than synthetically derived. This matches
the "thin slice" MVP scope rather than building a full XBRL normalization engine."""

from datetime import date, datetime

from app.clients import edgar_client

_REVENUE_CANDIDATES = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
]
_NET_INCOME_CANDIDATES = ["NetIncomeLoss", "ProfitLoss"]
_ASSETS_CANDIDATES = ["Assets"]
_EQUITY_CANDIDATES = ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]
_DEBT_CANDIDATES = ["LongTermDebt"]
_DEBT_NONCURRENT_CANDIDATES = ["LongTermDebtNoncurrent"]
_DEBT_CURRENT_CANDIDATES = ["LongTermDebtCurrent", "DebtCurrent"]
_CAPEX_CANDIDATES = ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]

_VALID_FORMS = {"10-Q", "10-K"}


def _get_concept_entries(facts: dict, candidates: list[str]) -> list[dict] | None:
    """Companies sometimes switch which XBRL tag they report a concept under over the years
    (e.g. Apple moved from `Revenues` to `RevenueFromContractWithCustomerExcludingAssessedTax`
    around 2018). Picking the first candidate that merely *exists* can lock onto a tag the
    company stopped using years ago. Instead, evaluate every candidate that exists and pick
    whichever has the most recent reported period — that's the one still in active use."""
    usgaap = facts.get("facts", {}).get("us-gaap", {})
    best_entries: list[dict] | None = None
    best_max_end = ""
    for name in candidates:
        units = usgaap.get(name, {}).get("units", {})
        entries = units.get("USD")
        if not entries:
            continue
        valid_ends = [e["end"] for e in entries if e.get("val") is not None and e.get("form") in _VALID_FORMS]
        if not valid_ends:
            continue
        max_end = max(valid_ends)
        if max_end > best_max_end:
            best_max_end = max_end
            best_entries = entries
    return best_entries


def _dedupe_latest_filed(entries: list[dict]) -> dict[str, dict]:
    best: dict[str, dict] = {}
    for e in entries:
        if e.get("val") is None or e.get("form") not in _VALID_FORMS or not e.get("end"):
            continue
        end = e["end"]
        if end not in best or e["filed"] > best[end]["filed"]:
            best[end] = e
    return best


def _instant_series(entries: list[dict]) -> list[dict]:
    """Point-in-time balance-sheet figures (Assets, Equity, Debt) — latest value per end date."""
    return sorted(_dedupe_latest_filed(entries).values(), key=lambda e: e["end"], reverse=True)


def _is_quarter_duration(start_str: str, end_str: str) -> bool:
    days = (date.fromisoformat(end_str) - date.fromisoformat(start_str)).days
    return 80 <= days <= 100


def _quarterly_flow_series(entries: list[dict]) -> list[dict]:
    """Income-statement figures (Revenue, NetIncome) — single-quarter entries only, excludes YTD."""
    quarterly = [e for e in entries if e.get("start") and _is_quarter_duration(e["start"], e["end"])]
    return sorted(_dedupe_latest_filed(quarterly).values(), key=lambda e: e["end"], reverse=True)


def _debt_series(facts: dict) -> list[dict]:
    direct = _get_concept_entries(facts, _DEBT_CANDIDATES)
    if direct:
        return _instant_series(direct)

    noncurrent = _get_concept_entries(facts, _DEBT_NONCURRENT_CANDIDATES)
    current = _get_concept_entries(facts, _DEBT_CURRENT_CANDIDATES)
    if not noncurrent:
        return []
    nc_by_end = {e["end"]: e for e in _instant_series(noncurrent)}
    if not current:
        return sorted(nc_by_end.values(), key=lambda e: e["end"], reverse=True)

    cur_by_end = {e["end"]: e for e in _instant_series(current)}
    combined = [
        {"end": end, "val": nc["val"] + cur_by_end[end]["val"], "filed": max(nc["filed"], cur_by_end[end]["filed"])}
        for end, nc in nc_by_end.items()
        if end in cur_by_end
    ]
    return sorted(combined, key=lambda e: e["end"], reverse=True)


def _series_by_concept(facts: dict, metric: str) -> list[dict]:
    if metric == "revenue":
        entries = _get_concept_entries(facts, _REVENUE_CANDIDATES) or []
        return _quarterly_flow_series(entries)
    if metric == "net_income":
        entries = _get_concept_entries(facts, _NET_INCOME_CANDIDATES) or []
        return _quarterly_flow_series(entries)
    if metric == "total_assets":
        entries = _get_concept_entries(facts, _ASSETS_CANDIDATES) or []
        return _instant_series(entries)
    if metric == "total_equity":
        entries = _get_concept_entries(facts, _EQUITY_CANDIDATES) or []
        return _instant_series(entries)
    if metric == "total_debt":
        return _debt_series(facts)
    if metric == "capex":
        entries = _get_concept_entries(facts, _CAPEX_CANDIDATES) or []
        return _quarterly_flow_series(entries)
    raise ValueError(f"Unknown metric {metric}")


def build_quarterly_history(facts: dict, quarters: int = 8) -> list[dict]:
    """Merges revenue/net_income/total_debt/total_assets into one row per period (period = quarter
    end date), keeping the most recent `quarters` periods that have at least one metric populated."""
    series = {metric: {e["end"]: e["val"] for e in _series_by_concept(facts, metric)} for metric in (
        "revenue", "net_income", "total_debt", "total_assets"
    )}

    all_ends = sorted({end for metric_series in series.values() for end in metric_series}, reverse=True)
    rows = []
    for end in all_ends[:quarters]:
        rows.append(
            {
                "period": datetime.strptime(end, "%Y-%m-%d").date(),
                "revenue": series["revenue"].get(end),
                "net_income": series["net_income"].get(end),
                "total_debt": series["total_debt"].get(end),
                "total_assets": series["total_assets"].get(end),
            }
        )
    return rows


def build_latest_summary(facts: dict) -> dict:
    history = build_quarterly_history(facts, quarters=8)
    equity_series = {e["end"]: e["val"] for e in _series_by_concept(facts, "total_equity")}

    if not history:
        return {
            "period": None,
            "revenue": None,
            "net_income": None,
            "total_debt": None,
            "total_assets": None,
            "debt_to_equity": None,
            "net_margin": None,
            "revenue_growth_qoq": None,
            "revenue_growth_yoy": None,
        }

    latest = history[0]
    latest_equity = equity_series.get(latest["period"].isoformat())

    debt_to_equity = (
        latest["total_debt"] / latest_equity if latest["total_debt"] is not None and latest_equity else None
    )
    net_margin = (
        latest["net_income"] / latest["revenue"]
        if latest["net_income"] is not None and latest["revenue"]
        else None
    )

    def _growth(periods_back: int) -> float | None:
        if len(history) <= periods_back or latest["revenue"] is None:
            return None
        prior_revenue = history[periods_back]["revenue"]
        if not prior_revenue:
            return None
        return (latest["revenue"] - prior_revenue) / prior_revenue * 100

    return {
        "period": latest["period"],
        "revenue": latest["revenue"],
        "net_income": latest["net_income"],
        "total_debt": latest["total_debt"],
        "total_assets": latest["total_assets"],
        "debt_to_equity": debt_to_equity,
        "net_margin": net_margin,
        "revenue_growth_qoq": _growth(1),
        "revenue_growth_yoy": _growth(4),
    }


def get_fundamentals_summary(symbol: str) -> dict:
    cik = edgar_client.get_cik_for_ticker(symbol)
    facts = edgar_client.get_company_facts(cik)
    return build_latest_summary(facts)


def get_fundamentals_history(symbol: str, quarters: int = 8) -> list[dict]:
    cik = edgar_client.get_cik_for_ticker(symbol)
    facts = edgar_client.get_company_facts(cik)
    return build_quarterly_history(facts, quarters=quarters)


def get_filings(symbol: str, limit: int = 10) -> list[dict]:
    cik = edgar_client.get_cik_for_ticker(symbol)
    return edgar_client.get_recent_filings(cik, limit=limit)


def get_capex_trend(symbol: str, quarters: int = 4) -> list[dict]:
    """Recent quarterly capital-expenditure figures — used by Pillar 4's deep research to
    surface investment-spending changes for a ticker, not currently shown in the main
    Fundamentals UI (which only covers revenue/net_income/debt/assets per plan.md 8.2)."""
    cik = edgar_client.get_cik_for_ticker(symbol)
    facts = edgar_client.get_company_facts(cik)
    entries = _series_by_concept(facts, "capex")[:quarters]
    return [{"period": datetime.strptime(e["end"], "%Y-%m-%d").date(), "capex": e["val"]} for e in entries]
