# insights/ml/marketing_source_metrics.py
"""Lead source metrics for MarketingCRM Intelligence."""

import frappe
from typing import Dict, Any, List


def get_leads_by_source(period_start: str, period_end: str) -> List[Dict]:
    """Lead count grouped by source."""
    query = """
        SELECT utm_source as source, COUNT(*) as count
        FROM `tabLead`
        WHERE creation BETWEEN %s AND %s
        AND utm_source IS NOT NULL AND utm_source != ''
        GROUP BY utm_source
        ORDER BY count DESC
    """
    return [dict(r) for r in frappe.db.sql(query, (period_start, period_end), as_dict=True)]


def get_hot_leads_by_source(period_start: str, period_end: str) -> List[Dict]:
    """Hot leads (Interested/Opportunity status) by source."""
    query = """
        SELECT utm_source as source, COUNT(*) as count
        FROM `tabLead`
        WHERE creation BETWEEN %s AND %s
        AND utm_source IS NOT NULL AND utm_source != ''
        AND status IN ('Interested', 'Opportunity')
        GROUP BY utm_source
        ORDER BY count DESC
    """
    return [dict(r) for r in frappe.db.sql(query, (period_start, period_end), as_dict=True)]


def get_source_costs(period_start: str, period_end: str) -> Dict[str, float]:
    """
    Marketing spend per source from GL entries in source-named cost centers.
    Convention: cost center named like 'Indiamart - Marketing - XXX'.
    """
    query = """
        SELECT cc.name as cost_center,
               SUM(gle.debit - gle.credit) as spend
        FROM `tabGL Entry` gle
        JOIN `tabCost Center` cc ON cc.name = gle.cost_center
        WHERE gle.posting_date BETWEEN %s AND %s
        AND gle.is_cancelled = 0
        AND (cc.name LIKE '%%Marketing%%' OR cc.cost_center_name LIKE '%%Marketing%%')
        GROUP BY cc.name
    """
    rows = frappe.db.sql(query, (period_start, period_end), as_dict=True)

    # Try to match cost center names to lead sources
    sources = [r["utm_source"] for r in frappe.db.sql(
        "SELECT DISTINCT utm_source FROM `tabLead` WHERE utm_source IS NOT NULL AND utm_source != ''",
        as_dict=True,
    )]

    cost_map = {}
    for source in sources:
        source_lower = source.lower()
        for row in rows:
            if source_lower in row["cost_center"].lower():
                cost_map[source] = float(row.get("spend") or 0)
                break
        if source not in cost_map:
            cost_map[source] = 0

    return cost_map


def get_cost_per_lead(period_start: str, period_end: str) -> List[Dict]:
    """Cost per lead for each source."""
    leads = get_leads_by_source(period_start, period_end)
    costs = get_source_costs(period_start, period_end)

    result = []
    for lead_row in leads:
        source = lead_row["source"]
        count = lead_row["count"]
        cost = costs.get(source, 0)
        result.append({
            "source": source,
            "lead_count": count,
            "total_cost": cost,
            "cost_per_lead": round(cost / count, 2) if count > 0 else 0,
            "has_cost_data": cost > 0,
        })
    return result


def get_territory_leads(period_start: str, period_end: str) -> List[Dict]:
    """Lead count by territory."""
    query = """
        SELECT territory, COUNT(*) as count
        FROM `tabLead`
        WHERE creation BETWEEN %s AND %s
        AND territory IS NOT NULL AND territory != ''
        GROUP BY territory
        ORDER BY count DESC
    """
    return [dict(r) for r in frappe.db.sql(query, (period_start, period_end), as_dict=True)]
