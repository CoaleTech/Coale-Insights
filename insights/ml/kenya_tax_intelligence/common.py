# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Shared helpers for the Kenya tax sections: reporting window, safe execution,
payload builders (KPI, chip), tax-account discovery and the holiday list.

Every section module exposes `compute(ctx: TaxContext) -> dict` and nothing else
the orchestrator needs. Sections never raise: `model.py` wraps each in `safe()`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Dict, Iterable, List, Optional

import frappe

from insights.ml.kenya_tax_intelligence import rules

PERIODS = ("3m", "6m", "12m", "fy")
_PERIOD_MONTHS = {"3m": 3, "6m": 6, "12m": 12}
NO_DATA = None  # payload value for "missing"; the UI renders it as "-", never 0


# --------------------------------------------------------------------------- context
@dataclass
class TaxContext:
    company: Optional[str]
    base_currency: str
    period: str
    period_name: str
    start: date
    end: date
    today: date
    fy_name: str
    fy_start: date
    fy_end: date
    _cache: Dict[str, Any]

    def window(self) -> Dict[str, str]:
        return {
            "key": self.period,
            "name": self.period_name,
            "start_date": self.start.isoformat(),
            "end_date": self.end.isoformat(),
        }


def today() -> date:
    return datetime.now().date()


def as_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def days_until(target: Optional[date], ref: date) -> Optional[int]:
    return None if target is None else (target - ref).days


def default_company() -> Optional[str]:
    return frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")


def base_currency(company: Optional[str]) -> str:
    if company:
        cur = frappe.db.get_value("Company", company, "default_currency", cache=True)
        if cur:
            return cur
    return frappe.db.get_single_value("Global Defaults", "default_currency") or "KES"


def fiscal_year_for(company: Optional[str], on: date) -> Dict[str, Any]:
    """Fiscal Year covering `on` (company-specific first), else the calendar year.

    Kenya's income year is the calendar year by default, so the fallback is Jan-Dec.
    """
    FY = frappe.qb.DocType("Fiscal Year")
    FYC = frappe.qb.DocType("Fiscal Year Company")
    if company:
        rows = (
            frappe.qb.from_(FY)
            .left_join(FYC)
            .on(FYC.parent == FY.name)
            .select(FY.name, FY.year_start_date, FY.year_end_date)
            .where(FY.disabled == 0)
            .where((on >= FY.year_start_date) & (on <= FY.year_end_date))
            .where((FYC.company == company) | FYC.company.isnull())
            .orderby(FY.year_start_date, order=frappe.qb.desc)
            .limit(1)
            .run(as_dict=True)
        )
        if rows:
            return rows[0]
    rows = (
        frappe.qb.from_(FY)
        .select(FY.name, FY.year_start_date, FY.year_end_date)
        .where(FY.disabled == 0)
        .where((on >= FY.year_start_date) & (on <= FY.year_end_date))
        .orderby(FY.year_start_date, order=frappe.qb.desc)
        .limit(1)
        .run(as_dict=True)
    )
    if rows:
        return rows[0]
    return {"name": str(on.year), "year_start_date": date(on.year, 1, 1), "year_end_date": date(on.year, 12, 31)}


def build_context(period: str = "fy") -> TaxContext:
    """Resolve company, currency and reporting window for `period` (3m/6m/12m/fy/custom:a:b)."""
    from insights.api.ml.utils import parse_custom_range

    custom = parse_custom_range(period)
    if not (period in PERIODS or custom):
        period = "fy"
    t = today()
    company = default_company()
    fy = fiscal_year_for(company, t)
    fy_start, fy_end = as_date(fy["year_start_date"]), as_date(fy["year_end_date"])
    if custom:
        start, end, name = custom[0].date(), custom[1].date(), "Custom Range"
    elif period == "fy":
        start, end, name = fy_start, fy_end, fy["name"]
    else:
        months = _PERIOD_MONTHS[period]
        start, end, name = rules.add_months(t, -months), t, f"Last {months} Months"
    return TaxContext(
        company=company,
        base_currency=base_currency(company),
        period=period,
        period_name=name,
        start=start,
        end=end,
        today=t,
        fy_name=fy["name"],
        fy_start=fy_start,
        fy_end=fy_end,
        _cache={},
    )


# --------------------------------------------------------------------------- safety
def safe(fn: Callable, *args, default: Any = None, **kwargs) -> Any:
    """Call `fn`; log and return `default` on any exception so one section never blocks the rest."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        frappe.log_error(f"KenyaTaxIntelligence section failed [{getattr(fn, '__module__', '')}.{fn.__name__}]: {exc}", "ML Tax")
        return default


def doctype_exists(doctype: str) -> bool:
    return bool(frappe.db.exists("DocType", doctype)) and bool(frappe.db.table_exists(doctype))


def has_field(doctype: str, fieldname: str) -> bool:
    """True when the column exists on the table (custom fields included)."""
    return doctype_exists(doctype) and bool(frappe.db.has_column(doctype, fieldname))


def unavailable(reason: str, **extra) -> Dict[str, Any]:
    """Section payload when its data source is missing. `kpis` stays so the UI shows '-' tiles."""
    return {"available": False, "message": reason, "kpis": [], **extra}


# --------------------------------------------------------------------------- payload builders
def kpi(key: str, label: str, value: Any, unit: str = "money", sub: str = "", tone: str = "neutral") -> Dict[str, Any]:
    """KPI tile. unit: money|pct|count|text|date. value None renders '-'. tone: neutral|warn|bad|good."""
    return {"key": key, "label": label, "value": value, "unit": unit, "sub": sub, "tone": tone}


def chip(tone: str, label: str) -> Dict[str, str]:
    """Status chip. tone: pos|warn|neg|mut|acc. The UI adds the icon; `label` must be text."""
    return {"tone": tone, "label": label}


def month_key(d: date) -> str:
    return d.strftime("%Y-%m")


def month_starts(end: date, n: int) -> List[date]:
    """First day of each of the `n` months ending with the month of `end`, oldest first."""
    first = end.replace(day=1)
    return [rules.add_months(first, -i) for i in range(n - 1, -1, -1)]


def pct(part: Optional[float], whole: Optional[float]) -> Optional[float]:
    """Percentage 0-100 rounded to 2dp; None when the denominator is missing or zero."""
    if part is None or not whole:
        return None
    return round(part / whole * 100, 2)


# --------------------------------------------------------------------------- data lookups
def holidays(ctx: TaxContext, span_days: int = 400) -> List[date]:
    """Holiday dates from the company's (or default) Holiday List, from `today` for `span_days`."""
    key = "holidays"
    if key in ctx._cache:
        return ctx._cache[key]
    out: List[date] = []
    if doctype_exists("Holiday List"):
        hl = (frappe.db.get_value("Company", ctx.company, "default_holiday_list") if ctx.company else None)
        if hl:
            from datetime import timedelta

            rows = frappe.get_all(
                "Holiday",
                filters={"parent": hl, "holiday_date": ["between", [ctx.today, ctx.today + timedelta(days=span_days)]]},
                pluck="holiday_date",
            )
            out = [d for d in (as_date(r) for r in rows) if d]
    ctx._cache[key] = out
    return out


def tax_accounts(ctx: TaxContext, kind: str) -> List[str]:
    """Leaf Account names for the company whose account_name matches rules.ACCOUNT_PATTERNS[kind].

    Matches Tax / Payable / Receivable / Expense accounts by name fragment, because ERPNext has
    no Kenya tax-type field. Cached on the context.
    """
    cache = ctx._cache.setdefault("accounts", {})
    if kind not in cache:
        rows = frappe.get_all(
            "Account",
            filters={"company": ctx.company, "is_group": 0, "disabled": 0},
            fields=["name", "account_name"],
        ) if ctx.company else []
        frags = rules.ACCOUNT_PATTERNS[kind]
        cache[kind] = [r["name"] for r in rows if any(f in f" {(r['account_name'] or '').lower()} " for f in frags)]
    return cache[kind]


def gl_net(ctx: TaxContext, accounts: Iterable[str], start: date, end: date, credit_positive: bool = True) -> Optional[float]:
    """Sum of non-cancelled GL Entries on `accounts` between dates (credit - debit by default).

    None when there are no accounts (so callers show '-' instead of 0).
    """
    accounts = list(accounts)
    if not accounts:
        return None
    row = frappe.db.sql(
        """SELECT COALESCE(SUM(credit - debit), 0) FROM `tabGL Entry`
           WHERE company = %s AND is_cancelled = 0 AND account IN %s AND posting_date BETWEEN %s AND %s""",
        (ctx.company, tuple(accounts), start, end),
    )
    val = float(row[0][0] or 0)
    return val if credit_positive else -val


def money_short(ctx: TaxContext, value: Optional[float]) -> str:
    """'KES 3.72M' / 'KES 4.8k' / 'KES 950' for sub-text; '-' when value is None."""
    if value is None:
        return "-"
    v = abs(value)
    body = f"{v / 1e6:.2f}M" if v >= 1e6 else f"{v / 1e3:.1f}k" if v >= 1e4 else f"{v:,.0f}"
    return f"{ctx.base_currency} {'-' if value < 0 else ''}{body}"


def drill_page(columns: List[Dict[str, Any]], rows: List[Dict[str, Any]], filters: Dict[str, Any], page_len: int = 50) -> Dict[str, Any]:
    """Drill-down envelope: one 1-based `filters.page` slice of `rows` plus the full `total`."""
    start = (max(int((filters or {}).get("page") or 1), 1) - 1) * page_len
    return {"columns": columns, "rows": rows[start:start + page_len], "total": len(rows)}


def gl_debit(ctx: TaxContext, accounts: Iterable[str], start: date, end: date, voucher_types: Iterable[str] = ("Payment Entry", "Journal Entry")) -> Optional[float]:
    """Sum of debits on `accounts` posted by `voucher_types` between dates: money paid out to the authority.

    None when there are no accounts. Debits from other voucher types (e.g. debit-note reversals) are not payments.
    """
    accounts, vts = list(accounts), tuple(voucher_types)
    if not accounts:
        return None
    row = frappe.db.sql(
        """SELECT COALESCE(SUM(debit), 0) FROM `tabGL Entry`
           WHERE company = %s AND is_cancelled = 0 AND account IN %s AND voucher_type IN %s AND posting_date BETWEEN %s AND %s""",
        (ctx.company, tuple(accounts), vts, start, end),
    )
    return float(row[0][0] or 0)


def vat_tax_cond(ctx: TaxContext, kind: str, alias: str = "t"):
    """(SQL condition, params) selecting VAT rows of a Sales/Purchase Taxes and Charges table.

    A row is VAT when its account matches `tax_accounts(ctx, kind)` ('vat_output'/'vat_input')
    or its rate is the 16% VAT rate. `alias` is a code constant, never user input.
    """
    accounts = tax_accounts(ctx, kind)
    params: Dict[str, Any] = {"vat_rate": rules.VAT_RATE * 100}
    if not accounts:
        return f"{alias}.rate = %(vat_rate)s", params
    params["vat_acc"] = tuple(accounts)
    return f"({alias}.account_head IN %(vat_acc)s OR {alias}.rate = %(vat_rate)s)", params
