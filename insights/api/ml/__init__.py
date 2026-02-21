# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
ML API Package
Consolidated ML API endpoints organized by domain
"""

import frappe
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timedelta


def parse_date_filter(date_filter: str = '12m') -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Parse a date filter string into start_date and end_date.

    Args:
        date_filter: Filter string like '7d', '30d', '90d', '6m', '12m', '24m', 'all'

    Returns:
        Tuple of (start_date, end_date) where end_date is always today
        Returns (None, None) for 'all' to indicate no date filtering
    """
    if not date_filter or date_filter == 'all':
        return None, None

    end_date = datetime.now()

    # Parse the filter value
    if date_filter.endswith('d'):
        days = int(date_filter[:-1])
        start_date = end_date - timedelta(days=days)
    elif date_filter.endswith('m'):
        months = int(date_filter[:-1])
        # Approximate months as 30 days each
        start_date = end_date - timedelta(days=months * 30)
    elif date_filter.endswith('y'):
        years = int(date_filter[:-1])
        start_date = end_date - timedelta(days=years * 365)
    else:
        # Default to 12 months
        start_date = end_date - timedelta(days=365)

    return start_date, end_date


def get_date_filter_sql(date_filter: str = '12m', date_column: str = 'posting_date', alias: str = '') -> str:
    """
    Generate SQL WHERE clause for date filtering.
    """
    start_date, end_date = parse_date_filter(date_filter)

    if start_date is None:
        return ""

    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    if alias:
        date_col = f"{alias}.{date_column}"
    else:
        date_col = date_column

    return f"AND {date_col} BETWEEN '{start_str}' AND '{end_str}'"


# Re-export all whitelisted functions for backward compatibility
from .customer import *
from .sales import *
from .inventory import *
from .procurement import *
from .financial import *
from .hr import *
from .executive import *
from .search import *
from .predictive import *
from .general import *
from .risk import *
from .tax import *
from .strategic_finance import *
from .esg import *
from .hotel import *