# Cashew 🥜 — Roadmap & Execution Plan

## What's Done (v1.0) ✅

- [x] Monarch Money → local JSON cache (pull command)
- [x] Rules-based categorization engine (YAML, 6-pass)
- [x] Google Sheets sync with personal Gmail OAuth
- [x] Fixed-row layout: rows 6-170 expenses, 172-185 income, 187-200 investments
- [x] SUM formulas (edit any cell → totals auto-update)
- [x] Diff row (Income - Expenses - Investment = unaccounted money)
- [x] Emoji categories with dropdown menus
- [x] Refunds as negative amounts (naturally subtract from SUM)
- [x] < $1 transactions filtered out
- [x] Formula-safe names (apostrophe prefix for +/-/@/= chars)
- [x] Section subtotals on separator rows (Income, Investments)
- [x] CLI reports: markdown, HTML, Sankey, trend
- [x] 129 tests passing
- [x] Private GitHub repo (pratik-nagelia/cashew)

---

## Phase 2: Category/Subcategory Hierarchy 🏗️

**Goal**: Use Monarch's existing group→category hierarchy. Current flat categories become subcategories. Reports aggregate at the group (category) level.

### Monarch's Built-in Hierarchy

| Category (Group) | Subcategories (what's in the sheet today) |
|---|---|
| 🚗 Auto & Transport | Auto, Transport |
| 📱 Bills & Utilities | Utilities |
| 🍽️ Food & Dining | Groceries, Dining, Coffee Shops |
| 🏦 Financial | Insurance, Fees |
| 💊 Health & Wellness | Health |
| 🏠 Housing | Housing, Home Improvement |
| 🛍️ Shopping | Shopping, Clothing, Vape & Nashe |
| 🎓 Education | Education |
| ✈️ Travel & Lifestyle | Travel, Entertainment, Personal |
| ❓ Other | Uncategorized, Refund |

### Implementation

1. Add `category_hierarchy.yaml` mapping subcategory → parent category
2. Keep subcategory in the sheet (granular view for daily use)
3. Reports tab aggregates by parent category for trends
4. Rules engine stays the same — hierarchy is a reporting concern only

### Tasks
- [ ] Create `rules/category_hierarchy.yaml` with Monarch group mappings
- [ ] Update `sheets.py` to write both subcategory and parent category
- [ ] Update `report.py` to support grouped aggregation
- [ ] Add parent category to the sheet (optional hidden column or lookup)

---

## Phase 3: Google Sheets Reports Tab 📊

**Goal**: A "Reports" tab in the same spreadsheet with live charts that auto-update when data changes. No external rendering.

### Reports to Generate

1. **Income Trend** — 6-month line chart (monthly income)
2. **Expense Trend** — 6-month line chart (monthly total expenses)
3. **Category Breakdown** — stacked bar or pie showing spend by parent category per month
4. **Category Trends** — line chart per parent category over 6 months
5. **Monthly Summary Table** — Income | Expenses | Investment | Diff for all months

### Implementation Approach

**Option A (Recommended): Formula-driven data table + native Sheets charts**
- Create a "Reports" tab with a summary data table
- Each cell uses cross-sheet references: `='FY-26-Auto'!D2` for Jan income, etc.
- Sheets native charts read from this data table
- Charts auto-update when FY-26-Auto data changes
- Code creates the charts via Google Sheets API `addChart` batch requests

**Why not Apps Script?** — Adds complexity, requires separate deployment. Formula-based is simpler and fits the "no hosting" principle.

### Tasks
- [ ] Create summary data table in Reports tab (formulas referencing FY-26-Auto)
- [ ] Generate Income trend line chart via API
- [ ] Generate Expense trend line chart via API
- [ ] Generate Category breakdown chart (requires Phase 2 hierarchy)
- [ ] Generate Category trends multi-line chart
- [ ] Add monthly summary table with conditional formatting

---

## Phase 4: Plaid Direct Integration 🔌 (Low Priority)

**Goal**: Replace Monarch Money ($100/yr) with direct Plaid API for bank connectivity. Pull transactions directly from Chase, Capital One, Bilt, etc.

### Key Decisions (Future)

- **Plaid vs Teller vs SimpleFIN**: Plaid has best US coverage, free dev tier (100 connections)
- **Architecture**: Replace `monarch_client.py` with `plaid_client.py` — same interface, different data source
- **Category mapping**: Plaid has its own categories; need a mapping layer to our hierarchy
- **Auth**: Plaid Link flow (browser-based) to connect each bank account

### Prerequisites
- Plaid developer account (free)
- Each bank account linked individually via Plaid Link
- Category mapping from Plaid → Cashew categories

### Tasks
- [ ] Sign up for Plaid developer account
- [ ] Create `plaid_client.py` with same interface as `monarch_client.py`
- [ ] Build Plaid Link auth flow (one-time per bank)
- [ ] Map Plaid categories → Cashew category hierarchy
- [ ] Test with 1-2 accounts before full migration
- [ ] Run parallel (Monarch + Plaid) for 1 month to verify data match

---

## Phase 5: Future Ideas 💡

- [ ] **Budget targets**: Set monthly budget per category, show actual vs budget in Reports
- [ ] **Multi-year support**: FY-25, FY-24 tabs with same layout
- [ ] **Recurring transaction detection**: Auto-flag subscriptions
- [ ] **Net worth tracking**: Account balances over time (separate tab)
- [ ] **Mobile notifications**: Alert when spending exceeds budget threshold
- [ ] **CSV import**: For banks not on Plaid (India accounts, etc.)
- [ ] **Yearly tax summary**: Aggregate by tax-relevant categories for filing

---

## Technical Debt

- [ ] Fix tests after report.py sign-change (abs → -txn.amount)
- [ ] Rename package from `expense_planner` to `cashew` in pyproject.toml
- [ ] Add integration tests for sheets.py (mock gspread)
- [ ] Add `--dry-run` flag to sync command (show what would change)

---

*Last updated: 2026-06-25*
