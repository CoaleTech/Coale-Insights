# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""VAT tab: output/input VAT, supply mix, input VAT at risk and VAT on imported services.

Source choice (documented, deliberate): VAT comes from the *tax rows of submitted Sales and
Purchase Invoices*, not from GL balances. A "VAT payable/receivable" GL account mixes the tax
charged with VAT3 settlements and offsets, so its movement is not output or input VAT. A tax row
is VAT when its account matches `common.tax_accounts('vat_output'|'vat_input')` or its rate is
16% (`common.vat_tax_cond`). Purchase rows of category 'Valuation' (non-recoverable) are ignored.

Periods: the monthly series covers the 12 months ending with the month of `min(period end, today)`;
the headline KPIs, supply mix and reverse charge use that latest month (VAT3 is monthly). Input-VAT
risk uses the selected period (same invoices as the eTIMS tab), except "near the cut-off", which
looks at invoices whose 6-month claim window closes within 30 days of today.

Input VAT at risk, by reason:
  * no eTIMS CU number  - `etims.purchase_rows` coverage; None when the site has no eTIMS data.
  * within 30 days of the 6-month cut-off - ERPNext has no "claimed on VAT3" flag, so every
    invoice with input VAT in the last 30 days of its window is listed.
  * used for exempt supplies - not derivable: None.
  * blocked category - expense account or item name containing `BLOCKED_FRAGMENTS`; VAT share
    = blocked item value x the invoice's effective VAT/net ratio.

Drill-down metrics: `vat_month` (filters.month YYYY-MM, side output|input), `vat_input_risk`
(filters.reason no_cu|near_cutoff|blocked), `vat_supplier_risk` (filters.supplier),
`vat_reverse_charge`.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import frappe
from frappe import _
from frappe.utils import flt

from insights.ml.kenya_tax_intelligence import customs, etims, rules
from insights.ml.kenya_tax_intelligence.common import (
    TaxContext,
    chip,
    days_until,
    doctype_exists,
    gl_net,
    holidays,
    kpi,
    month_key,
    month_starts,
    pct,
    tax_accounts,
    unavailable,
    vat_tax_cond,
)

PAGE_SIZE = 50
BLOCKED_FRAGMENTS = ("entertainment", "hospitality", "gift", "fines", "penalt", "club", "donation")
NEAR_CUTOFF_DAYS = 30
SUPPLY_LABELS = {
    "standard": "Standard-rated {rate}%",
    "zero": "Zero-rated 0%",
    "exempt": "Exempt",
    "out_of_scope": "Out of scope",
}
SUPPLY_NOTES = {
    "standard": "Output VAT charged",
    "zero": "Exports and specified zero-rated supplies",
    "exempt": "No output VAT · input VAT not claimable",
    "out_of_scope": "No VAT row on the invoice",
}


# --------------------------------------------------------------------------- pure helpers
def supply_kind(item_rate: Optional[float], template: Optional[str], invoice_rate: Optional[float]) -> str:
    """VAT treatment of one sales line from its item tax rate, item tax template name and the invoice's VAT rate."""
    t = (template or "").lower()
    rate = item_rate if item_rate is not None else invoice_rate
    if rate and rate > 0:
        return "standard"
    if "exempt" in t:
        return "exempt"
    if any(k in t for k in ("out of scope", "outside scope", "non-vat", "non vat")):
        return "out_of_scope"
    return "out_of_scope" if rate is None else "zero"


def is_blocked(text: Optional[str]) -> bool:
    t = (text or "").lower()
    return any(f in t for f in BLOCKED_FRAGMENTS)


def window_chip(days_left: Optional[int]) -> Dict[str, str]:
    if days_left is None:
        return chip("mut", _("Unknown"))
    if days_left < 0:
        return chip("neg", _("Window closed"))
    tone = "neg" if days_left <= 14 else "warn" if days_left <= 30 else "mut"
    return chip(tone, _("Closes in {0} d").format(days_left))


def _item_rate(raw: Optional[str]) -> Optional[float]:
    """Highest rate in a Sales Invoice Item `item_tax_rate` JSON ({account: rate}); None when unset."""
    # ponytail: takes the max over all accounts in the map (includes non-VAT levies); fine for 0 vs >0 split
    try:
        rates = [flt(v) for v in json.loads(raw).values()] if raw else []
    except (ValueError, AttributeError):
        return None
    return max(rates) if rates else None


# --------------------------------------------------------------------------- data
def _daily(table: str, parent: str, ctx: TaxContext, kind: str, start: date, end: date, sign: str = "") -> Dict[date, float]:
    cond, cparams = vat_tax_cond(ctx, kind, "t")
    rows = frappe.db.sql(
        f"""SELECT p.posting_date, SUM({sign or 't.base_tax_amount_after_discount_amount'})
            FROM `tab{table}` t JOIN `tab{parent}` p ON p.name = t.parent AND t.parenttype = '{parent}'
            WHERE p.docstatus = 1 AND p.company = %(company)s AND p.posting_date BETWEEN %(start)s AND %(end)s AND {cond}
            {"AND COALESCE(t.category, 'Total') <> 'Valuation'" if parent == "Purchase Invoice" else ""}
            GROUP BY p.posting_date""",
        {"company": ctx.company, "start": start, "end": end, **cparams},
    )
    return {r[0]: flt(r[1]) for r in rows}


_PURCHASE_SIGN = "CASE WHEN t.add_deduct_tax = 'Deduct' THEN -t.base_tax_amount_after_discount_amount ELSE t.base_tax_amount_after_discount_amount END"


def build_series(months: List[date], out: Dict[date, float], inp: Dict[date, float]) -> List[Dict[str, Any]]:
    """Monthly output/input/net. A side with no VAT rows at all is None (unknown), not 0; net is None when both are."""
    series = {month_key(m): [0.0, 0.0] for m in months}
    for d, v in out.items():
        series[month_key(d)][0] += v
    for d, v in inp.items():
        series[month_key(d)][1] += v
    o_ok, i_ok = bool(out), bool(inp)
    return [
        {"month": k, "output": round(o, 2) if o_ok else None, "input": round(i, 2) if i_ok else None,
         "net": round(o - i, 2) if o_ok or i_ok else None}
        for k, (o, i) in series.items()
    ]


def _monthly(ctx: TaxContext, last: date) -> Tuple[List[Dict[str, Any]], bool, bool]:
    months = month_starts(last, 12)
    start, end = months[0], rules.month_end(last)
    out = _daily("Sales Taxes and Charges", "Sales Invoice", ctx, "vat_output", start, end)
    inp = _daily("Purchase Taxes and Charges", "Purchase Invoice", ctx, "vat_input", start, end, _PURCHASE_SIGN)
    return build_series(months, out, inp), bool(out), bool(inp)


def _supply_mix(ctx: TaxContext, start: date, end: date) -> List[Dict[str, Any]]:
    cond, cparams = vat_tax_cond(ctx, "vat_output", "t")
    params = {"company": ctx.company, "start": start, "end": end}
    inv_rate = dict(
        frappe.db.sql(
            f"""SELECT t.parent, MAX(t.rate) FROM `tabSales Taxes and Charges` t
                JOIN `tabSales Invoice` si ON si.name = t.parent AND t.parenttype = 'Sales Invoice'
                WHERE si.docstatus = 1 AND si.company = %(company)s AND si.posting_date BETWEEN %(start)s AND %(end)s AND {cond}
                GROUP BY t.parent""",
            {**params, **cparams},
        )
    )
    items = frappe.db.sql(
        """SELECT i.parent, i.base_net_amount AS net, i.item_tax_template, i.item_tax_rate
           FROM `tabSales Invoice Item` i JOIN `tabSales Invoice` si ON si.name = i.parent
           WHERE si.docstatus = 1 AND si.company = %(company)s AND si.posting_date BETWEEN %(start)s AND %(end)s""",
        params,
        as_dict=True,
    )
    totals = {k: 0.0 for k in SUPPLY_LABELS}
    for i in items:
        r = inv_rate.get(i["parent"])
        totals[supply_kind(_item_rate(i["item_tax_rate"]), i["item_tax_template"], None if r is None else flt(r))] += flt(i["net"])
    whole = sum(totals.values())
    return [
        {
            "key": k,
            "label": _(SUPPLY_LABELS[k]).format(rate=f"{rules.VAT_RATE * 100:g}") if k == "standard" else _(SUPPLY_LABELS[k]),
            "taxable_value": round(v, 2),
            "share_pct": pct(v, whole) if whole > 0 else None,
            "note": _(SUPPLY_NOTES[k]),
        }
        for k, v in totals.items()
    ]


def _blocked_vat(ctx: TaxContext, start: date, end: date) -> Dict[str, float]:
    """Purchase Invoice -> net value of lines whose expense account or item name is a blocked category."""
    like = [f"%{f}%" for f in BLOCKED_FRAGMENTS]
    clauses = " OR ".join(["LOWER(COALESCE(pii.expense_account, '')) LIKE %s OR LOWER(COALESCE(pii.item_name, '')) LIKE %s"] * len(like))
    rows = frappe.db.sql(
        f"""SELECT pii.parent, SUM(pii.base_net_amount) FROM `tabPurchase Invoice Item` pii
            JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
            WHERE pi.docstatus = 1 AND pi.is_return = 0 AND pi.company = %s AND pi.posting_date BETWEEN %s AND %s
              AND ({clauses})
            GROUP BY pii.parent""",
        (ctx.company, start, end, *[p for p in like for _x in (0, 1)]),
    )
    return {r[0]: flt(r[1]) for r in rows}


def _pool(ctx: TaxContext) -> List[Dict[str, Any]]:
    """Purchase invoices covering the period and the last 6 months, flagged per risk reason."""
    if "vat_pool" in ctx._cache:
        return ctx._cache["vat_pool"]
    lo = min(ctx.start, rules.add_months(ctx.today, -rules.INPUT_VAT_WINDOW_MONTHS))
    hi = max(ctx.end, ctx.today)
    blocked = _blocked_vat(ctx, lo, hi)
    out = []
    for r in etims.purchase_rows(ctx, lo, hi):
        r = dict(r)
        r["closes"] = rules.input_vat_window_closes(r["invoice_date"])
        r["days_left"] = days_until(r["closes"], ctx.today)
        r["in_period"] = ctx.start <= r["posting_date"] <= ctx.end
        r["no_cu"] = r["covered"] is False and r["vat"] > 0
        r["near_cutoff"] = r["vat"] > 0 and 0 <= r["days_left"] <= NEAR_CUTOFF_DAYS
        r["blocked_vat"] = round(blocked.get(r["name"], 0.0) * r["vat"] / r["net"], 2) if r["name"] in blocked and r["net"] > 0 else 0.0
        out.append(r)
    ctx._cache["vat_pool"] = out
    return out


def _reason_rows(pool: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "no_cu": [r for r in pool if r["in_period"] and r["no_cu"]],
        "near_cutoff": [r for r in pool if r["near_cutoff"]],
        "blocked": [r for r in pool if r["in_period"] and r["blocked_vat"] > 0],
    }



# --------------------------------------------------------------------------- compute
def compute(ctx: TaxContext) -> Dict[str, Any]:
    if not (ctx.company and doctype_exists("Sales Invoice") and doctype_exists("Purchase Invoice")):
        return unavailable(_("Sales and Purchase Invoices are required to compute VAT; install ERPNext"))

    last = min(ctx.end, ctx.today)
    monthly, has_out, has_in = _monthly(ctx, last)
    cur, prev = monthly[-1], monthly[-2]
    m_start, m_end = last.replace(day=1), rules.month_end(last)
    month_name = m_start.strftime("%b")

    pool = _pool(ctx)
    tracked = any(r["covered"] is not None for r in pool)
    reasons = _reason_rows(pool)
    # unique at-risk invoices over the period (no CU no. or blocked): union, VAT counted once per invoice
    at_risk = {r["name"]: r for k in ("no_cu", "blocked") for r in reasons[k]}
    at_risk_vat = sum(max(r["vat"] if r["no_cu"] else 0.0, r["blocked_vat"]) for r in at_risk.values())
    period_input = sum(r["vat"] for r in pool if r["in_period"])
    month_pool = [r for r in pool if m_start <= r["posting_date"] <= m_end]
    month_at_risk = sum(max(r["vat"] if r["no_cu"] else 0.0, r["blocked_vat"]) for r in month_pool)
    claimable = round(cur["input"] - month_at_risk, 2) if cur["input"] is not None else None

    due = rules.monthly_due_dates(m_end, holidays(ctx))["vat"]
    left = days_until(due, ctx.today)
    due_sub = _("VAT3 due {0} · {1} days").format(due.strftime("%a %d %b"), left) if left >= 0 else _("VAT3 due {0} · {1} days ago").format(due.strftime("%a %d %b"), -left)
    mom = pct(cur["output"] - prev["output"], prev["output"]) if cur["output"] is not None and prev["output"] else None
    prev_name = date.fromisoformat(prev["month"] + "-01").strftime("%b")
    std = f"{rules.VAT_RATE * 100:g}"
    out_sub = _("{0:+.1f}% vs {1} · {2}% standard").format(mom, prev_name, std) if mom is not None else _("{0}% standard").format(std)

    wht_vat_accts = [a for a in tax_accounts(ctx, "wht") if "vat" in a.lower()]
    wht_bal = gl_net(ctx, wht_vat_accts, date(1900, 1, 1), ctx.today, credit_positive=False)

    foreign = customs.foreign_service_lines(ctx, m_start, m_end)
    country_ok = customs.country_tracked()
    rc_tracked = country_ok and (has_out or has_in)
    rc_amount = round(sum(flt(r["net"]) for r in foreign if flt(r["vat_charged"]) <= 0) * rules.VAT_RATE, 2) if rc_tracked else None
    rc_note = (
        _("Computed at {0}% of service value from non-resident suppliers where no VAT was charged; output and the matching input are both in this month's VAT3.").format(f"{rules.VAT_RATE * 100:g}")
        if rc_tracked else _("Set Supplier country to detect non-resident suppliers") if not country_ok else _("No VAT tax rows found in the last 12 months")
    )
    supply_mix = _supply_mix(ctx, m_start, m_end)
    if not has_out:
        supply_mix = [{**s, "taxable_value": None, "share_pct": None} for s in supply_mix]

    kpis = [
        kpi("output_vat", _("Output VAT, {0}").format(month_name), cur["output"], "money", out_sub),
        kpi("input_vat_claimable", _("Input VAT claimable"), claimable, "money", _("Month's input VAT less invoices without CU no. or in blocked categories")),
        kpi("net_vat_payable", _("Net VAT payable"), cur["net"], "money", due_sub),
        kpi("input_vat_at_risk", _("Input VAT at risk"), round(at_risk_vat, 2) if has_in and (tracked or any(r["blocked_vat"] for r in pool)) else None, "money",
            _("{0}% of input VAT in the period").format(pct(at_risk_vat, period_input)) if period_input > 0 and tracked else _("No eTIMS data: only blocked categories can be assessed"),
            "bad" if (at_risk_vat or 0) > 0 else "neutral"),
        kpi("wht_vat_credits_unapplied", _("WHT-VAT credits unapplied"), max(wht_bal, 0.0) if wht_bal is not None else None, "money",
            _("Debit balance on the WHT-VAT account") if wht_bal is not None else _("No 2% WHT-VAT account found"), "warn" if (wht_bal or 0) > 0 else "neutral"),
        kpi("vat_on_imported_services", _("VAT on imported services"), rc_amount, "money", _("Self-accounted at {0}% · reverse charge").format(f"{rules.VAT_RATE * 100:g}") if rc_tracked else rc_note),
    ]
    kpis[0]["drill"] = {"metric": "vat_month", "filters": {"month": cur["month"], "side": "output"}}
    kpis[1]["drill"] = {"metric": "vat_month", "filters": {"month": cur["month"], "side": "input"}}
    kpis[3]["drill"] = {"metric": "vat_input_risk", "filters": {"reason": "all"}}
    kpis[5]["drill"] = {"metric": "vat_reverse_charge", "filters": {}}

    def row(reason, key, action, items):
        return {"reason": reason, "invoices": len(items) if items is not None else None,
                "input_vat": round(sum(i["vat"] if key != "blocked" else i["blocked_vat"] for i in items), 2) if items is not None else None,
                "action_label": action, "drill": {"metric": "vat_input_risk", "filters": {"reason": key}}}

    input_risk = [
        row(_("No eTIMS CU number"), "no_cu", _("Review"), reasons["no_cu"] if tracked and has_in else None),
        row(_("Within 30 days of the 6-month cut-off"), "near_cutoff", _("Claim now"), reasons["near_cutoff"] if has_in else None),
        {"reason": _("Used for exempt supplies (apportion)"), "invoices": None, "input_vat": None, "action_label": _("Open"), "drill": None},
        row(_("Blocked category (e.g. entertainment)"), "blocked", _("Open"), reasons["blocked"] if has_in else None),
    ]

    # suppliers closest to the cut-off: invoices still inside their window that are at risk (no CU no. or blocked)
    by_sup: Dict[str, Dict[str, Any]] = {}
    for r in pool if has_in else []:
        if (r["no_cu"] or r["blocked_vat"] > 0) and r["days_left"] >= 0:
            s = by_sup.setdefault(r["supplier"], {"supplier": r["supplier_name"] or r["supplier"], "key": r["supplier"], "invoices": 0, "input_vat_at_risk": 0.0, "oldest_date": r["invoice_date"]})
            s["invoices"] += 1
            s["input_vat_at_risk"] += max(r["vat"] if r["no_cu"] else 0.0, r["blocked_vat"])
            s["oldest_date"] = min(s["oldest_date"], r["invoice_date"])
    suppliers = []
    for s in sorted(by_sup.values(), key=lambda s: s["oldest_date"])[:10]:
        closes = rules.input_vat_window_closes(s["oldest_date"])
        dl = days_until(closes, ctx.today)
        suppliers.append({"supplier": s["supplier"], "invoices": s["invoices"], "input_vat_at_risk": round(s["input_vat_at_risk"], 2),
                          "oldest_date": s["oldest_date"].isoformat(), "window_closes": closes.isoformat(), "days_left": dl, "chip": window_chip(dl),
                          "drill": {"metric": "vat_supplier_risk", "filters": {"supplier": s["key"]}}})

    return {
        "available": True,
        "kpis": kpis,
        "monthly": monthly,
        "supply_mix": supply_mix,
        "input_risk": input_risk,
        "suppliers_at_risk": suppliers,
        "reverse_charge": {"amount": rc_amount, "note": rc_note},
    }


# --------------------------------------------------------------------------- drill-down
_INVOICE_COLS = [
    {"label": "Purchase Invoice", "fieldname": "name", "fieldtype": "Link", "options": "Purchase Invoice"},
    {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier"},
    {"label": "Invoice date", "fieldname": "invoice_date", "fieldtype": "Date"},
    {"label": "Net", "fieldname": "net", "fieldtype": "Currency"},
    {"label": "Input VAT", "fieldname": "vat", "fieldtype": "Currency"},
    {"label": "Window closes", "fieldname": "closes", "fieldtype": "Date"},
]


def _page(rows: List[Dict[str, Any]], columns: List[Dict[str, Any]], filters: Dict[str, Any]) -> Dict[str, Any]:
    page = max(int((filters or {}).get("page") or 1), 1)
    return {"columns": columns, "rows": rows[(page - 1) * PAGE_SIZE : page * PAGE_SIZE], "total": len(rows)}


def _inv(r: Dict[str, Any], vat: Optional[float] = None) -> Dict[str, Any]:
    return {"name": r["name"], "supplier": r["supplier"], "invoice_date": r["invoice_date"], "net": r["net"],
            "vat": r["vat"] if vat is None else vat, "closes": rules.input_vat_window_closes(r["invoice_date"])}


def drilldown(ctx: TaxContext, metric: str, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if metric not in ("vat_month", "vat_input_risk", "vat_supplier_risk", "vat_reverse_charge"):
        return None
    filters = filters or {}
    if not (ctx.company and doctype_exists("Sales Invoice") and doctype_exists("Purchase Invoice")):
        return {"columns": [], "rows": [], "total": 0}

    if metric == "vat_reverse_charge":
        frappe.has_permission("Purchase Invoice", throw=True)
        last = min(ctx.end, ctx.today)
        cols = [
            {"label": "Purchase Invoice", "fieldname": "invoice", "fieldtype": "Link", "options": "Purchase Invoice"},
            {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier"},
            {"label": "Service", "fieldname": "service", "fieldtype": "Data"},
            {"label": "Value", "fieldname": "net", "fieldtype": "Currency"},
            {"label": "Reverse-charge VAT", "fieldname": "vat", "fieldtype": "Currency"},
        ]
        rows = [{"invoice": r["invoice"], "supplier": r["supplier"], "service": r["service"], "net": flt(r["net"]), "vat": round(flt(r["net"]) * rules.VAT_RATE, 2)}
                for r in customs.foreign_service_lines(ctx, last.replace(day=1), rules.month_end(last)) if flt(r["vat_charged"]) <= 0]
        return _page(rows, cols, filters)

    if metric == "vat_month":
        month, side = str(filters.get("month") or ""), filters.get("side")
        try:
            start = date.fromisoformat(month + "-01")
        except ValueError:
            return {"columns": [], "rows": [], "total": 0}
        end = rules.month_end(start)
        if side == "output":
            frappe.has_permission("Sales Invoice", throw=True)
            cond, cparams = vat_tax_cond(ctx, "vat_output", "t")
            rows = frappe.db.sql(
                f"""SELECT si.name, si.customer, si.posting_date, si.base_net_total AS net, SUM(t.base_tax_amount_after_discount_amount) AS vat
                    FROM `tabSales Taxes and Charges` t JOIN `tabSales Invoice` si ON si.name = t.parent AND t.parenttype = 'Sales Invoice'
                    WHERE si.docstatus = 1 AND si.company = %(company)s AND si.posting_date BETWEEN %(start)s AND %(end)s AND {cond}
                    GROUP BY si.name, si.customer, si.posting_date, si.base_net_total ORDER BY vat DESC""",
                {"company": ctx.company, "start": start, "end": end, **cparams},
                as_dict=True,
            )
            cols = [
                {"label": "Sales Invoice", "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice"},
                {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
                {"label": "Date", "fieldname": "posting_date", "fieldtype": "Date"},
                {"label": "Net", "fieldname": "net", "fieldtype": "Currency"},
                {"label": "Output VAT", "fieldname": "vat", "fieldtype": "Currency"},
            ]
            return _page(rows, cols, filters)
        frappe.has_permission("Purchase Invoice", throw=True)
        rows = [_inv(r) for r in sorted(etims.purchase_rows(ctx, start, end), key=lambda r: -r["vat"]) if r["vat"]]
        return _page(rows, _INVOICE_COLS, filters)

    frappe.has_permission("Purchase Invoice", throw=True)
    pool = _pool(ctx)
    if metric == "vat_supplier_risk":
        sup = filters.get("supplier")
        sel = [r for r in pool if r["supplier"] == sup and (r["no_cu"] or r["blocked_vat"] > 0) and r["days_left"] >= 0] if isinstance(sup, str) else []
        return _page([_inv(r, max(r["vat"] if r["no_cu"] else 0.0, r["blocked_vat"])) for r in sorted(sel, key=lambda r: r["invoice_date"])], _INVOICE_COLS, filters)

    reason = filters.get("reason")
    reasons = _reason_rows(pool)
    if reason in reasons:
        sel = reasons[reason]
    else:  # "all": every invoice at risk for any reason
        sel = list({r["name"]: r for k in ("no_cu", "near_cutoff", "blocked") for r in reasons[k]}.values())
    return _page([_inv(r, r["blocked_vat"] if reason == "blocked" else None) for r in sorted(sel, key=lambda r: -r["vat"])], _INVOICE_COLS, filters)
