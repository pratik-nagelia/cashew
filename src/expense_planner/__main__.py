"""CLI entry point for expense-planner."""

import argparse
import os
import sys

from dotenv import load_dotenv

from .exceptions import ConfigError, DataError, MonarchAuthError


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="expense-planner",
        description="Deterministic personal finance reports from Monarch Money",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # pull
    pull_p = sub.add_parser("pull", help="Pull transactions from Monarch Money")
    pull_p.add_argument("--month", required=True, help="Month in YYYY-MM format")

    # report
    report_p = sub.add_parser("report", help="Generate monthly report")
    report_p.add_argument("--month", required=True, help="Month in YYYY-MM format")
    report_p.add_argument(
        "--fmt", choices=["cli", "markdown", "html"], default="cli",
        help="Output format (default: cli)",
    )
    report_p.add_argument("--rules", help="Path to rules YAML")

    # sankey
    sankey_p = sub.add_parser("sankey", help="Generate Sankey diagram")
    sankey_p.add_argument("--month", required=True, help="Month in YYYY-MM format")
    sankey_p.add_argument("--rules", help="Path to rules YAML")

    # trend
    trend_p = sub.add_parser("trend", help="Generate month-over-month trend report")
    trend_group = trend_p.add_mutually_exclusive_group(required=True)
    trend_group.add_argument(
        "--months", help="Comma-separated months (e.g. 2026-04,2026-05,2026-06)",
    )
    trend_group.add_argument(
        "--last", type=int, help="Number of months back from current month",
    )
    trend_p.add_argument("--rules", help="Path to rules YAML")

    # categories
    cat_p = sub.add_parser("categories", help="List transaction categories for a month")
    cat_p.add_argument("--month", required=True, help="Month in YYYY-MM format")
    cat_p.add_argument("--rules", help="Path to rules YAML")

    # sync — push to Google Sheets
    sync_p = sub.add_parser("sync", help="Sync monthly data to Google Sheets")
    sync_p.add_argument(
        "--months",
        help="Comma-separated months (e.g. 2026-01,2026-02,...,2026-06). "
             "Defaults to all months with cached data.",
    )
    sync_p.add_argument("--rules", help="Path to rules YAML")
    sync_p.add_argument(
        "--sheet-id",
        default=os.environ.get("EXPENSE_SHEET_ID", ""),
        help="Google Spreadsheet ID (or set EXPENSE_SHEET_ID env var)",
    )
    sync_p.add_argument(
        "--tab",
        default="FY-26-Auto",
        help="Tab name to write to (default: FY-26-Auto)",
    )

    # reports-tab — build Reports tab with charts
    rtab_p = sub.add_parser("reports-tab", help="Build Reports tab with charts in Google Sheets")
    rtab_p.add_argument(
        "--sheet-id",
        default=os.environ.get("EXPENSE_SHEET_ID", ""),
        help="Google Spreadsheet ID (or set EXPENSE_SHEET_ID env var)",
    )
    rtab_p.add_argument(
        "--months",
        default="1,2,3,4,5,6",
        help="Comma-separated month numbers (default: 1,2,3,4,5,6)",
    )
    rtab_p.add_argument(
        "--data-tab",
        default="FY-26-Auto",
        help="Data tab to reference (default: FY-26-Auto)",
    )

    args = parser.parse_args()

    try:
        if args.command == "pull":
            _cmd_pull(args)
        elif args.command == "report":
            _cmd_report(args)
        elif args.command == "sankey":
            _cmd_sankey(args)
        elif args.command == "trend":
            _cmd_trend(args)
        elif args.command == "categories":
            _cmd_categories(args)
        elif args.command == "sync":
            _cmd_sync(args)
        elif args.command == "reports-tab":
            _cmd_reports_tab(args)
    except (ConfigError, DataError, MonarchAuthError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_pull(args):
    from .monarch_client import pull_transactions

    txns = pull_transactions(args.month)
    print(f"Pulled {len(txns)} transactions for {args.month}")
    print(f"Cached to data/transactions/{args.month}.json")


def _cmd_report(args):
    from .categorizer import categorize_all
    from .monarch_client import load_cached_transactions
    from .report import generate_report, render_report

    txns = load_cached_transactions(args.month)
    categorize_all(txns, rules_file=args.rules)
    report = generate_report(args.month, txns, rules_file=args.rules)
    render_report(report, fmt=args.fmt)


def _cmd_sankey(args):
    from .categorizer import categorize_all
    from .monarch_client import load_cached_transactions
    from .sankey import generate_sankey

    txns = load_cached_transactions(args.month)
    categorize_all(txns, rules_file=args.rules)
    generate_sankey(args.month, txns, rules_file=args.rules)


def _cmd_trend(args):
    from .categorizer import categorize_all
    from .monarch_client import load_cached_transactions
    from .report import generate_report
    from .trend import compute_months_back, render_trend_html, generate_trend_report

    if args.months:
        months = [m.strip() for m in args.months.split(",")]
    else:
        months = compute_months_back(args.last)

    # Load and process each month
    reports = []
    missing = []
    for month in months:
        try:
            txns = load_cached_transactions(month)
        except DataError:
            missing.append(month)
            continue
        categorize_all(txns, rules_file=args.rules)
        report = generate_report(month, txns, rules_file=args.rules)
        reports.append(report)

    if missing:
        print(f"Error: No cached data for: {', '.join(missing)}", file=sys.stderr)
        print("Run these commands first:", file=sys.stderr)
        for m in missing:
            print(f"  expense-planner pull --month {m}", file=sys.stderr)
        sys.exit(1)

    trend = generate_trend_report(months, reports)
    render_trend_html(trend)


def _cmd_categories(args):
    from rich.console import Console
    from rich.table import Table

    from .categorizer import categorize_all, get_known_categories
    from .monarch_client import load_cached_transactions

    txns = load_cached_transactions(args.month)
    categorize_all(txns, rules_file=args.rules)
    known = get_known_categories(args.rules)

    console = Console()
    console.print(f"\n[bold blue]Categories for {args.month}[/bold blue]\n")

    # Collect all resolved categories
    from collections import defaultdict
    from decimal import Decimal
    from .models import TransactionType

    cat_data = defaultdict(lambda: {"amount": Decimal("0"), "count": 0, "type": None})
    for txn in txns:
        if txn.resolved_type in (TransactionType.EXCLUDE,):
            continue
        key = txn.resolved_category or txn.category
        cat_data[key]["amount"] += abs(txn.amount)
        cat_data[key]["count"] += 1
        cat_data[key]["type"] = txn.resolved_type

    # Mapped categories
    mapped = {k: v for k, v in cat_data.items() if k in known}
    unmapped = {k: v for k, v in cat_data.items() if k not in known}

    if mapped:
        table = Table(title="Mapped Categories")
        table.add_column("Category", style="bold")
        table.add_column("Type")
        table.add_column("Amount", justify="right")
        table.add_column("Txns", justify="right")
        for name, data in sorted(mapped.items(), key=lambda x: x[1]["amount"], reverse=True):
            table.add_row(
                name,
                data["type"].value if data["type"] else "?",
                f"${data['amount']:,.2f}",
                str(data["count"]),
            )
        console.print(table)

    if unmapped:
        console.print()
        table = Table(title="⚠️  Unmapped Categories (using Monarch originals)")
        table.add_column("Category", style="bold yellow")
        table.add_column("Type")
        table.add_column("Amount", justify="right")
        table.add_column("Txns", justify="right")
        for name, data in sorted(unmapped.items(), key=lambda x: x[1]["amount"], reverse=True):
            table.add_row(
                name,
                data["type"].value if data["type"] else "?",
                f"${data['amount']:,.2f}",
                str(data["count"]),
            )
        console.print(table)
        console.print(
            "\n[dim]Add rules for these in rules/rules.yaml[/dim]\n"
        )
    else:
        console.print("\n[green]✓ All categories are mapped in rules[/green]\n")


def _cmd_sync(args):
    from pathlib import Path

    from .categorizer import categorize_all
    from .monarch_client import DATA_DIR, load_cached_transactions
    from .report import generate_report
    from .sheets import format_sheet, sync_to_sheet

    # Determine which months to sync
    if args.months:
        months = [m.strip() for m in args.months.split(",")]
    else:
        # Auto-detect: all cached month files
        txn_dir = DATA_DIR / "transactions"
        if not txn_dir.exists():
            print("No cached data found. Run 'expense-planner pull --month YYYY-MM' first.")
            sys.exit(1)
        months = sorted(
            p.stem for p in txn_dir.glob("*.json")
        )

    if not months:
        print("No months to sync.")
        sys.exit(1)

    print(f"Syncing {len(months)} month(s) to Google Sheets: {', '.join(months)}")

    # Load, categorize, and generate reports for each month
    reports = []
    for month in months:
        try:
            txns = load_cached_transactions(month)
        except Exception as e:
            print(f"  ⚠ Skipping {month}: {e}")
            continue
        categorize_all(txns, rules_file=args.rules)
        report = generate_report(month, txns, rules_file=args.rules)
        reports.append((report, txns))
        print(f"  ✓ {month}: {len(txns)} txns → "
              f"income=${float(report.total_income):,.0f} "
              f"expenses=${float(report.total_expenses):,.0f} "
              f"investments=${float(report.total_investments):,.0f}")

    if not reports:
        print("No data to sync.")
        sys.exit(1)

    # Push to Google Sheets
    print(f"\nWriting to tab '{args.tab}'...")
    url = sync_to_sheet(reports, args.sheet_id, tab_name=args.tab)

    # Apply formatting
    print("Applying formatting...")
    format_sheet(args.sheet_id, tab_name=args.tab, num_months=len(months))

    print(f"\n✅ Done! View your spreadsheet:")
    print(f"   {url}")


def _cmd_reports_tab(args):
    from .reports_tab import build_reports_tab

    months = [int(m.strip()) for m in args.months.split(",")]
    print(f"Building Reports tab for months: {', '.join(str(m) for m in months)}")
    print(f"Referencing data from tab: {args.data_tab}")

    url = build_reports_tab(
        spreadsheet_id=args.sheet_id,
        months=months,
        data_tab=args.data_tab,
    )

    print(f"\n✅ Reports tab built! View your spreadsheet:")
    print(f"   {url}")


if __name__ == "__main__":
    main()
