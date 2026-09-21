"""Phase 1 batch runner — manual, on demand, local. No scheduler, no email, no deployment.

Usage:
    uv run python -m app.cli report --start 2026-09-01 --end 2026-09-20
    uv run python -m app.cli report --start 2026-09-01 --end 2026-09-20 --skip-ingest
    uv run python -m app.cli report --start 2026-09-01 --end 2026-09-20 --max-filings 25

Fetches whatever is new from SEC Form 4 (insider buys/sells) and House PTRs (congressional
buys/sells) for the given date range, plus whatever institutional 13F holdings changes already
exist in that window, and prints a report of every disclosed buy or sell found. No correlation,
no scoring, no filtering — see technical-spec.md's "Signal detection" section for why that's
deliberately deferred.
"""

import argparse
import logging
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.sync import get_sync_db
from app.models.backtest import Hypothesis, HypothesisRun
from app.models.congress import CongressTrade, Legislator
from app.models.insiders import Insider, InsiderTrade
from app.models.ticker import Ticker
from app.models.whales import HoldingsChange, Institution
from app.services import backtest_service, congress_service, insider_service

logger = logging.getLogger(__name__)


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _role_label(trade: InsiderTrade) -> str:
    labels = []
    if trade.is_officer:
        labels.append(trade.officer_title or "Officer")
    if trade.is_director:
        labels.append("Director")
    if trade.is_ten_percent_owner:
        labels.append("10% Owner")
    return ", ".join(labels) or "Insider"


def _fetch_insider_rows(db: Session, start: date, end: date) -> list[tuple[InsiderTrade, Insider, Ticker]]:
    return list(
        db.execute(
            select(InsiderTrade, Insider, Ticker)
            .join(Insider, InsiderTrade.insider_id == Insider.id)
            .join(Ticker, InsiderTrade.ticker_id == Ticker.id)
            .where(InsiderTrade.filed_date >= start, InsiderTrade.filed_date <= end)
            .order_by(InsiderTrade.filed_date, Ticker.symbol)
        ).all()
    )


def _fetch_congress_rows(db: Session, start: date, end: date) -> list[tuple[CongressTrade, Legislator, Ticker | None]]:
    return list(
        db.execute(
            select(CongressTrade, Legislator, Ticker)
            .join(Legislator, CongressTrade.legislator_id == Legislator.id)
            .outerjoin(Ticker, CongressTrade.ticker_id == Ticker.id)
            .where(CongressTrade.filed_date >= start, CongressTrade.filed_date <= end)
            .order_by(CongressTrade.filed_date, Legislator.name)
        ).all()
    )


def _fetch_whale_rows(db: Session, start: date, end: date) -> list[tuple[HoldingsChange, Institution, Ticker]]:
    return list(
        db.execute(
            select(HoldingsChange, Institution, Ticker)
            .join(Institution, HoldingsChange.institution_id == Institution.id)
            .join(Ticker, HoldingsChange.ticker_id == Ticker.id)
            .where(HoldingsChange.period >= start, HoldingsChange.period <= end)
            .order_by(HoldingsChange.period, Ticker.symbol)
        ).all()
    )


def _format_amount(low: float, high: float | None, unbounded: bool) -> str:
    if unbounded:
        return f"${low:,.0f}+"
    if high is None:
        return f"${low:,.0f}"
    return f"${low:,.0f}-${high:,.0f}"


def _print_report(db: Session, start: date, end: date) -> None:
    insider_rows = _fetch_insider_rows(db, start, end)
    congress_rows = _fetch_congress_rows(db, start, end)
    whale_rows = _fetch_whale_rows(db, start, end)

    print(f"\n=== Market Intelligence Report: {start} to {end} ===\n")

    print(f"--- Insider trades, Form 4 (P/S only): {len(insider_rows)} ---")
    if not insider_rows:
        print("  (none)")
    for trade, insider, ticker in insider_rows:
        price = f" @ ${trade.price_per_share:,.2f}" if trade.price_per_share else ""
        print(
            f"  [{trade.filed_date}] {ticker.symbol:<6} {trade.direction.upper():<4} "
            f"{trade.shares:>14,.0f} sh{price:<14}  {insider.name} ({_role_label(trade)})  "
            f"traded {trade.transaction_date}"
        )

    print(f"\n--- Congressional trades, House PTR (P/S only): {len(congress_rows)} ---")
    if not congress_rows:
        print("  (none)")
    for trade, legislator, ticker in congress_rows:
        symbol = ticker.symbol if ticker else "—"
        owner = f" ({trade.owner})" if trade.owner else ""
        amount = _format_amount(float(trade.amount_low), float(trade.amount_high) if trade.amount_high else None, trade.amount_unbounded)
        print(
            f"  [{trade.filed_date}] {symbol:<6} {trade.direction.upper():<4} {amount:<18}  "
            f"{legislator.name}{owner}  {trade.asset_description[:50]}  traded {trade.transaction_date}"
        )

    print(f"\n--- Institutional holdings changes, 13F (tracked institutions only): {len(whale_rows)} ---")
    if not whale_rows:
        print("  (none)")
    for change, institution, ticker in whale_rows:
        print(
            f"  [{change.period}] {ticker.symbol:<6} {change.change_type.upper():<8} "
            f"{change.magnitude:>16,.0f} sh  {institution.name}"
        )

    print()


def cmd_report(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with get_sync_db() as db:
        if not args.skip_ingest:
            print(f"Fetching new Form 4 filings from {args.start} to {args.end} ...")
            new_count = insider_service.ingest_form4_range(db, args.start, args.end, max_filings=args.max_filings)
            print(f"  ingested {new_count} new insider trade row(s)")

            print(f"Fetching new House PTRs from {args.start} to {args.end} ...")
            new_count = congress_service.ingest_ptr_range(db, args.start, args.end, max_filings=args.max_filings)
            print(f"  ingested {new_count} new congressional trade row(s)")
        _print_report(db, args.start, args.end)


def cmd_hypothesis_run(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    presets = [args.preset] if args.preset else list(backtest_service.PRESET_HYPOTHESES.keys())
    with get_sync_db() as db:
        for name in presets:
            preset = backtest_service.PRESET_HYPOTHESES.get(name)
            if not preset:
                print(f"Unknown preset: {name} (known: {list(backtest_service.PRESET_HYPOTHESES.keys())})")
                continue
            hyp = backtest_service.get_or_create_hypothesis(
                db, name, preset["description"], preset["params"], source="manual"
            )
            db.commit()
            print(f"\nRunning '{name}': {preset['description']}")
            run = backtest_service.run_and_save(db, hyp)
            print(f"  window {run.data_window_start} to {run.data_window_end}, sample_size={run.sample_size}")
            for horizon, stats in run.results.items():
                print(f"  {horizon}: {stats}")


def cmd_hypothesis_list(args: argparse.Namespace) -> None:
    with get_sync_db() as db:
        hyps = db.scalars(select(Hypothesis).order_by(Hypothesis.created_at)).all()
        for hyp in hyps:
            runs = db.scalars(
                select(HypothesisRun)
                .where(HypothesisRun.hypothesis_id == hyp.id)
                .order_by(HypothesisRun.run_at.desc())
            ).all()
            print(f"\n{hyp.name} ({hyp.source}): {hyp.description}")
            print(f"  params: {hyp.params}")
            print(f"  {len(runs)} run(s) on record" + (f", most recent: {runs[0].run_at}" if runs else ""))
            if runs and args.verbose:
                for run in runs:
                    print(f"    [{run.run_at}] n={run.sample_size} {run.results}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Market intelligence platform — Phase 1 manual batch runner")
    sub = parser.add_subparsers(dest="command", required=True)

    report = sub.add_parser("report", help="Ingest new filings and print a buy/sell report for a date range")
    report.add_argument("--start", type=_parse_date, required=True, help="YYYY-MM-DD")
    report.add_argument("--end", type=_parse_date, required=True, help="YYYY-MM-DD")
    report.add_argument(
        "--skip-ingest", action="store_true", help="Only print from what's already in the database"
    )
    report.add_argument(
        "--max-filings", type=int, default=None, help="Cap the number of Form 4 filings fetched (useful for a quick test run)"
    )
    report.set_defaults(func=cmd_report)

    hyp_run = sub.add_parser("hypothesis-run", help="Run one or all preset hypotheses and log the result")
    hyp_run.add_argument("--preset", default=None, help="Preset name (omit to run all presets)")
    hyp_run.set_defaults(func=cmd_hypothesis_run)

    hyp_list = sub.add_parser("hypothesis-list", help="List hypotheses and their run history")
    hyp_list.add_argument("--verbose", action="store_true", help="Show every run's full results, not just the count")
    hyp_list.set_defaults(func=cmd_hypothesis_list)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
