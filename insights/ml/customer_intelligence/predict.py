# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Customer Intelligence - Predict
Get cached or fresh predictions for customer intelligence.
"""

from typing import Any, Dict, Optional

from frappe import _


def predict(intelligence, customer: Optional[str] = None, allow_train: bool = False) -> Dict[str, Any]:
    """Get cached predictions.

    `allow_train` is off by default so an incidental caller cannot trigger a full
    training pass. The dashboard endpoint
    (`insights.api.ml.customer.customer_intelligence`) opts in, because it computes
    inline and must produce a payload.
    """
    cached = intelligence.get_cached_results("customer_intelligence")
    if not cached:
        if not allow_train:
            return {
                "status": "warming",
                "message": _("Customer intelligence is being computed. Refresh shortly."),
            }
        cached = intelligence.train()

    if customer:
        customers = cached.get('customers', [])
        cust_data = next((c for c in customers if c['customer_id'] == customer), None)
        if cust_data:
            actions = [a for a in cached.get('next_best_actions', []) if a['customer_id'] == customer]
            return {"status": "success", "customer": cust_data, "actions": actions[0] if actions else None}
        return {"status": "error", "message": "Customer not found"}

    return cached
