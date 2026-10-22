# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Customs & Excise tab: import taxes, excise and digital services from abroad.

Data:
  * Imports = submitted Landed Cost Vouchers whose taxes table has at least one customs line
    (duty / IDF / RDL / import VAT / excise, identified by description or expense-account name).
    CIF = sum of the voucher's item amounts. IDF, RDL and import VAT are read from voucher lines
    when present, otherwise computed with `rules.landed_import_taxes` (flagged by `computed` in
    the KPI sub). Import VAT needs the duty, so it stays None when no duty line is carried.
  * Excise = GL postings on `tax_accounts(ctx, 'excise')` in the latest month (Liability accounts
    only count towards the amount due on the 20th).
  * Digital services = Purchase Invoice lines for non-stock, non-asset items from Suppliers whose
    `country` is set and is not Kenya. Residency is never guessed when the country is blank.
  * Export-certificate tracking exists only if Landed Cost Voucher has a custom field whose name
    contains 'export_cert', 'certificate' or 'icms'; otherwise docs are "not tracked" (None).

Period: the selected reporting period for imports/digital services; the month of
`min(period end, today)` for excise.

Drill-down metrics: `customs_entries` (all import entries), `customs_entry` (filters.entry: the
voucher's tax lines), `customs_digital_services` (invoice lines).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

import frappe
from frappe import _
from frappe.utils import flt

from insights.ml.kenya_tax_intelligence import rules
from insights.ml.kenya_tax_intelligence.common import (
    TaxContext,
    chip,
    doctype_exists,
    holidays,
    kpi,
    tax_accounts,
    unavailable,
    vat_tax_cond,
)

PAGE_SIZE = 50
LANDED_KIND_PATTERNS = (  # first match wins: IDF/RDL/VAT/excise names before the generic duty words
    ("idf", ("idf", "import declaration")),
    ("rdl", ("rdl", "railway development")),
    ("vat", ("vat",)),
    ("excise", ("excise",)),
    ("duty", ("duty", "customs", "tariff")),
)
DOCS_FIELD_HINTS = ("export_cert", "certificate", "icms")


# --------------------------------------------------------------------------- pure helpers
def landed_line_kind(text: str) -> Optional[str]:
    """'duty'|'idf'|'rdl'|'vat'|'excise' for a landed-cost line's description/account, else None."""
    t = (text or "").lower()
    for kind, frags in LANDED_KIND_PATTERNS:
        if any(f in t for f in frags):
            return kind
    return None


def entry_taxes(cif: float, lines: Dict[str, float]) -> Dict[str, Any]:
    """Duty/IDF/RDL/VAT for one import: line amounts where present, else computed. `computed` lists the filled gaps."""
    duty = lines.get("duty")
    excise = lines.get("excise", 0.0)
    calc = rules.landed_import_taxes(cif, duty or 0.0, excise)
    out: Dict[str, Any] = {"duty": duty, "computed": []}
    for k in ("idf", "rdl", "vat"):
        if k in lines:
            out[k] = round(lines[k], 2)
        elif k == "vat" and duty is None:
            out[k] = None  # import VAT base includes duty; unknown duty -> unknown VAT
        else:
            out[k] = calc[k]
            out["computed"].append(k)
    return out


# --------------------------------------------------------------------------- shared with vat.py
def foreign_service_lines(ctx: TaxContext, start: date, end: date) -> List[Dict[str, Any]]:
    """Service lines on submitted Purchase Invoices from non-resident suppliers (Supplier.country set, not Kenya).

    `vat_charged` is the invoice's input-VAT rows (base currency); 0 means the VAT was not charged by the supplier.
    """
    if not (ctx.company and doctype_exists("Purchase Invoice") and doctype_exists("Supplier")):
        return []
    cond, cparams = vat_tax_cond(ctx, "vat_input", "t")
    return frappe.db.sql(
        f"""SELECT pi.name AS invoice, pi.supplier, pi.supplier_name, pii.item_name AS service,
                   pii.base_net_amount AS net, pi.posting_date,
                   (SELECT COALESCE(SUM(t.base_tax_amount_after_discount_amount), 0)
                      FROM `tabPurchase Taxes and Charges` t
                     WHERE t.parent = pi.name AND t.parenttype = 'Purchase Invoice' AND {cond}) AS vat_charged
            FROM `tabPurchase Invoice Item` pii
            JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
            JOIN `tabSupplier` s ON s.name = pi.supplier
            LEFT JOIN `tabItem` it ON it.name = pii.item_code
            WHERE pi.docstatus = 1 AND pi.company = %(company)s AND pi.posting_date BETWEEN %(start)s AND %(end)s
              AND s.country IS NOT NULL AND s.country <> '' AND s.country <> 'Kenya'
              AND COALESCE(it.is_stock_item, 0) = 0 AND COALESCE(it.is_fixed_asset, 0) = 0""",
        {"company": ctx.company, "start": start, "end": end, **cparams},
        as_dict=True,
    )


def country_tracked() -> bool:
    return bool(doctype_exists("Supplier") and frappe.db.count("Supplier", {"country": ["is", "set"]}))


# --------------------------------------------------------------------------- data
def _docs_field() -> Optional[str]:
    if not doctype_exists("Landed Cost Voucher"):
        return None
    for df in frappe.get_meta("Landed Cost Voucher").fields:
        if (df.fieldname or "").startswith("custom_") and any(h in df.fieldname for h in DOCS_FIELD_HINTS) and df.fieldtype in ("Check", "Attach", "Attach Image", "Data", "Link"):
            return df.fieldname
    return None


def _entries(ctx: TaxContext, docs_field: Optional[str]) -> List[Dict[str, Any]]:
    docs_col = f", lcv.`{docs_field}` AS docs" if docs_field else ""
    vouchers = frappe.db.sql(
        f"""SELECT lcv.name, lcv.posting_date{docs_col} FROM `tabLanded Cost Voucher` lcv
            WHERE lcv.docstatus = 1 AND lcv.company = %s AND lcv.posting_date BETWEEN %s AND %s
            ORDER BY lcv.posting_date DESC, lcv.name DESC""",
        (ctx.company, ctx.start, ctx.end),
        as_dict=True,
    )
    if not vouchers:
        return []
    names = tuple(v["name"] for v in vouchers)
    lines: Dict[str, Dict[str, float]] = {}
    for r in frappe.db.sql(
        """SELECT parent, description, expense_account, base_amount FROM `tabLanded Cost Taxes and Charges` WHERE parent IN %s""",
        (names,),
        as_dict=True,
    ):
        kind = landed_line_kind(f"{r['description'] or ''} {r['expense_account'] or ''}")
        if kind:
            d = lines.setdefault(r["parent"], {})
            d[kind] = d.get(kind, 0.0) + flt(r["base_amount"])
    cif = dict(frappe.db.sql("""SELECT parent, SUM(amount) FROM `tabLanded Cost Item` WHERE parent IN %s GROUP BY parent""", (names,)))
    supplier = dict(frappe.db.sql("""SELECT parent, MIN(supplier) FROM `tabLanded Cost Purchase Receipt` WHERE parent IN %s GROUP BY parent""", (names,)))
    out = []
    for v in vouchers:
        if v["name"] not in lines:
            continue  # not an import: no customs line
        c = flt(cif.get(v["name"]))
        t = entry_taxes(c, lines[v["name"]])
        if docs_field:
            ch = chip("pos", _("Complete")) if v.get("docs") else chip("neg", _("No export cert."))
        else:
            ch = chip("mut", _("Docs not tracked"))
        out.append({
            "entry": v["name"], "supplier": supplier.get(v["name"]), "cif": round(c, 2), "duty": t["duty"], "idf": t["idf"],
            "rdl": t["rdl"], "vat": t["vat"], "chip": ch, "computed": t["computed"], "has_docs": bool(v.get("docs")) if docs_field else None,
            "drill": {"metric": "customs_entry", "filters": {"entry": v["name"]}},
        })
    return out


def _sum(rows: List[Dict[str, Any]], key: str) -> Optional[float]:
    vals = [r[key] for r in rows if r[key] is not None]
    return round(sum(vals), 2) if vals else None


def _excise(ctx: TaxContext, month_start: date, month_end: date):
    accounts = tax_accounts(ctx, "excise")
    if not accounts:
        return None, []
    rows = frappe.db.sql(
        """SELECT a.account_name, a.root_type, SUM(g.credit - g.debit) AS cr
           FROM `tabGL Entry` g JOIN `tabAccount` a ON a.name = g.account
           WHERE g.company = %s AND g.is_cancelled = 0 AND g.account IN %s AND g.posting_date BETWEEN %s AND %s
           GROUP BY a.account_name, a.root_type""",
        (ctx.company, tuple(accounts), month_start, month_end),
        as_dict=True,
    )
    table, due = [], 0.0
    for r in rows:
        liability = r["root_type"] == "Liability"
        amount = flt(r["cr"]) if liability else -flt(r["cr"])
        if round(amount, 2) == 0:
            continue
        due += amount if liability else 0.0
        table.append({"item": r["account_name"], "basis": None, "rate": None, "amount": round(amount, 2)})  # basis/rate are not recorded in the GL
    return round(due, 2), table


def _digital(ctx: TaxContext) -> List[Dict[str, Any]]:
    grouped: Dict[tuple, Dict[str, Any]] = {}
    for r in foreign_service_lines(ctx, ctx.start, ctx.end):
        g = grouped.setdefault((r["supplier_name"] or r["supplier"], r["service"]), {"amount": 0.0, "charged": False})
        g["amount"] += flt(r["net"])
        g["charged"] = g["charged"] or flt(r["vat_charged"]) > 0
    # ponytail: VAT charged on the invoice => supplier is VAT-registered here (SEP tax is theirs); none => we self-account
    return sorted(
        (
            {
                "supplier": k[0], "service": k[1],
                "tax_note": _("SEP tax {0}% (supplier registers)").format(f"{rules.SEP_RATE * 100:g}") if g["charged"] else _("VAT reverse charge"),
                "amount": round(g["amount"], 2),
            }
            for k, g in grouped.items()
        ),
        key=lambda x: -x["amount"],
    )


# --------------------------------------------------------------------------- compute
def compute(ctx: TaxContext) -> Dict[str, Any]:
    if not (ctx.company and doctype_exists("Landed Cost Voucher")):
        return unavailable(_("Landed Cost Voucher is not available; install ERPNext to track customs"))

    docs_field = _docs_field()
    entries = _entries(ctx, docs_field)
    computed = sorted({c for e in entries for c in e["computed"]})
    cif_total = _sum(entries, "cif")
    none_sub = _("No landed cost vouchers with customs lines in the period")
    comp_note = _(" · {0} computed where the voucher has no line").format(", ".join(c.upper() for c in computed)) if computed else ""

    m_end = min(ctx.end, ctx.today)
    m_start, m_last = m_end.replace(day=1), rules.month_end(m_end)
    excise_due, excise_rows = _excise(ctx, m_start, m_last)
    due_date = rules.monthly_due_dates(m_last, holidays(ctx))["excise"]
    missing = [e for e in entries if e["has_docs"] is False] if docs_field else None

    duty, idf, rdl, vat = (_sum(entries, k) if entries else None for k in ("duty", "idf", "rdl", "vat"))
    kpis = [
        kpi("import_duty", _("Import duty"), duty, "money", _("{0} entries · from landed cost lines").format(len(entries)) if entries else none_sub),
        kpi("idf", _("Import declaration fee"), idf, "money",
            _("{0}% of CIF · {1} entries{2}").format(f"{rules.IDF_RATE * 100:g}", len(entries), comp_note) if entries else none_sub),
        kpi("rdl", _("Railway development levy"), rdl, "money", _("{0}% of CIF{1}").format(f"{rules.RDL_RATE * 100:g}", comp_note) if entries else none_sub),
        kpi("import_vat", _("Import VAT"), vat, "money",
            _("{0}% on CIF + duty · claimable").format(f"{rules.VAT_RATE * 100:g}") if entries else none_sub),
        kpi("excise_due", _("Excise due {0}").format(due_date.strftime("%d %b")), excise_due, "money",
            _("Return and payment") if excise_due is not None else _("No excise account found"), "warn" if excise_due else "neutral"),
        kpi("entries_missing_docs", _("Entries missing export certificate"), len(missing) if missing is not None else None, "count",
            _("Docs not tracked: no export-certificate field on Landed Cost Voucher") if missing is None else _("Required from 1 Sep 2026"),
            "bad" if missing else "neutral"),
    ]
    return {
        "available": True,
        "kpis": kpis,
        "landed": [
            {"label": _("Import duty"), "amount": duty},
            {"label": _("Import VAT"), "amount": vat},
            {"label": _("Declaration fee {0}%").format(f"{rules.IDF_RATE * 100:g}"), "amount": idf},
            {"label": _("Railway levy {0}%").format(f"{rules.RDL_RATE * 100:g}"), "amount": rdl},
        ],
        "entries": [{k: v for k, v in e.items() if k not in ("computed", "has_docs")} for e in sorted(entries, key=lambda e: -e["cif"])[:25]],
        "entry_total": len(entries),
        "cif_total": cif_total,
        "excise": excise_rows,
        "digital_services": _digital(ctx)[:25],
    }


# --------------------------------------------------------------------------- drill-down
def _page(rows: List[Dict[str, Any]], columns: List[Dict[str, Any]], filters: Dict[str, Any]) -> Dict[str, Any]:
    page = max(int((filters or {}).get("page") or 1), 1)
    return {"columns": columns, "rows": rows[(page - 1) * PAGE_SIZE : page * PAGE_SIZE], "total": len(rows)}


def drilldown(ctx: TaxContext, metric: str, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if metric not in ("customs_entries", "customs_entry", "customs_digital_services"):
        return None
    filters = filters or {}
    if metric == "customs_digital_services":
        frappe.has_permission("Purchase Invoice", throw=True)
        cols = [
            {"label": "Purchase Invoice", "fieldname": "invoice", "fieldtype": "Link", "options": "Purchase Invoice"},
            {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier"},
            {"label": "Service", "fieldname": "service", "fieldtype": "Data"},
            {"label": "Date", "fieldname": "posting_date", "fieldtype": "Date"},
            {"label": "Amount", "fieldname": "net", "fieldtype": "Currency"},
            {"label": "VAT charged", "fieldname": "vat_charged", "fieldtype": "Currency"},
        ]
        return _page([{k: r[k] for k in ("invoice", "supplier", "service", "posting_date", "net", "vat_charged")} for r in foreign_service_lines(ctx, ctx.start, ctx.end)], cols, filters)
    frappe.has_permission("Landed Cost Voucher", throw=True)
    if not doctype_exists("Landed Cost Voucher"):
        return {"columns": [], "rows": [], "total": 0}
    if metric == "customs_entries":
        cols = [
            {"label": "Landed Cost Voucher", "fieldname": "entry", "fieldtype": "Link", "options": "Landed Cost Voucher"},
            {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier"},
            {"label": "CIF", "fieldname": "cif", "fieldtype": "Currency"},
            {"label": "Duty", "fieldname": "duty", "fieldtype": "Currency"},
            {"label": "IDF", "fieldname": "idf", "fieldtype": "Currency"},
            {"label": "RDL", "fieldname": "rdl", "fieldtype": "Currency"},
            {"label": "VAT", "fieldname": "vat", "fieldtype": "Currency"},
        ]
        return _page([{k: e[k] for k in ("entry", "supplier", "cif", "duty", "idf", "rdl", "vat")} for e in _entries(ctx, _docs_field())], cols, filters)
    entry = filters.get("entry")
    cols = [
        {"label": "Description", "fieldname": "description", "fieldtype": "Data"},
        {"label": "Expense Account", "fieldname": "expense_account", "fieldtype": "Link", "options": "Account"},
        {"label": "Amount", "fieldname": "base_amount", "fieldtype": "Currency"},
    ]
    if not isinstance(entry, str) or not frappe.has_permission("Landed Cost Voucher", doc=entry):
        return {"columns": cols, "rows": [], "total": 0}
    rows = frappe.get_all("Landed Cost Taxes and Charges", filters={"parent": entry, "parenttype": "Landed Cost Voucher"}, fields=["description", "expense_account", "base_amount"], order_by="idx")
    return _page(rows, cols, filters)
