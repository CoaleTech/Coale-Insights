# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Standalone self-check for `_fifo_replay_age` (no frappe/DB needed).

Run directly: python insights/ml/test_fifo_replay_age.py
"""

from datetime import date

from insights.ml.inventory_intelligence import _fifo_replay_age


def demo():
    today = date(2026, 1, 1)

    # Single receipt, never consumed: age = days since that receipt.
    assert _fifo_replay_age([(10, date(2025, 12, 1))], today) == 31

    # Two receipts; a partial consume eats the OLDEST layer first (FIFO),
    # leaving only the newer layer on hand -- age must reflect the newer
    # date, not a blend of both receipt dates.
    ledger = [
        (10, date(2025, 1, 1)),   # oldest layer, fully consumed below
        (10, date(2025, 12, 1)),  # newer layer, untouched
        (-10, date(2025, 12, 15)),  # consumes exactly the old layer
    ]
    assert _fifo_replay_age(ledger, today) == 31  # only the Dec-1 layer remains

    # Fully consumed item currently has zero on-hand stock -> excluded.
    ledger_empty = [(5, date(2025, 1, 1)), (-5, date(2025, 6, 1))]
    assert _fifo_replay_age(ledger_empty, today) is None

    # Qty-weighted average across two remaining layers of different ages.
    ledger_mixed = [
        (10, date(2025, 11, 1)),  # 61 days old
        (10, date(2025, 12, 1)),  # 31 days old
    ]
    assert _fifo_replay_age(ledger_mixed, today) == 46.0  # (10*61 + 10*31) / 20

    print("all _fifo_replay_age checks passed")


if __name__ == "__main__":
    demo()
