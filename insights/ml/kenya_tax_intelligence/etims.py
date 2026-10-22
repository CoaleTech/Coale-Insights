# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""eTIMS tab: transmission and CU-number coverage from the Coale `kenya_etims_compliance` app.

Real data used (verified against the app source):
  * Sales Invoice: `custom_current_receipt_number` (CU no.) / `custom_update_sales_to_etims`
    ("Registered In TIMs"). Transmitted = either is set.
  * Purchase Invoice: `custom_kra_match_status` (Pending|Matched|Mismatched|Not in KRA, set by the
    KRA purchase-register reconciliation), `custom_purchase_is_from_etims`, `custom_etims_purchase_invoice`.
    "Has a CU number" = Matched, Mismatched, from eTIMS, or linked to an eTIMS Purchase Invoice.
    Everything else (Not in KRA, Pending, blank) is "without a confirmed eTIMS invoice".
  * eTIMS Invoice Queue: status Queued|Processing|Sent|Failed, `last_error`, `queued_at`.
    Failed rows whose error is connectivity/device related are NOT counted as KRA rejections.

Shared with vat.py: `purchase_rows(ctx, start, end)` (Purchase Invoices + input VAT + CU flag).

Drill-down metrics: `etims_exceptions` (filters.kind = all|no_cu|not_transmitted|awaiting|rejected|credit_note).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import frappe
from frappe import _
from frappe.utils import flt

from insights.ml.kenya_tax_intelligence import rules
from insights.ml.kenya_tax_intelligence.common import (
    TaxContext,
    as_date,
    chip,
    doctype_exists,
    has_field,
    kpi,
    pct,
    unavailable,
    vat_tax_cond,
)

QUEUE = "eTIMS Invoice Queue"
PAGE_SIZE = 50
NOT_KRA_REJECTION = ("Transmission timeout", "Device not initialised")
MATCHED = ("Matched", "Mismatched")


# --------------------------------------------------------------------------- pure helpers
def classify_queue_error(text: Optional[str]) -> str:
    """Bucket a queue `last_error` into a short reason label."""
    t = (text or "").lower()
    if not t.strip():
        return "No error recorded"
    if any(k in t for k in ("timeout", "timed out", "connection", "pre-flight", "unreachable", "resolution")):
        return "Transmission timeout"
    if "no active tis device" in t or "authentication" in t or "cmckey" in t:
        return "Device not initialised"
    if re.search(r"\b(pin|tin|custtin)\b", t):
        return "Invalid PIN"
    if "item" in t:
        return "Item code"
    if "tax" in t:
        return "Tax code"
    return "Other"


def week_label(d: date) -> str:
    y, w, _d = d.isocalendar()
    return f"{y}-W{w:02d}"


def _covered(row: Dict[str, Any], tracked: bool) -> Optional[bool]:
    if not tracked:
        return None
    return row.get("status") in MATCHED or bool(row.get("from_etims")) or bool(row.get("etims_pi"))


# --------------------------------------------------------------------------- shared data
def purchase_rows(ctx: TaxContext, start: date, end: date) -> List[Dict[str, Any]]:
    """Submitted, non-return Purchase Invoices in the window with `vat` (input VAT, base currency),
    `invoice_date` (bill date or posting date) and `covered` (True/False, None when the site has
    no eTIMS fields at all). Cached on the context."""
    key = ("pi_rows", start, end)
    if key in ctx._cache:
        return ctx._cache[key]
    if not (ctx.company and doctype_exists("Purchase Invoice")):
        return []
    status = "pi.custom_kra_match_status" if has_field("Purchase Invoice", "custom_kra_match_status") else "NULL"
    from_etims = "pi.custom_purchase_is_from_etims" if has_field("Purchase Invoice", "custom_purchase_is_from_etims") else "NULL"
    etims_pi = "pi.custom_etims_purchase_invoice" if has_field("Purchase Invoice", "custom_etims_purchase_invoice") else "NULL"
    tracked = any(c != "NULL" for c in (status, from_etims, etims_pi))
    params: Dict[str, Any] = {"company": ctx.company, "start": start, "end": end}
    rows = frappe.db.sql(
        f"""SELECT pi.name, pi.supplier, pi.supplier_name, pi.posting_date,
                   COALESCE(pi.bill_date, pi.posting_date) AS invoice_date, pi.base_net_total AS net,
                   {status} AS status, {from_etims} AS from_etims, {etims_pi} AS etims_pi
            FROM `tabPurchase Invoice` pi
            WHERE pi.docstatus = 1 AND pi.is_return = 0 AND pi.company = %(company)s
              AND pi.posting_date BETWEEN %(start)s AND %(end)s""",
        params,
        as_dict=True,
    )
    cond, cparams = vat_tax_cond(ctx, "vat_input", "t")
    vat = dict(
        frappe.db.sql(
            f"""SELECT t.parent,
                       SUM(CASE WHEN t.add_deduct_tax = 'Deduct' THEN -t.base_tax_amount_after_discount_amount
                                ELSE t.base_tax_amount_after_discount_amount END)
                FROM `tabPurchase Taxes and Charges` t
                JOIN `tabPurchase Invoice` pi ON pi.name = t.parent AND t.parenttype = 'Purchase Invoice'
                WHERE pi.docstatus = 1 AND pi.is_return = 0 AND pi.company = %(company)s
                  AND pi.posting_date BETWEEN %(start)s AND %(end)s
                  AND COALESCE(t.category, 'Total') <> 'Valuation' AND {cond}
                GROUP BY t.parent""",
            {**params, **cparams},
        )
    )
    for r in rows:
        r["net"] = flt(r["net"])
        r["vat"] = flt(vat.get(r["name"]))
        r["invoice_date"] = as_date(r["invoice_date"])
        r["posting_date"] = as_date(r["posting_date"])
        r["covered"] = _covered(r, tracked)
    ctx._cache[key] = rows
    return rows


def _sales_stats(ctx: TaxContext):
    """(total, transmitted) submitted Sales Invoices in the period; transmitted None when no eTIMS field exists."""
    receipt = has_field("Sales Invoice", "custom_current_receipt_number")
    flag = has_field("Sales Invoice", "custom_update_sales_to_etims")
    expr = " OR ".join(
        (["COALESCE(si.custom_current_receipt_number, '') <> ''"] if receipt else [])
        + (["si.custom_update_sales_to_etims = 1"] if flag else [])
    )
    sent = f"SUM(CASE WHEN {expr} THEN 1 ELSE 0 END)" if expr else "NULL"
    row = frappe.db.sql(
        f"""SELECT COUNT(*), {sent} FROM `tabSales Invoice` si
            WHERE si.docstatus = 1 AND si.company = %s AND si.posting_date BETWEEN %s AND %s""",
        (ctx.company, ctx.start, ctx.end),
    )[0]
    return int(row[0] or 0), (None if row[1] is None else int(row[1]))


def _untransmitted_sales(ctx: TaxContext, limit: int = 1000) -> List[Dict[str, Any]]:
    # ponytail: capped at 1000 largest invoices; the exact count comes from _sales_stats
    receipt = has_field("Sales Invoice", "custom_current_receipt_number")
    flag = has_field("Sales Invoice", "custom_update_sales_to_etims")
    conds = (["COALESCE(si.custom_current_receipt_number, '') = ''"] if receipt else []) + (
        ["COALESCE(si.custom_update_sales_to_etims, 0) = 0"] if flag else []
    )
    if not conds:
        return []
    rows = frappe.db.sql(
        f"""SELECT si.name, si.customer_name, si.posting_date, si.base_grand_total AS amount
            FROM `tabSales Invoice` si
            WHERE si.docstatus = 1 AND si.company = %s AND si.posting_date BETWEEN %s AND %s
              AND {' AND '.join(conds)}
            ORDER BY si.base_grand_total DESC LIMIT {int(limit)}""",
        (ctx.company, ctx.start, ctx.end),
        as_dict=True,
    )
    return rows


def _queue_rows(ctx: TaxContext) -> List[Dict[str, Any]]:
    """Open (Queued/Processing/Failed) queue entries of this company's Sales/Purchase Invoices, newest per document."""
    rows = frappe.db.sql(
        """SELECT q.name, q.reference_doctype, q.reference_name, q.status, q.retry_count, q.last_error, q.queued_at,
                  COALESCE(si.customer_name, pi.supplier_name) AS counterparty,
                  COALESCE(si.base_grand_total, pi.base_grand_total) AS amount
           FROM `tabeTIMS Invoice Queue` q
           LEFT JOIN `tabSales Invoice` si ON q.reference_doctype = 'Sales Invoice' AND si.name = q.reference_name
           LEFT JOIN `tabPurchase Invoice` pi ON q.reference_doctype = 'Purchase Invoice' AND pi.name = q.reference_name
           WHERE q.status IN ('Queued', 'Processing', 'Failed')
             AND q.reference_doctype IN ('Sales Invoice', 'Purchase Invoice')
             AND COALESCE(si.company, pi.company) = %s
           ORDER BY q.name DESC""",
        (ctx.company,),
        as_dict=True,
    )
    seen, out = set(), []
    for r in rows:
        k = (r["reference_doctype"], r["reference_name"])
        if k not in seen:
            seen.add(k)
            r["reason"] = classify_queue_error(r["last_error"]) if r["status"] == "Failed" or r["last_error"] else None
            out.append(r)
    return out


def _credit_notes_past_window(ctx: TaxContext) -> List[Dict[str, Any]]:
    if not has_field("Sales Invoice", "return_against"):
        return []
    rows = frappe.db.sql(
        """SELECT si.name, si.customer_name, si.posting_date, si.base_grand_total AS amount,
                  si.base_total_taxes_and_charges AS vat, o.posting_date AS orig_date
           FROM `tabSales Invoice` si JOIN `tabSales Invoice` o ON o.name = si.return_against
           WHERE si.docstatus = 1 AND si.is_return = 1 AND si.company = %s AND si.posting_date BETWEEN %s AND %s""",
        (ctx.company, ctx.start, ctx.end),
        as_dict=True,
    )
    return [r for r in rows if rules.add_months(as_date(r["orig_date"]), rules.INPUT_VAT_WINDOW_MONTHS) < as_date(r["posting_date"])]


# --------------------------------------------------------------------------- exceptions
def _exceptions(ctx: TaxContext, purchases: List[Dict[str, Any]], queue: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """All exception rows (unsorted-capped), keyed so a queue entry overrides a coverage/untransmitted row."""
    out: Dict[tuple, Dict[str, Any]] = {}
    for r in purchases:
        if r["covered"] is False:
            exp = rules.etims_exposure(r["net"], r["vat"])["total"]
            not_in_kra = r["status"] == "Not in KRA"
            out[("Purchase Invoice", r["name"])] = {
                "document": r["name"], "doctype": "Purchase Invoice", "counterparty": r["supplier_name"] or r["supplier"],
                "amount": r["net"], "issue_chip": chip("neg", _("No CU number")) if not_in_kra else chip("warn", _("Not matched to KRA")),
                "age_days": (ctx.today - r["posting_date"]).days, "exposure": exp, "action_label": _("Request invoice"), "kind": "no_cu",
            }
    for r in _untransmitted_sales(ctx):
        out[("Sales Invoice", r["name"])] = {
            "document": r["name"], "doctype": "Sales Invoice", "counterparty": r["customer_name"], "amount": flt(r["amount"]),
            "issue_chip": chip("warn", _("Not transmitted")), "age_days": (ctx.today - as_date(r["posting_date"])).days,
            "exposure": None, "action_label": _("Retry"), "kind": "not_transmitted",
        }
    for r in _credit_notes_past_window(ctx):
        out[("Sales Invoice", r["name"])] = {
            "document": r["name"], "doctype": "Sales Invoice", "counterparty": r["customer_name"], "amount": abs(flt(r["amount"])),
            "issue_chip": chip("neg", _("Credit note > 6 months")), "age_days": (ctx.today - as_date(r["posting_date"])).days,
            "exposure": abs(flt(r["vat"])), "action_label": _("Review"), "kind": "credit_note",
        }
    for q in queue:
        key = (q["reference_doctype"], q["reference_name"])
        base = out.get(key, {})
        rejected = q["status"] == "Failed" and q["reason"] not in NOT_KRA_REJECTION
        out[key] = {
            "document": q["reference_name"], "doctype": q["reference_doctype"], "counterparty": q["counterparty"],
            "amount": flt(q["amount"]),
            "issue_chip": chip("neg", _("Rejected: {0}").format(q["reason"])) if rejected else chip("warn", _("Awaiting transmission")),
            "age_days": (ctx.today - as_date(q["queued_at"])).days if q["queued_at"] else None,
            "exposure": base.get("exposure"), "action_label": _("Fix & resend") if rejected else _("Retry"),
            "kind": "rejected" if rejected else "awaiting",
        }
    for row in out.values():
        row["drill"] = {"metric": "etims_exceptions", "filters": {"kind": row["kind"]}}
    return sorted(out.values(), key=lambda x: (x["exposure"] is None, -(x["exposure"] or 0), -(x["age_days"] or 0)))


# --------------------------------------------------------------------------- compute
def compute(ctx: TaxContext) -> Dict[str, Any]:
    if not doctype_exists(QUEUE):
        return unavailable(_("Install the kenya_etims_compliance app to track eTIMS"))

    sales_total, sales_sent = _sales_stats(ctx)
    purchases = purchase_rows(ctx, ctx.start, ctx.end)
    known = [r for r in purchases if r["covered"] is not None]
    without = [r for r in known if r["covered"] is False]
    queue = _queue_rows(ctx)
    cn = _credit_notes_past_window(ctx)

    awaiting = [q for q in queue if q["status"] in ("Queued", "Processing") or q["reason"] in NOT_KRA_REJECTION]
    rejected = [q for q in queue if q["status"] == "Failed" and q["reason"] not in NOT_KRA_REJECTION]
    oldest = min((as_date(q["queued_at"]) for q in awaiting if q["queued_at"]), default=None)
    rej_reasons: Dict[str, int] = {}
    for q in rejected:
        rej_reasons[q["reason"]] = rej_reasons.get(q["reason"], 0) + 1
    top = " · ".join(f"{k} {v}" for k, v in sorted(rej_reasons.items(), key=lambda kv: -kv[1])[:3])

    sales_pct = pct(sales_sent, sales_total) if sales_sent is not None else None
    cov_pct = pct(len(known) - len(without), len(known))
    kpis = [
        kpi("sales_transmitted_pct", _("Sales invoices transmitted"), sales_pct, "pct",
            _("{0} of {1} · target 100%").format(sales_sent, sales_total) if sales_pct is not None else _("No eTIMS fields on Sales Invoice"),
            "good" if (sales_pct or 0) >= 99.5 else "bad" if sales_pct is not None and sales_pct < 95 else "warn" if sales_pct is not None else "neutral"),
        kpi("purchase_cu_coverage_pct", _("Purchase invoices with CU no."), cov_pct, "pct",
            _("{0} of {1} without eTIMS invoice").format(len(without), len(known)) if cov_pct is not None else _("No purchase invoices in the period"),
            "good" if (cov_pct or 0) >= 99.5 else "bad" if cov_pct is not None and cov_pct < 90 else "warn" if cov_pct is not None else "neutral"),
        kpi("awaiting_transmission", _("Awaiting transmission"), len(awaiting), "count",
            _("Oldest {0} days · retry queue").format((ctx.today - oldest).days) if oldest else _("Queue is clear"),
            "warn" if awaiting else "good"),
        kpi("rejected_by_kra", _("Rejected by KRA"), len(rejected), "count", top or _("No rejected invoices"), "bad" if rejected else "good"),
        kpi("buyer_initiated", _("Buyer-initiated invoices"), None, "count", _("Not tracked"), "neutral"),
        kpi("credit_notes_past_6m", _("Credit notes past 6 months"), len(cn), "count", _("Cannot reduce VAT after the window"), "bad" if cn else "good"),
    ]

    # weekly purchase CU coverage, last 12 ISO weeks (Monday-anchored)
    this_monday = ctx.today - timedelta(days=ctx.today.weekday())
    mondays = [this_monday - timedelta(weeks=i) for i in range(11, -1, -1)]
    buckets = {week_label(m): [0, 0] for m in mondays}
    for r in purchase_rows(ctx, mondays[0], ctx.today):
        if r["covered"] is None:
            continue
        b = buckets.get(week_label(r["posting_date"]))
        if b is not None:
            b[1] += 1
            b[0] += 1 if r["covered"] else 0
    trend = [{"week": w, "pct": pct(c, n)} for w, (c, n) in buckets.items()]

    spend = sum(r["net"] for r in without)
    vat_lost = sum(r["vat"] for r in without)
    exp = rules.etims_exposure(spend, vat_lost)
    exposure = {
        "spend_without_invoice": round(spend, 2),
        "income_tax_disallowance": exp["income_tax_disallowance"],
        "input_vat_lost": exp["input_vat_lost"],
        "cit_rate": rules.CIT_RATE,
        "total": exp["total"],
    } if known else {"spend_without_invoice": None, "income_tax_disallowance": None, "input_vat_lost": None, "cit_rate": rules.CIT_RATE, "total": None}

    exceptions = _exceptions(ctx, purchases, queue)
    # failure reasons: missing CU numbers plus open queue errors by bucket
    reasons: Dict[str, int] = {}
    if without:
        reasons[_("Missing CU number")] = len(without)
    for q in queue:
        if q["reason"]:
            reasons[q["reason"]] = reasons.get(q["reason"], 0) + 1
    return {
        "available": True,
        "kpis": kpis,
        "coverage_trend": trend,
        "exposure": exposure,
        "exceptions": [{k: v for k, v in e.items() if k != "kind"} for e in exceptions[:25]],
        "exception_total": len(exceptions),
        "failure_reasons": [{"label": k, "count": v} for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])],
        "by_channel": [],  # the queue records no OSCU/VSCU/web channel
        "penalty_reference": rules.PENALTY_REFERENCE,
    }


# --------------------------------------------------------------------------- drill-down
_COLUMNS = [
    {"label": "Document", "fieldname": "document", "fieldtype": "Data"},
    {"label": "Type", "fieldname": "doctype", "fieldtype": "Data"},
    {"label": "Counterparty", "fieldname": "counterparty", "fieldtype": "Data"},
    {"label": "Amount", "fieldname": "amount", "fieldtype": "Currency"},
    {"label": "Issue", "fieldname": "issue", "fieldtype": "Data"},
    {"label": "Age (days)", "fieldname": "age_days", "fieldtype": "Int"},
    {"label": "Exposure", "fieldname": "exposure", "fieldtype": "Currency"},
]


def drilldown(ctx: TaxContext, metric: str, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if metric != "etims_exceptions":
        return None
    if not doctype_exists(QUEUE):
        return {"columns": _COLUMNS, "rows": [], "total": 0}
    frappe.has_permission("Sales Invoice", throw=True)
    frappe.has_permission("Purchase Invoice", throw=True)
    kind = (filters or {}).get("kind") or "all"
    page = max(int((filters or {}).get("page") or 1), 1)
    rows = _exceptions(ctx, purchase_rows(ctx, ctx.start, ctx.end), _queue_rows(ctx))
    if kind != "all":
        rows = [r for r in rows if r["kind"] == kind]
    page_rows = rows[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
    return {
        "columns": _COLUMNS,
        "rows": [{**{k: r[k] for k in ("document", "doctype", "counterparty", "amount", "age_days", "exposure")}, "issue": r["issue_chip"]["label"]} for r in page_rows],
        "total": len(rows),
    }
