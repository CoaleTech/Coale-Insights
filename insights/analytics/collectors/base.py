# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Base Data Collector
Abstract base class for ERPNext module-specific data collectors.
"""

from typing import Dict, Any, Optional

from frappe.utils import nowdate, add_months

from insights.api.ml.permissions import permitted_company


class BaseCollector:
    """Base class for data collectors"""

    def __init__(self, filters: Optional[Dict] = None):
        self.filters = filters or {}
        # `company` used to arrive as client-supplied JSON and go straight into
        # the query, falling back to a site-wide default when absent. Both are
        # resolved here now, against the companies this user may actually see,
        # so every collector is covered by construction rather than by each
        # entry point remembering to check.
        self.company = permitted_company(self.filters)
        self.from_date = filters.get("from_date") if filters else add_months(nowdate(), -12)
        self.to_date = filters.get("to_date") if filters else nowdate()

    def collect(self) -> Dict[str, Any]:
        """Override in subclass to return collected data."""
        raise NotImplementedError
