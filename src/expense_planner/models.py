"""Core data models for the expense planner."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional


class TransactionType(Enum):
    """Classification of a transaction after rules are applied."""

    INCOME = "income"
    EXPENSE = "expense"
    INVESTMENT = "investment"
    REMITTANCE = "remittance"
    TRANSFER = "transfer"
    EXCLUDE = "exclude"


@dataclass
class Transaction:
    """A single financial transaction from Monarch Money."""

    id: str
    date: date
    amount: Decimal  # positive = income, negative = expense (Monarch convention)
    merchant: str
    category: str  # Monarch's original category name
    category_id: str
    account: str  # account display name
    account_id: str
    month: str  # "YYYY-MM", derived from date for trend grouping
    notes: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    pending: bool = False
    is_recurring: bool = False
    hide_from_reports: bool = False
    plaid_name: Optional[str] = None
    is_split_transaction: bool = False
    needs_review: bool = False
    # Set by the categorizer:
    resolved_type: Optional[TransactionType] = None
    resolved_category: Optional[str] = None

    @classmethod
    def from_monarch_dict(cls, raw: dict) -> "Transaction":
        """Single translation point from Monarch API JSON to Transaction."""
        txn_date = date.fromisoformat(raw["date"])
        return cls(
            id=str(raw["id"]),
            date=txn_date,
            amount=Decimal(str(raw["amount"])),
            merchant=(raw.get("merchant") or {}).get("name", "Unknown"),
            category=(raw.get("category") or {}).get("name", "Uncategorized"),
            category_id=str((raw.get("category") or {}).get("id", "")),
            account=(raw.get("account") or {}).get("displayName", "Unknown"),
            account_id=str((raw.get("account") or {}).get("id", "")),
            month=txn_date.strftime("%Y-%m"),
            notes=raw.get("notes"),
            tags=[tag["name"] for tag in (raw.get("tags") or [])],
            pending=raw.get("pending", False),
            is_recurring=raw.get("isRecurring", False),
            hide_from_reports=raw.get("hideFromReports", False),
            plaid_name=raw.get("plaidName"),
            is_split_transaction=raw.get("isSplitTransaction", False),
            needs_review=raw.get("needsReview", False),
        )


@dataclass
class CategorySummary:
    """Aggregated spending for a single category."""

    name: str
    amount: Decimal
    count: int


@dataclass
class MonthlyReport:
    """A complete monthly financial report."""

    month: str  # "YYYY-MM"
    total_income: Decimal
    total_expenses: Decimal
    total_investments: Decimal
    total_remittances: Decimal
    net_cashflow: Decimal
    expense_categories: list[CategorySummary]
    income_sources: list[CategorySummary]
    investment_categories: list[CategorySummary]
    remittance_categories: list[CategorySummary]
    unknown_categories: list[CategorySummary]
    top_expenses: list[Transaction]
    transactions: list[Transaction]
