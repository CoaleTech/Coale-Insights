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

    `allow_train` is off by default so a cache miss cannot turn a web request into
    a full training pass. Worker-side callers
    (`insights.api.ml.customer._compute_customer_intelligence`) opt in.
    """
    cached = intelligence.get_cached_results("customer_intelligence")
    if not cached:
        if not allow_train:
            # Redis is wiped by every deploy and by `bench clear-cache`, which
            # leaves usable numbers on disk and an empty cache. Serve those
            # rather than a placeholder.
            return intelligence.get_last_good_results("customer_intelligence") or {
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
        return {"status": "error", "message": _("Customer not found")}

    return cached
