# Cashew 🥜

Deterministic personal finance reports from [Monarch Money](https://www.monarchmoney.com/) → Google Sheets. No LLM in the runtime path — pure Python, rules-based categorization, reproducible output.

Pull transactions from Monarch, categorize them with customizable rules, and sync everything to a Google Sheet you can view from any device.

> **Naming note:** the project is branded **Cashew**, but the Python package is still `expense_planner` and the console script installed by `pip` is `expense-planner`. The `cashew` command does not exist yet — the package rename is tracked as tech debt (see [Status](#status--roadmap)). All examples below use `python -m expense_planner`, which always works.

## Quick Start

```bash
# Clone and install
git clone git@github.com:pratik-nagelia/cashew.git && cd cashew
cp .env.example .env   # fill in Monarch credentials + Sheet ID
pip install -e .

# Pull & sync
python -m expense_planner pull --month 2026-07
python -m expense_planner sync                     # syncs all cached months to Google Sheets
python -m expense_planner report --month 2026-07   # CLI report
```

### Credentials on a fresh machine (maintainer shortcut)

This repo carries no keys. If you have the private `nagelia-dev-setup` repo, skip
the manual `.env` step entirely — it injects everything from GCP Secret Manager:

```bash
git clone <nagelia-dev-setup> && cd nagelia-dev-setup
./bootstrap.sh                            # once per machine: gcloud auth
./install.sh cashew --path ~/dev/cashew   # writes .env + .secrets/, sets paths
```

Everyone else fills in `.env` by hand and drops a Desktop OAuth client at
`.secrets/google-credentials.json`.

## Commands

| Command | Description |
|---------|-------------|
| `pull --month YYYY-MM` | Pull transactions from Monarch Money and cache locally |
| `sync [--months M1,M2] [--sheet-id ID] [--tab NAME]` | Sync to Google Sheets (all cached months by default) |
| `report --month YYYY-MM [--fmt cli\|markdown\|html]` | Generate monthly report |
| `sankey --month YYYY-MM` | Generate interactive Sankey cash-flow diagram |
| `trend --last N` or `--months M1,M2,M3` | Month-over-month trend report |
| `categories --month YYYY-MM` | List categories, flag unmapped ones |
| `reports-tab [--months 1,2,..] [--data-tab NAME]` | Build the Reports tab with native charts |

## Configuration

### Credentials (`.env`)

```
MONARCH_EMAIL=your@email.com
MONARCH_PASSWORD=your-password
MONARCH_MFA_SECRET=your-totp-secret
EXPENSE_SHEET_ID=your-google-spreadsheet-id
SSL_CERT_FILE=/path/to/certifi/cacert.pem  # macOS Python 3.12 fix
```

### Google Sheets Auth

1. Create a Desktop OAuth client at [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Enable Google Sheets API
3. Put the credentials JSON where Cashew looks. Resolution order:
   1. `GOOGLE_CREDENTIALS_FILE` in `.env`
   2. `./.secrets/google-credentials.json` (gitignored — the recommended spot)
   3. `../google-credentials.json`, one level above the repo (legacy)
4. First run opens browser for OAuth — subsequent runs reuse the token.
   The token is written next to the credentials file, or at `GOOGLE_TOKEN_FILE`.

### Categorization Rules (`rules/rules.yaml`)

Rules control how transactions are classified. Evaluation order is:
**investment → exclude → remittance → income → expense override → default.**

- **investment_rules** — investment contributions tracked separately (India transfers, stocks, FDs, education)
- **exclude_rules** — internal transfers, CC payments (filtered out entirely)
- **remittance_rules** — money sent abroad, tracked as its own bucket
- **income_rules** — salary and other inflows
- **expense_overrides** — remap Monarch categories to your preferred names

Categories map to a parent/subcategory hierarchy (`rules/category_hierarchy.yaml`), the single category list. Each parent has a type (expense, income, investment or exclude); each subcategory shows in the sheet with its emoji (🏠 Rent, 🛒 Groceries, 🍽️ Dining, falling back to the parent's emoji). The expense, investment and income sections get dropdowns of their parents' subcategories, and the Reports tab gets one row per expense subcategory and parent, all in YAML order. Exclude parents (Transfers) appear in neither. To add or rename a category, edit the YAML (and `rules.yaml` if a rule assigns it), not the code.

## Google Sheet Layout

Two tabs are owned by this tool. **It never modifies tabs it did not create.**

### Tab: `FY-26-Auto` (transaction data)

Each month gets 5 columns (Date | Category | Name | Amount | spacer):

- **Rows 1–5**: Summary (Income, Expenses, Investment, Diff) — all SUM formulas
- **Rows 6–305**: Expense transactions sorted by date (300 slots)
- **Row 306**: Investment section header with subtotal
- **Rows 307–326**: Investment transactions (20 slots)
- **Row 327**: Income section header with subtotal
- **Rows 328–352**: Income transactions (25 slots)

Sync **pads each section to its fixed size** and **raises `SectionOverflowError`** if a month has more transactions than a section can hold — it never silently truncates, since dropping rows would corrupt the SUM totals. Transactions < $1 are filtered out. Refunds appear as negative amounts and naturally subtract from totals.

### Tab: `Reports` (charts & aggregates)

- Monthly summary (cross-sheet formulas)
- Subcategory breakdown (SUMIFS) and parent-category breakdown, each with a TOTAL row
- 3 native charts: income/expense trend, category stacked bar, and top-10 subcategory trends (ranked by actual amount)

## Architecture

```
src/expense_planner/
├── __main__.py         # CLI entry (argparse)
├── models.py           # Transaction, MonthlyReport, CategorySummary
├── monarch_client.py   # Monarch API wrapper + JSON caching
├── categorizer.py      # YAML rules engine (6-pass)
├── hierarchy.py        # Parent ↔ subcategory hierarchy
├── sheets.py           # Google Sheets sync + formatting + dropdowns
├── reports_tab.py      # Reports tab builder (charts via batch API)
├── report.py           # Report generation + CLI/MD/HTML renderers
├── sankey.py           # Plotly Sankey diagrams
├── trend.py            # Month-over-month trend analysis
└── exceptions.py       # ConfigError, DataError, MonarchAuthError

rules/
├── rules.yaml              # Categorization rules
└── category_hierarchy.yaml # Parent → subcategory mapping
```

**Data flow**: Pull → Cache (JSON) → Categorize (rules) → Sync to Sheets / Render reports

## Status & Roadmap

- ✅ Monarch → Google Sheets sync (pull, sync, report, sankey, trend, categories, reports-tab)
- ✅ Category/subcategory hierarchy with emoji + dropdowns
- ✅ Reports tab with 3 native charts
- ✅ Section-overflow guard (no silent transaction drops)
- 🔲 **Incremental sync with a verified checkpoint** — a manually-set "sync from" month so past months stay frozen (never re-pulled or overwritten) while recent months refresh via a configurable `--lookback`. *Designed, not yet implemented; today's `sync` clears and rewrites the whole tab.*
- 🔧 Tech debt: package rename (`expense_planner` → `cashew`); two stale `test_report.py` assertions from the v2 category overhaul (`test_net_cashflow_value`, `test_kept_transaction_count`) need updating to current behavior
- 🔲 Plaid direct integration (low priority)

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```
