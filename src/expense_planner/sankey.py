"""Sankey diagram generator for cash-flow visualization.

Produces a self-contained Plotly HTML file showing money flowing from
income sources through a central hub into expense categories, remittances,
and (when positive) savings.
"""

from decimal import Decimal
from pathlib import Path
from typing import Optional

import plotly.graph_objects as go

from .models import MonthlyReport, Transaction, TransactionType
from .report import generate_report

REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"

# Link colours (semi-transparent for overlap readability)
_GREEN = "rgba(44, 160, 44, 0.5)"
_RED = "rgba(214, 39, 40, 0.5)"
_CYAN = "rgba(6, 182, 212, 0.5)"
_AMBER = "rgba(255, 152, 0, 0.5)"

# Node colours (opaque)
_NODE_GREEN = "rgba(44, 160, 44, 0.8)"
_NODE_RED = "rgba(214, 39, 40, 0.8)"
_NODE_CYAN = "rgba(6, 182, 212, 0.8)"
_NODE_AMBER = "rgba(255, 152, 0, 0.8)"


def _format_amount(amount: Decimal) -> str:
    """Format a Decimal as a dollar string like '$3,460'."""
    return f"${abs(amount):,.0f}"


def generate_sankey(
    month: str,
    transactions: list[Transaction],
    rules_file: Optional[str] = None,
) -> None:
    """Generate a Plotly Sankey diagram and write it as self-contained HTML.

    Flow layout (three columns):
        [Income Sources] --> [Total Income Hub] --> [Expense / Remittance / Savings]

    Args:
        month: Target month in "YYYY-MM" format.
        transactions: List of Transaction objects for the period.
        rules_file: Optional path to a categorisation-rules YAML file,
            forwarded to ``generate_report``.
    """
    report: MonthlyReport = generate_report(month, transactions, rules_file)

    # ------------------------------------------------------------------
    # Build node lists and link lists.
    #
    # Index layout:
    #   0 .. N-1          income source nodes  (left column)
    #   N                 hub node             (centre)
    #   N+1 .. N+M        expense nodes        (right column)
    #   N+M+1 .. N+M+R    remittance nodes     (right column)
    #   (optional)        savings node         (right column)
    # ------------------------------------------------------------------

    node_labels: list[str] = []
    node_colors: list[str] = []

    sources: list[int] = []
    targets: list[int] = []
    values: list[float] = []
    link_colors: list[str] = []

    # --- Left column: income sources ---
    income_indices: list[int] = []
    for src in report.income_sources:
        idx = len(node_labels)
        income_indices.append(idx)
        node_labels.append(f"{src.name}\n{_format_amount(src.amount)}")
        node_colors.append(_NODE_GREEN)

    # --- Centre hub ---
    hub_idx = len(node_labels)
    node_labels.append(f"Total Income\n{_format_amount(report.total_income)}")
    node_colors.append(_NODE_GREEN)

    # Links: income sources → hub
    for i, src in zip(income_indices, report.income_sources):
        sources.append(i)
        targets.append(hub_idx)
        values.append(float(abs(src.amount)))
        link_colors.append(_GREEN)

    # --- Right column: expense categories ---
    for cat in report.expense_categories:
        idx = len(node_labels)
        node_labels.append(f"{cat.name}\n{_format_amount(cat.amount)}")
        node_colors.append(_NODE_RED)

        sources.append(hub_idx)
        targets.append(idx)
        values.append(float(abs(cat.amount)))
        link_colors.append(_RED)

    # --- Right column: investment categories ---
    for cat in report.investment_categories:
        idx = len(node_labels)
        node_labels.append(f"{cat.name}\n{_format_amount(cat.amount)}")
        node_colors.append(_NODE_CYAN)

        sources.append(hub_idx)
        targets.append(idx)
        values.append(float(abs(cat.amount)))
        link_colors.append(_CYAN)

    # --- Right column: remittance categories ---
    for cat in report.remittance_categories:
        idx = len(node_labels)
        node_labels.append(f"{cat.name}\n{_format_amount(cat.amount)}")
        node_colors.append(_NODE_AMBER)

        sources.append(hub_idx)
        targets.append(idx)
        values.append(float(abs(cat.amount)))
        link_colors.append(_AMBER)

    # --- Right column: savings (only when net cash-flow is positive) ---
    if report.net_cashflow > 0:
        savings_idx = len(node_labels)
        node_labels.append(f"Savings\n{_format_amount(report.net_cashflow)}")
        node_colors.append(_NODE_GREEN)

        sources.append(hub_idx)
        targets.append(savings_idx)
        values.append(float(report.net_cashflow))
        link_colors.append(_GREEN)

    # ------------------------------------------------------------------
    # Build and write the figure
    # ------------------------------------------------------------------
    fig = go.Figure(
        data=[
            go.Sankey(
                node=dict(
                    pad=20,
                    thickness=25,
                    line=dict(color="black", width=0.5),
                    label=node_labels,
                    color=node_colors,
                ),
                link=dict(
                    source=sources,
                    target=targets,
                    value=values,
                    color=link_colors,
                ),
            )
        ]
    )

    fig.update_layout(
        title_text=f"Cash Flow — {month}",
        width=1200,
        height=800,
        font_size=12,
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORTS_DIR / f"{month}-sankey.html"
    fig.write_html(str(output_path))
