"""Google Sheets Reports tab — formula-driven charts and summaries.

Creates a 'Reports' tab in the spreadsheet with:
1. Monthly summary table (Income, Expenses, Investment, Diff for all months)
2. Subcategory breakdown table (each subcategory × each month)
3. Parent category breakdown table (aggregated from subcategories)
4. Native Google Sheets charts:
   - Income vs Expenses trend (line chart)
   - Category breakdown (stacked bar)
   - Subcategory trends (line chart)

All data cells use cross-sheet formulas referencing FY-26-Auto,
so editing any cell in FY-26-Auto auto-updates the reports.

SAFETY: This module ONLY creates/updates the 'Reports' tab.
It never touches any other tab in the spreadsheet.
"""

from .hierarchy import (
    build_subcategory_to_parent_map,
    get_expense_parents,
    get_parent_emoji,
    load_hierarchy,
)
from .sheets import (
    EXPENSE_CATEGORIES,
    EXPENSE_END,
    EXPENSE_START,
    INCOME_CATEGORIES,
    INCOME_END,
    INCOME_START,
    INVEST_END,
    INVEST_START,
    INVESTMENT_CATEGORIES,
    MONTH_NAMES,
    _authenticate,
    _col_letter,
    _month_col_offset,
)

# Reports tab layout constants
DATA_TAB = "FY-26-Auto"
REPORTS_TAB = "Reports"

# Subcategories we report on (must match what's in the sheet data)
REPORT_SUBCATEGORIES = [
    "Auto", "Clothing", "Coffee Shops", "Dining", "Education",
    "Entertainment", "Fees", "Groceries", "Health", "Home Improvement",
    "Housing", "Insurance", "Personal", "Refund", "Shopping",
    "Transport", "Travel", "Uncategorized", "Utilities", "Vape & Nashe",
]


def _get_or_create_tab(spreadsheet, tab_name, rows=300, cols=20):
    """Get or create a worksheet tab. NEVER deletes existing tabs."""
    try:
        return spreadsheet.worksheet(tab_name)
    except Exception:
        return spreadsheet.add_worksheet(title=tab_name, rows=rows, cols=cols)


def _build_monthly_summary_formulas(months: list[int]) -> list[list[str]]:
    """Build the monthly summary table with cross-sheet formulas.

    Layout:
    Row 1: Header
    Row 2: Month names
    Row 3: Income (formulas)
    Row 4: Expenses (formulas)
    Row 5: Investment (formulas)
    Row 6: Diff (formulas)
    """
    rows = []

    # Header row
    header = ["📊 Monthly Summary"]
    for m in months:
        header.append(MONTH_NAMES[m - 1])
    rows.append(header)

    # Income row
    income_row = ["💰 Income"]
    for m in months:
        col_start = _month_col_offset(m)
        amt_col = _col_letter(col_start + 3)
        income_row.append(f"='{DATA_TAB}'!{amt_col}2")
    rows.append(income_row)

    # Expenses row
    expense_row = ["💸 Expenses"]
    for m in months:
        col_start = _month_col_offset(m)
        amt_col = _col_letter(col_start + 3)
        expense_row.append(f"='{DATA_TAB}'!{amt_col}3")
    rows.append(expense_row)

    # Investment row
    invest_row = ["📈 Investment"]
    for m in months:
        col_start = _month_col_offset(m)
        amt_col = _col_letter(col_start + 3)
        invest_row.append(f"='{DATA_TAB}'!{amt_col}4")
    rows.append(invest_row)

    # Diff row
    diff_row = ["📐 Diff"]
    for m in months:
        col_start = _month_col_offset(m)
        amt_col = _col_letter(col_start + 3)
        diff_row.append(f"='{DATA_TAB}'!{amt_col}5")
    rows.append(diff_row)

    return rows


def _build_subcategory_table(months: list[int], subcategories: list[str]) -> list[list[str]]:
    """Build subcategory breakdown table with SUMIFS formulas.

    Each cell uses SUMIFS to sum amounts in FY-26-Auto where the category
    column matches the subcategory name (with emoji prefix).

    Returns rows starting with a header, then one row per subcategory.
    """
    from .sheets import CATEGORY_EMOJI, _emoji_category

    rows = []

    # Header
    header = ["📋 Subcategory Breakdown"]
    for m in months:
        header.append(MONTH_NAMES[m - 1])
    rows.append(header)

    for subcat in subcategories:
        row = [f"{CATEGORY_EMOJI.get(subcat, '')} {subcat}"]
        emoji_name = _emoji_category(subcat)

        for m in months:
            col_start = _month_col_offset(m)
            cat_col = _col_letter(col_start + 1)  # Category column
            amt_col = _col_letter(col_start + 3)  # Amount column

            # SUMIFS: sum amounts where category matches, across expense rows
            formula = (
                f"=SUMIFS('{DATA_TAB}'!{amt_col}{EXPENSE_START}:{amt_col}{EXPENSE_END},"
                f"'{DATA_TAB}'!{cat_col}{EXPENSE_START}:{cat_col}{EXPENSE_END},"
                f"\"{emoji_name}\")"
            )
            row.append(formula)
        rows.append(row)

    # Total row
    total_row = ["TOTAL"]
    for i, m in enumerate(months):
        col = _col_letter(i + 1)
        # Sum from row 2 (first subcat) to row 1+len(subcategories)
        start_row = len(rows) - len(subcategories) + 1
        end_row = len(rows)
        total_row.append(f"=SUM({col}{start_row}:{col}{end_row})")
    rows.append(total_row)

    return rows


def _build_parent_category_table(
    months: list[int],
    subcategories: list[str],
    subcat_table_start_row: int,
) -> list[list[str]]:
    """Build parent category table that aggregates subcategory rows.

    Uses SUM formulas referencing the subcategory table rows.
    """
    hierarchy = load_hierarchy()
    sub_to_parent = build_subcategory_to_parent_map(hierarchy)
    parents = get_expense_parents(hierarchy)

    # Map parent → which rows in the subcategory table
    parent_to_subcat_rows = {}
    for i, subcat in enumerate(subcategories):
        parent = sub_to_parent.get(subcat, "Other")
        if parent not in parent_to_subcat_rows:
            parent_to_subcat_rows[parent] = []
        # Row in the sheet = subcat_table_start_row + 1 (header) + i
        parent_to_subcat_rows[parent].append(subcat_table_start_row + 1 + i)

    rows = []

    # Header
    header = ["📊 Category Breakdown"]
    for m in months:
        header.append(MONTH_NAMES[m - 1])
    rows.append(header)

    for parent in parents:
        emoji = get_parent_emoji(parent, hierarchy)
        row = [f"{emoji} {parent}"]
        subcat_rows = parent_to_subcat_rows.get(parent, [])

        for i, m in enumerate(months):
            col = _col_letter(i + 1)
            if subcat_rows:
                # Sum the specific subcategory rows for this parent
                refs = "+".join(f"{col}{r}" for r in subcat_rows)
                row.append(f"={refs}")
            else:
                row.append("0")
        rows.append(row)

    # Total row
    total_row = ["TOTAL"]
    for i, m in enumerate(months):
        col = _col_letter(i + 1)
        start = len(rows) - len(parents) + 1
        end = len(rows)
        # Offset by the table start position
        total_row.append(f"=SUM({col}{start}:{col}{end})")
    rows.append(total_row)

    return rows


def _add_charts(spreadsheet, sheet_id: int, months: list[int],
                summary_start: int, subcat_start: int, parent_start: int,
                num_subcats: int, num_parents: int):
    """Add native Google Sheets charts via batch API."""
    num_months = len(months)

    requests = []

    # Chart 1: Income vs Expenses vs Investment trend (line chart)
    requests.append({
        "addChart": {
            "chart": {
                "spec": {
                    "title": "💰 Income vs 💸 Expenses vs 📈 Investment",
                    "basicChart": {
                        "chartType": "LINE",
                        "legendPosition": "BOTTOM_LEGEND",
                        "axis": [
                            {"position": "BOTTOM_AXIS", "title": "Month"},
                            {"position": "LEFT_AXIS", "title": "Amount ($)"},
                        ],
                        "domains": [{
                            "domain": {
                                "sourceRange": {
                                    "sources": [{
                                        "sheetId": sheet_id,
                                        "startRowIndex": summary_start,
                                        "endRowIndex": summary_start + 1,
                                        "startColumnIndex": 1,
                                        "endColumnIndex": 1 + num_months,
                                    }]
                                }
                            }
                        }],
                        "series": [
                            {  # Income
                                "series": {
                                    "sourceRange": {
                                        "sources": [{
                                            "sheetId": sheet_id,
                                            "startRowIndex": summary_start + 1,
                                            "endRowIndex": summary_start + 2,
                                            "startColumnIndex": 1,
                                            "endColumnIndex": 1 + num_months,
                                        }]
                                    }
                                },
                                "targetAxis": "LEFT_AXIS",
                                "color": {"red": 0.13, "green": 0.77, "blue": 0.37},
                            },
                            {  # Expenses
                                "series": {
                                    "sourceRange": {
                                        "sources": [{
                                            "sheetId": sheet_id,
                                            "startRowIndex": summary_start + 2,
                                            "endRowIndex": summary_start + 3,
                                            "startColumnIndex": 1,
                                            "endColumnIndex": 1 + num_months,
                                        }]
                                    }
                                },
                                "targetAxis": "LEFT_AXIS",
                                "color": {"red": 0.94, "green": 0.27, "blue": 0.27},
                            },
                            {  # Investment
                                "series": {
                                    "sourceRange": {
                                        "sources": [{
                                            "sheetId": sheet_id,
                                            "startRowIndex": summary_start + 3,
                                            "endRowIndex": summary_start + 4,
                                            "startColumnIndex": 1,
                                            "endColumnIndex": 1 + num_months,
                                        }]
                                    }
                                },
                                "targetAxis": "LEFT_AXIS",
                                "color": {"red": 0.02, "green": 0.71, "blue": 0.83},
                            },
                        ],
                        "headerCount": 1,
                    },
                },
                "position": {
                    "overlayPosition": {
                        "anchorCell": {
                            "sheetId": sheet_id,
                            "rowIndex": summary_start + 5,
                            "columnIndex": 0,
                        },
                        "widthPixels": 800,
                        "heightPixels": 400,
                    }
                },
            }
        }
    })

    # Chart 2: Category breakdown (stacked bar)
    cat_series = []
    # Colors for parent categories
    cat_colors = [
        {"red": 0.94, "green": 0.27, "blue": 0.27},  # red
        {"red": 0.13, "green": 0.59, "blue": 0.95},  # blue
        {"red": 0.30, "green": 0.69, "blue": 0.31},  # green
        {"red": 1.0, "green": 0.76, "blue": 0.03},   # yellow
        {"red": 0.61, "green": 0.15, "blue": 0.69},   # purple
        {"red": 1.0, "green": 0.60, "blue": 0.0},     # orange
        {"red": 0.0, "green": 0.74, "blue": 0.83},    # teal
        {"red": 0.91, "green": 0.12, "blue": 0.39},   # pink
        {"red": 0.47, "green": 0.33, "blue": 0.28},   # brown
        {"red": 0.62, "green": 0.62, "blue": 0.62},   # grey
    ]

    for i in range(num_parents):
        color = cat_colors[i % len(cat_colors)]
        cat_series.append({
            "series": {
                "sourceRange": {
                    "sources": [{
                        "sheetId": sheet_id,
                        "startRowIndex": parent_start + 1 + i,
                        "endRowIndex": parent_start + 2 + i,
                        "startColumnIndex": 1,
                        "endColumnIndex": 1 + num_months,
                    }]
                }
            },
            "targetAxis": "LEFT_AXIS",
            "color": color,
        })

    requests.append({
        "addChart": {
            "chart": {
                "spec": {
                    "title": "📊 Expense Categories by Month",
                    "basicChart": {
                        "chartType": "COLUMN",
                        "legendPosition": "RIGHT_LEGEND",
                        "stackedType": "STACKED",
                        "axis": [
                            {"position": "BOTTOM_AXIS", "title": "Month"},
                            {"position": "LEFT_AXIS", "title": "Amount ($)"},
                        ],
                        "domains": [{
                            "domain": {
                                "sourceRange": {
                                    "sources": [{
                                        "sheetId": sheet_id,
                                        "startRowIndex": parent_start,
                                        "endRowIndex": parent_start + 1,
                                        "startColumnIndex": 1,
                                        "endColumnIndex": 1 + num_months,
                                    }]
                                }
                            }
                        }],
                        "series": cat_series,
                        "headerCount": 1,
                    },
                },
                "position": {
                    "overlayPosition": {
                        "anchorCell": {
                            "sheetId": sheet_id,
                            "rowIndex": summary_start + 28,
                            "columnIndex": 0,
                        },
                        "widthPixels": 800,
                        "heightPixels": 450,
                    }
                },
            }
        }
    })

    # Chart 3: Top subcategory trends (line chart — top 8 subcategories)
    top_subcats_series = []
    # Use first 8 subcategories (highest spend typically)
    top_indices = list(range(min(8, num_subcats)))

    for idx, i in enumerate(top_indices):
        color = cat_colors[idx % len(cat_colors)]
        top_subcats_series.append({
            "series": {
                "sourceRange": {
                    "sources": [{
                        "sheetId": sheet_id,
                        "startRowIndex": subcat_start + 1 + i,
                        "endRowIndex": subcat_start + 2 + i,
                        "startColumnIndex": 1,
                        "endColumnIndex": 1 + num_months,
                    }]
                }
            },
            "targetAxis": "LEFT_AXIS",
            "color": color,
        })

    requests.append({
        "addChart": {
            "chart": {
                "spec": {
                    "title": "📋 Subcategory Trends (Top 8)",
                    "basicChart": {
                        "chartType": "LINE",
                        "legendPosition": "RIGHT_LEGEND",
                        "axis": [
                            {"position": "BOTTOM_AXIS", "title": "Month"},
                            {"position": "LEFT_AXIS", "title": "Amount ($)"},
                        ],
                        "domains": [{
                            "domain": {
                                "sourceRange": {
                                    "sources": [{
                                        "sheetId": sheet_id,
                                        "startRowIndex": subcat_start,
                                        "endRowIndex": subcat_start + 1,
                                        "startColumnIndex": 1,
                                        "endColumnIndex": 1 + num_months,
                                    }]
                                }
                            }
                        }],
                        "series": top_subcats_series,
                        "headerCount": 1,
                    },
                },
                "position": {
                    "overlayPosition": {
                        "anchorCell": {
                            "sheetId": sheet_id,
                            "rowIndex": summary_start + 53,
                            "columnIndex": 0,
                        },
                        "widthPixels": 800,
                        "heightPixels": 450,
                    }
                },
            }
        }
    })

    if requests:
        spreadsheet.batch_update({"requests": requests})


def _format_reports_tab(spreadsheet, sheet_id: int, num_months: int,
                        summary_start: int, subcat_start: int,
                        parent_start: int, num_subcats: int, num_parents: int):
    """Apply formatting to the Reports tab."""
    requests = []

    # Bold + background for all header rows
    for header_row_0idx in [
        summary_start - 1,  # Monthly summary header
        subcat_start - 1,   # Subcategory header
        parent_start - 1,   # Parent category header
    ]:
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": header_row_0idx,
                    "endRowIndex": header_row_0idx + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 1 + num_months,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.8},
                        "textFormat": {"bold": True, "fontSize": 11,
                                       "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        })

    # Bold for label column (column A) in all data rows
    for start, count in [
        (summary_start, 4),
        (subcat_start, num_subcats + 1),
        (parent_start, num_parents + 1),
    ]:
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": start,
                    "endRowIndex": start + count,
                    "startColumnIndex": 0,
                    "endColumnIndex": 1,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True},
                    }
                },
                "fields": "userEnteredFormat(textFormat)",
            }
        })

    # Number format for all data cells
    for start, count in [
        (summary_start, 4),
        (subcat_start, num_subcats + 1),
        (parent_start, num_parents + 1),
    ]:
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": start,
                    "endRowIndex": start + count,
                    "startColumnIndex": 1,
                    "endColumnIndex": 1 + num_months,
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

    # Column widths
    requests.append({
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "startIndex": 0,
                "endIndex": 1,
            },
            "properties": {"pixelSize": 200},
            "fields": "pixelSize",
        }
    })
    for col_idx in range(1, 1 + num_months):
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": col_idx,
                    "endIndex": col_idx + 1,
                },
                "properties": {"pixelSize": 110},
                "fields": "pixelSize",
            }
        })

    # Freeze header
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 1},
            },
            "fields": "gridProperties(frozenRowCount,frozenColumnCount)",
        }
    })

    if requests:
        spreadsheet.batch_update({"requests": requests})


def build_reports_tab(
    spreadsheet_id: str,
    months: list[int] = None,
    data_tab: str = "FY-26-Auto",
) -> str:
    """Build the Reports tab with formula-driven tables and charts.

    SAFETY: Only creates/updates the Reports tab. Never touches other tabs.

    Args:
        spreadsheet_id: Google Spreadsheet ID
        months: List of month numbers (1-12). Defaults to [1..6].
        data_tab: Name of the data tab to reference. Defaults to FY-26-Auto.

    Returns:
        URL of the spreadsheet
    """
    global DATA_TAB
    DATA_TAB = data_tab

    if months is None:
        months = list(range(1, 7))

    gc = _authenticate()
    spreadsheet = gc.open_by_key(spreadsheet_id)

    # Get or create Reports tab (NEVER delete other tabs)
    ws = _get_or_create_tab(spreadsheet, REPORTS_TAB, rows=300, cols=1 + len(months))
    sheet_id = ws.id

    # Clear only the Reports tab
    ws.clear()

    # Resize if needed
    needed_cols = 1 + len(months)
    if ws.col_count < needed_cols:
        ws.resize(cols=needed_cols)

    # === Section 1: Monthly Summary (rows 1-5) ===
    summary_rows = _build_monthly_summary_formulas(months)
    summary_start_row = 1  # 1-indexed
    ws.update(
        f"A{summary_start_row}:{ _col_letter(len(months))}{summary_start_row + len(summary_rows) - 1}",
        summary_rows,
        value_input_option="USER_ENTERED",
    )

    # === Section 2: Subcategory Breakdown (starts after summary + gap) ===
    subcat_gap = 2
    subcat_start_row = summary_start_row + len(summary_rows) + subcat_gap
    subcat_rows = _build_subcategory_table(months, REPORT_SUBCATEGORIES)
    ws.update(
        f"A{subcat_start_row}:{_col_letter(len(months))}{subcat_start_row + len(subcat_rows) - 1}",
        subcat_rows,
        value_input_option="USER_ENTERED",
    )

    # === Section 3: Parent Category Breakdown (starts after subcategory + gap) ===
    parent_gap = 2
    parent_start_row = subcat_start_row + len(subcat_rows) + parent_gap
    parent_rows = _build_parent_category_table(
        months, REPORT_SUBCATEGORIES, subcat_start_row
    )
    ws.update(
        f"A{parent_start_row}:{_col_letter(len(months))}{parent_start_row + len(parent_rows) - 1}",
        parent_rows,
        value_input_option="USER_ENTERED",
    )

    # === Apply formatting ===
    hierarchy = load_hierarchy()
    num_parents = len(get_expense_parents(hierarchy))

    _format_reports_tab(
        spreadsheet, sheet_id, len(months),
        summary_start=summary_start_row,  # 1-indexed for formatting (convert to 0-idx inside)
        subcat_start=subcat_start_row,
        parent_start=parent_start_row,
        num_subcats=len(REPORT_SUBCATEGORIES),
        num_parents=num_parents,
    )

    # === Add charts ===
    # Delete existing charts first (only on Reports tab)
    existing = spreadsheet.fetch_sheet_metadata()
    for sheet in existing.get("sheets", []):
        if sheet["properties"]["sheetId"] == sheet_id:
            for chart in sheet.get("charts", []):
                spreadsheet.batch_update({
                    "requests": [{"deleteEmbeddedObject": {"objectId": chart["chartId"]}}]
                })

    _add_charts(
        spreadsheet, sheet_id, months,
        summary_start=summary_start_row - 1,   # 0-indexed for chart API
        subcat_start=subcat_start_row - 1,      # 0-indexed (header row)
        parent_start=parent_start_row - 1,      # 0-indexed (header row)
        num_subcats=len(REPORT_SUBCATEGORIES),
        num_parents=num_parents,
    )

    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
