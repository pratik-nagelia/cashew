"""Google Sheets sync — push categorized Monarch data to a personal Google Sheet.

Authenticates via Desktop OAuth (google-token.json / google-credentials.json).
No Meta infra dependency. Works standalone with personal Gmail OAuth.

Layout per month (5 columns: Date | Category | Name | Amount | spacer):
  Row 1:  Month header + Year
  Row 2:  Income =SUM(income rows)
  Row 3:  Expenses =SUM(expense rows)
  Row 4:  Investment =SUM(investment rows)
  Row 5:  Diff =Income - Expenses - Investment (should be ~0 if all money accounted for)
  Row 6–170:  Expense transactions (fixed region, sorted by date)
  Row 171: "--- Income ---" separator
  Row 172–185: Income transactions (fixed region)
  Row 186: "--- Investments ---" separator
  Row 187–200: Investment transactions (fixed region)

Amounts:
  Expenses: positive = outflow, negative = refund (subtracts from total)
  Income: positive = inflow, negative = reversal
  Investments: positive = outflow, negative = reversal/refund

Transactions < $1 are filtered out.
"""

from decimal import Decimal
from pathlib import Path

import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .models import MonthlyReport, Transaction, TransactionType

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Central credentials location (shared across projects)
CREDS_DIR = Path(__file__).parent.parent.parent.parent  # ~/Downloads/claude-projects/
CREDS_FILE = CREDS_DIR / "google-credentials.json"
TOKEN_FILE = CREDS_DIR / "google-token.json"

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# Fixed row regions (1-indexed)
SUMMARY_START = 1     # Row 1-5: header + summary
EXPENSE_START = 6     # Row 6-170: expenses
EXPENSE_END = 170
INCOME_LABEL = 171    # Row 171: separator
INCOME_START = 172    # Row 172-185: income
INCOME_END = 185
INVEST_LABEL = 186    # Row 186: separator
INVEST_START = 187    # Row 187-200: investments
INVEST_END = 200
TOTAL_ROWS = 200

# Emoji map for categories — matches Monarch's visual style
CATEGORY_EMOJI = {
    # Expenses
    "Auto": "🚗",
    "Clothing": "👔",
    "Coffee Shops": "☕",
    "Dining": "🍽️",
    "Education": "🎓",
    "Entertainment": "🎭",
    "Fees": "🏦",
    "Groceries": "🛒",
    "Health": "💊",
    "Home Improvement": "🔨",
    "Housing": "🏠",
    "Insurance": "🛡️",
    "Personal": "👤",
    "Refund": "↩️",
    "Shopping": "🛍️",
    "Transport": "🚕",
    "Travel": "✈️",
    "Uncategorized": "❓",
    "Utilities": "📱",
    "Vape & Nashe": "🌿",
    # Income
    "Paycheck": "💰",
    "Interest": "🏦",
    "Other Income": "💵",
    "Business Income": "💼",
    # Investment
    "India Transfer": "🇮🇳",
    "Robinhood": "📈",
}


def _emoji_category(category: str) -> str:
    """Prepend emoji to category name for display."""
    emoji = CATEGORY_EMOJI.get(category, "")
    if emoji:
        return f"{emoji} {category}"
    return category


# Build dropdown lists with emojis
EXPENSE_CATEGORIES = sorted([
    _emoji_category(c) for c in [
        "Auto", "Clothing", "Coffee Shops", "Dining", "Education",
        "Entertainment", "Fees", "Groceries", "Health", "Home Improvement",
        "Housing", "Insurance", "Personal", "Refund", "Shopping",
        "Transport", "Travel", "Uncategorized", "Utilities", "Vape & Nashe",
    ]
])

INCOME_CATEGORIES = sorted([
    _emoji_category(c) for c in [
        "Paycheck", "Interest", "Other Income", "Business Income",
    ]
])

INVESTMENT_CATEGORIES = sorted([
    _emoji_category(c) for c in [
        "India Transfer", "Robinhood",
    ]
])

ALL_CATEGORIES = sorted(set(EXPENSE_CATEGORIES + INCOME_CATEGORIES + INVESTMENT_CATEGORIES))

MIN_AMOUNT = Decimal("1.00")  # Filter out transactions < $1


def _authenticate() -> gspread.Client:
    """Authenticate with Google using Desktop OAuth flow."""
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_FILE.exists():
                raise FileNotFoundError(
                    f"Google credentials not found at {CREDS_FILE}. "
                    "Download from Google Cloud Console (Desktop app type)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=8092, open_browser=False)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return gspread.authorize(creds)


def _month_col_offset(month_num: int) -> int:
    """Starting column index (0-based) for a month (1-12).

    Each month = 5 columns: Date | Category | Name | Amount | spacer
    """
    return (month_num - 1) * 5


def _col_letter(col_idx: int) -> str:
    """Convert 0-based column index to A1 notation letter(s)."""
    result = ""
    idx = col_idx
    while True:
        result = chr(ord("A") + idx % 26) + result
        idx = idx // 26 - 1
        if idx < 0:
            break
    return result


def _ensure_tab(spreadsheet: gspread.Spreadsheet, tab_name: str) -> gspread.Worksheet:
    """Get or create a worksheet tab."""
    try:
        return spreadsheet.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=tab_name, rows=TOTAL_ROWS, cols=62)


def _txn_name(txn: Transaction) -> str:
    """Get the raw bank statement name (plaidName). Falls back to merchant.

    Prefixes with apostrophe if the name starts with +, =, -, or @
    to prevent Google Sheets from interpreting it as a formula.
    """
    name = txn.plaid_name or txn.merchant
    if name and name[0] in ("+", "=", "-", "@"):
        return "'" + name
    return name


def _filter_small(txns: list[Transaction]) -> list[Transaction]:
    """Remove transactions with abs(amount) < $1."""
    return [t for t in txns if abs(t.amount) >= MIN_AMOUNT]


def _txn_to_row(txn: Transaction, is_expense: bool = True) -> list[str]:
    """Convert a transaction to a sheet row [Date, Category, Name, Amount]."""
    amt = float(txn.amount)
    if is_expense or txn.resolved_type == TransactionType.INVESTMENT:
        # Negative in Monarch = outflow → positive in sheet
        # Positive in Monarch = refund → negative in sheet (subtracts from SUM)
        display_amt = abs(amt) if amt < 0 else -amt
    else:
        # Income: positive stays positive, negative stays negative
        display_amt = amt
    return [
        str(txn.date),
        _emoji_category(txn.resolved_category or txn.category),
        _txn_name(txn),
        f"{display_amt:.2f}",
    ]


def _build_month_cells(
    report: MonthlyReport,
    transactions: list[Transaction],
    col_start: int,
) -> list[tuple[str, list[list[str]]]]:
    """Build cell updates for one month in fixed-row layout.

    Returns list of (range_a1, values) tuples for batch writing.
    """
    month_num = int(report.month.split("-")[1])
    year = report.month.split("-")[0]
    month_name = MONTH_NAMES[month_num - 1]
    amt_col = _col_letter(col_start + 3)
    col_a = _col_letter(col_start)
    col_d = _col_letter(col_start + 3)

    updates = []

    # --- Summary rows 1-5 ---
    summary = [
        [month_name, "", "", year],
        ["Income", "", "", f"=SUM({amt_col}{INCOME_START}:{amt_col}{INCOME_END})"],
        ["Expenses", "", "", f"=SUM({amt_col}{EXPENSE_START}:{amt_col}{EXPENSE_END})"],
        ["Investment", "", "", f"=SUM({amt_col}{INVEST_START}:{amt_col}{INVEST_END})"],
        ["Diff", "", "", f"={amt_col}2-{amt_col}3-{amt_col}4"],
    ]
    updates.append((f"{col_a}1:{col_d}5", summary))

    # --- Expense transactions (rows 6-170) ---
    expense_txns = _filter_small(sorted(
        [t for t in transactions if t.resolved_type == TransactionType.EXPENSE],
        key=lambda t: t.date,
    ))
    exp_rows = [_txn_to_row(t, is_expense=True) for t in expense_txns]
    # Pad to fill the fixed region (empty rows)
    while len(exp_rows) < (EXPENSE_END - EXPENSE_START + 1):
        exp_rows.append(["", "", "", ""])
    # Truncate if somehow more than the region
    exp_rows = exp_rows[:EXPENSE_END - EXPENSE_START + 1]
    updates.append((f"{col_a}{EXPENSE_START}:{col_d}{EXPENSE_END}", exp_rows))

    # --- Income separator + transactions (rows 171-185) ---
    income_txns = _filter_small(sorted(
        [t for t in transactions if t.resolved_type == TransactionType.INCOME],
        key=lambda t: t.date,
    ))
    separator_and_income = [["", "--- Income ---", "", f"=SUM({amt_col}{INCOME_START}:{amt_col}{INCOME_END})"]]
    updates.append((f"{col_a}{INCOME_LABEL}:{col_d}{INCOME_LABEL}", separator_and_income))

    inc_rows = [_txn_to_row(t, is_expense=False) for t in income_txns]
    while len(inc_rows) < (INCOME_END - INCOME_START + 1):
        inc_rows.append(["", "", "", ""])
    inc_rows = inc_rows[:INCOME_END - INCOME_START + 1]
    updates.append((f"{col_a}{INCOME_START}:{col_d}{INCOME_END}", inc_rows))

    # --- Investment separator + transactions (rows 186-200) ---
    invest_txns = _filter_small(sorted(
        [t for t in transactions if t.resolved_type == TransactionType.INVESTMENT],
        key=lambda t: t.date,
    ))
    separator_and_invest = [["", "--- Investments ---", "", f"=SUM({amt_col}{INVEST_START}:{amt_col}{INVEST_END})"]]
    updates.append((f"{col_a}{INVEST_LABEL}:{col_d}{INVEST_LABEL}", separator_and_invest))

    inv_rows = [_txn_to_row(t, is_expense=False) for t in invest_txns]
    # Investment outflows: use expense-style sign logic
    inv_rows = []
    for t in invest_txns:
        inv_rows.append(_txn_to_row(t, is_expense=True))
    while len(inv_rows) < (INVEST_END - INVEST_START + 1):
        inv_rows.append(["", "", "", ""])
    inv_rows = inv_rows[:INVEST_END - INVEST_START + 1]
    updates.append((f"{col_a}{INVEST_START}:{col_d}{INVEST_END}", inv_rows))

    return updates


def sync_to_sheet(
    reports: list[tuple[MonthlyReport, list[Transaction]]],
    spreadsheet_id: str,
    tab_name: str = "FY-26-Auto",
) -> str:
    """Sync multiple months to the Google Sheet with fixed-row layout."""
    gc = _authenticate()
    spreadsheet = gc.open_by_key(spreadsheet_id)
    ws = _ensure_tab(spreadsheet, tab_name)

    # Ensure worksheet is big enough
    max_month = max(int(r.month.split("-")[1]) for r, _ in reports)
    needed_cols = max_month * 5
    if ws.row_count < TOTAL_ROWS:
        ws.resize(rows=TOTAL_ROWS)
    if ws.col_count < needed_cols:
        ws.resize(cols=needed_cols)

    # Clear the entire sheet first
    ws.clear()

    # Write each month's data
    for report, transactions in reports:
        month_num = int(report.month.split("-")[1])
        col_start = _month_col_offset(month_num)
        cell_updates = _build_month_cells(report, transactions, col_start)

        for cell_range, values in cell_updates:
            ws.update(cell_range, values, value_input_option="USER_ENTERED")

    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"


def format_sheet(
    spreadsheet_id: str,
    tab_name: str = "FY-26-Auto",
    num_months: int = 6,
) -> None:
    """Apply formatting: bold headers, yellow summary, column widths, dropdowns."""
    gc = _authenticate()
    spreadsheet = gc.open_by_key(spreadsheet_id)
    ws = spreadsheet.worksheet(tab_name)
    sheet_id = ws.id

    requests = []

    for month_idx in range(num_months):
        col_start = month_idx * 5

        # Bold + yellow background for row 1 (month header)
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": col_start,
                    "endColumnIndex": col_start + 4,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 1, "green": 1, "blue": 0},
                        "textFormat": {"bold": True, "fontSize": 11},
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        })

        # Bold for summary rows 2-5 (Income, Expenses, Investment, Diff)
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": 5,
                    "startColumnIndex": col_start,
                    "endColumnIndex": col_start + 4,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True},
                    }
                },
                "fields": "userEnteredFormat(textFormat)",
            }
        })

        # Yellow background for Diff row (row 5)
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 4,
                    "endRowIndex": 5,
                    "startColumnIndex": col_start,
                    "endColumnIndex": col_start + 4,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 1, "green": 1, "blue": 0},
                        "textFormat": {"bold": True},
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        })

        # Bold + background for separator rows (Income label=171, Investment label=186)
        for sep_row_0idx in [INCOME_LABEL - 1, INVEST_LABEL - 1]:
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": sep_row_0idx,
                        "endRowIndex": sep_row_0idx + 1,
                        "startColumnIndex": col_start,
                        "endColumnIndex": col_start + 4,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.85, "green": 0.92, "blue": 1},
                            "textFormat": {"bold": True, "italic": True},
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            })

        # Number format for Amount column (currency with parentheses for negatives)
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": TOTAL_ROWS,
                    "startColumnIndex": col_start + 3,
                    "endColumnIndex": col_start + 4,
                },
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {
                            "type": "NUMBER",
                            "pattern": "#,##0.00;(#,##0.00)",
                        },
                    }
                },
                "fields": "userEnteredFormat(numberFormat)",
            }
        })

        # Column widths: Date=90, Category=130, Name=220, Amount=90, Spacer=20
        for i, width in enumerate([90, 130, 220, 90, 20]):
            requests.append({
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": col_start + i,
                        "endIndex": col_start + i + 1,
                    },
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize",
                }
            })

        # Category dropdowns — section-specific lists
        # Expenses get expense categories, income gets income, investments get investment
        for start_row, end_row, cat_list in [
            (EXPENSE_START - 1, EXPENSE_END, EXPENSE_CATEGORIES),
            (INCOME_START - 1, INCOME_END, INCOME_CATEGORIES),
            (INVEST_START - 1, INVEST_END, INVESTMENT_CATEGORIES),
        ]:
            requests.append({
                "setDataValidation": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": start_row,
                        "endRowIndex": end_row,
                        "startColumnIndex": col_start + 1,
                        "endColumnIndex": col_start + 2,
                    },
                    "rule": {
                        "condition": {
                            "type": "ONE_OF_LIST",
                            "values": [
                                {"userEnteredValue": cat}
                                for cat in cat_list
                            ],
                        },
                        "showCustomUi": True,
                        "strict": False,  # Allow custom values too
                    },
                }
            })

    # Freeze first row and first 5 rows (summary)
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 5},
            },
            "fields": "gridProperties.frozenRowCount",
        }
    })

    if requests:
        spreadsheet.batch_update({"requests": requests})
