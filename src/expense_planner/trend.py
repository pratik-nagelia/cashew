"""Month-over-month trend report generator.

Compares financial data across multiple months, producing a TrendReport
dataclass and a self-contained Plotly HTML file with summary charts,
net-cashflow line, category trend lines, and a data table.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .models import CategorySummary, MonthlyReport, Transaction, TransactionType

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"

# How many top categories to show as individual lines; rest → "Other"
_TOP_CATEGORY_COUNT = 8


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TrendReport:
    """Aggregated trend data across multiple months."""

    months: list[str]                                # ["2026-04", "2026-05", …], ordered
    monthly_reports: list[MonthlyReport]              # same order as months
    income_trend: dict[str, Decimal] = field(default_factory=dict)
    expense_trend: dict[str, Decimal] = field(default_factory=dict)
    investment_trend: dict[str, Decimal] = field(default_factory=dict)
    remittance_trend: dict[str, Decimal] = field(default_factory=dict)
    net_trend: dict[str, Decimal] = field(default_factory=dict)
    # {category_name: {month: amount}}
    category_trends: dict[str, dict[str, Decimal]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def generate_trend_report(
    months: list[str],
    reports: list[MonthlyReport],
) -> TrendReport:
    """Build a TrendReport from chronologically-ordered months and reports.

    ``months`` and ``reports`` must be the same length and in the same
    (chronological) order.
    """
    income_trend: dict[str, Decimal] = {}
    expense_trend: dict[str, Decimal] = {}
    investment_trend: dict[str, Decimal] = {}
    remittance_trend: dict[str, Decimal] = {}
    net_trend: dict[str, Decimal] = {}

    # Collect every category name that appears in any month (expenses + investments + remittances).
    all_category_names: set[str] = set()

    # First pass: top-level trends and category discovery.
    for month, report in zip(months, reports):
        income_trend[month] = report.total_income
        expense_trend[month] = report.total_expenses
        investment_trend[month] = report.total_investments
        remittance_trend[month] = report.total_remittances
        net_trend[month] = report.net_cashflow

        for cat in report.expense_categories:
            all_category_names.add(cat.name)
        for cat in report.investment_categories:
            all_category_names.add(cat.name)
        for cat in report.remittance_categories:
            all_category_names.add(cat.name)

    # Second pass: build per-category trend dicts, filling missing months
    # with Decimal("0").
    category_trends: dict[str, dict[str, Decimal]] = {}
    for cat_name in sorted(all_category_names):
        month_amounts: dict[str, Decimal] = {}
        for month, report in zip(months, reports):
            amount = Decimal("0")
            for cat in report.expense_categories:
                if cat.name == cat_name:
                    amount += cat.amount
            for cat in report.investment_categories:
                if cat.name == cat_name:
                    amount += cat.amount
            for cat in report.remittance_categories:
                if cat.name == cat_name:
                    amount += cat.amount
            month_amounts[month] = amount
        category_trends[cat_name] = month_amounts

    return TrendReport(
        months=list(months),
        monthly_reports=list(reports),
        income_trend=income_trend,
        expense_trend=expense_trend,
        investment_trend=investment_trend,
        remittance_trend=remittance_trend,
        net_trend=net_trend,
        category_trends=category_trends,
    )


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def render_trend_html(
    trend: TrendReport,
    output_path: str | Path | None = None,
) -> None:
    """Render a self-contained Plotly HTML trend report.

    Sections
    --------
    1. Summary bar chart (income / expenses / remittances per month)
    2. Net cashflow line
    3. Category trend lines (top 8 + "Other")
    4. Data table (category × month grid with delta indicators)
    """
    months = trend.months

    if output_path is None:
        first = months[0]
        last = months[-1]
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = REPORTS_DIR / f"trend-{first}-to-{last}.html"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Plotly charts (3 rows) ──────────────────────────────────────────
    fig = make_subplots(
        rows=3,
        cols=1,
        subplot_titles=(
            "Monthly Summary",
            "Net Cashflow",
            "Category Trends (Top 8 + Other)",
        ),
        vertical_spacing=0.10,
    )

    # 1) Summary bar chart ---------------------------------------------------
    fig.add_trace(
        go.Bar(
            x=months,
            y=[float(trend.income_trend[m]) for m in months],
            name="Income",
            marker_color="#2ecc71",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=months,
            y=[float(trend.expense_trend[m]) for m in months],
            name="Expenses",
            marker_color="#e74c3c",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=months,
            y=[float(trend.investment_trend[m]) for m in months],
            name="Investments",
            marker_color="#06b6d4",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=months,
            y=[float(trend.remittance_trend[m]) for m in months],
            name="Remittances",
            marker_color="#f39c12",
        ),
        row=1,
        col=1,
    )

    # 2) Net cashflow line ----------------------------------------------------
    net_values = [float(trend.net_trend[m]) for m in months]
    point_colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in net_values]

    fig.add_trace(
        go.Scatter(
            x=months,
            y=net_values,
            mode="lines+markers",
            name="Net Cashflow",
            line=dict(color="#3498db", width=2),
            marker=dict(color=point_colors, size=10),
        ),
        row=2,
        col=1,
    )
    # Zero reference line
    fig.add_hline(y=0, line_dash="dash", line_color="grey", row=2, col=1)

    # 3) Category trend lines ------------------------------------------------
    # Determine top 8 categories by total spend across all months.
    category_totals: list[tuple[str, Decimal]] = []
    for cat_name, month_map in trend.category_trends.items():
        total = sum(month_map.values(), Decimal("0"))
        category_totals.append((cat_name, total))
    category_totals.sort(key=lambda t: t[1], reverse=True)

    top_cats = [name for name, _ in category_totals[:_TOP_CATEGORY_COUNT]]
    other_cats = [name for name, _ in category_totals[_TOP_CATEGORY_COUNT:]]

    for cat_name in top_cats:
        month_map = trend.category_trends[cat_name]
        fig.add_trace(
            go.Scatter(
                x=months,
                y=[float(month_map.get(m, Decimal("0"))) for m in months],
                mode="lines+markers",
                name=cat_name,
            ),
            row=3,
            col=1,
        )

    # "Other" bucket
    if other_cats:
        other_values: list[float] = []
        for m in months:
            total = Decimal("0")
            for cat_name in other_cats:
                total += trend.category_trends[cat_name].get(m, Decimal("0"))
            other_values.append(float(total))
        fig.add_trace(
            go.Scatter(
                x=months,
                y=other_values,
                mode="lines+markers",
                name="Other",
                line=dict(dash="dot"),
            ),
            row=3,
            col=1,
        )

    # Layout tweaks
    fig.update_layout(
        barmode="group",
        height=1200,
        title_text=f"Financial Trends: {months[0]} to {months[-1]}",
        showlegend=True,
        template="plotly_white",
    )
    fig.update_yaxes(title_text="Amount ($)", row=1, col=1)
    fig.update_yaxes(title_text="Net ($)", row=2, col=1)
    fig.update_yaxes(title_text="Amount ($)", row=3, col=1)

    # ── Data table (raw HTML below charts) ──────────────────────────────
    table_html = _build_data_table_html(trend, category_totals)

    # Write full HTML
    plotly_html = fig.to_html(full_html=False, include_plotlyjs="cdn")

    full_html = _wrap_full_html(plotly_html, table_html, months)
    output_path.write_text(full_html, encoding="utf-8")


def _build_data_table_html(
    trend: TrendReport,
    category_totals: list[tuple[str, Decimal]],
) -> str:
    """Build the category × month HTML data table with delta indicators."""
    months = trend.months

    rows_html: list[str] = []
    for cat_name, total in category_totals:
        month_map = trend.category_trends[cat_name]
        cells: list[str] = []
        prev_amount: Decimal | None = None
        for m in months:
            amount = month_map.get(m, Decimal("0"))
            delta = _delta_indicator(prev_amount, amount)
            cells.append(
                f'<td class="amt">${float(amount):,.2f} {delta}</td>'
            )
            prev_amount = amount
        total_cell = f'<td class="amt total">${float(total):,.2f}</td>'
        rows_html.append(
            f"<tr><td class='cat'>{cat_name}</td>"
            + "".join(cells)
            + total_cell
            + "</tr>"
        )

    header_cells = "".join(f"<th>{m}</th>" for m in months)
    thead = f"<thead><tr><th>Category</th>{header_cells}<th>Total</th></tr></thead>"
    tbody = "<tbody>" + "\n".join(rows_html) + "</tbody>"
    return f'<table class="trend-table">{thead}{tbody}</table>'


def _delta_indicator(prev: Decimal | None, cur: Decimal) -> str:
    """Return a colored arrow or dash for month-over-month change."""
    if prev is None:
        return ""  # first month — no comparison
    if prev == Decimal("0") and cur > Decimal("0"):
        return '<span class="new">—</span>'
    if cur > prev:
        return '<span class="up">↑</span>'      # ↑ red (costs went up)
    if cur < prev:
        return '<span class="down">↓</span>'    # ↓ green (costs went down)
    return ""  # unchanged


def _wrap_full_html(plotly_div: str, table_html: str, months: list[str]) -> str:
    """Wrap Plotly div + data table into a complete HTML page."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Financial Trends: {months[0]} to {months[-1]}</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    margin: 20px auto;
    max-width: 1200px;
    background: #fafafa;
    color: #333;
  }}
  h2 {{
    margin-top: 40px;
    border-bottom: 2px solid #ddd;
    padding-bottom: 8px;
  }}
  .trend-table {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 12px;
    font-size: 14px;
  }}
  .trend-table th {{
    background: #34495e;
    color: #fff;
    padding: 10px 12px;
    text-align: right;
  }}
  .trend-table th:first-child {{
    text-align: left;
  }}
  .trend-table td {{
    padding: 8px 12px;
    border-bottom: 1px solid #e0e0e0;
  }}
  .trend-table tr:hover {{
    background: #eef2f7;
  }}
  .trend-table .cat {{
    font-weight: 600;
    text-align: left;
  }}
  .trend-table .amt {{
    text-align: right;
    font-variant-numeric: tabular-nums;
  }}
  .trend-table .total {{
    font-weight: 700;
    background: #f7f9fc;
  }}
  .up {{
    color: #e74c3c;
    font-weight: bold;
    margin-left: 4px;
  }}
  .down {{
    color: #27ae60;
    font-weight: bold;
    margin-left: 4px;
  }}
  .new {{
    color: #7f8c8d;
    margin-left: 4px;
  }}
</style>
</head>
<body>
{plotly_div}
<h2>Category Detail</h2>
{table_html}
</body>
</html>"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compute_months_back(n: int) -> list[str]:
    """Return the last *n* month strings ending with the current month.

    >>> compute_months_back(3)  # if today is 2026-06-21
    ['2026-04', '2026-05', '2026-06']
    """
    today = date.today()
    result: list[str] = []
    for i in range(n - 1, -1, -1):
        # Walk backwards: subtract *i* months from today.
        # We step via first-of-month arithmetic to avoid day-overflow issues.
        year = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year -= 1
        result.append(f"{year:04d}-{month:02d}")
    return result
