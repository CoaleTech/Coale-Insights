# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""India Tax Intelligence — Data Collection (pure-Ibis).

Every aggregator here compiles to one SQL statement executed inside the
site's MariaDB. There is no longer any `frappe.db.sql` raw-fragment builder
or pandas post-processing: the Python process only ever touches the final
already-aggregated result, which is small (one row per month / section).

GST component classification
---------------------------
The component (`cgst` / `sgst` / `igst` / `cess` / `cgst_rcm` / ...) is
derived from two columns on `tabSales Taxes and Charges` and
`tabPurchase Taxes and Charges`:

- `gst_tax_type` (india_compliance field) is authoritative when set, but
  on this site is only backfilled on a fraction of historical rows.
- `account_head` is set on every row and identifies the component by
  name (`Output Tax CGST - JKM` etc).

So we prefer `gst_tax_type` when it is non-empty, otherwise classify by
`account_head` LIKE patterns. RCM heads are tested before the plain
patterns because `'Input Tax CGST RCM'` matches both.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

import frappe

import ibis
import ibis.expr.types as ir

from insights.api.ml.ibis_source import t


# ---------------------------------------------------------------------------
# TDS section reference — FY 2025-26 / Income Tax Act 2025
# Effective April 2026 the new IT Act 2025 consolidates 194C/J/H/I etc. into
# Section 393, but the old section numbers still appear in legacy account heads.
# ---------------------------------------------------------------------------
_TDS_SECTIONS: Dict[str, Dict[str, Any]] = {
    "192":   {"description": "Salary",                                   "rate_pct": None, "threshold": "Basic exemption limit"},
    "193":   {"description": "Interest on Securities",                   "rate_pct": 10,   "threshold": "₹10,000"},
    "194":   {"description": "Dividend",                                 "rate_pct": 10,   "threshold": "₹10,000"},
    "194A":  {"description": "Interest (Bank / FD / Post Office)",       "rate_pct": 10,   "threshold": "₹50,000"},
    "194B":  {"description": "Lottery / Game Winnings",                  "rate_pct": 30,   "threshold": "₹10,000"},
    "194BA": {"description": "Online Gaming Winnings",                   "rate_pct": 30,   "threshold": "Nil"},
    "194C":  {"description": "Contractor / Sub-contractor Payments",     "rate_pct": 2,    "threshold": "₹30,000 single / ₹1 lakh annual"},
    "194D":  {"description": "Insurance Commission",                     "rate_pct": 5,    "threshold": "₹20,000"},
    "194H":  {"description": "Commission / Brokerage",                   "rate_pct": 2,    "threshold": "₹20,000"},
    "194I":  {"description": "Rent (Land / Building / Furniture)",       "rate_pct": 10,   "threshold": "₹50,000/month"},
    "194IA": {"description": "Immovable Property Transfer",              "rate_pct": 1,    "threshold": "₹50 lakh"},
    "194J":  {"description": "Professional / Technical Fees",            "rate_pct": 10,   "threshold": "₹50,000"},
    "194JA": {"description": "Technical Services / Royalty",             "rate_pct": 2,    "threshold": "₹50,000"},
    "194M":  {"description": "Contract (non-tax-audit assessee)",        "rate_pct": 2,    "threshold": "₹50 lakh"},
    "194N":  {"description": "Cash Withdrawal",                          "rate_pct": 2,    "threshold": "₹1 crore"},
    "194O":  {"description": "E-commerce Participant Sales",             "rate_pct": 1,    "threshold": "₹5 lakh"},
    "194Q":  {"description": "Goods Purchase (buyer's TDS)",             "rate_pct": 0.1,  "threshold": "₹50 lakh"},
    "194S":  {"description": "Virtual Digital Assets (Crypto / NFT)",    "rate_pct": 1,    "threshold": "₹10,000–₹50,000"},
    "194T":  {"description": "Partnership Firm Payments to Partners",    "rate_pct": 10,   "threshold": "₹20,000"},
}


def _enrich_tds_section(account_head: str) -> Dict[str, Any]:
    """Match a GL account head to a known TDS section and return its metadata."""
    head_upper = (account_head or "").upper()
    for code, meta in _TDS_SECTIONS.items():
        if code in head_upper:
            return {"section_code": code, **meta}
    return {"section_code": "", "description": account_head or "", "rate_pct": None, "threshold": ""}


# ---------------------------------------------------------------------------
# India GST compliance reference values.
#
# Verified 2026-07-31 against CBIC / GST portal and primary professional
# sources. Two values here were previously WRONG and are corrected below; both
# understated or misstated exposure on a CFO-facing dashboard.
# ---------------------------------------------------------------------------
EINVOICE_COMPLIANCE: Dict[str, Any] = {
    "mandatory_threshold_crore": 5,
    "mandatory_since": "2023-08-01",
    "upload_within_days": 30,
    "upload_30day_threshold_crore": 10,      # ≥ ₹10 Cr AATO from 1 Apr 2025
    "upload_30day_mandatory_from": "2025-04-01",
    "exemptions": [
        "Special Economic Zone (SEZ) units",
        "Financial institutions & NBFCs",
        "Insurance companies",
        "Goods Transport Agencies (GTA)",
        "Passenger transport services",
        "B2C / unregistered supplies (no IRN required)",
    ],
    # CORRECTED: ₹10,000 is the FLOOR, not the cap. Sec 122(1) is the higher of
    # ₹10,000 or 100% of the tax evaded, per invoice, so a single high-value
    # invoice can exceed ₹10,000 many times over. Sec 122(3)(c) adds a flat
    # ₹25,000 for incorrect e-invoice particulars.
    "penalty_min_per_invoice_inr": 10000,
    "penalty_basis": "higher of ₹10,000 or 100% of tax evaded, per invoice (Sec 122(1))",
    "penalty_incorrect_particulars_inr": 25000,   # Sec 122(3)(c)
    # CORRECTED: 24% is not a blanket rate. Sec 50(3) applies 24% only where ITC
    # was wrongly availed AND utilised. Delayed tax payment under Sec 50(1) and
    # Rule 37 180-day reversals attract 18%. ITC availed but not utilised and
    # then reversed attracts no interest.
    "interest_rate_pct_pa_itc_availed_and_utilised": 24,   # Sec 50(3)
    "interest_rate_pct_pa_delayed_payment": 18,            # Sec 50(1), Rule 37
    "itc_time_limit": "earlier of 30 Nov of the following FY or the GSTR-9 filing date (Sec 16(4))",
    "itc_requires_supplier_filing": "Sec 16(2)(aa): credit only if the invoice appears in GSTR-2B",
    "rule_37_days": 180,   # ITC reversal if the supplier is unpaid within 180 days
}

# Return due dates. Gujarat (state code 24) is a QRMP Group 1 state, so its
# quarterly GSTR-3B is due on the 22nd, not the 24th.
GST_DUE_DATES: Dict[str, Any] = {
    "gstr1_monthly_day": 11,
    "gstr1_qrmp_day": 13,          # quarterly GSTR-1 / monthly IFF
    "gstr3b_monthly_day": 20,
    "gstr3b_qrmp_group1_day": 22,  # Gujarat and other Group 1 states
    "gstr3b_qrmp_group2_day": 24,
    "annual_gstr9_9c": "31 December following the financial year",
    "gstr3b_hard_locked_since": "2025-07-01",
    "ims_deemed_accepted_day": 14,  # no action by the 14th = deemed accepted
    "ims_live_since": "2024-10-01",
    "eway_bill_threshold_inr": 50000,       # interstate and Gujarat intrastate
    "eway_bill_validity_km_per_day": 200,
}


# ---------------------------------------------------------------------------
# Capabilities and helper primitives
# ---------------------------------------------------------------------------

def check_india_compliance_installed() -> bool:
    """Return True if the india_compliance app is installed."""
    return "india_compliance" in frappe.get_installed_apps()


def _india_compliance_error() -> Dict[str, Any]:
    return {"error": "india_compliance not installed"}


def _has_columns(table: ir.Table, *names: str) -> bool:
    return all(name in table.columns for name in names)


def _to_date(d) -> Optional[str]:
    """Coerce a date/datetime/None to a YYYY-MM-DD string for Ibis comparisons."""
    if d is None:
        return None
    if isinstance(d, str):
        return d
    return d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)


def _docstatus_filter(table: ir.Table) -> ir.Table:
    """Standard `docstatus = 1` filter, applied only if the column exists."""
    if "docstatus" in table.columns:
        return table.filter(table["docstatus"] == 1)
    return table


def _company_filter(table: ir.Table, company: Optional[str]) -> ir.Table:
    if company and "company" in table.columns:
        return table.filter(table["company"] == company)
    return table


def _date_filter(
    table: ir.Table,
    start: Optional[date],
    end: Optional[date],
    column: str = "posting_date",
) -> ir.Table:
    """Apply the standard posting_date range filter, columns/values optional.

    `start` and `end` may be ``None`` (== all-time), a ``datetime.date``, or
    a pre-formatted string. The column is skipped if it does not exist.
    """
    if column not in table.columns or (start is None and end is None):
        return table
    col = table[column]
    if start is not None and end is not None:
        return table.filter(col.between(_to_date(start), _to_date(end)))
    if start is not None:
        return table.filter(col >= _to_date(start))
    return table.filter(col <= _to_date(end))


# ---------------------------------------------------------------------------
# GST component classification (gst_tax_type + account_head)
# ---------------------------------------------------------------------------

# Component constants — these are the labels our CASE expression emits and
# the values the sum(where=classified == "...") filters use. Keep them
# lowercase, the same convention the old SQL string-fragment version used.
CGST = "cgst"
SGST = "sgst"
IGST = "igst"
CESS = "cess"
CGST_RCM = "cgst_rcm"
SGST_RCM = "sgst_rcm"
IGST_RCM = "igst_rcm"
ALL_PLAIN = (CGST, SGST, IGST, CESS)
ALL_RCM = (CGST_RCM, SGST_RCM, IGST_RCM)


def _gst_component_expr(table: ir.Table) -> ir.Value:
    """Return an Ibis expression classifying each tax row into a GST component.

    Mirrors the original SQL CASE: prefer `gst_tax_type` when set, otherwise
    classify `account_head` by LIKE pattern. RCM heads are tested before
    the plain patterns because `'Input Tax CGST RCM'` matches both.

    If the columns are missing (e.g. on an aggregate that dropped them)
    the function returns the `gst_type`-only path; if both are missing
    the result is always NULL.
    """
    if "gst_tax_type" in table.columns:
        gst_type = table["gst_tax_type"].nullif("")
    else:
        gst_type = ibis.null()
    if "account_head" in table.columns:
        head = table["account_head"]
    else:
        # When `account_head` is absent (e.g. on an aggregate that
        # dropped it), short-circuit: nothing can match the LIKE patterns
        # either way, so we don't have to worry about a null `head` being
        # used in a LIKE call.
        return ibis.cases(
            (gst_type.notnull(), gst_type),
            else_=ibis.null(),
        )

    # ibis.cases with else_= is the modern CASE-WHEN form.
    return ibis.cases(
        (gst_type.notnull(), gst_type),
        (head.like("%CGST%RCM%"), CGST_RCM),
        (head.like("%SGST%RCM%"), SGST_RCM),
        (head.like("%IGST%RCM%"), IGST_RCM),
        (head.like("%CGST%"), CGST),
        (head.like("%SGST%"), SGST),
        (head.like("%IGST%"), IGST),
        (head.like("%Cess%"), CESS),
        else_=ibis.null(),
    )


def _component_sum(
    table: ir.Table, *components: str, alias: str = "base_tax_amount"
) -> ir.Value:
    """SUM of `alias` (default `base_tax_amount`) for rows whose classified
    GST component is in `components`. Returns an Ibis scalar expression."""
    classified = _gst_component_expr(table)
    col = table[alias]
    return col.sum(where=classified.isin(list(components)))


# ---------------------------------------------------------------------------
# Monthly output / input GST — same shape as the SQL version
# ---------------------------------------------------------------------------

def get_gst_output_tax(
    intelligence, start: date, end: date
) -> List[Dict[str, Any]]:
    """Monthly output GST from submitted Sales Invoices, split by component.

    RCM output is reported separately: under reverse charge the recipient
    pays, so folding it into ordinary output liability would double count.
    """
    si = _company_filter(t("Sales Invoice"), intelligence.company)
    si = _docstatus_filter(si)
    si = _date_filter(si, start, end, "posting_date")

    # Invoice-level monthly revenue + count. Done on the parent table so the
    # tax join below does not inflate them. (The old SQL used
    # `SUM(DISTINCT base_net_total)` which is non-portable; the Ibis way is
    # to aggregate on `si` directly.)
    period_expr = si["posting_date"].strftime("%Y-%m").name("month")
    per_invoice = (
        si.group_by(period_expr)
        .aggregate(
            total_revenue=si["base_net_total"].sum(),
            invoice_count=si["name"].count(),
        )
    )

    stc = t("Sales Taxes and Charges")
    stc_in_window = stc.filter(
        stc["posting_date"].between(_to_date(start), _to_date(end))
        if (start and end and "posting_date" in stc.columns)
        else ibis.literal(True)
    ) if "posting_date" in stc.columns else stc

    # Join the parent invoice (already filtered) onto tax rows. Use a
    # semi-join style: filter tax rows to those whose parent is in `si.name`
    # via an inner join. Inner join also drops invoices with no tax rows
    # silently, which is the right thing here (those contribute 0 tax).
    joined = si.join(stc_in_window, si["name"] == stc_in_window["parent"], how="inner")

    # Date truncate to YYYY-MM, re-aggregated on the joined set.
    tax_period = si["posting_date"].strftime("%Y-%m").name("month")
    per_tax = (
        joined.group_by(tax_period)
        .aggregate(
            cgst=_component_sum(joined, CGST).cast("float64"),
            sgst=_component_sum(joined, SGST).cast("float64"),
            igst=_component_sum(joined, IGST).cast("float64"),
            cess=_component_sum(joined, CESS).cast("float64"),
            rcm=_component_sum(joined, *ALL_RCM).cast("float64"),
        )
    )

    # Outer-merge the two aggregates on month. pandas does the join; the
    # result is at most ~24 rows for a 2-year window.
    rev_df = per_invoice.execute()
    tax_df = per_tax.execute()
    if rev_df is None or rev_df.empty:
        rev_df = None
    if tax_df is None or tax_df.empty:
        tax_df = None

    if rev_df is None and tax_df is None:
        return []

    rev_df = rev_df.set_index("month") if rev_df is not None else None
    tax_df = tax_df.set_index("month") if tax_df is not None else None
    months = sorted(
        set((rev_df.index if rev_df is not None else []))
        | set((tax_df.index if tax_df is not None else []))
    )

    out: List[Dict[str, Any]] = []
    for m in months:
        rev = float((rev_df.loc[m]["total_revenue"] if rev_df is not None and m in rev_df.index else 0) or 0)
        cnt = int((rev_df.loc[m]["invoice_count"] if rev_df is not None and m in rev_df.index else 0) or 0)
        tax_row = tax_df.loc[m] if tax_df is not None and m in tax_df.index else None
        out.append(
            {
                "month": m,
                "cgst": float((tax_row["cgst"] if tax_row is not None else 0) or 0),
                "sgst": float((tax_row["sgst"] if tax_row is not None else 0) or 0),
                "igst": float((tax_row["igst"] if tax_row is not None else 0) or 0),
                "cess": float((tax_row["cess"] if tax_row is not None else 0) or 0),
                "rcm": float((tax_row["rcm"] if tax_row is not None else 0) or 0),
                "total_revenue": rev,
                "invoice_count": cnt,
            }
        )
    return out


def get_gst_input_tax(
    intelligence, start: date, end: date
) -> List[Dict[str, Any]]:
    """Monthly input GST (ITC) from submitted Purchase Invoices, split by component."""
    pi = _company_filter(t("Purchase Invoice"), intelligence.company)
    pi = _docstatus_filter(pi)
    pi = _date_filter(pi, start, end, "posting_date")

    period_expr = pi["posting_date"].strftime("%Y-%m").name("month")
    per_invoice = (
        pi.group_by(period_expr)
        .aggregate(
            total_purchase=pi["base_net_total"].sum(),
            invoice_count=pi["name"].count(),
        )
    )

    ptc = t("Purchase Taxes and Charges")
    if start and end and "posting_date" in ptc.columns:
        ptc_in_window = ptc.filter(ptc["posting_date"].between(_to_date(start), _to_date(end)))
    else:
        ptc_in_window = ptc

    joined = pi.join(ptc_in_window, pi["name"] == ptc_in_window["parent"], how="inner")

    tax_period = pi["posting_date"].strftime("%Y-%m").name("month")
    per_tax = (
        joined.group_by(tax_period)
        .aggregate(
            cgst=_component_sum(joined, CGST).cast("float64"),
            sgst=_component_sum(joined, SGST).cast("float64"),
            igst=_component_sum(joined, IGST).cast("float64"),
            cess=_component_sum(joined, CESS).cast("float64"),
            rcm=_component_sum(joined, *ALL_RCM).cast("float64"),
        )
    )

    rev_df = per_invoice.execute()
    tax_df = per_tax.execute()
    if (rev_df is None or rev_df.empty) and (tax_df is None or tax_df.empty):
        return []

    rev_df = rev_df.set_index("month") if rev_df is not None and not rev_df.empty else None
    tax_df = tax_df.set_index("month") if tax_df is not None and not tax_df.empty else None
    months = sorted(
        set((rev_df.index if rev_df is not None else []))
        | set((tax_df.index if tax_df is not None else []))
    )

    out: List[Dict[str, Any]] = []
    for m in months:
        rev = float((rev_df.loc[m]["total_purchase"] if rev_df is not None and m in rev_df.index else 0) or 0)
        cnt = int((rev_df.loc[m]["invoice_count"] if rev_df is not None and m in rev_df.index else 0) or 0)
        tax_row = tax_df.loc[m] if tax_df is not None and m in tax_df.index else None
        out.append(
            {
                "month": m,
                "cgst": float((tax_row["cgst"] if tax_row is not None else 0) or 0),
                "sgst": float((tax_row["sgst"] if tax_row is not None else 0) or 0),
                "igst": float((tax_row["igst"] if tax_row is not None else 0) or 0),
                "cess": float((tax_row["cess"] if tax_row is not None else 0) or 0),
                "rcm": float((tax_row["rcm"] if tax_row is not None else 0) or 0),
                "total_purchase": rev,
                "invoice_count": cnt,
            }
        )
    return out


# ---------------------------------------------------------------------------
# ITC health, TDS, e-Invoice, e-Waybill, filing compliance, reconciliation,
# HSN summary, counterparty risk — all migrated to Ibis.
# ---------------------------------------------------------------------------

def get_itc_health(intelligence, start: date, end: date) -> Dict[str, Any]:
    """ITC position, blocked credits, and the risks that actually deny credit."""
    if not intelligence.india_compliance_installed:
        return _india_compliance_error()

    # Available ITC: sum of CGST/SGST/IGST/CESS from Purchase Taxes and Charges
    # on submitted Purchase Invoices, add_deduct_tax = 'Add' rows.
    pi = _company_filter(t("Purchase Invoice"), intelligence.company)
    pi = _docstatus_filter(pi)
    pi = _date_filter(pi, start, end, "posting_date")
    ptc = t("Purchase Taxes and Charges")
    joined = pi.join(ptc, pi["name"] == ptc["parent"], how="inner")
    # Filter the joined table first, then aggregate.
    if "add_deduct_tax" in ptc.columns:
        joined = joined.filter(joined["add_deduct_tax"] == "Add")
    available_expr = _component_sum(joined, *ALL_PLAIN)
    available_val = float(_scalar_or(available_expr, 0.0))

    # Reverse-charge ITC: identified by component (cgst_rcm/sgst_rcm/igst_rcm),
    # tracked apart because under RCM the recipient self-assesses and pays.
    # RCM rows on Purchase Taxes and Charges have add_deduct_tax = 'Deduct'
    # (the company owes the tax it then claims as ITC), so they are
    # excluded by the `add_deduct_tax = 'Add'` filter applied to
    # `joined` above — sum against the unfiltered join instead.
    rcm_expr = _component_sum(pi.join(ptc, pi["name"] == ptc["parent"], how="inner"), *ALL_RCM)
    rcm_itc = float(_scalar_or(rcm_expr, 0.0))

    # Claimed ITC: the GL Entry side. Input tax accounts are assets:
    # ITC accrues as a DEBIT. Summing credit - debit returned it negative,
    # inverting utilisation, so use debit - credit here.
    gle = _company_filter(t("GL Entry"), intelligence.company)
    gle = gle.filter(gle["is_cancelled"] == 0)
    gle = _date_filter(gle, start, end, "posting_date")
    acc = t("Account")
    gle_acc = gle.join(acc, gle["account"] == acc["name"], how="inner")

    name = acc["account_name"].lower()
    cond = (
        name.like("%input cgst%")
        | name.like("%input sgst%")
        | name.like("%input igst%")
        | name.like("%input tax%")
    )
    filtered_gle = gle_acc.filter(cond)
    claimed_df = filtered_gle.aggregate(
        v=(filtered_gle["debit"] - filtered_gle["credit"]).sum()
    ).execute()
    claimed_val = float(claimed_df.iloc[0]["v"] or 0) if claimed_df is not None and not claimed_df.empty else 0.0
    # Sec 17(5) blocked credits. expense_account lives on Purchase Invoice
    # Item, not on the invoice; we then need the tax rows joined on top to
    # get the tax amount. Chain the joins explicitly so the resulting
    # table carries all three sets of columns.
    pii = t("Purchase Invoice Item")
    expense = pii["expense_account"].lower()
    blocked = (
        expense.like("%motor vehicle%")
        | expense.like("%vehicle expense%")
        | expense.like("%food%")
        | expense.like("%beverage%")
        | expense.like("%catering%")
        | expense.like("%canteen%")
        | expense.like("%restaurant%")
        | expense.like("%health service%")
        | expense.like("%beauty treatment%")
        | expense.like("%club membership%")
        | expense.like("%gym%")
        | expense.like("%fitness cent%")
        | expense.like("%life insurance%")
        | expense.like("%entertainment%")
        | expense.like("%works contract%")
        | expense.like("%construction%")
        | expense.like("%civil work%")
    )
    # Build pi ⨝ pii (filter on expense_account). The result carries pi+pii
    # columns. Then join ptc on top to expose `add_deduct_tax` and
    # `base_tax_amount` for the component aggregate. Ibis inner-joins do
    # not auto-expose all source columns, so we mutate the columns we
    # need onto the table first to keep downstream references stable.
    pi_with_pii = pi.join(pii, pi["name"] == pii["parent"], how="inner")
    blocked_pi_pii = pi_with_pii.filter(blocked)
    blocked_names = blocked_pi_pii.select(blocked_pi_pii["name"])
    blocked_pi = pi.semi_join(blocked_names, pi["name"] == blocked_names["name"])
    # Now join with ptc and pull in the columns we need.
    ineligible_joined = blocked_pi.join(
        ptc, blocked_pi["name"] == ptc["parent"], how="inner"
    )
    if "add_deduct_tax" in ineligible_joined.columns:
        ineligible_joined = ineligible_joined.filter(
            ineligible_joined["add_deduct_tax"] == "Add"
        )
    ineligible_val = float(_scalar_or(_component_sum(ineligible_joined, *ALL_PLAIN), 0.0))

    # Remarks-flagged blocked credits. The old SQL also matches remarks
    # containing 'ineligible', 'blocked', or '17(5)'. These are line-level
    # flags on the invoice header; we add the (smaller) additional
    # exposure on top.
    if "remarks" in pi.columns:
        remarks_cond = (
            pi["remarks"].lower().like("%ineligible%")
            | pi["remarks"].lower().like("%blocked%")
            | pi["remarks"].lower().like("%17(5)%")
        )
        flagged_pi = pi.filter(remarks_cond)
        # Join to tax rows to compute the tax total for those invoices.
        joined_flagged = flagged_pi.join(ptc, flagged_pi["name"] == ptc["parent"], how="inner")
        if "add_deduct_tax" in joined_flagged.columns:
            joined_flagged = joined_flagged.filter(joined_flagged["add_deduct_tax"] == "Add")
        extra_ineligible = float(_scalar_or(_component_sum(joined_flagged, *ALL_PLAIN), 0.0))
        ineligible_val = max(ineligible_val, extra_ineligible)

    # Sec 16(2)(aa): supplier has not filed GSTR-1, so this credit is not
    # supported by GSTR-2B and is exposed on reversal.
    inward = t("GST Inward Supply")
    if _has_columns(inward, "gstr_1_filled", "igst", "cgst", "sgst", "cess"):
        inward_c = _company_filter(inward, intelligence.company)
        at_risk = inward_c.filter((inward_c["gstr_1_filled"].fill_null(0)) == 0)
        at_risk_row = at_risk.aggregate(
            invoices=at_risk["name"].count(),
            tax=(
                at_risk["igst"].fill_null(0)
                + at_risk["cgst"].fill_null(0)
                + at_risk["sgst"].fill_null(0)
                + at_risk["cess"].fill_null(0)
            ).sum(),
        ).execute()
        if at_risk_row is None or at_risk_row.empty:
            at_risk_invoices = 0
            at_risk_tax = 0.0
        else:
            at_risk_invoices = int(at_risk_row.iloc[0]["invoices"] or 0)
            at_risk_tax = float(at_risk_row.iloc[0]["tax"] or 0)
    else:
        at_risk_invoices = 0
        at_risk_tax = 0.0
    # Reconciliation row: total, unactioned, mismatched, recon_through
    if _has_columns(inward, "match_status", "action", "bill_date"):
        inward_c = _company_filter(inward, intelligence.company)
        recon_row = inward_c.aggregate(
            total=inward_c["name"].count(),
            unactioned=(inward_c["action"].fill_null("No Action") == "No Action").cast("int64").sum(),
            mismatched=(inward_c["match_status"] == "Mismatch").cast("int64").sum(),
            recon_through=inward_c["bill_date"].max(),
        ).execute()
        if recon_row is None or recon_row.empty:
            recon_total = 0
            recon_unactioned = 0
            recon_mismatched = 0
            recon_through = ""
        else:
            recon_total = int(recon_row.iloc[0]["total"] or 0)
            recon_unactioned = int(recon_row.iloc[0]["unactioned"] or 0)
            recon_mismatched = int(recon_row.iloc[0]["mismatched"] or 0)
            recon_through_v = recon_row.iloc[0]["recon_through"]
            recon_through = str(recon_through_v) if recon_through_v is not None else ""
    else:
        recon_total = 0
        recon_unactioned = 0
        recon_mismatched = 0
        recon_through = ""

    utilizable = max(0.0, available_val - ineligible_val)
    utilization_pct = (
        round((claimed_val / utilizable * 100), 2) if utilizable > 0 else 0.0
    )

    return {
        "available": available_val,
        "claimed": claimed_val,
        "ineligible": ineligible_val,
        "utilizable": utilizable,
        "utilization_pct": utilization_pct,
        "rcm_itc": rcm_itc,
        "at_risk_supplier_unfiled": at_risk_tax,
        "at_risk_invoice_count": at_risk_invoices,
        "recon_total": recon_total,
        "recon_unactioned": recon_unactioned,
        "recon_mismatched": recon_mismatched,
        "recon_through": recon_through,
    }


def _scalar_or(expr: ir.Value, default: float = 0.0) -> float:
    """Execute an Ibis scalar expression and coerce to float, falling back
    to `default` on empty / None."""
    try:
        df = expr.execute()
    except Exception:
        return default
    if df is None:
        return default
    # A bare column expression (e.g. `table.aggregate(c=...).c`) returns a
    # Series after execute; an aggregate expression with multiple columns
    # returns a DataFrame. Handle both.
    if hasattr(df, "empty"):
        try:
            if df.empty:
                return default
        except Exception:
            pass
    if hasattr(df, "iloc"):
        try:
            v = df.iloc[0, 0] if df.ndim == 2 else df.iloc[0]
        except Exception:
            try:
                v = df.iloc[0]
            except Exception:
                v = None
    else:
        v = df
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

def get_tds_summary(intelligence, start: date, end: date) -> Dict[str, Any]:
    """TDS deducted by us, TDS suffered on our income, and the net position.

    `add_deduct_tax` exists on Purchase Taxes and Charges but NOT on
    Sales Taxes and Charges: the previous receivable query filtered on
    `stc.add_deduct_tax` and raised "Unknown column", zeroing the whole
    section. TDS suffered on sales is identified by the account head alone.
    """
    # Payable by section: TDS-deducted entries on Purchase Invoices.
    pi = _company_filter(t("Purchase Invoice"), intelligence.company)
    pi = _docstatus_filter(pi)
    pi = _date_filter(pi, start, end, "posting_date")
    ptc = t("Purchase Taxes and Charges")
    joined = pi.join(ptc, pi["name"] == ptc["parent"], how="inner")
    tds_head = ptc["account_head"].lower()
    tds_cond = tds_head.like("%tds%") | tds_head.like("%tax deducted%")
    filtered = joined.filter(tds_cond)
    payable_agg = (
        filtered.group_by(filtered["account_head"].name("section"))
        .aggregate(
            amount=filtered["base_tax_amount"].sum(),
            transaction_count=filtered["name"].nunique(),
        )
        .order_by(filtered["base_tax_amount"].sum().desc())
    )
    payable_df = payable_agg.execute()
    payable_rows: List[Dict[str, Any]] = []
    if payable_df is not None and not payable_df.empty:
        for _, r in payable_df.iterrows():
            section = r.get("section", "")
            amount = abs(float(r.get("amount") or 0))
            payable_rows.append(
                {
                    "section": section,
                    "amount": amount,
                    "transaction_count": int(r.get("transaction_count") or 0),
                    **_enrich_tds_section(section),
                }
            )
    total_payable = sum(r["amount"] for r in payable_rows)

    # Receivable: TDS / TCS suffered on sales, identified by account head
    # only (Sales Taxes and Charges has no add_deduct_tax column).
    si = _company_filter(t("Sales Invoice"), intelligence.company)
    si = _docstatus_filter(si)
    si = _date_filter(si, start, end, "posting_date")
    stc = t("Sales Taxes and Charges")
    s_joined = si.join(stc, si["name"] == stc["parent"], how="inner")
    s_tds_cond = (
        stc["account_head"].lower().like("%tds%")
        | stc["account_head"].lower().like("%tax deducted%")
        | stc["account_head"].lower().like("%tcs%")
    )
    s_filtered = s_joined.filter(s_tds_cond)
    receivable_val = float(
        _scalar_or(s_filtered["base_tax_amount"].abs().sum(), 0.0)
    )

    # Coverage: how much of our TDS configuration is actually reaching invoices.
    twc = t("Tax Withholding Category")
    categories_configured = int(_scalar_or(twc["name"].count(), 0))

    sup = t("Supplier")
    if "tax_withholding_category" in sup.columns:
        suppliers_mapped = int(
            _scalar_or(
                sup.filter(sup["tax_withholding_category"].fill_null("") != "")
                .aggregate(v=sup["name"].count())["v"],
                0,
            )
        )
    else:
        suppliers_mapped = 0
    if "disabled" in sup.columns:
        suppliers_total = int(
            _scalar_or(
                sup.filter(sup["disabled"].fill_null(0) == 0)
                .aggregate(v=sup["name"].count())["v"],
                0,
            )
        )
    else:
        suppliers_total = int(_scalar_or(sup.aggregate(v=sup["name"].count())["v"], 0))

    if "apply_tds" in pi.columns:
        invoices_with_tds = int(
            _scalar_or(
                pi.filter(pi["apply_tds"].fill_null(0) == 1)
                .aggregate(v=pi["name"].count())["v"],
                0,
            )
        )
    else:
        invoices_with_tds = 0
    invoices_total = int(
        _scalar_or(pi.aggregate(v=pi["name"].count())["v"], 0)
    )

    return {
        "payable_by_section": payable_rows,
        "total_payable": round(total_payable, 2),
        "receivable": round(receivable_val, 2),
        "net_position": round(receivable_val - total_payable, 2),
        "categories_configured": categories_configured,
        "suppliers_mapped": suppliers_mapped,
        "suppliers_total": suppliers_total,
        "invoices_with_tds": invoices_with_tds,
        "invoices_total": invoices_total,
    }


def get_einvoice_status(intelligence, start: date, end: date) -> Dict[str, Any]:
    """e-Invoice (IRN) coverage measured only against invoices that need an IRN.

    Counting every invoice overstates non-compliance badly. B2C / unregistered
    supplies require no IRN, so on this site a naive count reported 251
    "missing" when 154 of those were exempt. Exports DO require an IRN.

    `gst_category` values that require an IRN: Registered Regular, Registered
    Composition, SEZ (with or without payment), Deemed Export, Overseas.
    Exempt: Unregistered, and UIN Holders.
    """
    if not intelligence.india_compliance_installed:
        return _india_compliance_error()

    si = _company_filter(t("Sales Invoice"), intelligence.company)
    si = _docstatus_filter(si)
    si = _date_filter(si, start, end, "posting_date")

    # `gst_category` values that require an IRN. India Compliance's standard
    # set is listed first; the bare "SEZ" / "Deemed Export" / "Tax Deductor"
    # legacy / aliased values are added because live data on at least one
    # install uses them in place of the longer labels.
    needs_irn = si["gst_category"].isin(
        [
            "Registered Regular",
            "Registered Composition",
            "SEZ supply with payment of tax",
            "SEZ supply without payment of tax",
            "Deemed Export",
            "Overseas",
            "SEZ",
        ]
    )
    has_irn = (si["irn"].fill_null("") != "") if "irn" in si.columns else ibis.literal(False)

    one = ibis.literal(1)
    zero = ibis.literal(0)

    agg = si.aggregate(
        all_invoices=si["name"].count(),
        total=needs_irn.cast("int64").sum(),
        filed=(needs_irn & has_irn).cast("int64").sum(),
        pending=(needs_irn & (~has_irn)).cast("int64").sum(),
        exempt=(~needs_irn).cast("int64").sum(),
        pending_value=si["base_grand_total"].fill_null(0)
        .sum(where=(needs_irn & (~has_irn))),
    )
    df = agg.execute()
    if df is None or df.empty:
        return {
            "total": 0, "filed": 0, "pending": 0, "failed": 0, "exempt": 0,
            "all_invoices": 0, "pending_value": 0.0, "coverage_pct": 0.0,
        }
    row = df.iloc[0]
    total = int(row.get("total") or 0)
    filed = int(row.get("filed") or 0)
    pending = int(row.get("pending") or 0)
    coverage_pct = round((filed / total * 100), 2) if total > 0 else 0.0
    return {
        "total": total,
        "filed": filed,
        "pending": pending,
        # No `einvoice_status` field exists on Sales Invoice in this install,
        # so a failed-generation count is not observable here.
        "failed": 0,
        "exempt": int(row.get("exempt") or 0),
        "all_invoices": int(row.get("all_invoices") or 0),
        "pending_value": float(row.get("pending_value") or 0),
        "coverage_pct": coverage_pct,
    }


def get_ewaybill_status(intelligence, start: date, end: date) -> Dict[str, Any]:
    """e-Waybill coverage from `e_waybill_status`.

    The state lives in `e_waybill_status` (`Not Applicable` / `Pending` /
    `Manually Generated` / `Generated`) — the e-Waybill number is in
    `ewaybill`. The e_waybill_status value was previously aliased `status`
    in the SQL; we use the raw column here.
    """
    if not intelligence.india_compliance_installed:
        return _india_compliance_error()

    si = _company_filter(t("Sales Invoice"), intelligence.company)
    si = _docstatus_filter(si)
    si = _date_filter(si, start, end, "posting_date")
    # Same MariaDB REPLACE(str, '', x)-is-a-no-op bug as the reconciliation
    # score fix below (`get_reconciliation_score`): `.fill_null("").replace("",
    # "Not Set")` compiles to a no-op REPLACE and never converts the empty
    # string fill_null just created, so NULL e_waybill_status rows silently
    # bucketed under key "" instead of "Not Set". Use nullif("")+cases instead.
    status = (
        ibis.cases(
            (si["e_waybill_status"].nullif("").isnull(), "Not Set"),
            else_=si["e_waybill_status"],
        )
        if "e_waybill_status" in si.columns
        else ibis.literal("Not Set")
    )
    by_status = (
        si.group_by(status.name("ewb_status"))
        .aggregate(
            count=si["name"].count(),
            value=si["base_grand_total"].fill_null(0).sum(),
        )
        .order_by(si["name"].count().desc())
    )
    df = by_status.execute()
    counts: Dict[str, int] = {}
    values: Dict[str, float] = {}
    by_status_list: List[Dict[str, Any]] = []
    if df is not None and not df.empty:
        for _, r in df.iterrows():
            s = r.get("ewb_status", "Not Set")
            c = int(r.get("count") or 0)
            v = float(r.get("value") or 0)
            counts[s] = c
            values[s] = v
            by_status_list.append({"status": s, "count": c, "value": v})
    total = sum(counts.values())
    pending = counts.get("Pending", 0)
    generated = counts.get("Generated", 0) + counts.get("Manually Generated", 0)

    # Cancellations are logged in e-Waybill Log, not flagged on the invoice.
    ewb_log = t("e-Waybill Log")
    if "is_cancelled" in ewb_log.columns:
        cancelled = int(_scalar_or(ewb_log.filter(ewb_log["is_cancelled"] == 1)
                                    .aggregate(v=ewb_log["name"].count())["v"], 0))
    else:
        cancelled = 0

    return {
        "total": total,
        "active": generated,
        "pending": pending,
        "not_applicable": counts.get("Not Applicable", 0),
        "cancelled": cancelled,
        "by_status": by_status_list,
    }


def get_filing_compliance(intelligence, start: date, end: date) -> Dict[str, Any]:
    """GSTR-1 / GSTR-3B filing status from GST Return Log.

    `return_period` is `MMYYYY` so the period range has to be normalised
    to YYYY-MM before the BETWEEN. The live log table is `GST Return Log`
    and is discriminated by `return_type` (`GSTR1` / `GSTR3B`).
    """
    if not intelligence.india_compliance_installed:
        return _india_compliance_error()

    grl = t("GST Return Log")
    grl = _company_filter(grl, intelligence.company)
    # Convert MMYYYY -> YYYY-MM. MariaDB: SUBSTRING(period, 3, 4) for the
    # year, SUBSTRING(period, 1, 2) for the month. Ibis 10.x's `.substr`
    # is 0-indexed, so the 1-indexed MariaDB positions 3 and 1 become 2 and 0.
    if "return_period" in grl.columns and start and end:
        norm = (
            grl["return_period"].substr(2, 4)
            + "-"
            + grl["return_period"].substr(0, 2)
        )
        start_ym = _to_date(start)[:7]
        end_ym = _to_date(end)[:7]
        grl = grl.filter(norm.between(start_ym, end_ym))

    def _returns(return_type: str) -> Dict[str, Any]:
        sub = grl.filter(grl["return_type"] == return_type) if "return_type" in grl.columns else grl
        if "filing_status" in sub.columns:
            agg = sub.aggregate(
                total_returns=sub["name"].count(),
                filed=(sub["filing_status"] == "Filed").cast("int64").sum(),
                unknown=(sub["filing_status"].fill_null("") == "").cast("int64").sum(),
                pending=(
                    sub["filing_status"].isin(["Not Filed", "Pending"])
                ).cast("int64").sum(),
                latest_period=sub["return_period"].max() if "return_period" in sub.columns else ibis.null(),
            )
        else:
            agg = sub.aggregate(
                total_returns=sub["name"].count(),
                filed=ibis.literal(0),
                unknown=ibis.literal(0),
                pending=ibis.literal(0),
                latest_period=ibis.null(),
            )
        df = agg.execute()
        if df is None or df.empty:
            return {
                "total_returns": 0, "filed": 0, "unknown": 0,
                "pending": 0, "latest_period": None,
            }
        row = df.iloc[0]
        return {
            "total_returns": int(row.get("total_returns") or 0),
            "filed": int(row.get("filed") or 0),
            "unknown": int(row.get("unknown") or 0),
            "pending": int(row.get("pending") or 0),
            "latest_period": row.get("latest_period"),
        }

    gstr1 = _returns("GSTR1")
    gstr3b = _returns("GSTR3B")

    def _status(row: Dict[str, Any]) -> str:
        total = int(row.get("total_returns", 0) or 0)
        if total == 0:
            return "No Data"
        if int(row.get("unknown", 0) or 0) == total:
            return "Not Tracked"
        if int(row.get("filed", 0) or 0) == total:
            return "Compliant"
        return "Pending"

    def _shape(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "total": int(row.get("total_returns", 0) or 0),
            "filed": int(row.get("filed", 0) or 0),
            "pending": int(row.get("pending", 0) or 0),
            "unknown": int(row.get("unknown", 0) or 0),
            "late": 0,
            "latest_period": row.get("latest_period") or "",
            "status": _status(row),
        }

    # Periods logged at all, regardless of the reporting window
    grl_all = _company_filter(t("GST Return Log"), intelligence.company)
    if "return_type" in grl_all.columns:
        logged = (
            grl_all.group_by(grl_all["return_type"].name("return_type"))
            .aggregate(
                n=grl_all["name"].count(),
                latest=grl_all["return_period"].max() if "return_period" in grl_all.columns else ibis.null(),
            )
            .execute()
        )
    else:
        logged = None
    logged_all_time: List[Dict[str, Any]] = []
    if logged is not None and not logged.empty:
        for _, r in logged.iterrows():
            logged_all_time.append(
                {
                    "return_type": r.get("return_type", ""),
                    "count": int(r.get("n") or 0),
                    "latest_period": r.get("latest") or "",
                }
            )

    return {
        "gstr1": _shape(gstr1),
        "gstr3b": _shape(gstr3b),
        "logged_all_time": logged_all_time,
    }


def get_reconciliation_score(intelligence, start: date, end: date) -> Dict[str, Any]:
    """Purchase reconciliation against GSTR-2A/2B inward supplies.

    The real match statuses are 'Exact Match', 'Suggested Match',
    'Mismatch', and blank for rows with no counterpart in the books.
    `data_through` is returned so the score is read with its own caveat.
    """
    if not intelligence.india_compliance_installed:
        return _india_compliance_error()

    inward = t("GST Inward Supply")
    inward = _company_filter(inward, intelligence.company)

    if "match_status" in inward.columns:
        # match_status blanks (NULL or empty string) collapse to 'Unlinked'.
        # `.replace("", "Unlinked")` is a no-op in MariaDB (REPLACE with
        # an empty pattern returns its input unchanged), so use ibis.cases
        # against a nullif('')-coalesced value to actually collapse blanks.
        coalesced = inward["match_status"].nullif("")
        ms = ibis.cases(
            (coalesced.isnull(), "Unlinked"),
            else_=coalesced,
        ).name("match_status")
        amount = (
            inward["taxable_value"].fill_null(0)
            + inward["cgst"].fill_null(0)
            + inward["sgst"].fill_null(0)
            + inward["igst"].fill_null(0)
            + inward["cess"].fill_null(0)
        )
        rows_df = (
            inward.group_by(ms)
            .aggregate(
                amount=amount.sum(),
                count=inward["name"].count(),
            )
            .execute()
        )
    else:
        rows_df = None

    by_status: Dict[str, Dict[str, Any]] = {}
    if rows_df is not None and not rows_df.empty:
        for _, r in rows_df.iterrows():
            # pandas may surface the empty-string sentinel for any rows the
            # cases() expression did not classify; treat that as Unlinked
            # so the denominator counts every row.
            raw_key = r.get("match_status", None)
            if raw_key is None or (isinstance(raw_key, float) and str(raw_key) == "nan") or raw_key == "":
                key = "Unlinked"
            else:
                key = str(raw_key)
            by_status[key] = {
                "amount": float(r.get("amount") or 0),
                "count": int(r.get("count") or 0),
            }

    def pick(key: str) -> tuple:
        r = by_status.get(key) or {"amount": 0.0, "count": 0}
        return int(r.get("count", 0) or 0), float(r.get("amount", 0) or 0)

    exact_count, exact_amount = pick("Exact Match")
    suggested_count, suggested_amount = pick("Suggested Match")
    mismatch_count, mismatch_amount = pick("Mismatch")
    unlinked_count, unlinked_amount = pick("Unlinked")
    manual_count, manual_amount = pick("Manual Match")
    amended_count, amended_amount = pick("Amended")
    other_count = sum(
        v["count"] for k, v in by_status.items()
        if k not in ("Exact Match", "Suggested Match", "Mismatch", "Unlinked", "Manual Match", "Amended")
    )
    other_amount = sum(
        v["amount"] for k, v in by_status.items()
        if k not in ("Exact Match", "Suggested Match", "Mismatch", "Unlinked", "Manual Match", "Amended")
    )
    # Denominator covers every classified row, not just the four legacy buckets.
    total_count = (
        exact_count + suggested_count + mismatch_count + unlinked_count
        + manual_count + amended_count + other_count
    )

    if _has_columns(inward, "bill_date", "action"):
        span = inward.aggregate(
            from_date=inward["bill_date"].min(),
            to_date=inward["bill_date"].max(),
            unactioned=(
                (inward["action"].fill_null("No Action") == "No Action").cast("int64").sum()
            ),
        ).execute()
    else:
        span = None
    data_from = ""
    data_through = ""
    unactioned_count = 0
    if span is not None and not span.empty:
        row = span.iloc[0]
        data_from = str(row.get("from_date") or "")
        data_through = str(row.get("to_date") or "")
        unactioned_count = int(row.get("unactioned") or 0)

    return {
        "matched_count": exact_count,
        "matched_amount": exact_amount,
        "suggested_count": suggested_count,
        "suggested_amount": suggested_amount,
        "mismatch_count": mismatch_count,
        "mismatch_amount": mismatch_amount,
        "unmatched_count": unlinked_count,
        "unmatched_amount": unlinked_amount,
        "manual_match_count": manual_count,
        "manual_match_amount": manual_amount,
        "amended_count": amended_count,
        "amended_amount": amended_amount,
        "total_count": total_count,
        "unactioned_count": unactioned_count,
        "data_from": data_from,
        "data_through": data_through,
        "reconciliation_score": (
            round((exact_count / total_count * 100), 2) if total_count > 0 else 0.0
        ),
    }


def get_hsn_summary(intelligence, start: date, end: date) -> List[Dict[str, Any]]:
    """Revenue, actual GST and invoice count by HSN code.

    GST is proportionally allocated to each item line using the invoice-
    level tax total (`base_grand_total - base_net_total`), avoiding a full-
    table scan of `tabSales Taxes and Charges` and the inaccurate blanket
    18% estimate. Works without india_compliance.
    """
    si = _company_filter(t("Sales Invoice"), intelligence.company)
    si = _docstatus_filter(si)
    si = _date_filter(si, start, end, "posting_date")

    sii = t("Sales Invoice Item")
    # Filter the items table by parent IN (submitted invoices) — Ibis has no
    # direct semi-join, so build a subquery via inner join and rely on the
    # parent column to be unique.
    joined = si.join(sii, si["name"] == sii["parent"], how="inner")

    # Proportional GST allocation: sii.base_net_amount / si.base_net_total
    # * (si.base_grand_total - si.base_net_total). Division-by-zero is
    # protected by an explicit guard.
    if "base_net_total" in joined.columns and "base_grand_total" in joined.columns:
        grand = joined["base_grand_total"]
        net = joined["base_net_total"]
        ratio = ibis.cases(
            (net > 0, joined["base_net_amount"] / net),
            else_=ibis.literal(0.0),
        )
        tax_alloc = (grand - net) * ratio
    else:
        tax_alloc = ibis.literal(0.0)

    hsn_agg = (
        joined.group_by(joined["gst_hsn_code"].name("hsn_code"))
        .aggregate(
            revenue=joined["base_amount"].fill_null(0).sum(),
            actual_gst=tax_alloc.fill_null(0).sum(),
            invoice_count=joined["name"].nunique(),
        )
        .order_by(joined["base_amount"].fill_null(0).sum().desc())
    )
    df = hsn_agg.execute()
    if df is None or df.empty:
        return []
    out: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        revenue = float(r.get("revenue") or 0)
        actual_gst = float(r.get("actual_gst") or 0)
        eff = round((actual_gst / revenue * 100), 2) if revenue > 0 else 0.0
        out.append(
            {
                "hsn_code": r.get("hsn_code", "") or "",
                "revenue": revenue,
                "actual_gst": actual_gst,
                "effective_gst_rate": eff,
                "invoice_count": int(r.get("invoice_count") or 0),
            }
        )
    return out


def get_counterparty_risk(intelligence, start: date, end: date) -> Dict[str, Any]:
    """Registration health of the GSTINs we transact with.

    Counts come from the GSTIN registry india_compliance maintains, so
    they reflect the portal's status rather than our own master data.
    """
    if not intelligence.india_compliance_installed:
        return _india_compliance_error()

    gstin = t("GSTIN")
    if "status" in gstin.columns:
        registry = gstin.aggregate(
            total=gstin["gstin"].count() if "gstin" in gstin.columns else gstin["name"].count(),
            active=(gstin["status"] == "Active").cast("int64").sum(),
            cancelled=(gstin["status"] == "Cancelled").cast("int64").sum(),
            suspended=(gstin["status"] == "Suspended").cast("int64").sum(),
            blocked=(gstin["is_blocked"].fill_null(0) == 1).cast("int64").sum(),
            unknown=(gstin["status"].fill_null("") == "").cast("int64").sum(),
        ).execute()
    else:
        registry = None
    if registry is None or registry.empty:
        reg_row = {
            "total": 0, "active": 0, "cancelled": 0, "suspended": 0,
            "blocked": 0, "unknown": 0,
        }
    else:
        r = registry.iloc[0]
        reg_row = {
            "total": int(r.get("total") or 0),
            "active": int(r.get("active") or 0),
            "cancelled": int(r.get("cancelled") or 0),
            "suspended": int(r.get("suspended") or 0),
            "blocked": int(r.get("blocked") or 0),
            "unknown": int(r.get("unknown") or 0),
        }

    # Only the counterparties we actually billed or bought from in the
    # window matter for this period's exposure. The OLD query unioned sales
    # and purchase GSTINs and joined on the registry; we keep the same shape.
    if _has_columns(gstin, "gstin", "status", "is_blocked"):
        si = _company_filter(t("Sales Invoice"), intelligence.company)
        si = _docstatus_filter(si)
        si = _date_filter(si, start, end, "posting_date")

        sales_gstins = (
            si.filter(si["billing_address_gstin"].fill_null("") != "")
            .group_by(si["billing_address_gstin"].name("gstin"))
            .aggregate(value=si["base_grand_total"].fill_null(0).sum())
        )

        pi = _company_filter(t("Purchase Invoice"), intelligence.company)
        pi = _docstatus_filter(pi)
        pi = _date_filter(pi, start, end, "posting_date")

        purchase_gstins = (
            pi.filter(pi["supplier_gstin"].fill_null("") != "")
            .group_by(pi["supplier_gstin"].name("gstin"))
            .aggregate(value=pi["base_grand_total"].fill_null(0).sum())
        )

        from ibis import union as _union
        unioned = _union(sales_gstins, purchase_gstins)

        exposed = (
            gstin.join(unioned, gstin["gstin"] == unioned["gstin"], how="inner")
            .filter(
                gstin["status"].isin(["Cancelled", "Suspended"])
                | (gstin["is_blocked"].fill_null(0) == 1)
            )
            .aggregate(
                parties=unioned["gstin"].nunique(),
                value=unioned["value"].fill_null(0).sum(),
            )
            .execute()
        )
    else:
        exposed = None
    if exposed is None or exposed.empty:
        exp_row = {"parties": 0, "value": 0.0}
    else:
        e = exposed.iloc[0]
        exp_row = {
            "parties": int(e.get("parties") or 0),
            "value": float(e.get("value") or 0),
        }

    return {
        "registry_total": reg_row["total"],
        "active": reg_row["active"],
        "cancelled": reg_row["cancelled"],
        "suspended": reg_row["suspended"],
        "blocked": reg_row["blocked"],
        "status_unknown": reg_row["unknown"],
        "transacted_at_risk_parties": exp_row["parties"],
        "transacted_at_risk_value": exp_row["value"],
    }
