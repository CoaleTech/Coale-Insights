# insights/ml/source_attribution.py
"""Lead-to-Invoice source attribution chain walker."""

import frappe
from typing import Dict, List, Optional


def build_source_attribution_map(
    period_start: str,
    period_end: str,
    force_refresh: bool = False,
) -> Dict[str, str]:
    """
    Build a map of Sales Invoice -> Lead Source by walking:
    Lead.source -> Opportunity.lead -> Quotation.opportunity
    -> Sales Order Item.prevdoc_docname -> Sales Invoice Item.sales_order

    Returns: {invoice_name: lead_source}
    """
    cache_key = f"source_attribution_{period_start}_{period_end}"
    if not force_refresh:
        cached = frappe.cache.get_value(cache_key)
        if cached:
            return cached

    query = """
        SELECT DISTINCT
            si.name as invoice,
            l.utm_source as utm_source
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        JOIN `tabSales Order` so ON so.name = sii.sales_order
        JOIN `tabSales Order Item` soi ON soi.parent = so.name
        JOIN `tabQuotation` q ON q.name = soi.prevdoc_docname AND soi.prevdoc_doctype = 'Quotation'
        JOIN `tabOpportunity` opp ON opp.name = q.opportunity AND opp.opportunity_from = 'Lead'
        JOIN `tabLead` l ON l.name = opp.party_name
        WHERE si.docstatus = 1
        AND si.posting_date BETWEEN %s AND %s
        AND l.utm_source IS NOT NULL AND l.utm_source != ''
    """
    try:
        rows = frappe.db.sql(query, (period_start, period_end), as_dict=True)
    except Exception:
        # Lead table may not have lead_source column in this ERPNext version
        return {}
    result = {r["invoice"]: r["utm_source"] for r in rows}

    frappe.cache.set_value(cache_key, result, expires_in_sec=3600)
    return result


def get_invoices_by_source(
    period_start: str, period_end: str, force_refresh: bool = False,
) -> Dict[str, List[str]]:
    """Group invoices by lead source. Returns {source: [invoice_names]}."""
    attr_map = build_source_attribution_map(period_start, period_end, force_refresh)
    by_source: Dict[str, List[str]] = {}
    for invoice, source in attr_map.items():
        by_source.setdefault(source, []).append(invoice)
    return by_source


def get_source_for_invoice(
    invoice_name: str, period_start: str, period_end: str,
) -> Optional[str]:
    """Get the lead source for a single invoice."""
    attr_map = build_source_attribution_map(period_start, period_end)
    return attr_map.get(invoice_name)