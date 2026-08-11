from __future__ import annotations
# insights/ml/customer_intelligence/counts.py
"""Customer count and segmentation queries."""

import frappe
from typing import Dict, Any, TYPE_CHECKING
if TYPE_CHECKING:
    import pandas as pd


def get_customer_counts(intelligence, active_cutoff_months: int = 6) -> Dict[str, Any]:
    """Get all customer count metrics."""
    period_start, period_end = intelligence.period_start, intelligence.period_end

    total = frappe.db.count("Customer", {"disabled": 0})

    new_by_creation = frappe.db.count("Customer", {
        "disabled": 0,
        "creation": ["between", [period_start, period_end]],
    })

    # New by first transaction
    first_txn_query = f"""
        SELECT COUNT(DISTINCT si.customer) as cnt
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
        AND si.customer IN (
            SELECT customer FROM (
                SELECT customer, MIN(posting_date) as first_date
                FROM `tabSales Invoice`
                WHERE docstatus = 1
                GROUP BY customer
                HAVING first_date BETWEEN %s AND %s
            ) first_customers
        )
    """
    new_by_txn_result = frappe.db.sql(first_txn_query, (period_start, period_end), as_dict=True)
    new_by_first_txn = new_by_txn_result[0]["cnt"] if new_by_txn_result else 0

    # Active customers: transacted within the cutoff.
    #
    # Counted on Sales Order OR Sales Invoice, not Sales Order alone. This
    # business invoices directly: 873 submitted invoices against 68 submitted
    # sales orders, and in the last six months 1 order versus 70 invoices from
    # 58 customers. Keying `active` off orders alone reported active=1 and
    # inactive=585, so the dashboard showed a dead customer base while 58
    # customers were actively buying.
    cutoff_date = frappe.utils.add_months(frappe.utils.nowdate(), -active_cutoff_months)
    active_query = """
        SELECT COUNT(DISTINCT customer) AS cnt FROM (
            SELECT customer FROM `tabSales Order`
            WHERE docstatus = 1 AND transaction_date >= %(cutoff)s
            UNION
            SELECT customer FROM `tabSales Invoice`
            WHERE docstatus = 1 AND posting_date >= %(cutoff)s
        ) t
    """
    active_result = frappe.db.sql(active_query, {"cutoff": cutoff_date}, as_dict=True)
    active = active_result[0]["cnt"] if active_result else 0

    # Advance payment customers
    advance_query = """
        SELECT COUNT(DISTINCT party) as cnt
        FROM `tabPayment Entry`
        WHERE docstatus = 1
        AND payment_type = 'Receive'
        AND party_type = 'Customer'
        AND unallocated_amount > 0
    """
    advance_result = frappe.db.sql(advance_query, as_dict=True)
    advance = advance_result[0]["cnt"] if advance_result else 0

    # Customer category segmentation
    try:
        manufacturers = frappe.db.count("Customer", {
            "disabled": 0, "custom_customer_category": "Manufacturer",
        })
        traders = frappe.db.count("Customer", {
            "disabled": 0, "custom_customer_category": "Trader",
        })
    except Exception:
        # Field may not exist in this ERPNext version
        manufacturers = 0
        traders = 0

    return {
        "total": total,
        "new_by_creation": new_by_creation,
        "new_by_first_txn": new_by_first_txn,
        "existing": total - new_by_creation,
        "active": active,
        "inactive": total - active,
        "advance_payment": advance,
        "manufacturers": manufacturers,
        "traders": traders,
        "active_cutoff_months": active_cutoff_months,
    }


def get_customer_revenue_split(intelligence) -> Dict[str, Any]:
    """Revenue from new vs existing customers."""
    period_start = intelligence.period_start
    period_end = intelligence.period_end

    query = f"""
        SELECT
            CASE
                WHEN first_txn.first_date BETWEEN %s AND %s THEN 'new'
                ELSE 'existing'
            END as customer_type,
            SUM(si.grand_total) as revenue,
            COUNT(DISTINCT si.customer) as customer_count
        FROM `tabSales Invoice` si
        JOIN (
            SELECT customer, MIN(posting_date) as first_date
            FROM `tabSales Invoice`
            WHERE docstatus = 1
            GROUP BY customer
        ) first_txn ON si.customer = first_txn.customer
        WHERE si.docstatus = 1
        AND si.posting_date BETWEEN %s AND %s
        GROUP BY customer_type
    """
    result = frappe.db.sql(query, (period_start, period_end, period_start, period_end), as_dict=True)

    split = {"new_revenue": 0, "existing_revenue": 0, "new_count": 0, "existing_count": 0}
    for row in result:
        if row.customer_type == "new":
            split["new_revenue"] = float(row.revenue or 0)
            split["new_count"] = row.customer_count
        else:
            split["existing_revenue"] = float(row.revenue or 0)
            split["existing_count"] = row.customer_count

    total = split["new_revenue"] + split["existing_revenue"]
    split["new_pct"] = round(split["new_revenue"] / total * 100, 1) if total else 0
    split["existing_pct"] = round(split["existing_revenue"] / total * 100, 1) if total else 0
    return split
