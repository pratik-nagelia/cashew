"""Report generator — deterministic monthly financial reports."""

from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .categorizer import get_known_categories
from .models import CategorySummary, MonthlyReport, Transaction, TransactionType

REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"


# ---------------------------------------------------------------------------
# Core report logic
# ---------------------------------------------------------------------------


def generate_report(
    month: str,
    transactions: list[Transaction],
    rules_file: Optional[str] = None,
) -> MonthlyReport:
    """Build a MonthlyReport from already-categorized transactions.

    Transactions with resolved_type=EXCLUDE are stripped from the report.
    All arithmetic is Decimal — no floats.
    """
    known = get_known_categories(rules_file)

    # Partition by resolved type
    income_txns: list[Transaction] = []
    expense_txns: list[Transaction] = []
    investment_txns: list[Transaction] = []
    remittance_txns: list[Transaction] = []
    kept: list[Transaction] = []  # everything except EXCLUDE

    for txn in transactions:
        if txn.resolved_type == TransactionType.EXCLUDE:
            continue
        # Filter out sub-dollar transactions to match sheet behavior
        if abs(txn.amount) < Decimal("1.00"):
            continue
        kept.append(txn)
        if txn.resolved_type == TransactionType.INCOME:
            income_txns.append(txn)
        elif txn.resolved_type == TransactionType.EXPENSE:
            expense_txns.append(txn)
        elif txn.resolved_type == TransactionType.INVESTMENT:
            investment_txns.append(txn)
        elif txn.resolved_type == TransactionType.REMITTANCE:
            remittance_txns.append(txn)
        # TRANSFER txns are kept in `transactions` but don't affect totals

    # Totals — sign-aware: negative amounts are outflows, positive are refunds
    # For expenses: -txn.amount turns negative outflows positive, and positive
    # refunds become negative, naturally netting them out.
    total_income = sum((txn.amount for txn in income_txns), Decimal("0"))
    total_expenses = sum((-txn.amount for txn in expense_txns), Decimal("0"))
    total_investments = sum((-txn.amount for txn in investment_txns), Decimal("0"))
    total_remittances = sum((-txn.amount for txn in remittance_txns), Decimal("0"))
    net_cashflow = total_income - total_expenses - total_investments - total_remittances

    # Category aggregation helpers
    expense_categories = _aggregate_by_category(expense_txns)
    income_sources = _aggregate_by_category(income_txns)
    investment_categories = _aggregate_by_category(investment_txns)
    remittance_categories = _aggregate_by_category(remittance_txns)

    # Unknown = expense categories not in the rules file
    unknown_categories = [cat for cat in expense_categories if cat.name not in known]

    # Top 10 expenses by absolute amount
    top_expenses = sorted(expense_txns, key=lambda t: abs(t.amount), reverse=True)[:10]

    return MonthlyReport(
        month=month,
        total_income=total_income,
        total_expenses=total_expenses,
        total_investments=total_investments,
        total_remittances=total_remittances,
        net_cashflow=net_cashflow,
        expense_categories=expense_categories,
        income_sources=income_sources,
        investment_categories=investment_categories,
        remittance_categories=remittance_categories,
        unknown_categories=unknown_categories,
        top_expenses=top_expenses,
        transactions=kept,
    )


def _aggregate_by_category(txns: list[Transaction]) -> list[CategorySummary]:
    """Group transactions by resolved_category and return sorted summaries."""
    buckets: dict[str, list[Transaction]] = defaultdict(list)
    for txn in txns:
        key = txn.resolved_category or txn.category
        buckets[key].append(txn)

    summaries = [
        CategorySummary(
            name=name,
            amount=sum(-t.amount for t in group),
            count=len(group),
        )
        for name, group in buckets.items()
    ]
    summaries.sort(key=lambda s: s.amount, reverse=True)
    return summaries


# ---------------------------------------------------------------------------
# Render dispatch
# ---------------------------------------------------------------------------


def render_report(report: MonthlyReport, fmt: str = "cli") -> None:
    """Render a MonthlyReport in the requested format."""
    renderers = {
        "cli": _render_cli,
        "markdown": _render_markdown,
        "md": _render_markdown,
        "html": _render_html,
    }
    renderer = renderers.get(fmt)
    if renderer is None:
        raise ValueError(f"Unknown format {fmt!r}. Choose from: {', '.join(renderers)}")
    renderer(report)


# ---------------------------------------------------------------------------
# CLI renderer (rich)
# ---------------------------------------------------------------------------


def _render_cli(report: MonthlyReport) -> None:
    """Print a full report to the terminal with rich tables."""
    console = Console()
    console.print()
    console.rule(f"[bold]Monthly Report — {report.month}[/bold]")
    console.print()

    # ── Summary ──────────────────────────────────────────────
    summary = Table(title="Summary", show_header=True, header_style="bold")
    summary.add_column("Metric", style="bold")
    summary.add_column("Amount", justify="right")

    summary.add_row("Total Income", _rich_money(report.total_income, "green"))
    summary.add_row("Total Expenses", _rich_money(report.total_expenses, "red"))
    if report.total_investments > 0:
        summary.add_row("Investments", _rich_money(report.total_investments, "cyan"))
    if report.total_remittances > 0:
        summary.add_row("Remittances", _rich_money(report.total_remittances, "yellow"))
    ncf_color = "green" if report.net_cashflow >= 0 else "red"
    summary.add_row("Net Cash Flow", _rich_money(report.net_cashflow, ncf_color))
    console.print(summary)
    console.print()

    # ── Expenses by Category ─────────────────────────────────
    if report.expense_categories:
        cat_table = Table(title="Expenses by Category", show_header=True, header_style="bold")
        cat_table.add_column("Category")
        cat_table.add_column("Amount", justify="right")
        cat_table.add_column("Txns", justify="right")
        cat_table.add_column("% of Total", justify="right")

        for cat in report.expense_categories:
            pct = (
                (cat.amount / report.total_expenses * 100)
                if report.total_expenses > 0
                else Decimal("0")
            )
            cat_table.add_row(
                cat.name,
                f"${cat.amount:,.2f}",
                str(cat.count),
                f"{pct:.1f}%",
            )
        console.print(cat_table)
        console.print()

    # ── Investments ──────────────────────────────────────────
    if report.investment_categories:
        inv_table = Table(title="Investments", show_header=True, header_style="bold")
        inv_table.add_column("Category")
        inv_table.add_column("Amount", justify="right")
        inv_table.add_column("Txns", justify="right")

        for cat in report.investment_categories:
            inv_table.add_row(cat.name, f"${cat.amount:,.2f}", str(cat.count))
        console.print(inv_table)
        console.print()

    # ── Remittances ──────────────────────────────────────────
    if report.remittance_categories:
        rem_table = Table(title="Remittances", show_header=True, header_style="bold")
        rem_table.add_column("Category")
        rem_table.add_column("Amount", justify="right")
        rem_table.add_column("Txns", justify="right")

        for cat in report.remittance_categories:
            rem_table.add_row(cat.name, f"${cat.amount:,.2f}", str(cat.count))
        console.print(rem_table)
        console.print()

    # ── Top 10 Biggest Expenses ──────────────────────────────
    if report.top_expenses:
        top_table = Table(title="Top 10 Biggest Expenses", show_header=True, header_style="bold")
        top_table.add_column("Date")
        top_table.add_column("Merchant")
        top_table.add_column("Category")
        top_table.add_column("Amount", justify="right")
        top_table.add_column("Account")

        for txn in report.top_expenses:
            top_table.add_row(
                str(txn.date),
                txn.merchant,
                txn.resolved_category or txn.category,
                f"${abs(txn.amount):,.2f}",
                txn.account,
            )
        console.print(top_table)
        console.print()

    # ── Unknown Categories ───────────────────────────────────
    if report.unknown_categories:
        console.print("[bold yellow]⚠️  Unknown Categories[/bold yellow]")
        console.print(
            "[dim]Add rules for these in rules/rules.yaml[/dim]"
        )
        unk_table = Table(show_header=True, header_style="bold yellow")
        unk_table.add_column("Category")
        unk_table.add_column("Amount", justify="right")
        unk_table.add_column("Txns", justify="right")

        for cat in report.unknown_categories:
            unk_table.add_row(cat.name, f"${cat.amount:,.2f}", str(cat.count))
        console.print(unk_table)
        console.print()


def _rich_money(value: Decimal, color: str) -> str:
    """Format a money value with color markup for rich."""
    sign = "" if value >= 0 else "-"
    return f"[{color}]{sign}${abs(value):,.2f}[/{color}]"


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def _render_markdown(report: MonthlyReport) -> None:
    """Write a Markdown report to reports/{month}.md."""
    lines: list[str] = []
    _w = lines.append

    _w(f"# Monthly Report — {report.month}\n")

    # Summary
    _w("## Summary\n")
    _w("| Metric | Amount |")
    _w("|--------|-------:|")
    _w(f"| Total Income | ${report.total_income:,.2f} |")
    _w(f"| Total Expenses | ${report.total_expenses:,.2f} |")
    if report.total_investments > 0:
        _w(f"| Investments | ${report.total_investments:,.2f} |")
    if report.total_remittances > 0:
        _w(f"| Remittances | ${report.total_remittances:,.2f} |")
    sign = "" if report.net_cashflow >= 0 else "-"
    _w(f"| **Net Cash Flow** | **{sign}${abs(report.net_cashflow):,.2f}** |")
    _w("")

    # Expenses by Category
    if report.expense_categories:
        _w("## Expenses by Category\n")
        _w("| Category | Amount | Txns | % of Total |")
        _w("|----------|-------:|-----:|-----------:|")
        for cat in report.expense_categories:
            pct = (
                (cat.amount / report.total_expenses * 100)
                if report.total_expenses > 0
                else Decimal("0")
            )
            _w(f"| {cat.name} | ${cat.amount:,.2f} | {cat.count} | {pct:.1f}% |")
        _w("")

    # Investments
    if report.investment_categories:
        _w("## Investments\n")
        _w("| Category | Amount | Txns |")
        _w("|----------|-------:|-----:|")
        for cat in report.investment_categories:
            _w(f"| {cat.name} | ${cat.amount:,.2f} | {cat.count} |")
        _w("")

    # Remittances
    if report.remittance_categories:
        _w("## Remittances\n")
        _w("| Category | Amount | Txns |")
        _w("|----------|-------:|-----:|")
        for cat in report.remittance_categories:
            _w(f"| {cat.name} | ${cat.amount:,.2f} | {cat.count} |")
        _w("")

    # Top 10 Biggest Expenses
    if report.top_expenses:
        _w("## Top 10 Biggest Expenses\n")
        _w("| Date | Merchant | Category | Amount | Account |")
        _w("|------|----------|----------|-------:|---------|")
        for txn in report.top_expenses:
            cat = txn.resolved_category or txn.category
            _w(f"| {txn.date} | {txn.merchant} | {cat} | ${abs(txn.amount):,.2f} | {txn.account} |")
        _w("")

    # Unknown Categories
    if report.unknown_categories:
        _w("## ⚠️ Unknown Categories\n")
        _w("> Add rules for these in `rules/rules.yaml`\n")
        _w("| Category | Amount | Txns |")
        _w("|----------|-------:|-----:|")
        for cat in report.unknown_categories:
            _w(f"| {cat.name} | ${cat.amount:,.2f} | {cat.count} |")
        _w("")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"{report.month}.md"
    out.write_text("\n".join(lines), encoding="utf-8")

    console = Console()
    console.print(f"[green]Report written to {out}[/green]")


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------


def _render_html(report: MonthlyReport) -> None:
    """Write a self-contained HTML report to reports/{month}.html."""

    ncf_color = "#22c55e" if report.net_cashflow >= 0 else "#ef4444"
    ncf_sign = "" if report.net_cashflow >= 0 else "-"

    # ── Build category rows ──────────────────────────────────
    expense_rows = ""
    for cat in report.expense_categories:
        pct = (
            (cat.amount / report.total_expenses * 100)
            if report.total_expenses > 0
            else Decimal("0")
        )
        expense_rows += (
            f"<tr><td>{_esc(cat.name)}</td>"
            f"<td class='num'>${cat.amount:,.2f}</td>"
            f"<td class='num'>{cat.count}</td>"
            f"<td class='num'>{pct:.1f}%</td></tr>\n"
        )

    remittance_rows = ""
    for cat in report.remittance_categories:
        remittance_rows += (
            f"<tr><td>{_esc(cat.name)}</td>"
            f"<td class='num'>${cat.amount:,.2f}</td>"
            f"<td class='num'>{cat.count}</td></tr>\n"
        )

    top_rows = ""
    for txn in report.top_expenses:
        cat = txn.resolved_category or txn.category
        top_rows += (
            f"<tr><td>{txn.date}</td>"
            f"<td>{_esc(txn.merchant)}</td>"
            f"<td>{_esc(cat)}</td>"
            f"<td class='num'>${abs(txn.amount):,.2f}</td>"
            f"<td>{_esc(txn.account)}</td></tr>\n"
        )

    unknown_rows = ""
    for cat in report.unknown_categories:
        unknown_rows += (
            f"<tr><td>{_esc(cat.name)}</td>"
            f"<td class='num'>${cat.amount:,.2f}</td>"
            f"<td class='num'>{cat.count}</td></tr>\n"
        )

    # ── Conditional sections ─────────────────────────────────
    investment_card_html = ""
    if report.total_investments > 0:
        investment_card_html = f"""
        <div class="card summary-card" style="border-left: 4px solid #06b6d4;">
          <div class="card-label">Investments</div>
          <div class="card-value" style="color: #06b6d4;">${report.total_investments:,.2f}</div>
        </div>"""

    investment_rows = ""
    for cat in report.investment_categories:
        investment_rows += (
            f"<tr><td>{_esc(cat.name)}</td>"
            f"<td class='num'>${cat.amount:,.2f}</td>"
            f"<td class='num'>{cat.count}</td></tr>\n"
        )

    investment_section_html = ""
    if report.investment_categories:
        investment_section_html = f"""
    <section>
      <h2>Investments</h2>
      <table>
        <thead><tr><th>Category</th><th>Amount</th><th>Txns</th></tr></thead>
        <tbody>{investment_rows}</tbody>
      </table>
    </section>"""

    remittance_card_html = ""
    if report.total_remittances > 0:
        remittance_card_html = f"""
        <div class="card summary-card" style="border-left: 4px solid #eab308;">
          <div class="card-label">Remittances</div>
          <div class="card-value" style="color: #eab308;">${report.total_remittances:,.2f}</div>
        </div>"""

    remittance_section_html = ""
    if report.remittance_categories:
        remittance_section_html = f"""
    <section>
      <h2>Remittances</h2>
      <table>
        <thead><tr><th>Category</th><th>Amount</th><th>Txns</th></tr></thead>
        <tbody>{remittance_rows}</tbody>
      </table>
    </section>"""

    unknown_section_html = ""
    if report.unknown_categories:
        unknown_section_html = f"""
    <section>
      <h2>&#9888;&#65039; Unknown Categories</h2>
      <div class="warning">Add rules for these in <code>rules/rules.yaml</code></div>
      <table class="warning-table">
        <thead><tr><th>Category</th><th>Amount</th><th>Txns</th></tr></thead>
        <tbody>{unknown_rows}</tbody>
      </table>
    </section>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Expense Report — {_esc(report.month)}</title>
<style>
  :root {{
    --bg: #f8fafc; --card-bg: #ffffff; --text: #1e293b; --muted: #64748b;
    --border: #e2e8f0; --green: #22c55e; --red: #ef4444; --yellow: #eab308;
    --font: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: var(--font); background: var(--bg); color: var(--text);
          line-height: 1.6; padding: 2rem; max-width: 960px; margin: 0 auto; }}
  h1 {{ font-size: 1.75rem; margin-bottom: 1.5rem; }}
  h2 {{ font-size: 1.25rem; margin: 2rem 0 0.75rem; color: var(--text); }}
  .summary {{ display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.5rem; }}
  .card {{ background: var(--card-bg); border-radius: 8px; padding: 1.25rem 1.5rem;
           box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .summary-card {{ flex: 1; min-width: 180px; }}
  .card-label {{ font-size: 0.85rem; color: var(--muted); text-transform: uppercase;
                 letter-spacing: 0.05em; margin-bottom: 0.25rem; }}
  .card-value {{ font-size: 1.5rem; font-weight: 700; }}
  table {{ width: 100%; border-collapse: collapse; background: var(--card-bg);
           border-radius: 8px; overflow: hidden;
           box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 1rem; }}
  th {{ background: #f1f5f9; text-align: left; padding: 0.75rem 1rem;
       font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em;
       color: var(--muted); border-bottom: 2px solid var(--border); }}
  td {{ padding: 0.65rem 1rem; border-bottom: 1px solid var(--border); }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover {{ background: #f8fafc; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .warning {{ background: #fef9c3; border-left: 4px solid var(--yellow);
              padding: 0.75rem 1rem; border-radius: 4px; margin-bottom: 0.75rem;
              font-size: 0.9rem; color: #854d0e; }}
  .warning-table th {{ background: #fef9c3; }}
  code {{ background: #f1f5f9; padding: 0.15em 0.4em; border-radius: 3px;
          font-size: 0.85em; }}
</style>
</head>
<body>
  <h1>Monthly Report &mdash; {_esc(report.month)}</h1>

  <div class="summary">
    <div class="card summary-card" style="border-left: 4px solid var(--green);">
      <div class="card-label">Total Income</div>
      <div class="card-value" style="color: var(--green);">${report.total_income:,.2f}</div>
    </div>
    <div class="card summary-card" style="border-left: 4px solid var(--red);">
      <div class="card-label">Total Expenses</div>
      <div class="card-value" style="color: var(--red);">${report.total_expenses:,.2f}</div>
    </div>{investment_card_html}{remittance_card_html}
    <div class="card summary-card" style="border-left: 4px solid {ncf_color};">
      <div class="card-label">Net Cash Flow</div>
      <div class="card-value" style="color: {ncf_color};">{ncf_sign}${abs(report.net_cashflow):,.2f}</div>
    </div>
  </div>

  <section>
    <h2>Expenses by Category</h2>
    <table>
      <thead><tr><th>Category</th><th>Amount</th><th>Txns</th><th>% of Total</th></tr></thead>
      <tbody>{expense_rows}</tbody>
    </table>
  </section>
{investment_section_html}
{remittance_section_html}
  <section>
    <h2>Top 10 Biggest Expenses</h2>
    <table>
      <thead><tr><th>Date</th><th>Merchant</th><th>Category</th><th>Amount</th><th>Account</th></tr></thead>
      <tbody>{top_rows}</tbody>
    </table>
  </section>
{unknown_section_html}
</body>
</html>"""

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"{report.month}.html"
    out.write_text(html, encoding="utf-8")

    console = Console()
    console.print(f"[green]Report written to {out}[/green]")


def _esc(text: str) -> str:
    """Minimal HTML escaping for user-supplied strings."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
