from __future__ import annotations
# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Customer Intelligence - Data Collection
All database query methods for gathering customer transaction data.
"""

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import pandas as pd


def get_customer_transactions(intelligence) -> pd.DataFrame:
    """Get comprehensive customer transaction data (last 24 months)"""
    query = f"""
        SELECT
            c.name as customer_id,
            c.customer_name,
            c.customer_group,
            c.territory,
            c.creation as customer_since,
            c.account_manager,
            si.name as invoice_id,
            si.posting_date,
            si.due_date,
            si.grand_total,
            si.net_total,
            si.outstanding_amount,
            si.status,
            DATEDIFF(CURDATE(), si.posting_date) as days_since_transaction,
            CASE
                WHEN si.outstanding_amount = 0 THEN 'Paid'
                WHEN si.due_date < CURDATE() THEN 'Overdue'
                ELSE 'Outstanding'
            END as payment_status
        FROM `tabCustomer` c
        LEFT JOIN `tabSales Invoice` si ON c.name = si.customer AND si.docstatus = 1
            {intelligence.DATE_FILTER}
        WHERE c.disabled = 0
        ORDER BY c.name, si.posting_date DESC
    """
    return intelligence.get_training_data(query)


def get_territory_data(intelligence) -> pd.DataFrame:
    """Get territory hierarchy for geographic analysis"""
    query = """
        SELECT
            name as territory,
            parent_territory,
            territory_manager,
            lft, rgt, is_group
        FROM `tabTerritory`
        ORDER BY lft
    """
    return intelligence.get_training_data(query)


def get_customer_items(intelligence) -> pd.DataFrame:
    """Get customer purchase details by item (last 24 months)"""
    query = f"""
        SELECT
            si.customer as customer_id,
            sii.item_code,
            sii.item_name,
            i.item_group,
            i.brand,
            SUM(sii.qty) as total_qty,
            SUM(sii.amount) as total_amount,
            COUNT(DISTINCT si.name) as order_count
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON sii.parent = si.name
        LEFT JOIN `tabItem` i ON sii.item_code = i.name
        WHERE si.docstatus = 1
            {intelligence.DATE_FILTER}
        GROUP BY si.customer, sii.item_code
    """
    return intelligence.get_training_data(query)


def get_payment_history(intelligence) -> pd.DataFrame:
    """Get customer payment patterns (last 24 months)"""
    query = """
        SELECT
            pe.party as customer_id,
            pe.posting_date as payment_date,
            pe.paid_amount,
            per.reference_name as invoice,
            si.posting_date as invoice_date,
            DATEDIFF(pe.posting_date, si.posting_date) as days_to_pay
        FROM `tabPayment Entry` pe
        JOIN `tabPayment Entry Reference` per ON per.parent = pe.name
        LEFT JOIN `tabSales Invoice` si ON per.reference_name = si.name
        WHERE pe.docstatus = 1
            AND pe.payment_type = 'Receive'
            AND pe.party_type = 'Customer'
            AND pe.posting_date >= DATE_SUB(CURDATE(), INTERVAL 24 MONTH)
    """
    return intelligence.get_training_data(query)


def get_quotation_data(intelligence) -> pd.DataFrame:
    """Get quotation conversion data (last 24 months)"""
    query = """
        SELECT
            q.party_name as customer_id,
            q.name as quotation,
            q.transaction_date,
            q.grand_total,
            q.status,
            CASE WHEN q.status = 'Ordered' THEN 1 ELSE 0 END as converted
        FROM `tabQuotation` q
        WHERE q.docstatus = 1
            AND q.quotation_to = 'Customer'
            AND q.transaction_date >= DATE_SUB(CURDATE(), INTERVAL 24 MONTH)
    """
    return intelligence.get_training_data(query)
