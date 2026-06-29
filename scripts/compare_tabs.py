"""Create a fresh tab in the existing spreadsheet and compare with the old tab.

1. Syncs fresh-pulled data to a new "FY-26-Fresh" tab
2. Reads both "FY-26-Auto" and "FY-26-Fresh" tabs
3. Compares cell-by-cell and reports all discrepancies
"""

import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

SHEET_ID = os.environ["EXPENSE_SHEET_ID"]
OLD_TAB = "FY-26-Auto"
NEW_TAB = "FY-26-Fresh"


def sync_fresh_tab():
    """Run the full code pipeline into a new tab."""
    from expense_planner.categorizer import categorize_all
    from expense_planner.monarch_client import load_cached_transactions
    from expense_planner.report import generate_report
    from expense_planner.sheets import format_sheet, sync_to_sheet

    months = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]

    print("=== Loading & categorizing fresh data ===")
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

    print(f"\n=== Syncing to new tab '{NEW_TAB}' ===")
    sync_to_sheet(reports, SHEET_ID, tab_name=NEW_TAB)
    format_sheet(SHEET_ID, tab_name=NEW_TAB, num_months=len(months))
    print(f"  ✓ Done")


def compare_tabs():
    """Read both tabs and compare cell-by-cell."""
    from expense_planner.sheets import _authenticate

    gc = _authenticate()
    spreadsheet = gc.open_by_key(SHEET_ID)

    print(f"\n=== Reading both tabs ===")
    old_ws = spreadsheet.worksheet(OLD_TAB)
    new_ws = spreadsheet.worksheet(NEW_TAB)

    old_data = old_ws.get_all_values()
    new_data = new_ws.get_all_values()

    print(f"  {OLD_TAB}: {len(old_data)} rows × {len(old_data[0]) if old_data else 0} cols")
    print(f"  {NEW_TAB}: {len(new_data)} rows × {len(new_data[0]) if new_data else 0} cols")

    max_rows = max(len(old_data), len(new_data))
    max_cols = max(
        max((len(r) for r in old_data), default=0),
        max((len(r) for r in new_data), default=0),
    )

    # Pad shorter tab
    while len(old_data) < max_rows:
        old_data.append([""] * max_cols)
    while len(new_data) < max_rows:
        new_data.append([""] * max_cols)

    # Compare
    discrepancies = []
    matches = 0
    both_empty = 0

    for row_idx in range(max_rows):
        old_row = old_data[row_idx] if row_idx < len(old_data) else []
        new_row = new_data[row_idx] if row_idx < len(new_data) else []

        for col_idx in range(max_cols):
            old_val = old_row[col_idx] if col_idx < len(old_row) else ""
            new_val = new_row[col_idx] if col_idx < len(new_row) else ""

            # Normalize: strip whitespace
            old_val = old_val.strip()
            new_val = new_val.strip()

            if old_val == new_val:
                if old_val == "":
                    both_empty += 1
                else:
                    matches += 1
                continue

            # Try numeric comparison (handle rounding / formatting)
            try:
                old_num = float(old_val.replace(",", "").replace("(", "-").replace(")", ""))
                new_num = float(new_val.replace(",", "").replace("(", "-").replace(")", ""))
                if abs(old_num - new_num) < 0.02:
                    matches += 1
                    continue
            except (ValueError, TypeError):
                pass

            # Determine which month column this is
            col_letter = ""
            idx = col_idx
            while True:
                col_letter = chr(ord("A") + idx % 26) + col_letter
                idx = idx // 26 - 1
                if idx < 0:
                    break

            month_num = (col_idx // 5) + 1
            month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            month_label = month_names[month_num - 1] if 1 <= month_num <= 12 else "?"

            # Classify the row region
            row_1idx = row_idx + 1
            if row_1idx <= 5:
                region = "Summary"
            elif row_1idx <= 170:
                region = "Expenses"
            elif row_1idx == 171:
                region = "Income Label"
            elif row_1idx <= 185:
                region = "Income"
            elif row_1idx == 186:
                region = "Invest Label"
            elif row_1idx <= 200:
                region = "Investment"
            else:
                region = "Beyond"

            discrepancies.append({
                "cell": f"{col_letter}{row_1idx}",
                "month": month_label,
                "region": region,
                "old": old_val,
                "new": new_val,
            })

    # Report
    print(f"\n{'='*80}")
    print(f"  COMPARISON RESULTS")
    print(f"{'='*80}")
    print(f"  Matching cells:     {matches:,}")
    print(f"  Both empty:         {both_empty:,}")
    print(f"  Discrepancies:      {len(discrepancies):,}")
    print(f"{'='*80}")

    if not discrepancies:
        print("\n  ✅ PERFECT MATCH — both tabs are identical!")
        return

    # Group by region
    from collections import defaultdict
    by_region = defaultdict(list)
    for d in discrepancies:
        by_region[d["region"]].append(d)

    for region in ["Summary", "Expenses", "Income Label", "Income", "Invest Label", "Investment", "Beyond"]:
        items = by_region.get(region, [])
        if not items:
            continue

        print(f"\n  📍 {region} ({len(items)} differences)")
        print(f"  {'Cell':<8} {'Month':<6} {'Old Tab':<35} {'New Tab':<35}")
        print(f"  {'─'*8} {'─'*6} {'─'*35} {'─'*35}")

        # Show up to 30 per region
        for d in items[:30]:
            old_display = d['old'][:33] if d['old'] else '(empty)'
            new_display = d['new'][:33] if d['new'] else '(empty)'
            print(f"  {d['cell']:<8} {d['month']:<6} {old_display:<35} {new_display:<35}")

        if len(items) > 30:
            print(f"  ... and {len(items) - 30} more in {region}")

    # Summary of differences by month
    print(f"\n  📊 Discrepancies by month:")
    by_month = defaultdict(int)
    for d in discrepancies:
        by_month[d["month"]] += 1
    for m in ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]:
        count = by_month.get(m, 0)
        marker = "⚠️" if count > 0 else "✅"
        print(f"    {marker} {m}: {count} differences")


if __name__ == "__main__":
    sync_fresh_tab()
    compare_tabs()
