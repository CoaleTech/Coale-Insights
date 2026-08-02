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


def _india_compliance_error() -> Dict[str, Any]:
    return {"error": "india_compliance not installed"}


def _gst_component(alias: str) -> str:
    """SQL expression classifying one tax row into its GST component.

    Neither available field is sufficient alone, which is why this exists:

    - `gst_tax_type` is india_compliance's own splitter and is authoritative
      when set, but it is only backfilled on recent rows. Measured on this site:
      668 of 843 sales CGST rows carry it, so trusting it alone reported
      Rs 3.98M of output CGST against an actual Rs 24.99M.
    - `account_head` covers every row but is company-specific naming.

    So prefer the explicit field and fall back to the head. RCM heads are tested
    first because 'Input Tax CGST RCM' matches both the RCM and the plain CGST
    pattern. Rows matching nothing (freight, carriage, rounding) classify NULL
    and are excluded from GST totals, which is correct.

    Validated against account_head ground truth: sales CGST/SGST/IGST
    24,989,965 / 24,989,965 / 38,868,746 and purchase CGST/IGST
    15,071,908 / 11,378,183 both reconcile exactly.

    NOTE: the columns this module previously used (`cgst_amount`, `sgst_amount`,
    `igst_amount`, `cess_amount`) do not exist on the tax tables in any version
    of india_compliance installed here. Every query using them raised
    "Unknown column" and was swallowed by the caller's `_safe`, which is why the
    dashboard rendered zeros against non-zero data.
    """
    return f"""
        CASE
            WHEN NULLIF({alias}.gst_tax_type, '') IS NOT NULL THEN {alias}.gst_tax_type
            WHEN {alias}.account_head LIKE '%%CGST%%RCM%%' THEN 'cgst_rcm'
            WHEN {alias}.account_head LIKE '%%SGST%%RCM%%' THEN 'sgst_rcm'
            WHEN {alias}.account_head LIKE '%%IGST%%RCM%%' THEN 'igst_rcm'
            WHEN {alias}.account_head LIKE '%%CGST%%'      THEN 'cgst'
            WHEN {alias}.account_head LIKE '%%SGST%%'      THEN 'sgst'
            WHEN {alias}.account_head LIKE '%%IGST%%'      THEN 'igst'
            WHEN {alias}.account_head LIKE '%%Cess%%'      THEN 'cess'
        END
    """


def _component_sum(alias: str, *components: str) -> str:
    """SUM of `base_tax_amount` for the named GST components.

    SECURITY: this builds SQL *structure*, not values, so it is interpolated
    rather than parameterised — a placeholder cannot stand in for a CASE
    expression. Both arguments are closed sets supplied only by this module:
    `alias` is 'stc' or 'ptc', and `components` are the fixed component names.
    No caller passes user input, and every actual filter value in these queries
    (company, start, end) is a bound `%(name)s` parameter.

    semgrep's `frappe-sql-format-injection` flags the two query builders that
    consume this as WARNINGs. They are accepted deliberately: the rule taints any
    f-string reaching `frappe.db.sql` and cannot see that these operands are
    literals. Silencing it would mean inlining this CASE expression twice per
    query, duplicating roughly 40 lines of SQL and making a drift between the
    sales and purchase classifiers possible. Keep the single definition.
    """
    wanted = ", ".join(f"'{c}'" for c in components)
    return (
        f"COALESCE(SUM(CASE WHEN {_gst_component(alias)} IN ({wanted}) "
        f"THEN {alias}.base_tax_amount ELSE 0 END), 0)"
    )


def get_gst_output_tax(intelligence, start: str, end: str) -> List[Dict[str, Any]]:
    """Monthly output GST from submitted Sales Invoices, split by component.

    RCM output is reported separately: under reverse charge the recipient pays,
    so folding it into ordinary output liability would double count.
    """
    params = {"company": intelligence.company, "start": start, "end": end}
    sql = f"""
        SELECT
            DATE_FORMAT(si.posting_date, '%%Y-%%m')            AS month,
            {_component_sum('stc', 'cgst')}                    AS cgst,
            {_component_sum('stc', 'sgst')}                    AS sgst,
            {_component_sum('stc', 'igst')}                    AS igst,
            {_component_sum('stc', 'cess')}                    AS cess,
            {_component_sum('stc', 'cgst_rcm', 'sgst_rcm', 'igst_rcm')} AS rcm,
            COALESCE(SUM(DISTINCT si.base_net_total), 0)       AS total_revenue,
            COUNT(DISTINCT si.name)                            AS invoice_count
        FROM `tabSales Invoice` si
        LEFT JOIN `tabSales Taxes and Charges` stc ON stc.parent = si.name
        WHERE si.docstatus = 1
          AND si.company = %(company)s
          AND si.posting_date BETWEEN %(start)s AND %(end)s
        GROUP BY DATE_FORMAT(si.posting_date, '%%Y-%%m')
        ORDER BY month
        """
    return frappe.db.sql(sql, params, as_dict=True)


def get_gst_input_tax(intelligence, start: str, end: str) -> List[Dict[str, Any]]:
    """Monthly input GST (ITC) from submitted Purchase Invoices, split by component."""
    params = {"company": intelligence.company, "start": start, "end": end}
    sql = f"""
        SELECT
            DATE_FORMAT(pi.posting_date, '%%Y-%%m')            AS month,
            {_component_sum('ptc', 'cgst')}                    AS cgst,
            {_component_sum('ptc', 'sgst')}                    AS sgst,
            {_component_sum('ptc', 'igst')}                    AS igst,
            {_component_sum('ptc', 'cess')}                    AS cess,
            {_component_sum('ptc', 'cgst_rcm', 'sgst_rcm', 'igst_rcm')} AS rcm,
            COALESCE(SUM(DISTINCT pi.base_net_total), 0)       AS total_purchase,
            COUNT(DISTINCT pi.name)                            AS invoice_count
        FROM `tabPurchase Invoice` pi
        LEFT JOIN `tabPurchase Taxes and Charges` ptc ON ptc.parent = pi.name
        WHERE pi.docstatus = 1
          AND pi.company = %(company)s
          AND pi.posting_date BETWEEN %(start)s AND %(end)s
        GROUP BY DATE_FORMAT(pi.posting_date, '%%Y-%%m')
        ORDER BY month
        """
    return frappe.db.sql(sql, params, as_dict=True)



def get_itc_health(intelligence, start: str, end: str) -> Dict[str, Any]:
    """ITC position, blocked credits, and the risks that actually deny credit.

    Beyond arithmetic, this reports the two things that decide whether claimed
    ITC survives scrutiny:

    - Sec 16(2)(aa): credit is only available if the supplier filed GSTR-1 and
      the invoice appears in our GSTR-2B. Inward supplies where the supplier has
      not filed are credit we may have to reverse.
    - Reconciliation currency: 2A/2B data older than the purchase ledger means
      the comparison is not evidence of anything. Reported as `recon_through`
      so the number carries its own caveat.
    """
    if not intelligence.india_compliance_installed:
        return _india_compliance_error()

    params = {"company": intelligence.company, "start": start, "end": end}

    sql = f"""
        SELECT {_component_sum('ptc', 'cgst', 'sgst', 'igst', 'cess')} AS total
        FROM `tabPurchase Invoice` pi
        JOIN `tabPurchase Taxes and Charges` ptc ON ptc.parent = pi.name
        WHERE pi.docstatus = 1
          AND pi.company = %(company)s
          AND pi.posting_date BETWEEN %(start)s AND %(end)s
          AND ptc.add_deduct_tax = 'Add'
        """
    available = frappe.db.sql(sql, params, as_dict=True)[0].get("total", 0) or 0

    # Reverse-charge ITC is tracked apart: we self-assess and pay it, so it is
    # available credit but not supplier-dependent.
    sql = f"""
        SELECT {_component_sum('ptc', 'cgst_rcm', 'sgst_rcm', 'igst_rcm')} AS total
        FROM `tabPurchase Invoice` pi
        JOIN `tabPurchase Taxes and Charges` ptc ON ptc.parent = pi.name
        WHERE pi.docstatus = 1
          AND pi.company = %(company)s
          AND pi.posting_date BETWEEN %(start)s AND %(end)s
        """
    rcm_itc = frappe.db.sql(sql, params, as_dict=True)[0].get("total", 0) or 0

    claimed = frappe.db.sql(
        """
        -- Input tax accounts are assets: ITC accrues as a DEBIT. Summing
        -- `credit - debit` returned it negative, inverting utilisation.
        SELECT COALESCE(SUM(gle.debit - gle.credit), 0) AS total
        FROM `tabGL Entry` gle
        JOIN `tabAccount` acc ON gle.account = acc.name
        WHERE gle.company = %(company)s
          AND gle.posting_date BETWEEN %(start)s AND %(end)s
          AND gle.is_cancelled = 0
          AND (
              LOWER(acc.account_name) LIKE '%%input cgst%%'
              OR LOWER(acc.account_name) LIKE '%%input sgst%%'
              OR LOWER(acc.account_name) LIKE '%%input igst%%'
              OR LOWER(acc.account_name) LIKE '%%input tax%%'
          )
        """,
        params,
        as_dict=True,
    )[0].get("total", 0) or 0

    # Sec 17(5) blocked credits. `expense_account` lives on Purchase Invoice
    # Item, not on the invoice: the previous query read `pi.expense_account`,
    # which does not exist and made this branch unreachable.
    sql = f"""
        SELECT {_component_sum('ptc', 'cgst', 'sgst', 'igst', 'cess')} AS total
        FROM `tabPurchase Invoice` pi
        JOIN `tabPurchase Taxes and Charges` ptc ON ptc.parent = pi.name
        WHERE pi.docstatus = 1
          AND pi.company = %(company)s
          AND pi.posting_date BETWEEN %(start)s AND %(end)s
          AND (
              EXISTS (
                  SELECT 1 FROM `tabPurchase Invoice Item` pii
                  WHERE pii.parent = pi.name
                    AND (
                        LOWER(pii.expense_account) LIKE '%%motor vehicle%%'
                        OR LOWER(pii.expense_account) LIKE '%%vehicle expense%%'
                        OR LOWER(pii.expense_account) LIKE '%%food%%'
                        OR LOWER(pii.expense_account) LIKE '%%beverage%%'
                        OR LOWER(pii.expense_account) LIKE '%%catering%%'
                        OR LOWER(pii.expense_account) LIKE '%%canteen%%'
                        OR LOWER(pii.expense_account) LIKE '%%restaurant%%'
                        OR LOWER(pii.expense_account) LIKE '%%health service%%'
                        OR LOWER(pii.expense_account) LIKE '%%beauty treatment%%'
                        OR LOWER(pii.expense_account) LIKE '%%club membership%%'
                        OR LOWER(pii.expense_account) LIKE '%%gym%%'
                        OR LOWER(pii.expense_account) LIKE '%%fitness cent%%'
                        OR LOWER(pii.expense_account) LIKE '%%life insurance%%'
                        OR LOWER(pii.expense_account) LIKE '%%entertainment%%'
                        OR LOWER(pii.expense_account) LIKE '%%works contract%%'
                        OR LOWER(pii.expense_account) LIKE '%%construction%%'
                        OR LOWER(pii.expense_account) LIKE '%%civil work%%'
                    )
              )
              OR LOWER(pi.remarks) LIKE '%%ineligible%%'
              OR LOWER(pi.remarks) LIKE '%%blocked%%'
              OR LOWER(pi.remarks) LIKE '%%17(5)%%'
          )
        """
    ineligible = frappe.db.sql(sql, params, as_dict=True)[0].get("total", 0) or 0

    # Sec 16(2)(aa): supplier has not filed GSTR-1, so this credit is not
    # supported by GSTR-2B and is exposed on reversal.
    at_risk = frappe.db.sql(
        """
        SELECT
            COUNT(*) AS invoices,
            COALESCE(SUM(IFNULL(igst,0) + IFNULL(cgst,0) + IFNULL(sgst,0) + IFNULL(cess,0)), 0) AS tax
        FROM `tabGST Inward Supply`
        WHERE company = %(company)s
          AND IFNULL(gstr_1_filled, 0) = 0
        """,
        {"company": intelligence.company},
        as_dict=True,
    )[0]

    recon = frappe.db.sql(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN IFNULL(action, 'No Action') = 'No Action' THEN 1 ELSE 0 END) AS unactioned,
            SUM(CASE WHEN match_status = 'Mismatch' THEN 1 ELSE 0 END) AS mismatched,
            MAX(bill_date) AS recon_through
        FROM `tabGST Inward Supply`
        WHERE company = %(company)s
        """,
        {"company": intelligence.company},
        as_dict=True,
    )[0]

    available_f = float(available)
    claimed_f = float(claimed)
    ineligible_f = float(ineligible)
    utilizable = max(0.0, available_f - ineligible_f)
    utilization_pct = round((claimed_f / utilizable * 100), 2) if utilizable > 0 else 0.0

    return {
        "available": available_f,
        "claimed": claimed_f,
        "ineligible": ineligible_f,
        "utilizable": utilizable,
        "utilization_pct": utilization_pct,
        "rcm_itc": float(rcm_itc),
        "at_risk_supplier_unfiled": float(at_risk.get("tax", 0) or 0),
        "at_risk_invoice_count": int(at_risk.get("invoices", 0) or 0),
        "recon_total": int(recon.get("total", 0) or 0),
        "recon_unactioned": int(recon.get("unactioned", 0) or 0),
        "recon_mismatched": int(recon.get("mismatched", 0) or 0),
        "recon_through": str(recon.get("recon_through") or ""),
    }


def get_tds_summary(intelligence, start: str, end: str) -> Dict[str, Any]:
    """TDS deducted by us, TDS suffered on our income, and the net position.

    `add_deduct_tax` exists on Purchase Taxes and Charges but NOT on Sales Taxes
    and Charges: the previous receivable query filtered on `stc.add_deduct_tax`
    and raised "Unknown column", zeroing the whole section. TDS suffered on
    sales is identified by the account head alone.
    """
    params = {"company": intelligence.company, "start": start, "end": end}

    payable_by_section = frappe.db.sql(
        """
        SELECT
            ptc.account_head AS section,
            COALESCE(SUM(ptc.base_tax_amount), 0) AS amount,
            COUNT(DISTINCT pi.name) AS transaction_count
        FROM `tabPurchase Invoice` pi
        JOIN `tabPurchase Taxes and Charges` ptc ON ptc.parent = pi.name
        WHERE pi.docstatus = 1
          AND pi.company = %(company)s
          AND pi.posting_date BETWEEN %(start)s AND %(end)s
          AND (
              LOWER(ptc.account_head) LIKE '%%tds%%'
              OR LOWER(ptc.account_head) LIKE '%%tax deducted%%'
          )
        GROUP BY ptc.account_head
        ORDER BY amount DESC
        """,
        params,
        as_dict=True,
    )

    total_payable = sum(abs(float(row.get("amount", 0) or 0)) for row in payable_by_section)

    receivable = frappe.db.sql(
        """
        SELECT COALESCE(SUM(ABS(stc.base_tax_amount)), 0) AS total
        FROM `tabSales Invoice` si
        JOIN `tabSales Taxes and Charges` stc ON stc.parent = si.name
        WHERE si.docstatus = 1
          AND si.company = %(company)s
          AND si.posting_date BETWEEN %(start)s AND %(end)s
          AND (
              LOWER(stc.account_head) LIKE '%%tds%%'
              OR LOWER(stc.account_head) LIKE '%%tax deducted%%'
              OR LOWER(stc.account_head) LIKE '%%tcs%%'
          )
        """,
        params,
        as_dict=True,
    )[0].get("total", 0) or 0

    # Coverage: how much of our TDS configuration is actually reaching invoices.
    # 145 categories configured against a handful of tagged invoices is a
    # deduction-coverage question, not a reporting one.
    coverage = frappe.db.sql(
        """
        SELECT
            (SELECT COUNT(*) FROM `tabTax Withholding Category`) AS categories_configured,
            (SELECT COUNT(*) FROM `tabSupplier` WHERE IFNULL(tax_withholding_category, '') <> '')
                AS suppliers_mapped,
            (SELECT COUNT(*) FROM `tabSupplier` WHERE IFNULL(disabled, 0) = 0) AS suppliers_total,
            (SELECT COUNT(*) FROM `tabPurchase Invoice`
               WHERE docstatus = 1 AND company = %(company)s
                 AND posting_date BETWEEN %(start)s AND %(end)s
                 AND IFNULL(apply_tds, 0) = 1) AS invoices_with_tds,
            (SELECT COUNT(*) FROM `tabPurchase Invoice`
               WHERE docstatus = 1 AND company = %(company)s
                 AND posting_date BETWEEN %(start)s AND %(end)s) AS invoices_total
        """,
        params,
        as_dict=True,
    )[0]

    receivable_f = float(receivable)

    return {
        "payable_by_section": [
            {
                "section": row.get("section", ""),
                "amount": abs(float(row.get("amount", 0) or 0)),
                "transaction_count": row.get("transaction_count", 0),
                **_enrich_tds_section(row.get("section", "")),
            }
            for row in payable_by_section
        ],
        "total_payable": total_payable,
        "receivable": receivable_f,
        "net_position": receivable_f - total_payable,
        "categories_configured": int(coverage.get("categories_configured", 0) or 0),
        "suppliers_mapped": int(coverage.get("suppliers_mapped", 0) or 0),
        "suppliers_total": int(coverage.get("suppliers_total", 0) or 0),
        "invoices_with_tds": int(coverage.get("invoices_with_tds", 0) or 0),
        "invoices_total": int(coverage.get("invoices_total", 0) or 0),
    }


def get_einvoice_status(intelligence, start: str, end: str) -> Dict[str, Any]:
    """e-Invoice (IRN) coverage measured only against invoices that need an IRN.

    Counting every invoice overstates non-compliance badly. B2C / unregistered
    supplies require no IRN, so on this site a naive count reported 251 "missing"
    when 154 of those were exempt. Exports DO require an IRN.

    `gst_category` values that require an IRN: Registered Regular, Registered
    Composition, SEZ (with or without payment), Deemed Export, Overseas.
    Exempt: Unregistered, and UIN Holders.
    """
    if not intelligence.india_compliance_installed:
        return _india_compliance_error()

    result = frappe.db.sql(
        """
        SELECT
            COUNT(*) AS all_invoices,
            SUM(CASE WHEN needs_irn = 1 THEN 1 ELSE 0 END) AS total,
            SUM(CASE WHEN needs_irn = 1 AND has_irn = 1 THEN 1 ELSE 0 END) AS filed,
            SUM(CASE WHEN needs_irn = 1 AND has_irn = 0 THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN needs_irn = 0 THEN 1 ELSE 0 END) AS exempt,
            COALESCE(SUM(CASE WHEN needs_irn = 1 AND has_irn = 0 THEN grand ELSE 0 END), 0)
                AS pending_value
        FROM (
            SELECT
                si.base_grand_total AS grand,
                CASE WHEN IFNULL(si.irn, '') <> '' THEN 1 ELSE 0 END AS has_irn,
                CASE WHEN si.gst_category IN (
                        'Registered Regular', 'Registered Composition',
                        'SEZ supply with payment of tax',
                        'SEZ supply without payment of tax',
                        'Deemed Export', 'Overseas'
                     ) THEN 1 ELSE 0 END AS needs_irn
            FROM `tabSales Invoice` si
            WHERE si.docstatus = 1
              AND si.company = %(company)s
              AND si.posting_date BETWEEN %(start)s AND %(end)s
        ) x
        """,
        {"company": intelligence.company, "start": start, "end": end},
        as_dict=True,
    )[0]

    total = int(result.get("total", 0) or 0)
    filed = int(result.get("filed", 0) or 0)
    pending = int(result.get("pending", 0) or 0)
    coverage_pct = round((filed / total * 100), 2) if total > 0 else 0.0

    return {
        "total": total,
        "filed": filed,
        "pending": pending,
        # No `einvoice_status` field exists on Sales Invoice in this install, so
        # a failed-generation count is not observable here. Reported as 0 rather
        # than invented.
        "failed": 0,
        "exempt": int(result.get("exempt", 0) or 0),
        "all_invoices": int(result.get("all_invoices", 0) or 0),
        "pending_value": float(result.get("pending_value", 0) or 0),
        "coverage_pct": coverage_pct,
    }


def get_ewaybill_status(intelligence, start: str, end: str) -> Dict[str, Any]:
    """e-Waybill coverage from `e_waybill_status`.

    The previous query read `si.ewaybill_cancelled`, which does not exist, so the
    section was always empty. The real state lives in `e_waybill_status`
    ('Not Applicable' / 'Pending' / 'Manually Generated' / 'Generated') with the
    number itself in `ewaybill`.
    """
    if not intelligence.india_compliance_installed:
        return _india_compliance_error()

    by_status = frappe.db.sql(
        """
        SELECT
            IFNULL(NULLIF(si.e_waybill_status, ''), 'Not Set') AS ewb_status,
            COUNT(*) AS count,
            COALESCE(SUM(si.base_grand_total), 0) AS value
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.company = %(company)s
          AND si.posting_date BETWEEN %(start)s AND %(end)s
        -- Grouped by the expression, not an alias named `status`: Sales Invoice
        -- has its own `status` column (Paid / Overdue / Unpaid) and MariaDB binds
        -- the real column first. That split one e-Waybill state into three rows
        -- keyed by payment status, and the dict built from them collapsed 65
        -- pending waybills down to 4.
        GROUP BY IFNULL(NULLIF(si.e_waybill_status, ''), 'Not Set')
        ORDER BY count DESC
        """,
        {"company": intelligence.company, "start": start, "end": end},
        as_dict=True,
    )

    counts = {row["ewb_status"]: int(row["count"]) for row in by_status}
    total = sum(counts.values())
    pending = counts.get("Pending", 0)
    generated = counts.get("Generated", 0) + counts.get("Manually Generated", 0)

    return {
        "total": total,
        "active": generated,
        "pending": pending,
        "not_applicable": counts.get("Not Applicable", 0),
        # Cancellations are logged, not flagged on the invoice.
        "cancelled": frappe.db.count("e-Waybill Log", {"is_cancelled": 1}),
        "by_status": [
            {
                "status": r["ewb_status"],
                "count": int(r["count"]),
                "value": float(r["value"] or 0),
            }
            for r in by_status
        ],
    }


def get_filing_compliance(intelligence, start: str, end: str) -> Dict[str, Any]:
    """GSTR-1 / GSTR-3B filing status from GST Return Log.

    Three faults were fixed here, each of which alone emptied the section:

    - `tabGSTR-3B Entry` does not exist in any installed india_compliance
      version. The real log for every return type is `GST Return Log`,
      discriminated by `return_type`.
    - `tabGSTR-1 Log` is a legacy table left behind by a rename; it holds 0 rows.
      The live DocType `GSTR-1` is a Single and stores no per-period rows.
    - `return_period` is an `MMYYYY` string, so `BETWEEN '2026-04-01' AND
      '2027-03-31'` could never match. It is normalised to `YYYY-MM` here.

    Filing status is reported as observed. On this site `filing_status` is NULL
    on every row, so the honest answer is "not tracked", not "compliant".
    """
    if not intelligence.india_compliance_installed:
        return _india_compliance_error()

    def _returns(return_type: str) -> Dict[str, Any]:
        return frappe.db.sql(
            """
            SELECT
                COUNT(*) AS total_returns,
                SUM(CASE WHEN filing_status = 'Filed' THEN 1 ELSE 0 END) AS filed,
                SUM(CASE WHEN IFNULL(filing_status, '') = '' THEN 1 ELSE 0 END) AS unknown,
                SUM(CASE WHEN filing_status IN ('Not Filed', 'Pending') THEN 1 ELSE 0 END) AS pending,
                MAX(return_period) AS latest_period
            FROM `tabGST Return Log`
            WHERE company = %(company)s
              AND return_type = %(return_type)s
              AND CONCAT(SUBSTRING(return_period, 3, 4), '-', SUBSTRING(return_period, 1, 2))
                  BETWEEN DATE_FORMAT(%(start)s, '%%Y-%%m') AND DATE_FORMAT(%(end)s, '%%Y-%%m')
            """,
            {
                "company": intelligence.company,
                "return_type": return_type,
                "start": start,
                "end": end,
            },
            as_dict=True,
        )[0]

    gstr1 = _returns("GSTR1")
    gstr3b = _returns("GSTR3B")

    def _status(row) -> str:
        total = int(row.get("total_returns", 0) or 0)
        if total == 0:
            return "No Data"
        if int(row.get("unknown", 0) or 0) == total:
            return "Not Tracked"
        if int(row.get("filed", 0) or 0) == total:
            return "Compliant"
        return "Pending"

    def _shape(row) -> Dict[str, Any]:
        return {
            "total": int(row.get("total_returns", 0) or 0),
            "filed": int(row.get("filed", 0) or 0),
            "pending": int(row.get("pending", 0) or 0),
            "unknown": int(row.get("unknown", 0) or 0),
            "late": 0,
            "latest_period": row.get("latest_period") or "",
            "status": _status(row),
        }

    # Periods logged at all, regardless of the reporting window, so a window with
    # no returns does not read as "nothing has ever been filed".
    logged_all_time = frappe.db.sql(
        """
        SELECT return_type, COUNT(*) AS n, MAX(return_period) AS latest
        FROM `tabGST Return Log`
        WHERE company = %(company)s
        GROUP BY return_type
        """,
        {"company": intelligence.company},
        as_dict=True,
    )

    return {
        "gstr1": _shape(gstr1),
        "gstr3b": _shape(gstr3b),
        "logged_all_time": [
            {"return_type": r["return_type"], "count": int(r["n"]), "latest_period": r["latest"] or ""}
            for r in logged_all_time
        ],
    }


def get_reconciliation_score(intelligence, start: str, end: str) -> Dict[str, Any]:
    """Purchase reconciliation against GSTR-2A/2B inward supplies.

    Two faults were fixed: the table has no `posting_date` (the supplier document
    date is `bill_date`), and the previous filter looked for match statuses
    'Matched' / 'Unmatched' which india_compliance never writes. The real values
    are 'Exact Match', 'Suggested Match', 'Mismatch', and blank for rows with no
    counterpart in the books.

    `data_through` is returned so the score is read with its own caveat: 2A/2B
    data older than the purchase ledger means the comparison covers only part of
    the period.
    """
    if not intelligence.india_compliance_installed:
        return _india_compliance_error()

    rows = frappe.db.sql(
        """
        SELECT
            IFNULL(NULLIF(match_status, ''), 'Unlinked') AS match_status,
            COALESCE(SUM(IFNULL(taxable_value,0) + IFNULL(cgst,0) + IFNULL(sgst,0)
                         + IFNULL(igst,0) + IFNULL(cess,0)), 0) AS amount,
            COUNT(*) AS count
        FROM `tabGST Inward Supply`
        WHERE company = %(company)s
        GROUP BY match_status
        """,
        {"company": intelligence.company},
        as_dict=True,
    )
    by_status = {r["match_status"]: r for r in rows}

    def pick(key):
        r = by_status.get(key) or {"amount": 0, "count": 0}
        return int(r.get("count", 0) or 0), float(r.get("amount", 0) or 0)

    exact_count, exact_amount = pick("Exact Match")
    suggested_count, suggested_amount = pick("Suggested Match")
    mismatch_count, mismatch_amount = pick("Mismatch")
    unlinked_count, unlinked_amount = pick("Unlinked")

    total_count = exact_count + suggested_count + mismatch_count + unlinked_count

    span = frappe.db.sql(
        """
        SELECT MIN(bill_date) AS from_date, MAX(bill_date) AS to_date,
               SUM(CASE WHEN IFNULL(action, 'No Action') = 'No Action' THEN 1 ELSE 0 END) AS unactioned
        FROM `tabGST Inward Supply` WHERE company = %(company)s
        """,
        {"company": intelligence.company},
        as_dict=True,
    )[0]

    return {
        # Exact matches are the only ones needing no human decision.
        "matched_count": exact_count,
        "matched_amount": exact_amount,
        "suggested_count": suggested_count,
        "suggested_amount": suggested_amount,
        "mismatch_count": mismatch_count,
        "mismatch_amount": mismatch_amount,
        "unmatched_count": unlinked_count,
        "unmatched_amount": unlinked_amount,
        "total_count": total_count,
        "unactioned_count": int(span.get("unactioned", 0) or 0),
        "data_from": str(span.get("from_date") or ""),
        "data_through": str(span.get("to_date") or ""),
        "reconciliation_score": (
            round((exact_count / total_count * 100), 2) if total_count > 0 else 0.0
        ),
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


def get_counterparty_risk(intelligence, start: str, end: str) -> Dict[str, Any]:
    """Registration health of the GSTINs we transact with.

    This is the ITC risk that no amount of internal bookkeeping fixes. Credit
    taken on an invoice from a supplier whose registration was cancelled or
    suspended is challenged by the department, and a GSTIN blocked under
    Rule 86A cannot have its credit utilised at all.

    Counts come from the GSTIN registry india_compliance maintains, so they
    reflect the portal's status rather than our own master data.
    """
    if not intelligence.india_compliance_installed:
        return _india_compliance_error()

    registry = frappe.db.sql(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status = 'Active' THEN 1 ELSE 0 END) AS active,
            SUM(CASE WHEN status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled,
            SUM(CASE WHEN status = 'Suspended' THEN 1 ELSE 0 END) AS suspended,
            SUM(CASE WHEN IFNULL(is_blocked, 0) = 1 THEN 1 ELSE 0 END) AS blocked,
            SUM(CASE WHEN IFNULL(status, '') = '' THEN 1 ELSE 0 END) AS unknown
        FROM `tabGSTIN`
        """,
        as_dict=True,
    )[0]

    # Only the counterparties we actually billed or bought from in the window
    # matter for this period's exposure.
    exposed = frappe.db.sql(
        """
        SELECT COUNT(DISTINCT g.gstin) AS parties,
               COALESCE(SUM(x.value), 0) AS value
        FROM `tabGSTIN` g
        JOIN (
            SELECT billing_address_gstin AS gstin, SUM(base_grand_total) AS value
            FROM `tabSales Invoice`
            WHERE docstatus = 1 AND company = %(company)s
              AND posting_date BETWEEN %(start)s AND %(end)s
              AND IFNULL(billing_address_gstin, '') <> ''
            GROUP BY billing_address_gstin
            UNION ALL
            SELECT supplier_gstin AS gstin, SUM(base_grand_total) AS value
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1 AND company = %(company)s
              AND posting_date BETWEEN %(start)s AND %(end)s
              AND IFNULL(supplier_gstin, '') <> ''
            GROUP BY supplier_gstin
        ) x ON x.gstin = g.gstin
        WHERE g.status IN ('Cancelled', 'Suspended') OR IFNULL(g.is_blocked, 0) = 1
        """,
        {"company": intelligence.company, "start": start, "end": end},
        as_dict=True,
    )[0]

    return {
        "registry_total": int(registry.get("total", 0) or 0),
        "active": int(registry.get("active", 0) or 0),
        "cancelled": int(registry.get("cancelled", 0) or 0),
        "suspended": int(registry.get("suspended", 0) or 0),
        "blocked": int(registry.get("blocked", 0) or 0),
        "status_unknown": int(registry.get("unknown", 0) or 0),
        "transacted_at_risk_parties": int(exposed.get("parties", 0) or 0),
        "transacted_at_risk_value": float(exposed.get("value", 0) or 0),
    }
