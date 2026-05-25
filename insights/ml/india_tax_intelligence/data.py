# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""India Tax Intelligence — Data Collection

Queries GST, ITC, TDS, e-Invoice, e-Waybill, HSN and reconciliation data.
"""

import frappe
from typing import Dict, Any, List, Optional


def check_india_compliance_installed() -> bool:
    """Return True if the india_compliance app is installed."""
    return "india_compliance" in frappe.get_installed_apps()


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
    head_upper = account_head.upper()
    for code, meta in _TDS_SECTIONS.items():
        if code in head_upper:
            return {"section_code": code, **meta}
    return {"section_code": "", "description": account_head, "rate_pct": None, "threshold": ""}


# ---------------------------------------------------------------------------
# e-Invoice compliance thresholds (current as of FY 2025-26)
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
    ],
    "penalty_per_invoice_inr": 10000,        # Max ₹10,000 per invoice (Sec 122)
    "interest_rate_pct_pa": 24,              # On wrongful ITC claim reversal
}


def _india_compliance_error() -> Dict[str, Any]:
    return {"error": "india_compliance not installed"}


def get_gst_output_tax(intelligence, start: str, end: str) -> List[Dict[str, Any]]:
    """Monthly GST from submitted Sales Invoices.

    With india_compliance: returns split CGST / SGST / IGST from tax row columns.
    Without it: uses invoice-level totals (base_grand_total − base_net_total) as
    total GST reported in the igst field; cgst and sgst remain 0.
    """
    params = {"company": intelligence.company, "start": start, "end": end}

    if intelligence.india_compliance_installed:
        return frappe.db.sql(
            """
            SELECT
                DATE_FORMAT(si.posting_date, '%%Y-%%m')  AS month,
                COALESCE(SUM(stc.cgst_amount), 0)        AS cgst,
                COALESCE(SUM(stc.sgst_amount), 0)        AS sgst,
                COALESCE(SUM(stc.igst_amount), 0)        AS igst,
                COALESCE(SUM(si.base_net_total), 0)      AS total_revenue,
                COUNT(DISTINCT si.name)                   AS invoice_count
            FROM `tabSales Invoice` si
            LEFT JOIN `tabSales Taxes and Charges` stc ON stc.parent = si.name
            WHERE si.docstatus = 1
              AND si.company = %(company)s
              AND si.posting_date BETWEEN %(start)s AND %(end)s
            GROUP BY DATE_FORMAT(si.posting_date, '%%Y-%%m')
            ORDER BY month
            """,
            params,
            as_dict=True,
        )

    # Fallback: total tax = grand_total − net_total (no india_compliance columns needed)
    return frappe.db.sql(
        """
        SELECT
            DATE_FORMAT(si.posting_date, '%%Y-%%m')                          AS month,
            0                                                                  AS cgst,
            0                                                                  AS sgst,
            COALESCE(SUM(si.base_grand_total - si.base_net_total), 0)         AS igst,
            COALESCE(SUM(si.base_net_total), 0)                               AS total_revenue,
            COUNT(DISTINCT si.name)                                            AS invoice_count
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.company = %(company)s
          AND si.posting_date BETWEEN %(start)s AND %(end)s
        GROUP BY DATE_FORMAT(si.posting_date, '%%Y-%%m')
        ORDER BY month
        """,
        params,
        as_dict=True,
    )


def get_gst_input_tax(intelligence, start: str, end: str) -> List[Dict[str, Any]]:
    """Monthly input GST from submitted Purchase Invoices.

    With india_compliance: split CGST / SGST / IGST from tax row columns.
    Without it: total input tax via (base_grand_total − base_net_total) as igst.
    """
    params = {"company": intelligence.company, "start": start, "end": end}

    if intelligence.india_compliance_installed:
        return frappe.db.sql(
            """
            SELECT
                DATE_FORMAT(pi.posting_date, '%%Y-%%m')  AS month,
                COALESCE(SUM(ptc.cgst_amount), 0)        AS cgst,
                COALESCE(SUM(ptc.sgst_amount), 0)        AS sgst,
                COALESCE(SUM(ptc.igst_amount), 0)        AS igst,
                COALESCE(SUM(pi.base_net_total), 0)      AS total_purchase,
                COUNT(DISTINCT pi.name)                   AS invoice_count
            FROM `tabPurchase Invoice` pi
            LEFT JOIN `tabPurchase Taxes and Charges` ptc ON ptc.parent = pi.name
            WHERE pi.docstatus = 1
              AND pi.company = %(company)s
              AND pi.posting_date BETWEEN %(start)s AND %(end)s
            GROUP BY DATE_FORMAT(pi.posting_date, '%%Y-%%m')
            ORDER BY month
            """,
            params,
            as_dict=True,
        )

    return frappe.db.sql(
        """
        SELECT
            DATE_FORMAT(pi.posting_date, '%%Y-%%m')                          AS month,
            0                                                                  AS cgst,
            0                                                                  AS sgst,
            COALESCE(SUM(pi.base_grand_total - pi.base_net_total), 0)         AS igst,
            COALESCE(SUM(pi.base_net_total), 0)                               AS total_purchase,
            COUNT(DISTINCT pi.name)                                            AS invoice_count
        FROM `tabPurchase Invoice` pi
        WHERE pi.docstatus = 1
          AND pi.company = %(company)s
          AND pi.posting_date BETWEEN %(start)s AND %(end)s
        GROUP BY DATE_FORMAT(pi.posting_date, '%%Y-%%m')
        ORDER BY month
        """,
        params,
        as_dict=True,
    )


def get_itc_health(intelligence, start: str, end: str) -> Dict[str, Any]:
    """ITC availability, claims, ineligibility and utilization percentage."""
    if not intelligence.india_compliance_installed:
        return _india_compliance_error()

    # ITC available in Purchase Invoices (eligible for credit)
    available = frappe.db.sql(
        """
        SELECT
            COALESCE(SUM(ptc.cgst_amount + ptc.sgst_amount + ptc.igst_amount), 0) AS total
        FROM `tabPurchase Invoice` pi
        JOIN `tabPurchase Taxes and Charges` ptc ON ptc.parent = pi.name
        WHERE pi.docstatus = 1
          AND pi.company = %(company)s
          AND pi.posting_date BETWEEN %(start)s AND %(end)s
          AND ptc.add_deduct_tax = 'Add'
        """,
        {"company": intelligence.company, "start": start, "end": end},
        as_dict=True,
    )[0].get("total", 0) or 0

    # ITC claimed (assumed via GSTR-3B or Journal Entry against GST accounts)
    claimed = frappe.db.sql(
        """
        SELECT COALESCE(SUM(credit - debit), 0) AS total
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON gle.account = acc.name
        WHERE gle.company = %(company)s
          AND gle.posting_date BETWEEN %(start)s AND %(end)s
          AND gle.is_cancelled = 0
          AND (
              LOWER(acc.account_name) LIKE '%%input cgst%%'
              OR LOWER(acc.account_name) LIKE '%%input sgst%%'
              OR LOWER(acc.account_name) LIKE '%%input igst%%'
          )
        """,
        {"company": intelligence.company, "start": start, "end": end},
        as_dict=True,
    )[0].get("total", 0) or 0

    # Ineligible ITC — CGST Act Section 17(5): Blocked Credits
    # Clauses: (a) motor vehicles, (b) food/catering/beauty/health/insurance/club,
    #          (c)(d) works contract / construction of immovable property,
    #          (g) personal consumption, (h) gifts / samples / write-offs
    ineligible = frappe.db.sql(
        """
        SELECT COALESCE(SUM(ptc.cgst_amount + ptc.sgst_amount + ptc.igst_amount), 0) AS total
        FROM `tabPurchase Invoice` pi
        JOIN `tabPurchase Taxes and Charges` ptc ON ptc.parent = pi.name
        WHERE pi.docstatus = 1
          AND pi.company = %(company)s
          AND pi.posting_date BETWEEN %(start)s AND %(end)s
          AND (
              -- 17(5)(a): Motor vehicles (≤13-seater) unless for transport business
              LOWER(pi.expense_account) LIKE '%%motor vehicle%%'
              OR LOWER(pi.expense_account) LIKE '%%vehicle expense%%'
              -- 17(5)(b): Food, beverages, outdoor catering
              OR LOWER(pi.expense_account) LIKE '%%food%%'
              OR LOWER(pi.expense_account) LIKE '%%beverage%%'
              OR LOWER(pi.expense_account) LIKE '%%catering%%'
              OR LOWER(pi.expense_account) LIKE '%%canteen%%'
              OR LOWER(pi.expense_account) LIKE '%%restaurant%%'
              -- 17(5)(b): Health services, cosmetic / plastic surgery
              OR LOWER(pi.expense_account) LIKE '%%health service%%'
              OR LOWER(pi.expense_account) LIKE '%%cosmetic surgery%%'
              OR LOWER(pi.expense_account) LIKE '%%plastic surgery%%'
              OR LOWER(pi.expense_account) LIKE '%%beauty treatment%%'
              -- 17(5)(b): Club / gym / fitness centre memberships
              OR LOWER(pi.expense_account) LIKE '%%club membership%%'
              OR LOWER(pi.expense_account) LIKE '%%gym%%'
              OR LOWER(pi.expense_account) LIKE '%%fitness centre%%'
              OR LOWER(pi.expense_account) LIKE '%%fitness center%%'
              -- 17(5)(b): Life insurance / personal health insurance
              OR LOWER(pi.expense_account) LIKE '%%life insurance%%'
              OR LOWER(pi.expense_account) LIKE '%%personal insurance%%'
              -- 17(5)(b): Entertainment
              OR LOWER(pi.expense_account) LIKE '%%entertainment%%'
              -- 17(5)(c)(d): Works contract / construction of immovable property
              OR LOWER(pi.expense_account) LIKE '%%works contract%%'
              OR LOWER(pi.expense_account) LIKE '%%construction%%'
              OR LOWER(pi.expense_account) LIKE '%%civil work%%'
              -- Explicitly tagged via remarks (manual override)
              OR LOWER(pi.remarks) LIKE '%%ineligible%%'
              OR LOWER(pi.remarks) LIKE '%%blocked%%'
              OR LOWER(pi.remarks) LIKE '%%17(5)%%'
              OR LOWER(pi.remarks) LIKE '%%section 17%%'
          )
        """,
        {"company": intelligence.company, "start": start, "end": end},
        as_dict=True,
    )[0].get("total", 0) or 0

    available_f = float(available)
    claimed_f = float(claimed)
    ineligible_f = float(ineligible)
    utilizable = max(0, available_f - ineligible_f)
    utilization_pct = round((claimed_f / utilizable * 100), 2) if utilizable > 0 else 0.0

    return {
        "available": available_f,
        "claimed": claimed_f,
        "ineligible": ineligible_f,
        "utilizable": utilizable,
        "utilization_pct": utilization_pct,
    }


def get_tds_summary(intelligence, start: str, end: str) -> Dict[str, Any]:
    """TDS payable by section, total payable, receivable and net position."""
    # TDS deducted (payable) — we are the deductor
    payable_by_section = frappe.db.sql(
        """
        SELECT
            ptc.account_head AS section,
            COALESCE(SUM(ptc.tax_amount), 0) AS amount,
            COUNT(DISTINCT pi.name) AS transaction_count
        FROM `tabPurchase Invoice` pi
        JOIN `tabPurchase Taxes and Charges` ptc ON ptc.parent = pi.name
        WHERE pi.docstatus = 1
          AND pi.company = %(company)s
          AND pi.posting_date BETWEEN %(start)s AND %(end)s
          AND ptc.add_deduct_tax = 'Deduct'
          AND (
              LOWER(ptc.account_head) LIKE '%%tds%%'
              OR LOWER(ptc.account_head) LIKE '%%tax deducted%%'
          )
        GROUP BY ptc.account_head
        ORDER BY amount DESC
        """,
        {"company": intelligence.company, "start": start, "end": end},
        as_dict=True,
    )

    total_payable = sum(float(row.get("amount", 0)) for row in payable_by_section)

    # TDS receivable (suffered) — on our income
    receivable = frappe.db.sql(
        """
        SELECT COALESCE(SUM(stc.tax_amount), 0) AS total
        FROM `tabSales Invoice` si
        JOIN `tabSales Taxes and Charges` stc ON stc.parent = si.name
        WHERE si.docstatus = 1
          AND si.company = %(company)s
          AND si.posting_date BETWEEN %(start)s AND %(end)s
          AND stc.add_deduct_tax = 'Deduct'
          AND (
              LOWER(stc.account_head) LIKE '%%tds%%'
              OR LOWER(stc.account_head) LIKE '%%tax deducted%%'
          )
        """,
        {"company": intelligence.company, "start": start, "end": end},
        as_dict=True,
    )[0].get("total", 0) or 0

    receivable_f = float(receivable)
    net_position = receivable_f - total_payable

    return {
        "payable_by_section": [
            {
                "section": row.get("section", ""),
                "amount": float(row.get("amount", 0)),
                "transaction_count": row.get("transaction_count", 0),
                **_enrich_tds_section(row.get("section", "")),
            }
            for row in payable_by_section
        ],
        "total_payable": total_payable,
        "receivable": receivable_f,
        "net_position": net_position,
    }


def get_einvoice_status(intelligence, start: str, end: str) -> Dict[str, Any]:
    """e-Invoice filing status (requires india_compliance)."""
    if not intelligence.india_compliance_installed:
        return _india_compliance_error()

    result = frappe.db.sql(
        """
        SELECT
            COUNT(DISTINCT si.name) AS total,
            COUNT(DISTINCT CASE WHEN si.irn IS NOT NULL AND si.irn != '' THEN si.name END) AS filed,
            COUNT(DISTINCT CASE WHEN si.irn IS NULL OR si.irn = '' THEN si.name END) AS pending,
            COUNT(DISTINCT CASE WHEN si.einvoice_status = 'Failed' THEN si.name END) AS failed
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.company = %(company)s
          AND si.posting_date BETWEEN %(start)s AND %(end)s
        """,
        {"company": intelligence.company, "start": start, "end": end},
        as_dict=True,
    )[0]

    total = int(result.get("total", 0))
    filed = int(result.get("filed", 0))
    pending = int(result.get("pending", 0))
    failed = int(result.get("failed", 0))
    coverage_pct = round((filed / total * 100), 2) if total > 0 else 0.0

    return {
        "total": total,
        "filed": filed,
        "pending": pending,
        "failed": failed,
        "coverage_pct": coverage_pct,
    }


def get_ewaybill_status(intelligence, start: str, end: str) -> Dict[str, Any]:
    """e-Waybill status (requires india_compliance)."""
    if not intelligence.india_compliance_installed:
        return _india_compliance_error()

    result = frappe.db.sql(
        """
        SELECT
            COUNT(DISTINCT si.name) AS total,
            COUNT(DISTINCT CASE WHEN si.ewaybill IS NOT NULL AND si.ewaybill != '' THEN si.name END) AS active_count,
            COUNT(DISTINCT CASE WHEN si.ewaybill_cancelled = 1 THEN si.name END) AS cancelled_count
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.company = %(company)s
          AND si.posting_date BETWEEN %(start)s AND %(end)s
        """,
        {"company": intelligence.company, "start": start, "end": end},
        as_dict=True,
    )[0]

    total = int(result.get("total", 0))
    active_count = int(result.get("active_count", 0))
    cancelled_count = int(result.get("cancelled_count", 0))

    return {
        "total": total,
        "active": active_count,
        "cancelled": cancelled_count,
    }


def get_filing_compliance(intelligence, start: str, end: str) -> Dict[str, Any]:
    """GSTR-1 and GSTR-3B filing status (requires india_compliance)."""
    if not intelligence.india_compliance_installed:
        return _india_compliance_error()

    # GSTR-1 filing status
    gstr1 = frappe.db.sql(
        """
        SELECT
            COUNT(*) AS total_returns,
            SUM(CASE WHEN status = 'Filed' THEN 1 ELSE 0 END) AS filed,
            SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END) AS late
        FROM `tabGSTR-1 Log`
        WHERE company = %(company)s
          AND return_period BETWEEN %(start)s AND %(end)s
        """,
        {"company": intelligence.company, "start": start, "end": end},
        as_dict=True,
    )[0]

    # GSTR-3B filing status
    gstr3b = frappe.db.sql(
        """
        SELECT
            COUNT(*) AS total_returns,
            SUM(CASE WHEN status = 'Filed' THEN 1 ELSE 0 END) AS filed,
            SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END) AS late
        FROM `tabGSTR-3B Entry`
        WHERE company = %(company)s
          AND return_period BETWEEN %(start)s AND %(end)s
        """,
        {"company": intelligence.company, "start": start, "end": end},
        as_dict=True,
    )[0]

    def _compliance_status(row):
        total = int(row.get("total_returns", 0))
        filed = int(row.get("filed", 0))
        if total == 0:
            return "No Data"
        if filed == total:
            return "Compliant"
        if int(row.get("late", 0)) > 0:
            return "Late Filing"
        return "Pending"

    return {
        "gstr1": {
            "total": int(gstr1.get("total_returns", 0)),
            "filed": int(gstr1.get("filed", 0)),
            "pending": int(gstr1.get("pending", 0)),
            "late": int(gstr1.get("late", 0)),
            "status": _compliance_status(gstr1),
        },
        "gstr3b": {
            "total": int(gstr3b.get("total_returns", 0)),
            "filed": int(gstr3b.get("filed", 0)),
            "pending": int(gstr3b.get("pending", 0)),
            "late": int(gstr3b.get("late", 0)),
            "status": _compliance_status(gstr3b),
        },
    }


def get_reconciliation_score(intelligence, start: str, end: str) -> Dict[str, Any]:
    """Purchase reconciliation score from GST Inward Supply (requires india_compliance)."""
    if not intelligence.india_compliance_installed:
        return _india_compliance_error()

    rows = frappe.db.sql(
        """
        SELECT
            match_status,
            COALESCE(SUM(taxable_value + cgst + sgst + igst + cess), 0) AS amount,
            COUNT(*) AS count
        FROM `tabGST Inward Supply`
        WHERE company = %(company)s
          AND posting_date BETWEEN %(start)s AND %(end)s
          AND match_status IN ('Matched', 'Unmatched', 'Mismatch')
        GROUP BY match_status
        """,
        {"company": intelligence.company, "start": start, "end": end},
        as_dict=True,
    )
    by_status = {r["match_status"]: r for r in rows}
    matched   = by_status.get("Matched",   {"amount": 0, "count": 0})
    unmatched = by_status.get("Unmatched", {"amount": 0, "count": 0})
    mismatch  = by_status.get("Mismatch",  {"amount": 0, "count": 0})

    matched_count   = int(matched.get("count", 0))
    unmatched_count = int(unmatched.get("count", 0))
    mismatch_count  = int(mismatch.get("count", 0))
    total_count = matched_count + unmatched_count + mismatch_count

    return {
        "matched_count": matched_count,
        "matched_amount": float(matched.get("amount", 0)),
        "unmatched_count": unmatched_count,
        "unmatched_amount": float(unmatched.get("amount", 0)),
        "mismatch_count": mismatch_count,
        "mismatch_amount": float(mismatch.get("amount", 0)),
        "total_count": total_count,
        "reconciliation_score": round((matched_count / total_count * 100), 2) if total_count > 0 else 0.0,
    }


def get_hsn_summary(intelligence, start: str, end: str) -> List[Dict[str, Any]]:
    """Revenue, actual GST and invoice count by HSN code.

    GST is proportionally allocated to each item line using the invoice-level
    tax total (base_grand_total − base_net_total), avoiding a full-table scan
    of tabSales Taxes and Charges and the inaccurate blanket 18 % estimate.
    Works without india_compliance.
    """
    return frappe.db.sql(
        """
        SELECT
            sii.gst_hsn_code                           AS hsn_code,
            COALESCE(SUM(sii.base_amount), 0)           AS revenue,
            COALESCE(SUM(
                CASE WHEN si.base_net_total > 0
                THEN sii.base_net_amount
                     / si.base_net_total
                     * (si.base_grand_total - si.base_net_total)
                ELSE 0 END
            ), 0)                                       AS actual_gst,
            COUNT(DISTINCT si.name)                     AS invoice_count
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.docstatus = 1
          AND si.company   = %(company)s
          AND si.posting_date BETWEEN %(start)s AND %(end)s
        GROUP BY sii.gst_hsn_code
        ORDER BY revenue DESC
        """,
        {"company": intelligence.company, "start": start, "end": end},
        as_dict=True,
    )
