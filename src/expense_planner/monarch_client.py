"""Monarch Money API client — wraps async library into sync functions."""

import asyncio
import calendar
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .exceptions import DataError, MonarchAuthError
from .models import Transaction

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _session_file() -> str:
    """Path to the saved Monarch session file."""
    path = DATA_DIR / ".mm_session.pickle"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


async def _login(mm) -> None:
    """Login using env vars. Tries saved session first."""
    load_dotenv()

    email = os.environ.get("MONARCH_EMAIL")
    password = os.environ.get("MONARCH_PASSWORD")
    mfa_secret = os.environ.get("MONARCH_MFA_SECRET")

    if not email or not password:
        raise MonarchAuthError(
            "MONARCH_EMAIL and MONARCH_PASSWORD must be set in .env or environment"
        )

    try:
        await mm.login(
            email=email,
            password=password,
            mfa_secret_key=mfa_secret,
            use_saved_session=True,
            save_session=True,
        )
    except Exception as e:
        raise MonarchAuthError(f"Failed to login to Monarch Money: {e}") from e


async def _fetch_transactions(start_date: str, end_date: str) -> list[dict]:
    """Pull all transactions from Monarch for a date range, handling pagination."""
    from monarchmoney import MonarchMoney

    mm = MonarchMoney(session_file=_session_file())
    await _login(mm)

    all_txns = []
    offset = 0
    limit = 500

    while True:
        result = await mm.get_transactions(
            limit=limit,
            offset=offset,
            start_date=start_date,
            end_date=end_date,
        )
        batch = result.get("allTransactions", {}).get("results", []) or []
        if not batch:
            break
        all_txns.extend(batch)
        total = result.get("allTransactions", {}).get("totalCount", 0)
        if len(all_txns) >= total:
            break
        offset += limit

    return all_txns


def _parse_transactions(raw: list[dict]) -> list[Transaction]:
    """Convert raw Monarch JSON to Transaction objects, filtering split parents."""
    transactions = []
    for t in raw:
        txn = Transaction.from_monarch_dict(t)
        # Skip parent split transactions to avoid double-counting
        if txn.is_split_transaction:
            # Parent splits have children that sum to the same amount.
            # The children are separate transactions, so skip the parent.
            # Note: children have isSplitTransaction=False in Monarch's API.
            continue
        transactions.append(txn)
    return transactions


def pull_transactions(month: str) -> list[Transaction]:
    """
    Pull transactions from Monarch for a given month and cache them.

    Args:
        month: Month in "YYYY-MM" format (e.g. "2026-06")

    Returns:
        List of parsed Transaction objects
    """
    year, mon = month.split("-")
    start_date = f"{month}-01"
    last_day = calendar.monthrange(int(year), int(mon))[1]
    end_date = f"{month}-{last_day}"

    raw = asyncio.run(_fetch_transactions(start_date, end_date))

    # Cache raw JSON
    cache_dir = DATA_DIR / "transactions"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{month}.json"
    cache_file.write_text(json.dumps(raw, indent=2, default=str))

    return _parse_transactions(raw)


def load_cached_transactions(month: str) -> list[Transaction]:
    """Load transactions from cache without hitting the API."""
    cache_file = DATA_DIR / "transactions" / f"{month}.json"
    if not cache_file.exists():
        raise DataError(
            f"No cached data for {month}. Run 'expense-planner pull --month {month}' first."
        )
    raw = json.loads(cache_file.read_text())
    return _parse_transactions(raw)
