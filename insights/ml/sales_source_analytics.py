# insights/ml/sales_source_analytics.py
"""Source-attributed sales metrics and quotation analytics."""

import frappe
from typing import Dict, Any, List
from insights.ml.source_attribution import build_source_attribution_map


def get_source_attributed_sales(period_start: str, period_end: str) -> List[Dict]:
    """Revenue, orders, and gross profit attributed to each lead source."""
    attr_map = build_source_attribution_map(period_start, period_end)
    if not attr_map:
        return []

    invoices = list(attr_map.keys())
    # Chunk to avoid SQL IN clause limits
    chunk_size = 500
    source_data: Dict[str, Dict] = {}

    for i in range(0, len(invoices), chunk_size):
        chunk = invoices[i:i + chunk_size]
        placeholders = ", ".join(["%s"] * len(chunk))
        query = f"""
            SELECT si.name as invoice, si.grand_total,
                   SUM(sii.net_amount - (sii.qty * COALESCE(sii.incoming_rate, 0))) as gross_profit
            FROM `tabSales Invoice` si
            JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
            WHERE si.name IN ({placeholders})
            GROUP BY si.name
        """
        rows = frappe.db.sql(query, chunk, as_dict=True)
        for row in rows:
            source = attr_map.get(row["invoice"], "Unattributed")
            if source not in source_data:
                source_data[source] = {"revenue": 0, "gross_profit": 0, "order_count": 0}
            source_data[source]["revenue"] += float(row.get("grand_total") or 0)
            source_data[source]["gross_profit"] += float(row.get("gross_profit") or 0)
            source_data[source]["order_count"] += 1

    return [
        {"source": src, **vals}
        for src, vals in sorted(source_data.items(), key=lambda x: x[1]["revenue"], reverse=True)
    ]


def get_quotation_analytics(period_start: str, period_end: str) -> Dict[str, Any]:
    """Quotation funnel: total, won, lost by reason."""
    total = frappe.db.count("Quotation", {
        "transaction_date": ["between", [period_start, period_end]],
        "docstatus": 1,
    })

    won = frappe.db.count("Quotation", {
        "transaction_date": ["between", [period_start, period_end]],
        "docstatus": 1,
        "status": "Ordered",
    })

    lost_reasons_query = """
        SELECT order_lost_reason, COUNT(*) as count
        FROM `tabQuotation`
        WHERE docstatus = 1
        AND transaction_date BETWEEN %s AND %s
        AND status = 'Lost'
        AND order_lost_reason IS NOT NULL AND order_lost_reason != ''
        GROUP BY order_lost_reason
        ORDER BY count DESC
    """
    lost_reasons = frappe.db.sql(lost_reasons_query, (period_start, period_end), as_dict=True)
    total_lost = sum(r["count"] for r in lost_reasons)

    return {
        "total": total,
        "won": won,
        "lost": total_lost,
        "pending": total - won - total_lost,
        "conversion_rate": round(won / total * 100, 1) if total > 0 else 0,
        "lost_reasons": [dict(r) for r in lost_reasons],
    }


def get_territory_performance(period_start: str, period_end: str) -> List[Dict]:
    """Sales orders and gross profit by territory."""
    query = """
        SELECT si.territory,
               COUNT(DISTINCT si.name) as order_count,
               SUM(si.grand_total) as revenue,
               SUM(sii.net_amount - (sii.qty * COALESCE(sii.incoming_rate, 0))) as gross_profit
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE si.docstatus = 1
        AND si.posting_date BETWEEN %s AND %s
        AND si.territory IS NOT NULL AND si.territory != ''
        GROUP BY si.territory
        ORDER BY revenue DESC
    """
    return [dict(r) for r in frappe.db.sql(query, (period_start, period_end), as_dict=True)]
