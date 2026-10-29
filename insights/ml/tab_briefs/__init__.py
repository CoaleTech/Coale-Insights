"""Server-computed tab headlines (Rule 7).

One sentence and one severity per tab, built from the payload a dashboard has
already computed. No query, no scan, no endpoint: the 2 vCPU budget is untouched.
The client renders the string and never rebuilds it.

Each dashboard module exposes ``briefs(payload) -> {tab_id: brief(...)}``.
"""

from __future__ import annotations

import importlib
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import frappe

# cached_run key prefix (text before the first ":") -> module in this package.
MODULES = {
    "insights_ml_sales_intelligence": "revenue",
    "insights_ml_customer_intelligence": "customer",
    "insights_ml_financial_intelligence": "finance_actuals",
    "insights_ml_strategic_finance_intelligence": "finance_planning",
    "insights_ml_inventory_intelligence": "inventory",
    "insights_ml_procurement_intelligence": "procurement",
    "insights_ml_risk_intelligence": "risk",
    "insights_ml_tax_intelligence": "tax",
    "insights_ml_hr_overview": "hr",
    "insights_ml_marketing_overview": "marketing",
    "insights_ml_manufacturing_overview": "manufacturing",
}

_SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "AED": "AED ", "KES": "KSh "}


def brief(severity: str, headline: str, details: list | None = None, actions: list | None = None) -> dict:
    """One tab verdict.

    ``details``: ``[{label, text}]``, the short "why" lines under the headline.
    ``actions``: ``[{title, text, impact?, owner?}]``, ranked, rendered as the Actions card.
    Every number in these strings must come from the payload (no invented figures).
    """
    out = {"severity": severity, "headline": headline}
    if details:
        out["details"] = details
    if actions:
        out["actions"] = actions
    return out


def detail(label: str, text: str) -> dict:
    return {"label": label, "text": text}


def action(title: str, text: str, impact: str | None = None, owner: str | None = None) -> dict:
    return {"title": title, "text": text, "impact": impact, "owner": owner}


def money(value: Any, currency: str | None) -> str:
    """Exact en-US money, 0 decimals. Mirrors the client `formatMoney`."""
    if value is None:
        return "-"
    n = int(Decimal(str(value)).copy_abs().quantize(Decimal(1), rounding=ROUND_HALF_UP))
    symbol = _SYMBOLS.get(currency or "", f"{currency} " if currency else "")
    return f"{'-' if value < 0 and n else ''}{symbol}{n:,}"


def plural(n: int, singular: str, plural_form: str | None = None) -> str:
    return f"{n:,} {singular if n == 1 else plural_form or singular + 's'}"


def day(value: Any) -> str:
    """ISO date (a pandas Timestamp's time part is ignored) as "24 Oct 2026", like the page. Unparseable input passes through."""
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%d %b %Y")
    except ValueError:
        return str(value)


def _safe(fn, payload: dict, label: str) -> Any:
    try:
        return fn(payload)
    except Exception:
        # A headline bug must never blank a dashboard. Logger, not Error Log:
        # that table is already the largest on this site.
        frappe.logger("insights.tab_briefs").exception(label)
        return None


def attach(cache_key: str, result: Any) -> Any:
    """Add ``tab_briefs`` to a cached dashboard payload (enveloped or not)."""
    module = MODULES.get(cache_key.split(":", 1)[0])
    if not module or not isinstance(result, dict) or result.get("status") != "success":
        return result
    payload = result["data"] if isinstance(result.get("data"), dict) else result
    briefs = _safe(
        lambda p: importlib.import_module(f"{__name__}.{module}").briefs(p), payload, cache_key
    )
    if briefs is not None:
        payload["tab_briefs"] = briefs
    return result


def attach_lazy(result: Any, fn, label: str) -> Any:
    """Add ``brief`` to a lazily-loaded tab endpoint's own response."""
    if isinstance(result, dict) and result.get("status") == "success":
        target = result["data"] if isinstance(result.get("data"), dict) else result
        found = _safe(fn, target, label)
        if found is not None:
            target["brief"] = found
    return result
