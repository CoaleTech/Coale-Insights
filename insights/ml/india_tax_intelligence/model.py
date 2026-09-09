# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""India Tax Intelligence — Orchestration Model.

Pure-Ibis; no training, no caching, no background work. Every section
(GST, ITC, TDS, e-Invoice, e-Waybill, filing, reconciliation, HSN,
counterparty) is computed on the request and returned in one envelope.
Compliance score is the only non-Ibis piece — a 0–100 weighted average
over the per-section Ibis-computed inputs.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List

import frappe

import insights.ml.india_tax_intelligence.analytics as _analytics
import insights.ml.india_tax_intelligence.data as _data
from insights.ml.india_tax_intelligence.data import EINVOICE_COMPLIANCE


# India FY = April–March. The dashboard's period selector offers three
# rolling windows (3m/6m/12m) and 'fy' (current fiscal year).
_PERIODS = ("3m", "6m", "12m", "fy")
_PERIOD_MONTHS = {"3m": 3, "6m": 6, "12m": 12}


def _today_date() -> date:
    return datetime.now().date()


def _fiscal_year_for(company: str | None) -> Dict[str, Any]:
    """Resolve the active Fiscal Year for the company.

    Falls back to the calendar year if no Fiscal Year covers today — that
    case shows up on test sites with no Fiscal Year record, and the
    legacy code did the same calendar fallback.
    """
    today = _today_date()
    FiscalYear = frappe.qb.DocType("Fiscal Year")
    FiscalYearCompany = frappe.qb.DocType("Fiscal Year Company")
    if company:
        rows = (
            frappe.qb.from_(FiscalYear)
            .left_join(FiscalYearCompany)
            .on(FiscalYearCompany.parent == FiscalYear.name)
            .select(FiscalYear.name, FiscalYear.year_start_date, FiscalYear.year_end_date)
            .where(FiscalYear.disabled == 0)
            .where((today >= FiscalYear.year_start_date) & (today <= FiscalYear.year_end_date))
            .where((FiscalYearCompany.company == company) | FiscalYearCompany.company.isnull())
            .orderby(FiscalYear.year_start_date, order=frappe.qb.desc)
            .limit(1)
            .run(as_dict=True)
        )
        if rows:
            return rows[0]
    rows = (
        frappe.qb.from_(FiscalYear)
        .select(FiscalYear.name, FiscalYear.year_start_date, FiscalYear.year_end_date)
        .where(FiscalYear.disabled == 0)
        .where((today >= FiscalYear.year_start_date) & (today <= FiscalYear.year_end_date))
        .orderby(FiscalYear.year_start_date, order=frappe.qb.desc)
        .limit(1)
        .run(as_dict=True)
    )
    if rows:
        return rows[0]
    return {
        "name": str(today.year),
        "year_start_date": date(today.year, 1, 1),
        "year_end_date": date(today.year, 12, 31),
    }


def _base_currency(company: str | None) -> str:
    if company:
        cur = frappe.db.get_value("Company", company, "default_currency")
        if cur:
            return cur
    return (
        frappe.db.get_single_value("Global Defaults", "default_currency")
        or "INR"
    )


def _default_company() -> str | None:
    return (
        frappe.defaults.get_user_default("Company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
    )


class IndiaTaxIntelligence:
    """India Tax Intelligence Engine.

    Composes pure-Ibis aggregators (see `data.py`) into the payload the
    dashboard consumes. No sklearn, no caching, no training — every call
    to `train()` / `predict()` produces a fresh result in one synchronous
    request.
    """

    PERIODS = _PERIODS

    def __init__(self, period: str = "fy"):
        self.model_name = "IndiaTaxIntelligence"
        from insights.api.ml.utils import parse_custom_range

        self.period = period if (period in _PERIODS or parse_custom_range(period)) else "fy"
        self.company = _default_company()
        self.base_currency = _base_currency(self.company)
        self.fiscal_year = _fiscal_year_for(self.company) if self.company else None
        self.india_compliance_installed = _data.check_india_compliance_installed()

    # ------------------------------------------------------------------ window
    def _window(self) -> Dict[str, Any]:
        """Resolve the reporting window for the requested period."""
        from insights.api.ml.utils import parse_custom_range

        custom = parse_custom_range(self.period)
        if custom:
            start, end = custom
            return {"name": "Custom Range", "start": start.date(), "end": end.date()}
        if self.period == "fy":
            fy = self.fiscal_year or _fiscal_year_for(self.company)
            return {
                "name": fy.get("name"),
                "start": fy.get("year_start_date"),
                "end": fy.get("year_end_date"),
            }
        months = _PERIOD_MONTHS[self.period]
        end = _today_date()
        # Approximate month arithmetic without pulling in a date library:
        # step back whole months, clamping the day to avoid invalid dates.
        year, month = end.year, end.month - months
        while month <= 0:
            month += 12
            year -= 1
        day = min(end.day, 28)
        start = date(year, month, day)
        return {"name": f"Last {months} Months", "start": start, "end": end}

    # ------------------------------------------------------------------ safe
    def _safe(self, fn, *args, default=None):
        """Call fn(*args); return `default` on any exception (logged)."""
        try:
            return fn(*args)
        except Exception as exc:
            frappe.log_error(
                f"IndiaTaxIntelligence section failed [{fn.__name__}]: {exc}",
                "ML Tax",
            )
            return default

    # ------------------------------------------------------------------ compute
    def train(self) -> Dict[str, Any]:
        """Compute the full India tax intelligence payload.

        Called by both `tax_intelligence()` and the section sub-endpoints
        (`gst_summary`, `itc_health`, `tds_summary`). Synchronous, returns
        directly. Per-section failures are caught and produce empty
        payloads so one broken section never blocks the rest.
        """
        win = self._window()
        fy_start = win.get("start")
        fy_end = win.get("end")

        gst_summary = self._safe(
            _data.get_gst_output_tax, self, fy_start, fy_end, default=[]
        )
        input_tax = self._safe(
            _data.get_gst_input_tax, self, fy_start, fy_end, default=[]
        )
        itc_health = self._safe(
            _data.get_itc_health, self, fy_start, fy_end, default={}
        )
        tds_summary = self._safe(
            _data.get_tds_summary, self, fy_start, fy_end, default={}
        )
        einvoice_status = self._safe(
            _data.get_einvoice_status, self, fy_start, fy_end, default={}
        )
        ewaybill_status = self._safe(
            _data.get_ewaybill_status, self, fy_start, fy_end, default={}
        )
        filing_compliance = self._safe(
            _data.get_filing_compliance, self, fy_start, fy_end, default={}
        )
        reconciliation_score = self._safe(
            _data.get_reconciliation_score, self, fy_start, fy_end, default={}
        )
        hsn_summary = self._safe(
            _data.get_hsn_summary, self, fy_start, fy_end, default=[]
        )
        counterparty_risk = self._safe(
            _data.get_counterparty_risk, self, fy_start, fy_end, default={}
        )
        tax_forecast = self._safe(
            _analytics.get_tax_forecast, self, fy_start, fy_end,
            default={"forecast": [], "note": "Forecast unavailable"},
        )
        advance_tax_schedule = self._safe(
            _analytics.get_advance_tax_schedule, self, default=[]
        )

        total_output = sum(
            float((row.get("cgst") or 0) + (row.get("sgst") or 0) + (row.get("igst") or 0))
            for row in (gst_summary or [])
        )
        total_input = sum(
            float((row.get("cgst") or 0) + (row.get("sgst") or 0) + (row.get("igst") or 0))
            for row in (input_tax or [])
        )
        net_gst = total_output - total_input

        # Effective tax rate = Output GST / Pre-GST taxable revenue × 100
        # Denominator is base_net_total (pre-tax taxable value), not grand total,
        # so the rate reflects the true GST burden (e.g. 18% not ~15.3%).
        total_revenue = sum(
            float(row.get("total_revenue") or 0) for row in (gst_summary or [])
        )
        effective_tax_rate = (
            round((total_output / total_revenue * 100), 2) if total_revenue > 0 else 0.0
        )

        compliance_score = self._compute_compliance_score(
            einvoice_status, ewaybill_status, filing_compliance, reconciliation_score
        )

        return {
            "status": "success",
            "generated_at": datetime.now().isoformat(),
            "company": self.company,
            "base_currency": self.base_currency,
            "fiscal_year": {
                "name": win.get("name"),
                "start_date": str(fy_start) if fy_start else "",
                "end_date": str(fy_end) if fy_end else "",
            },
            "gst_summary": [
                {
                    "month": row.get("month"),
                    "cgst": float(row.get("cgst") or 0),
                    "sgst": float(row.get("sgst") or 0),
                    "igst": float(row.get("igst") or 0),
                    "total_revenue": float(row.get("total_revenue") or 0),
                    "invoice_count": int(row.get("invoice_count") or 0),
                }
                for row in (gst_summary or [])
            ],
            "input_tax": [
                {
                    "month": row.get("month"),
                    "cgst": float(row.get("cgst") or 0),
                    "sgst": float(row.get("sgst") or 0),
                    "igst": float(row.get("igst") or 0),
                    "total_purchase": float(row.get("total_purchase") or 0),
                    "invoice_count": int(row.get("invoice_count") or 0),
                }
                for row in (input_tax or [])
            ],
            "itc_health": itc_health or {},
            "tds_summary": tds_summary or {},
            "einvoice_status": einvoice_status or {},
            "ewaybill_status": ewaybill_status or {},
            "filing_compliance": filing_compliance or {},
            "counterparty_risk": counterparty_risk or {},
            "reconciliation_score": reconciliation_score or {},
            "hsn_summary": [
                {
                    "hsn_code": row.get("hsn_code", "") or "",
                    "revenue": float(row.get("revenue") or 0),
                    "actual_gst": float(row.get("actual_gst") or 0),
                    "effective_gst_rate": float(row.get("effective_gst_rate") or 0),
                    "invoice_count": int(row.get("invoice_count") or 0),
                }
                for row in (hsn_summary or [])
            ],
            "tax_forecast": tax_forecast or {},
            "advance_tax_schedule": advance_tax_schedule or [],
            "net_gst": round(net_gst, 2),
            "effective_tax_rate": effective_tax_rate,
            "compliance_score": compliance_score,
            # Reference data embedded in payload so the frontend never has to
            # hard-code thresholds.
            "einvoice_compliance_info": EINVOICE_COMPLIANCE,
        }

    def predict(self) -> Dict[str, Any]:
        """Same as `train`: every call is fresh; no stale cache."""
        return self.train()

    # ------------------------------------------------------------------ scoring
    def _compute_compliance_score(
        self,
        einvoice: Dict[str, Any],
        ewaybill: Dict[str, Any],
        filing: Dict[str, Any],
        recon: Dict[str, Any],
    ) -> float:
        """Compute a 0-100 compliance score (weighted average)."""
        scores: List[float] = []
        weights: List[float] = []

        if isinstance(einvoice, dict) and "error" not in einvoice:
            coverage = float(einvoice.get("coverage_pct") or 0)
            scores.append(min(coverage, 100))
            weights.append(25)

        if isinstance(ewaybill, dict) and "error" not in ewaybill:
            # Coverage is measured only against invoices that actually need an
            # e-Waybill: "Not Applicable" rows (below the movement threshold)
            # must not dilute the denominator, exactly as `get_einvoice_status`
            # measures IRN coverage only over `needs_irn` invoices.
            total = float(ewaybill.get("total") or 0)
            not_applicable = float(ewaybill.get("not_applicable") or 0)
            applicable = total - not_applicable
            active = float(ewaybill.get("active") or 0)
            pct = (active / applicable * 100) if applicable > 0 else 0
            scores.append(min(pct, 100))
            weights.append(15)

        if isinstance(filing, dict) and "error" not in filing:
            gstr1 = filing.get("gstr1") or {}
            gstr3b = filing.get("gstr3b") or {}
            # Denominator is periods that are actually due: a NULL filing_status
            # ("unknown") marks a period not yet due (future return_period), so
            # counting it as unfiled would understate compliance. Score only
            # over periods with a definite filed/pending status.
            gstr1_due = int(gstr1.get("total") or 0) - int(gstr1.get("unknown") or 0)
            gstr3b_due = int(gstr3b.get("total") or 0) - int(gstr3b.get("unknown") or 0)
            gstr1_filed = int(gstr1.get("filed") or 0)
            gstr3b_filed = int(gstr3b.get("filed") or 0)
            denom = gstr1_due + gstr3b_due
            filing_score = (
                (gstr1_filed + gstr3b_filed) / denom * 100 if denom > 0 else 0
            )
            scores.append(min(filing_score, 100))
            weights.append(35)

        if isinstance(recon, dict) and "error" not in recon:
            recon_score = float(recon.get("reconciliation_score") or 0)
            scores.append(recon_score)
            weights.append(25)

        if not scores:
            return 0.0
        total_weight = sum(weights)
        weighted = sum(s * w for s, w in zip(scores, weights))
        return round(weighted / total_weight, 2)
