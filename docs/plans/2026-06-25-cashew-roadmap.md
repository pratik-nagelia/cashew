# Cashew 🥜 — Roadmap & Execution Plan

## What's Done (v1.0 + Phase 2 + Phase 3) ✅

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
- [x] Category/Subcategory hierarchy (category_hierarchy.yaml)
- [x] Reports tab with 3 native Google Sheets charts
- [x] Cross-sheet SUMIFS formulas for live reporting

---

## Technical Debt 🔧

- [ ] Rename package from `expense_planner` to `cashew` in pyproject.toml + all imports
- [ ] Fix tests after report.py sign-change (abs → -txn.amount)
- [ ] Push to private GitHub repo (pratik-nagelia/cashew)
- [ ] Add integration tests for sheets.py (mock gspread)
- [ ] Add `--dry-run` flag to sync command (show what would change)

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
- [ ] **Sankey in Sheets**: Investigate embedded image or linked HTML approach
- [ ] **Year/month dropdown selectors**: Interactive report filtering in Reports tab

---

*Last updated: 2026-06-26*
