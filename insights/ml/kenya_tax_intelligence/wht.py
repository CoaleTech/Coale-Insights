# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Withholding tab: tax withheld, remittance timing and rate checks on supplier payments.

Heuristics (ERPNext has no Kenya WHT register; every one of these is a ceiling):
- WHT accounts = Liability accounts whose name matches `rules.ACCOUNT_PATTERNS["wht"]`.
  Withheld = credits on them (Purchase Invoice / Payment Entry / Journal Entry, net of invoice returns).
  Remitted = Payment/Journal Entry debits on them. Remittances are pooled against the oldest
  withholdings first; an unremitted amount is "late" once `rules.wht_due_date(deducted_on)` has passed.
  The deduction date stands in for the payment date, and only holidays from today on are known.
- Payment type comes from `rules.classify_wht_text` on the invoice's expense accounts / item names /
  descriptions (a Payment Entry takes the type of the first invoice it settles).
- Residency: Supplier `country` other than Kenya = non-resident; a blank country is treated as resident.
- Rate check: applied rate = WHT credited against the invoice (directly or via Payment Entry
  deductions, pro rata to allocation) / net amount of the invoice lines of its dominant type, against
  `rules.wht_rate`. No de-minimis thresholds and no exemption certificates are modelled.
- Certificates KPI exists only when Purchase Invoice has a custom field naming a WHT certificate.

Drill metrics (filters: `page`): wht_withheld, wht_unremitted, wht_rate_exceptions, wht_no_wht, wht_nonresident.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import frappe
from frappe import _

from insights.ml.kenya_tax_intelligence import rules
from insights.ml.kenya_tax_intelligence.common import (
    TaxContext,
    chip,
    doctype_exists,
    drill_page,
    holidays,
    kpi,
    money_short,
    pct,
    tax_accounts,
    unavailable,
)

TOL = 1.0
RATE_TOL = 0.005  # half a percentage point
FA2026_START = date(2026, 7, 1)  # interchange / merchant fees to non-residents become management fees
LIST_CAP = 25
OTHER = "other"
_RESIDENT_COUNTRY = "kenya"


# --------------------------------------------------------------------------- pure logic
def fifo_outstanding(withheld: List[Tuple[date, str, float]], remitted: float) -> List[Tuple[date, str, float]]:
    """Pool `remitted` against the oldest withholdings; return what is left as (date, ref, outstanding)."""
    left, out = remitted, []
    for d, ref, amt in sorted(withheld, key=lambda w: w[0]):
        used = min(left, amt)
        left -= used
        if amt - used > TOL:
            out.append((d, ref, round(amt - used, 2)))
    return out


def rate_check(kind: str, non_resident: bool, gross: float, withheld: float) -> Optional[Tuple[float, float]]:
    """(expected %, applied %) when the applied rate is off the statutory one, else None."""
    expected = rules.wht_rate(kind, not non_resident)
    if expected is None or not gross or gross <= 0:
        return None
    applied = withheld / gross
    if abs(applied - expected) <= RATE_TOL:
        return None
    return round(expected * 100, 2), round(applied * 100, 2)


def is_non_resident_country(country: Optional[str]) -> bool:
    c = (country or "").strip().lower()
    return bool(c) and c != _RESIDENT_COUNTRY


def invoice_kind(items: List[Dict[str, Any]]) -> Optional[Tuple[str, float]]:
    """(dominant WHT kind, net amount of its lines) over invoice items, None if no line looks like a WHT payment."""
    by: Dict[str, float] = {}
    for it in items:
        k = rules.classify_wht_text(f"{it.get('expense_account') or ''} {it.get('item_name') or ''} {(it.get('description') or '')[:200]}")
        if k:
            by[k] = by.get(k, 0.0) + float(it.get("base_net_amount") or 0)
    if not by:
        return None
    k = max(by, key=by.get)
    return k, by[k]


# --------------------------------------------------------------------------- data
def _build(ctx: TaxContext, accounts: List[str]) -> Dict[str, Any]:
    start, end = ctx.start, min(ctx.end, ctx.today)
    gl = frappe.db.sql(
        """SELECT posting_date, voucher_type AS vt, voucher_no AS vn, account, debit, credit, party FROM `tabGL Entry`
           WHERE company = %s AND is_cancelled = 0 AND account IN %s AND posting_date BETWEEN %s AND %s
           ORDER BY posting_date, creation""",
        (ctx.company, tuple(accounts), start, end),
        as_dict=True,
    )
    withheld: Dict[Tuple[str, str], Dict[str, Any]] = {}
    remitted = 0.0
    for g in gl:
        paid_out = g["vt"] in ("Payment Entry", "Journal Entry")
        if paid_out:
            remitted += float(g["debit"] or 0)
        amt = float(g["credit"] or 0) - (0.0 if paid_out else float(g["debit"] or 0))
        if amt > 0:
            w = withheld.setdefault((g["vt"], g["vn"]), {"vt": g["vt"], "vn": g["vn"], "date": g["posting_date"], "amount": 0.0, "party": g["party"], "account": g["account"]})
            w["amount"] += amt
    pe_names = sorted(vn for vt, vn in withheld if vt == "Payment Entry")
    refs = frappe.get_all("Payment Entry Reference", filters={"parent": ["in", pe_names], "reference_doctype": "Purchase Invoice"}, fields=["parent", "reference_name", "allocated_amount"]) if pe_names else []
    window_pis = frappe.get_all("Purchase Invoice", filters={"company": ctx.company, "docstatus": 1, "is_return": 0, "posting_date": ["between", [start, end]]}, pluck="name")
    pi_names = sorted({*window_pis, *(vn for vt, vn in withheld if vt == "Purchase Invoice"), *(r["reference_name"] for r in refs)})
    pis = {p["name"]: p for p in frappe.get_all("Purchase Invoice", filters={"name": ["in", pi_names]}, fields=["name", "supplier", "supplier_name", "posting_date"])} if pi_names else {}
    items: Dict[str, List[Dict[str, Any]]] = {}
    if pi_names:
        for it in frappe.get_all("Purchase Invoice Item", filters={"parent": ["in", pi_names]}, fields=["parent", "item_name", "description", "expense_account", "base_net_amount"]):
            items.setdefault(it["parent"], []).append(it)
    pes = {p["name"]: p for p in frappe.get_all("Payment Entry", filters={"name": ["in", pe_names]}, fields=["name", "party", "party_name"])} if pe_names else {}
    suppliers = {s["name"]: s["country"] for s in frappe.get_all("Supplier", fields=["name", "country"])}
    pi_kind = {n: invoice_kind(items.get(n, [])) for n in pi_names}

    alloc: Dict[str, float] = {}
    for r in refs:
        alloc[r["parent"]] = alloc.get(r["parent"], 0.0) + float(r["allocated_amount"] or 0)
    wh_pi: Dict[str, float] = {}  # WHT credited against each invoice
    first_ref: Dict[str, str] = {}
    for r in refs:
        first_ref.setdefault(r["parent"], r["reference_name"])
        if alloc[r["parent"]]:
            wh_pi[r["reference_name"]] = wh_pi.get(r["reference_name"], 0.0) + withheld[("Payment Entry", r["parent"])]["amount"] * float(r["allocated_amount"] or 0) / alloc[r["parent"]]
    for (vt, vn), w in withheld.items():
        if vt == "Purchase Invoice":
            wh_pi[vn] = wh_pi.get(vn, 0.0) + w["amount"]

    rows = []  # one per withholding voucher
    for (vt, vn), w in withheld.items():
        if vt == "Purchase Invoice":
            party, party_name = pis.get(vn, {}).get("supplier"), pis.get(vn, {}).get("supplier_name")
            src_pi = vn
        elif vt == "Payment Entry":
            party, party_name = pes.get(vn, {}).get("party"), pes.get(vn, {}).get("party_name")
            src_pi = first_ref.get(vn)
        else:
            party = party_name = w["party"]
            src_pi = None
        kind = (pi_kind.get(src_pi) or (None,))[0] or rules.classify_wht_text(w["account"]) or OTHER
        rows.append({**w, "payee": party_name or party or "-", "kind": kind, "non_resident": is_non_resident_country(suppliers.get(party))})

    exceptions = []
    for n in window_pis:
        k = pi_kind.get(n)
        if not k:
            continue
        sup = pis.get(n, {}).get("supplier")
        nr = is_non_resident_country(suppliers.get(sup))
        applied_w = wh_pi.get(n, 0.0)
        bad = rate_check(k[0], nr, k[1], applied_w)
        if bad:
            exceptions.append({
                "payment": n, "payee": pis[n].get("supplier_name") or sup, "kind": k[0], "gross": round(k[1], 2),
                "expected_rate": bad[0], "applied_rate": bad[1], "non_resident": nr,
                "chip": chip("neg", f"{bad[1]:g}%") if bad[1] == 0 else chip("warn", f"{bad[1]:g}%"),
                "drill": {"metric": "wht_rate_exceptions", "filters": {"payment": n}},
            })
    exceptions.sort(key=lambda e: -e["gross"])

    # card / merchant fees to non-residents since FA 2026
    card = None
    if window_pis:
        card = 0.0
        for n in window_pis:
            k = pi_kind.get(n)
            if k and k[0] == "card_merchant_fee" and is_non_resident_country(suppliers.get(pis.get(n, {}).get("supplier"))):
                if pis[n]["posting_date"] >= FA2026_START:
                    card += k[1]

    cert_field = next((df.fieldname for df in frappe.get_meta("Purchase Invoice").fields if df.fieldname.startswith("custom_") and "cert" in df.fieldname and ("wht" in df.fieldname or "withh" in df.fieldname)), None)
    certs = None
    if cert_field:
        inv = [vn for vt, vn in withheld if vt == "Purchase Invoice"]
        if inv:
            vals = frappe.get_all("Purchase Invoice", filters={"name": ["in", inv]}, pluck=cert_field)
            certs = pct(sum(1 for v in vals if v not in (None, "", 0, "0")), len(vals))

    return {"rows": sorted(rows, key=lambda r: r["date"]), "remitted": remitted, "rate_exceptions": exceptions, "card": card, "certs": certs}


def _load(ctx: TaxContext) -> Optional[Dict[str, Any]]:
    if "wht" not in ctx._cache:
        accts = tax_accounts(ctx, "wht")
        liab = frappe.get_all("Account", filters={"name": ["in", accts], "root_type": "Liability"}, pluck="name") if accts else []
        ctx._cache["wht"] = _build(ctx, liab) if liab else None
    return ctx._cache["wht"]


def _unremitted(ctx: TaxContext, d: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Outstanding withholdings whose 5-working-day deadline has passed."""
    hol = holidays(ctx)
    by_ref = {r["vn"]: r for r in d["rows"]}
    out = []
    for dt, ref, left in fifo_outstanding([(r["date"], r["vn"], r["amount"]) for r in d["rows"]], d["remitted"]):
        due = rules.wht_due_date(dt, hol)
        if due < ctx.today:
            late = (ctx.today - due).days
            out.append({
                "payment": ref, "payee": by_ref[ref]["payee"], "withheld": left, "deducted_on": dt.isoformat(), "due_on": due.isoformat(),
                "days_late": late, "chip": chip("neg" if late >= 7 else "warn", f"{late} days"),
                "drill": {"metric": "wht_unremitted", "filters": {}},
            })
    return out


# --------------------------------------------------------------------------- compute
def compute(ctx: TaxContext) -> Dict[str, Any]:
    if not ctx.company:
        return unavailable(_("Set a default Company to see withholding tax"))
    if not doctype_exists("Purchase Invoice"):
        return unavailable(_("ERPNext Purchase Invoice is required for the withholding view"))
    d = _load(ctx)
    if d is None:
        return unavailable(_("No withholding tax payable account found. Name it with 'Withholding' or 'WHT' to enable this view"))

    rows = d["rows"]
    total = sum(r["amount"] for r in rows)
    late = _unremitted(ctx, d)
    late_sum = sum(x["withheld"] for x in late)
    no_wht = [e for e in d["rate_exceptions"] if e["applied_rate"] == 0]
    nr_rows = [r for r in rows if r["non_resident"]]

    by_kind: Dict[str, float] = {}
    for r in rows:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0.0) + r["amount"]
    by_type = []
    for k, amt in sorted(by_kind.items(), key=lambda kv: -kv[1]):
        pair = rules.WHT_RATES.get(k)
        by_type.append({
            "kind": k, "label": rules.WHT_LABELS.get(k, "Other / unclassified"), "amount": round(amt, 2),
            "note": f"Resident {pair[0] * 100:g}% · non-resident {pair[1] * 100:g}%" if pair else _("Not matched to a payment type by name"),
        })

    k_late = kpi("past_5_working_days", "Past 5 working days", late_sum, "money", _("{0} payments · 5% penalty + 1%/month").format(len(late)), "bad" if late else "neutral")
    k_late["drill"] = {"metric": "wht_unremitted", "filters": {}}
    k_none = kpi(
        "payments_no_wht", "Payments with no WHT", len(no_wht), "count",
        _("{0} gross payment · rate check failed").format(money_short(ctx, sum(e["gross"] for e in no_wht))) if no_wht else _("Every payment of a WHT type shows a deduction"),
        "bad" if no_wht else "neutral",
    )
    k_none["drill"] = {"metric": "wht_no_wht", "filters": {}}
    k_w = kpi("withheld", "Tax withheld", total, "money", _("{0} payments to {1} payees").format(len(rows), len({r["payee"] for r in rows})))
    k_w["drill"] = {"metric": "wht_withheld", "filters": {}}
    nr_amt = sum(r["amount"] for r in nr_rows)
    k_nr = kpi("non_resident_wht", "Non-resident WHT", nr_amt, "money", _("Supplier country is not Kenya · {0} payees").format(len({r["payee"] for r in nr_rows})))
    k_nr["drill"] = {"metric": "wht_nonresident", "filters": {}}
    rem = min(d["remitted"], total)
    card = d["card"]
    return {
        "available": True,
        "kpis": [
            k_w,
            kpi("remitted", "Remitted", pct(rem, total), "pct", _("{0} of {1} withheld").format(money_short(ctx, rem), money_short(ctx, total))),
            k_late,
            k_none,
            kpi("certificates_issued", "Certificates issued", d["certs"], "pct", _("Withholdee certificates") if d["certs"] is not None else _("No WHT certificate field on Purchase Invoice")),
            k_nr,
        ],
        "by_type": by_type,
        "unremitted": late[:LIST_CAP],
        "unremitted_total": len(late),
        "rate_exceptions": d["rate_exceptions"][:LIST_CAP],
        "rate_exceptions_total": len(d["rate_exceptions"]),
        "rate_card": rules.wht_rate_card(),
        "watch": {
            "card_fees_amount": card,
            "note": _("Finance Act 2026: interchange and merchant fees paid to non-residents are treated as management fees, 20% withholding from 1 Jul 2026.")
            + (_(" Gross paid to non-residents since then: {0}.").format(money_short(ctx, card)) if card else ""),
        },
        "exceptions": [{**x, "exception": "unremitted"} for x in late[:LIST_CAP]] + [{**x, "exception": "rate"} for x in d["rate_exceptions"][:LIST_CAP]],
        "exception_total": len(late) + len(d["rate_exceptions"]),
    }


# --------------------------------------------------------------------------- drill-down
_PAYEE = {"label": "Payee", "fieldname": "payee", "fieldtype": "Data"}
_COLS = {
    "wht_withheld": [
        {"label": "Document", "fieldname": "vn", "fieldtype": "Data"}, _PAYEE,
        {"label": "Type", "fieldname": "kind", "fieldtype": "Data"},
        {"label": "Date", "fieldname": "date", "fieldtype": "Date"},
        {"label": "Withheld", "fieldname": "amount", "fieldtype": "Currency"},
    ],
    "wht_unremitted": [
        {"label": "Document", "fieldname": "payment", "fieldtype": "Data"}, _PAYEE,
        {"label": "Withheld", "fieldname": "withheld", "fieldtype": "Currency"},
        {"label": "Deducted", "fieldname": "deducted_on", "fieldtype": "Date"},
        {"label": "Due", "fieldname": "due_on", "fieldtype": "Date"},
        {"label": "Days late", "fieldname": "days_late", "fieldtype": "Int"},
    ],
    "wht_rate_exceptions": [
        {"label": "Purchase Invoice", "fieldname": "payment", "fieldtype": "Link", "options": "Purchase Invoice"}, _PAYEE,
        {"label": "Net amount", "fieldname": "gross", "fieldtype": "Currency"},
        {"label": "Expected %", "fieldname": "expected_rate", "fieldtype": "Percent"},
        {"label": "Applied %", "fieldname": "applied_rate", "fieldtype": "Percent"},
    ],
}
_COLS["wht_no_wht"] = _COLS["wht_rate_exceptions"]
_COLS["wht_nonresident"] = _COLS["wht_withheld"]


def drilldown(ctx: TaxContext, metric: str, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if metric not in _COLS:
        return None
    frappe.has_permission("GL Entry", throw=True)
    frappe.has_permission("Purchase Invoice", throw=True)
    d = _load(ctx) if ctx.company and doctype_exists("Purchase Invoice") else None
    if d is None:
        rows: List[Dict[str, Any]] = []
    elif metric == "wht_withheld":
        rows = d["rows"]
    elif metric == "wht_nonresident":
        rows = [r for r in d["rows"] if r["non_resident"]]
    elif metric == "wht_unremitted":
        rows = _unremitted(ctx, d)
    elif metric == "wht_no_wht":
        rows = [e for e in d["rate_exceptions"] if e["applied_rate"] == 0]
    else:
        rows = [e for e in d["rate_exceptions"] if not filters.get("payment") or e["payment"] == filters["payment"]]
    cols = _COLS[metric]
    return drill_page(cols, [{c["fieldname"]: r.get(c["fieldname"]) for c in cols} for r in rows], filters)
