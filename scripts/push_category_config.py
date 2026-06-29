"""Push a 'Category Config' tab to the expenses Google Sheet.

Lists every Monarch Money category with:
  - Monarch Group (parent in Monarch)
  - Monarch Category (exact API name)
  - Type (expense / income / transfer)
  - Current Cashew Mapping (what rules.yaml maps it to)
  - Cashew Parent (hierarchy parent in category_hierarchy.yaml)
  - Txn Count (how many times it appeared Jan-Jun 2026)
  - Status dropdown: Active / Inactive / Exclude

The user edits the Status column, then we read it back to rebuild rules.yaml.
"""

import json
import os
import sys
from pathlib import Path
from collections import Counter

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
import gspread
import yaml

from expense_planner.sheets import _authenticate

load_dotenv(Path(__file__).parent.parent / ".env")

SHEET_ID = os.environ["EXPENSE_SHEET_ID"]
TAB_NAME = "Category Config"

# ---------- Load current rules & hierarchy ----------

RULES_FILE = Path(__file__).parent.parent / "rules" / "rules.yaml"
HIERARCHY_FILE = Path(__file__).parent.parent / "rules" / "category_hierarchy.yaml"

with open(RULES_FILE) as f:
    rules = yaml.safe_load(f)

with open(HIERARCHY_FILE) as f:
    hierarchy = yaml.safe_load(f)["hierarchy"]


def _build_rules_map():
    """Build {monarch_category -> cashew_category} from rules.yaml."""
    mapping = {}

    # Exclude rules
    for r in rules.get("exclude_rules", []):
        pattern = r["pattern"]
        mapping[pattern] = "EXCLUDE"

    # Investment rules
    for r in rules.get("investment_rules", []):
        mapping[r["pattern"]] = r.get("assign_category", r["pattern"])

    # Income rules
    for r in rules.get("income_rules", []):
        mapping[r["pattern"]] = r.get("assign_category", r["pattern"])

    # Expense overrides
    for r in rules.get("expense_overrides", []):
        mapping[r["pattern"]] = r.get("assign_category", r["pattern"])

    return mapping


def _build_hierarchy_map():
    """Build {subcategory -> (parent, emoji, type)} from hierarchy."""
    result = {}
    for parent_name, info in hierarchy.items():
        emoji = info.get("emoji", "")
        cat_type = info.get("type", "expense")
        for sub in info.get("subcategories", []):
            result[sub] = (parent_name, emoji, cat_type)
    return result


def _count_transactions():
    """Count transactions per Monarch category across all cached months."""
    txn_dir = Path(__file__).parent.parent / "data" / "transactions"
    counts = Counter()
    for f in sorted(txn_dir.glob("*.json")):
        with open(f) as fh:
            txns = json.load(fh)
        for t in txns:
            cat = t.get("category", {})
            if isinstance(cat, dict):
                cat_name = cat.get("name", "UNKNOWN")
            else:
                cat_name = str(cat)
            counts[cat_name] += 1
    return counts


# ---------- Build the category table ----------

# All Monarch categories from the API response (hardcoded from the pull we just did)
# Structured as (group_name, group_type, category_name)
MONARCH_CATEGORIES = [
    # Auto & Transport
    ("Auto & Transport", "expense", "Auto Payment"),
    ("Auto & Transport", "expense", "Auto Maintenance"),
    ("Auto & Transport", "expense", "Gas"),
    ("Auto & Transport", "expense", "Parking & Tolls"),
    ("Auto & Transport", "expense", "Public Transit"),
    ("Auto & Transport", "expense", "Taxi & Ride Shares"),
    # Bills & Utilities
    ("Bills & Utilities", "expense", "Garbage"),
    ("Bills & Utilities", "expense", "Water"),
    ("Bills & Utilities", "expense", "Gas & Electric"),
    ("Bills & Utilities", "expense", "Internet & Cable"),
    ("Bills & Utilities", "expense", "Phone"),
    # Food & Dining
    ("Food & Dining", "expense", "Groceries"),
    ("Food & Dining", "expense", "Restaurants & Bars"),
    ("Food & Dining", "expense", "Coffee Shops"),
    # Housing
    ("Housing", "expense", "Rent"),
    ("Housing", "expense", "Home Improvement"),
    # Shopping
    ("Shopping", "expense", "Shopping"),
    ("Shopping", "expense", "Clothing"),
    ("Shopping", "expense", "Electronics"),
    ("Shopping", "expense", "Furniture & Housewares"),
    ("Shopping", "expense", "Postage & Shipping"),
    ("Shopping", "expense", "Vape & Nashe"),
    # Health & Wellness
    ("Health & Wellness", "expense", "Medical"),
    ("Health & Wellness", "expense", "Dentist"),
    ("Health & Wellness", "expense", "Fitness"),
    # Education
    ("Education", "expense", "Education"),
    ("Education", "expense", "Eva College"),
    ("Education", "expense", "Student Loans"),
    # Travel & Lifestyle
    ("Travel & Lifestyle", "expense", "Travel & Vacation"),
    ("Travel & Lifestyle", "expense", "Travel Food"),
    ("Travel & Lifestyle", "expense", "Entertainment & Recreation"),
    ("Travel & Lifestyle", "expense", "Personal"),
    ("Travel & Lifestyle", "expense", "Charity"),
    ("Travel & Lifestyle", "expense", "Pets"),
    ("Travel & Lifestyle", "expense", "Fun Money"),
    # Financial
    ("Financial", "expense", "Insurance"),
    ("Financial", "expense", "Financial Fees"),
    ("Financial", "expense", "Financial & Legal Services"),
    ("Financial", "expense", "Loan Repayment"),
    ("Financial", "expense", "Cash & ATM"),
    ("Financial", "expense", "Taxes"),
    # Income
    ("Income", "income", "Paychecks"),
    ("Income", "income", "Interest"),
    ("Income", "income", "Other Income"),
    ("Income", "income", "Business Income"),
    # Investment (custom group)
    ("Investment", "income", "Investment"),
    # Transfers
    ("Transfers", "transfer", "Transfer"),
    ("Transfers", "transfer", "Credit Card Payment"),
    ("Transfers", "transfer", "Balance Adjustments"),
    # Other
    ("Other", "expense", "Uncategorized"),
    ("Other", "expense", "India Transfer"),
    ("Other", "expense", "Miscellaneous"),
]


def build_config_rows():
    """Build the full table for the Category Config tab."""
    rules_map = _build_rules_map()
    hierarchy_map = _build_hierarchy_map()
    txn_counts = _count_transactions()

    rows = []
    for group_name, group_type, cat_name in MONARCH_CATEGORIES:
        # Current Cashew mapping
        cashew_cat = rules_map.get(cat_name, "—")
        if cashew_cat == "—":
            # Check if it passes through (unmatched → keep_original)
            cashew_cat = f"(passthrough: {cat_name})"

        # Hierarchy parent
        lookup = cashew_cat if cashew_cat != "EXCLUDE" else ""
        if lookup.startswith("(passthrough:"):
            lookup = cat_name
        parent_info = hierarchy_map.get(lookup, ("—", "", ""))
        cashew_parent = parent_info[0]
        emoji = parent_info[1]

        # Transaction count
        count = txn_counts.get(cat_name, 0)

        # Default status
        if cashew_cat == "EXCLUDE":
            status = "Exclude"
        elif count > 0:
            status = "Active"
        else:
            status = "Inactive"

        rows.append([
            group_name,       # A: Monarch Group
            cat_name,         # B: Monarch Category
            group_type,       # C: Type
            cashew_cat,       # D: Current Cashew Mapping
            cashew_parent,    # E: Cashew Parent
            emoji,            # F: Emoji
            count,            # G: Txn Count (Jan-Jun 2026)
            status,           # H: Status (dropdown)
        ])

    return rows


def push_to_sheet():
    """Create/update the Category Config tab in the expenses spreadsheet."""
    gc = _authenticate()
    spreadsheet = gc.open_by_key(SHEET_ID)

    # Get or create the tab
    try:
        ws = spreadsheet.worksheet(TAB_NAME)
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=TAB_NAME, rows=70, cols=10)

    # Header row
    headers = [
        "Monarch Group",
        "Monarch Category",
        "Type",
        "Current Cashew Mapping",
        "Cashew Parent",
        "Emoji",
        "Txn Count (Jan-Jun 2026)",
        "Status",
    ]

    rows = build_config_rows()
    all_data = [headers] + rows

    # Write all data
    ws.update(f"A1:H{len(all_data)}", all_data, value_input_option="USER_ENTERED")

    # --- Formatting ---
    sheet_id = ws.id
    requests = []

    # Bold + freeze header row
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0, "endRowIndex": 1,
                "startColumnIndex": 0, "endColumnIndex": 8,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.2},
                    "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat)",
        }
    })

    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 1},
            },
            "fields": "gridProperties.frozenRowCount",
        }
    })

    # Column widths
    widths = [160, 200, 80, 200, 160, 50, 160, 100]
    for i, w in enumerate(widths):
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": i, "endIndex": i + 1,
                },
                "properties": {"pixelSize": w},
                "fields": "pixelSize",
            }
        })

    # Status dropdown (column H, rows 2 onwards)
    requests.append({
        "setDataValidation": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": len(all_data),
                "startColumnIndex": 7,   # H
                "endColumnIndex": 8,
            },
            "rule": {
                "condition": {
                    "type": "ONE_OF_LIST",
                    "values": [
                        {"userEnteredValue": "Active"},
                        {"userEnteredValue": "Inactive"},
                        {"userEnteredValue": "Exclude"},
                    ],
                },
                "showCustomUi": True,
                "strict": True,
            },
        }
    })

    # Color-code rows by status using conditional formatting
    # Active = light green
    requests.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": sheet_id,
                    "startRowIndex": 1, "endRowIndex": len(all_data),
                    "startColumnIndex": 0, "endColumnIndex": 8,
                }],
                "booleanRule": {
                    "condition": {
                        "type": "CUSTOM_FORMULA",
                        "values": [{"userEnteredValue": '=$H2="Active"'}],
                    },
                    "format": {
                        "backgroundColor": {"red": 0.85, "green": 0.95, "blue": 0.85},
                    },
                },
            },
            "index": 0,
        }
    })

    # Inactive = light gray
    requests.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": sheet_id,
                    "startRowIndex": 1, "endRowIndex": len(all_data),
                    "startColumnIndex": 0, "endColumnIndex": 8,
                }],
                "booleanRule": {
                    "condition": {
                        "type": "CUSTOM_FORMULA",
                        "values": [{"userEnteredValue": '=$H2="Inactive"'}],
                    },
                    "format": {
                        "backgroundColor": {"red": 0.92, "green": 0.92, "blue": 0.92},
                    },
                },
            },
            "index": 1,
        }
    })

    # Exclude = light red
    requests.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": sheet_id,
                    "startRowIndex": 1, "endRowIndex": len(all_data),
                    "startColumnIndex": 0, "endColumnIndex": 8,
                }],
                "booleanRule": {
                    "condition": {
                        "type": "CUSTOM_FORMULA",
                        "values": [{"userEnteredValue": '=$H2="Exclude"'}],
                    },
                    "format": {
                        "backgroundColor": {"red": 0.98, "green": 0.85, "blue": 0.85},
                    },
                },
            },
            "index": 2,
        }
    })

    # Alternating row colors (subtle, overridden by conditional formatting)
    requests.append({
        "addBanding": {
            "bandedRange": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0, "endRowIndex": len(all_data),
                    "startColumnIndex": 0, "endColumnIndex": 8,
                },
                "rowProperties": {
                    "headerColor": {"red": 0.2, "green": 0.2, "blue": 0.2},
                    "firstBandColor": {"red": 1, "green": 1, "blue": 1},
                    "secondBandColor": {"red": 0.97, "green": 0.97, "blue": 0.97},
                },
            }
        }
    })

    spreadsheet.batch_update({"requests": requests})

    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    print(f"\n✅ Category Config tab created!")
    print(f"   {url}")
    print(f"\n📋 {len(rows)} categories listed.")
    print(f"   {sum(1 for r in rows if r[7] == 'Active')} Active | "
          f"{sum(1 for r in rows if r[7] == 'Inactive')} Inactive | "
          f"{sum(1 for r in rows if r[7] == 'Exclude')} Exclude")
    print(f"\n👉 Edit the 'Status' column (H) in the sheet, then run:")
    print(f"   python scripts/read_category_config.py")
    print(f"   to rebuild rules.yaml from your choices.")


if __name__ == "__main__":
    push_to_sheet()
