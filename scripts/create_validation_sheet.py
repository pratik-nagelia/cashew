"""Create a brand new Google Sheet and run the full Cashew pipeline.

This validates the entire code path end-to-end:
1. Creates a new spreadsheet
2. Loads fresh-pulled transactions from cache
3. Categorizes via rules engine
4. Syncs to the new sheet (data tab)
5. Applies formatting
6. Builds Reports tab with charts

No manual edits — purely code-driven.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from expense_planner.sheets import _authenticate


def create_new_spreadsheet():
    """Create a fresh Google Sheet and return its ID + URL."""
    gc = _authenticate()

    # Use Sheets API directly (doesn't need Drive API)
    body = {
        "properties": {"title": "Cashew FY-26 Validation (Jun 28)"},
    }
    response = gc.http_client.request(
        method="post",
        endpoint="https://sheets.googleapis.com/v4/spreadsheets",
        json=body,
    )
    data = response.json()
    sheet_id = data["spreadsheetId"]
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    print(f"✅ New spreadsheet created: {url}")
    print(f"   ID: {sheet_id}")
    return sheet_id, url


def run_full_pipeline(sheet_id: str):
    """Run the complete Cashew pipeline against the new sheet."""
    from expense_planner.categorizer import categorize_all
    from expense_planner.monarch_client import load_cached_transactions
    from expense_planner.report import generate_report
    from expense_planner.sheets import format_sheet, sync_to_sheet
    from expense_planner.reports_tab import build_reports_tab

    months = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]

    # Step 1: Load, categorize, generate reports
    print("\n=== Step 1: Load & Categorize ===")
    reports = []
    for month in months:
        txns = load_cached_transactions(month)
        categorize_all(txns)
        report = generate_report(month, txns)
        reports.append((report, txns))
        print(f"  ✓ {month}: {len(txns)} txns → "
              f"income=${float(report.total_income):,.2f} "
              f"expenses=${float(report.total_expenses):,.2f} "
              f"investments=${float(report.total_investments):,.2f}")

    # Step 2: Sync to Google Sheets
    print("\n=== Step 2: Sync to Google Sheets ===")
    url = sync_to_sheet(reports, sheet_id, tab_name="FY-26-Auto")
    print(f"  ✓ Data written to FY-26-Auto tab")

    # Step 3: Format
    print("\n=== Step 3: Apply Formatting ===")
    format_sheet(sheet_id, tab_name="FY-26-Auto", num_months=len(months))
    print(f"  ✓ Formatting applied (bold, colors, dropdowns, column widths)")

    # Step 4: Reports tab
    print("\n=== Step 4: Build Reports Tab ===")
    month_nums = [1, 2, 3, 4, 5, 6]
    build_reports_tab(spreadsheet_id=sheet_id, months=month_nums, data_tab="FY-26-Auto")
    print(f"  ✓ Reports tab built (3 tables + 3 charts)")

    return url


if __name__ == "__main__":
    sheet_id, url = create_new_spreadsheet()
    run_full_pipeline(sheet_id)
    print(f"\n🎉 Full pipeline complete!")
    print(f"   Validation spreadsheet: {url}")
    print(f"   Sheet ID: {sheet_id}")
    print(f"\n   Compare this cell-by-cell with the original:")
    print(f"   https://docs.google.com/spreadsheets/d/{os.environ.get('EXPENSE_SHEET_ID', '???')}")
