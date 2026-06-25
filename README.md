# Cashew 🥜

Deterministic personal finance reports from [Monarch Money](https://www.monarchmoney.com/) → Google Sheets. No LLM in the runtime path — pure Python, rules-based categorization, reproducible output.

Pull transactions from Monarch, categorize them with customizable rules, and sync everything to a Google Sheet you can view from any device.

## Quick Start

```bash
# Clone and install
git clone <repo> && cd cashew
cp .env.example .env   # fill in Monarch credentials + Sheet ID
pip install -e .

# Pull & sync
cashew pull --month 2026-06
cashew sync                     # syncs all cached months to Google Sheets
cashew report --month 2026-06   # CLI report
```

## Commands

| Command | Description |
|---------|-------------|
| `pull --month YYYY-MM` | Pull transactions from Monarch Money and cache locally |
| `sync [--months M1,M2] [--sheet-id ID]` | Sync to Google Sheets (all cached months by default) |
| `report --month YYYY-MM [--fmt cli\|markdown\|html]` | Generate monthly report |
| `sankey --month YYYY-MM` | Generate interactive Sankey cash-flow diagram |
| `trend --last N` or `--months M1,M2,M3` | Month-over-month trend report |
| `categories --month YYYY-MM` | List categories, flag unmapped ones |

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
3. Download credentials JSON to `../google-credentials.json` (one level above project)
4. First run opens browser for OAuth — subsequent runs reuse the token

### Categorization Rules (`rules/rules.yaml`)

Rules control how transactions are classified:

- **exclude_rules** — internal transfers, CC payments (filtered out entirely)
- **investment_rules** — investment contributions tracked separately
- **income_rules** — salary, interest, other income
- **expense_overrides** — remap Monarch categories to your preferred names

Each category gets an emoji prefix (🏠 Housing, 🛍️ Shopping, 🍽️ Dining, etc.) in the Google Sheet with dropdown menus.

## Google Sheet Layout

Each month gets 5 columns (Date | Category | Name | Amount | spacer):

- **Rows 1–5**: Summary (Income, Expenses, Investment, Diff) — all SUM formulas
- **Rows 6–170**: Expense transactions sorted by date
- **Row 171**: Income section header with subtotal
- **Rows 172–185**: Income transactions
- **Row 186**: Investment section header with subtotal
- **Rows 187–200**: Investment transactions

Transactions < $1 are filtered out. Refunds appear as negative amounts and naturally subtract from totals.

## Architecture

```
src/expense_planner/
├── __main__.py         # CLI entry (argparse)
├── models.py           # Transaction, MonthlyReport, CategorySummary
├── monarch_client.py   # Monarch API wrapper + JSON caching
├── categorizer.py      # YAML rules engine
├── sheets.py           # Google Sheets sync + formatting
├── report.py           # Report generation + CLI/MD/HTML renderers
├── sankey.py           # Plotly Sankey diagrams
└── trend.py            # Month-over-month trend analysis
```

**Data flow**: Pull → Cache (JSON) → Categorize (rules) → Sync to Sheets / Render reports

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT
