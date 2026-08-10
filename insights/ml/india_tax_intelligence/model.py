# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""India Tax Intelligence Model

Comprehensive tax analytics for India GST, ITC, TDS, e-Invoice,
e-Waybill, HSN and compliance scoring.
"""

import frappe
from datetime import date, datetime
from typing import Dict, Any, List

from insights.ml.base import BaseMLModel
import insights.ml.india_tax_intelligence.analytics as _analytics
import insights.ml.india_tax_intelligence.data as _data
from insights.ml.india_tax_intelligence.data import EINVOICE_COMPLIANCE


class IndiaTaxIntelligence(BaseMLModel):
    """
    India Tax Intelligence Engine

    Provides:
    - GST output / input tax monthly summaries
    - ITC health (available, claimed, ineligible, utilization)
    - TDS summary by section
    - e-Invoice / e-Waybill coverage
    - GSTR-1 / GSTR-3B filing compliance
    - GST Inward Supply reconciliation score
    - HSN-level revenue summary
    - 3-month GST forecast (linear regression)
    - Advance tax schedule
    """

    # Windows the dashboard's period selector can request. 'fy' uses the
    # company's fiscal year; the rest are rolling windows ending today.
    PERIODS = ("3m", "6m", "12m", "fy")

    def __init__(self, period: str = "fy"):
        super().__init__()
        self.model_name = "IndiaTaxIntelligence"
        self.period = period if period in self.PERIODS else "fy"
        self.company = (
            frappe.defaults.get_user_default("company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
        )
        self.fiscal_year = self._get_current_fiscal_year()
        self.india_compliance_installed = _data.check_india_compliance_installed()

    def _get_current_fiscal_year(self) -> Dict[str, Any]:
        """Get current fiscal year for the company."""
        today = datetime.now().date()
        fiscal_year = frappe.db.sql(
            """
            SELECT fy.name, fy.year_start_date, fy.year_end_date
            FROM `tabFiscal Year` fy
            LEFT JOIN `tabFiscal Year Company` fyc ON fyc.parent = fy.name
            WHERE fy.disabled = 0
              AND %(today)s BETWEEN fy.year_start_date AND fy.year_end_date
              AND (fyc.company = %(company)s OR fyc.company IS NULL)
            ORDER BY fy.year_start_date DESC
            LIMIT 1
            """,
            {"today": today, "company": self.company},
            as_dict=True,
        )
        if fiscal_year:
            return fiscal_year[0]

        fiscal_year = frappe.db.sql(
            """
            SELECT name, year_start_date, year_end_date
            FROM `tabFiscal Year`
            WHERE disabled = 0
              AND %(today)s BETWEEN year_start_date AND year_end_date
            ORDER BY year_start_date DESC
            LIMIT 1
            """,
            {"today": today},
            as_dict=True,
        )
        if fiscal_year:
            return fiscal_year[0]

        return {
            "name": str(today.year),
            "year_start_date": datetime(today.year, 1, 1).date(),
            "year_end_date": datetime(today.year, 12, 31).date(),
        }

    def _get_fiscal_dates(self) -> Dict[str, Any]:
        """Resolve the reporting window for the requested period.

        The dashboard offers Last 3 / 6 / 12 Months and Current FY. Before this,
        every one of them returned the fiscal year: the selector re-fetched and
        redrew identical numbers, so it looked functional while silently ignoring
        the choice. Verified by driving all four options and getting the same
        Net GST, effective rate and compliance score each time.

        Rolling windows end today rather than at the fiscal year end, which is
        the point of choosing them.
        """
        if self.period == "fy":
            return {
                "year_start_date": self.fiscal_year.get("year_start_date"),
                "year_end_date": self.fiscal_year.get("year_end_date"),
                "name": self.fiscal_year.get("name"),
            }

        months = {"3m": 3, "6m": 6, "12m": 12}[self.period]
        end = datetime.now().date()
        # Approximate month arithmetic without pulling in a date library:
        # step back whole months, clamping the day to avoid invalid dates.
        year, month = end.year, end.month - months
        while month <= 0:
            month += 12
            year -= 1
        day = min(end.day, 28)
        start = date(year, month, day)
        return {
            "year_start_date": start,
            "year_end_date": end,
            "name": f"Last {months} Months",
        }

    def _safe(self, fn, *args, default=None):
        """Call fn(*args), returning default on any exception (logged to frappe error log)."""
        try:
            return fn(*args)
        except Exception as exc:
            frappe.log_error(f"IndiaTaxIntelligence section failed [{fn.__name__}]: {exc}", "ML Tax")
            return default

    def train(self) -> Dict[str, Any]:
        """Run complete India tax intelligence analysis."""
        window = self._get_fiscal_dates()
        fy_start = window.get("year_start_date")
        fy_end = window.get("year_end_date")

        gst_summary       = self._safe(_data.get_gst_output_tax, self, fy_start, fy_end, default=[])
        input_tax         = self._safe(_data.get_gst_input_tax,  self, fy_start, fy_end, default=[])
        itc_health        = self._safe(_data.get_itc_health,       self, fy_start, fy_end, default={})
        tds_summary       = self._safe(_data.get_tds_summary,      self, fy_start, fy_end, default={})
        einvoice_status   = self._safe(_data.get_einvoice_status,  self, fy_start, fy_end, default={})
        ewaybill_status   = self._safe(_data.get_ewaybill_status,  self, fy_start, fy_end, default={})
        filing_compliance = self._safe(_data.get_filing_compliance,self, fy_start, fy_end, default={})
        reconciliation_score = self._safe(_data.get_reconciliation_score, self, fy_start, fy_end, default={})
        hsn_summary       = self._safe(_data.get_hsn_summary,     self, fy_start, fy_end, default=[])
        counterparty_risk = self._safe(
            _data.get_counterparty_risk, self, fy_start, fy_end, default={}
        )
        tax_forecast      = self._safe(_analytics.get_tax_forecast, self, fy_start, fy_end,
                                       default={"forecast": [], "note": "Forecast unavailable"})
        advance_tax_schedule = self._safe(
            _analytics.get_advance_tax_schedule, self, default=[]
        )

        # Net GST = Output - Input
        total_output = sum(
            float(row.get("cgst", 0) + row.get("sgst", 0) + row.get("igst", 0))
            for row in gst_summary
        )
        total_input = sum(
            float(row.get("cgst", 0) + row.get("sgst", 0) + row.get("igst", 0))
            for row in input_tax
        )
        net_gst = total_output - total_input

        # Effective tax rate = Output GST / Pre-GST taxable revenue × 100
        # Denominator is base_net_total (pre-tax taxable value), not grand total,
        # so the rate reflects the true GST burden (e.g. 18 % not ~15.3 %).
        total_revenue = sum(float(row.get("total_revenue", 0)) for row in gst_summary)
        effective_tax_rate = round((total_output / total_revenue * 100), 2) if total_revenue > 0 else 0.0

        # Compliance score (0-100)
        compliance_score = self._compute_compliance_score(
            einvoice_status, ewaybill_status, filing_compliance, reconciliation_score
        )

        result = {
            "status": "success",
            "generated_at": datetime.now().isoformat(),
            "company": self.company,
            "fiscal_year": {
                "name": window.get("name"),
                "year_start_date": str(fy_start),
                "year_end_date": str(fy_end),
            },
            "gst_summary": [
                {
                    "month": row.get("month"),
                    "cgst": float(row.get("cgst", 0)),
                    "sgst": float(row.get("sgst", 0)),
                    "igst": float(row.get("igst", 0)),
                    "total_revenue": float(row.get("total_revenue", 0)),
                    "invoice_count": int(row.get("invoice_count", 0)),
                }
                for row in gst_summary
            ],
            "input_tax": [
                {
                    "month": row.get("month"),
                    "cgst": float(row.get("cgst", 0)),
                    "sgst": float(row.get("sgst", 0)),
                    "igst": float(row.get("igst", 0)),
                    "total_purchase": float(row.get("total_purchase", 0)),
                    "invoice_count": int(row.get("invoice_count", 0)),
                }
                for row in input_tax
            ],
            "itc_health": itc_health,
            "tds_summary": tds_summary,
            "einvoice_status": einvoice_status,
            "ewaybill_status": ewaybill_status,
            "filing_compliance": filing_compliance,
            "counterparty_risk": counterparty_risk,
            "reconciliation_score": reconciliation_score,
            "hsn_summary": [
                {
                    "hsn_code": row.get("hsn_code", ""),
                    "revenue": float(row.get("revenue", 0)),
                    "actual_gst": float(row.get("actual_gst", 0)),
                    "effective_gst_rate": round(
                        float(row.get("actual_gst", 0)) / float(row.get("revenue", 0)) * 100, 2
                    ) if float(row.get("revenue", 0)) > 0 else 0.0,
                    "invoice_count": int(row.get("invoice_count", 0)),
                }
                for row in hsn_summary
            ],
            "tax_forecast": tax_forecast,
            "advance_tax_schedule": advance_tax_schedule,
            "net_gst": round(net_gst, 2),
            "effective_tax_rate": effective_tax_rate,
            "compliance_score": compliance_score,
            # Reference data embedded in payload so the frontend never hard-codes thresholds
            "einvoice_compliance_info": EINVOICE_COMPLIANCE,
        }

        # Cache per period, or switching the selector would serve another
        # window's numbers from cache.
        self.cache_results(f"india_tax_intelligence:{self.period}", result)
        return result

    def predict(self) -> Dict[str, Any]:
        """Return cached results or generate new ones."""
        cached = self.get_cached_results(f"india_tax_intelligence:{self.period}")
        if cached:
            return cached
        return self.train()

    def _compute_compliance_score(
        self,
        einvoice: Dict[str, Any],
        ewaybill: Dict[str, Any],
        filing: Dict[str, Any],
        recon: Dict[str, Any],
    ) -> float:
        """Compute a 0-100 compliance score."""
        scores = []
        weights = []

        if "error" not in einvoice:
            coverage = einvoice.get("coverage_pct", 0)
            scores.append(min(coverage, 100))
            weights.append(25)

        if "error" not in ewaybill:
            total = ewaybill.get("total", 0)
            active = ewaybill.get("active", 0)
            pct = (active / total * 100) if total > 0 else 0
            scores.append(min(pct, 100))
            weights.append(15)

        if "error" not in filing:
            gstr1 = filing.get("gstr1", {})
            gstr3b = filing.get("gstr3b", {})
            gstr1_total = gstr1.get("total", 0)
            gstr3b_total = gstr3b.get("total", 0)
            gstr1_filed = gstr1.get("filed", 0)
            gstr3b_filed = gstr3b.get("filed", 0)
            filing_score = 0
            if gstr1_total + gstr3b_total > 0:
                filing_score = (gstr1_filed + gstr3b_filed) / (gstr1_total + gstr3b_total) * 100
            scores.append(min(filing_score, 100))
            weights.append(35)

        if "error" not in recon:
            recon_score = recon.get("reconciliation_score", 0)
            scores.append(recon_score)
            weights.append(25)

        if not scores:
            return 0.0

        total_weight = sum(weights)
        weighted = sum(s * w for s, w in zip(scores, weights))
        return round(weighted / total_weight, 2)
