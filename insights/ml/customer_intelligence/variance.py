# insights/ml/customer_intelligence/variance.py
"""Customer target vs actual variance."""

import frappe
from typing import Dict, Any, List


def get_customer_variance(intelligence) -> List[Dict[str, Any]]:
    """
    Compare customer sales targets (from Sales Person/Territory)
    against actual Sales Invoice revenue.
    """
    period_start = intelligence.period_start
    period_end = intelligence.period_end

    # Get actual revenue per customer
    actual_query = """
        SELECT si.customer, si.customer_name, si.territory,
               SUM(si.grand_total) as actual_revenue
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
        AND si.posting_date BETWEEN %s AND %s
        GROUP BY si.customer
    """
    actuals = frappe.db.sql(actual_query, (period_start, period_end), as_dict=True)
    actual_map = {r["customer"]: r for r in actuals}

    # Get targets from Territory target
    target_query = """
        SELECT tt.parent as territory, tt.target_amount,
               tt.fiscal_year
        FROM `tabTarget Detail` tt
        JOIN `tabTerritory` t ON t.name = tt.parent
        WHERE tt.parenttype = 'Territory'
    """
    territory_targets = frappe.db.sql(target_query, as_dict=True)

    # Build territory -> target map
    territory_target_map = {}
    for t in territory_targets:
        territory_target_map[t["territory"]] = float(t.get("target_amount") or 0)

    # Merge
    results = []
    for customer, data in actual_map.items():
        territory = data.get("territory", "")
        target = territory_target_map.get(territory, 0)
        actual = float(data.get("actual_revenue") or 0)
        variance = actual - target
        variance_pct = round(actual / target * 100, 1) if target > 0 else 0

        rag = "green"
        if variance_pct < 80:
            rag = "red"
        elif variance_pct < 100:
            rag = "amber"

        results.append({
            "customer": customer,
            "customer_name": data["customer_name"],
            "territory": territory,
            "target": target,
            "actual": actual,
            "variance": variance,
            "variance_pct": variance_pct,
            "rag": rag,
        })

    results.sort(key=lambda x: x["variance"], reverse=True)
    return results
