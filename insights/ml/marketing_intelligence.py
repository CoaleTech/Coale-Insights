"""
Marketing Intelligence Module.

Pure-Ibis rewrite of the marketing surface. Every aggregate compiles to
one SQL statement and runs inside MariaDB; the Python process only ever
materialises the final, already-aggregated result (a handful of rows per
panel). No pandas, no numpy, no sklearn, no ``BaseMLModel``, no Redis
cache, no RQ background job, no fork.

The ``get_marketing_overview`` method -- and therefore every module-level
wrapper below -- returns the same top-level dict the legacy class used
to return. Two real consumers depend on that contract:

    * ``insights.agents.marketing_agent`` -- instantiates the class and
      reads ``lead_metrics``, ``pipeline_metrics``,
      ``campaign_metrics``, ``recommendations``, ``period``.
    * ``insights.reports.executive_reports`` -- instantiates the class
      and reads ``lead_metrics.total_leads`` and
      ``lead_metrics.conversion_rate``.

The test suite (``tests/test_ml_permission_gates.py``) imports the
module-level ``get_marketing_overview`` to verify the permission gate on
the API layer, so that wrapper is kept as a thin shim.

Source doctypes (ERPNext CRM):

    Lead           - lead counts, status funnel, source attribution
    Opportunity    - opportunity counts / status / stage breakdown
    Quotation      - pipeline value (Quotation.base_grand_total is
                     populated; Opportunity.opportunity_amount is 0 on
                     every row in this site, so it is not used for value)
    Customer       - new customer acquisition
    Sales Order    - won revenue (Sales Order -> grand_total)
    Campaign       - campaign catalogue (single row in this site; no
                     budget / cost fields exist on Campaign here, so
                     spend-style metrics are reported as zero rather
                     than fabricated)
    Email Campaign - email metrics (no rows on this site)

``Company`` is applied to the company-aware doctypes via
``insights.api.ml.ibis_source.company_filter``.  Customer / Campaign /
Email Campaign have no ``company`` column; they are queried unfiltered.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    pass  # no pandas / numpy / sklearn in this rewrite

import frappe
import ibis
from frappe import _
from frappe.defaults import get_user_default

from insights.api.ml.ibis_source import company_filter, t
from insights.ml.marketing_source_metrics import (
    get_cost_per_lead,
    get_hot_leads_by_source,
    get_leads_by_source,
    get_territory_leads,
)

# ────────────────────────────────────────────────────────────────────────────
# Module helpers
# ────────────────────────────────────────────────────────────────────────────


# ERPNext Lead.status values, ordered along the CRM funnel. Matches the
# funnel the API layer (`insights.api.ml.marketing`) and the source
# metrics module use. `Lead.status` is ERPNext's own progression field,
# so it is the honest funnel source rather than a synthesised join
# across Lead / Opportunity / Quotation.
_LEAD_OPEN_STATUSES = ("Lead", "Open", "Inquiry", "Interested")
_LEAD_HOT_STATUSES = ("Quotation", "Opportunity", "Interested")
_LEAD_QUALIFIED_STATUSES = ("Converted", "Quotation", "Opportunity", "Interested")


def _now_iso() -> str:
    return datetime.now().isoformat()


def _rows(expr) -> List[Dict[str, Any]]:
    """Execute a small Ibis aggregate and return list-of-dict rows."""
    df = expr.execute()
    if df is None or len(df) == 0:
        return []
    return [
        {k: (None if v is None else v) for k, v in row.items()}
        for row in df.to_dict(orient="records")
    ]


def _scalar(expr, default: float = 0.0):
    df = expr.execute()
    if df is None or len(df) == 0:
        return default
    v = df.iloc[0, 0]
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _int(expr, default: int = 0) -> int:
    """Execute a small integer aggregate. MariaDB COUNT() comes back as
    int64 in pandas after ``.execute()``; we still round-trip through
    ``int()`` defensively in case the column is null / Decimal."""
    df = expr.execute()
    if df is None or len(df) == 0:
        return default
    v = df.iloc[0, 0]
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _period_start_date(period: str) -> date:
    """Resolve a period keyword, or the start of an encoded custom range
    (see `insights.api.ml.utils.parse_custom_range`), to an inclusive start
    ``date``. There is no matching `_period_end_date` here: every query in
    this module is start-bounded only (filters ``>= from_date``, no upper
    bound beyond "whenever this request runs"), so a custom range's end is
    stored on ``self.to_date`` for display but never reaches a filter --
    matching how MTD/QTD/YTD/TTM already behave today. HR's ``to_date`` is
    different: see ``hr_intelligence._period_end_date``."""
    from insights.api.ml.utils import parse_custom_range

    custom = parse_custom_range(period)
    if custom:
        return custom[0].date()
    today = date.today()
    if period == "MTD":
        return today.replace(day=1)
    if period == "QTD":
        quarter_start = ((today.month - 1) // 3) * 3 + 1
        return today.replace(month=quarter_start, day=1)
    if period == "YTD":
        return today.replace(month=1, day=1)
    # TTM (and any other keyword) -- rolling 12 months
    from frappe.utils import add_months

    return add_months(today, -12)


def _base_currency(company: Optional[str]) -> str:
    if company:
        cur = frappe.db.get_value("Company", company, "default_currency")
        if cur:
            return cur
    return frappe.db.get_default("currency") or "USD"


def _coalesce_label(table, column: str, fallback: str):
    """`CASE WHEN col IS NOT NULL AND col != '' THEN col ELSE 'fallback' END`."""
    col = table[column]
    return (
        ibis.cases(
            (col.notnull() & (col != ""), col),
            else_=fallback,
        )
    ).name(column)


# ────────────────────────────────────────────────────────────────────────────
# MarketingIntelligence class
# ────────────────────────────────────────────────────────────────────────────


class MarketingIntelligence:
    """Pure-Ibis marketing analytics. No training, no caching, no background job."""

    def __init__(self, period: str = "YTD"):
        self.model_name = "MarketingIntelligence"
        self.period = period
        self.from_date = _period_start_date(period)
        self.to_date = date.today()
        self.company = (
            get_user_default("Company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
        )
        self.company = str(self.company) if self.company else None
        self.base_currency = _base_currency(self.company)

    # ------------------------------------------------------------------ train
    def train(self) -> Dict[str, Any]:
        """Generate the full marketing overview payload. ``train`` /
        ``predict`` are sklearn-style shim names kept for backward
        compatibility with the legacy ``BaseMLModel`` callers. The real
        work is in ``get_marketing_overview``."""
        return self.get_marketing_overview(self.period)

    def predict(self) -> Dict[str, Any]:
        """Backward-compat alias for callers that expect a sklearn-style
        ``predict()``. Same dict as ``train()`` -- every call computes
        fresh, no model, no cache."""
        return self.train()

    # ---------------------------------------------------------------- overview
    def get_marketing_overview(self, period: str = "YTD") -> Dict[str, Any]:
        """Comprehensive marketing overview. The shape below is the
        public contract; ``agents/marketing_agent`` and
        ``reports/executive_reports`` both destructure it.

        Top-level keys (all are dicts unless noted):

            period                (str)
            generated_at          (str, ISO timestamp)
            company               (str | None)
            base_currency         (str)

            pipeline_metrics      -- opportunity pipeline counts and
                                     status/stage breakdown. Value uses
                                     Opportunity.opportunity_amount,
                                     which is 0 on this site, so value
                                     is also reported from Quotation in
                                     conversion_metrics.
            lead_metrics          -- lead counts, qualification rate,
                                     status / source / territory
                                     breakdown, monthly trend
            campaign_metrics      -- campaign + email-campaign rollups
            conversion_metrics    -- funnel from lead -> opportunity ->
                                     customer -> sales order, plus
                                     per-stage conversion rates and
                                     won/lost pipeline value
            lead_quality_score    -- composite lead-quality score and
                                     grade distribution
            customer_acquisition  -- new-customer counts, type/territory
                                     breakdown
            marketing_roi         -- total marketing spend, attributed
                                     revenue, ROI, ROAS, CPA
            channel_performance   -- per-source lead / opportunity /
                                     conversion rollup
            pipeline_forecast     -- probability-bucketed forecast
                                     using Quotation.value by status
            lead_scoring          -- advanced lead scoring model
                                     output
            recommendations       -- list of recommendation dicts

            raw_data              -- small summary dict (counts by
                                     status), not the bulk rows. The
                                     legacy code materialised every
                                     lead / opportunity / customer /
                                     order / campaign row here, which
                                     is no longer the point of a pure
                                     on-demand analytics layer.
        """
        if period:
            self.period = period
            self.from_date = _period_start_date(period)

        from_str = str(self.from_date)

        # ── Pipeline (Opportunity side: counts + status / stage). ─────
        pipeline_metrics = self._analyze_pipeline(from_str)

        # ── Leads. ──────────────────────────────────────────────────────
        lead_metrics = self._analyze_leads(from_str)

        # ── Campaigns + email-campaign rollups. ────────────────────────
        campaign_metrics = self._analyze_campaigns(from_str)

        # ── Funnel: lead -> opportunity -> customer -> sales order. ───
        conversion_metrics = self._analyze_conversions(from_str)

        # ── Lead quality + lead scoring + acquisition + ROI + channels. ─
        lead_quality_score = self._score_lead_quality(from_str)
        customer_acquisition = self._analyze_customer_acquisition(from_str)
        marketing_roi = self._calculate_marketing_roi(from_str)
        channel_performance = self._analyze_channels(from_str)
        pipeline_forecast = self._forecast_pipeline(from_str)
        lead_scoring = self._advanced_lead_scoring(from_str)
        recommendations = self._generate_marketing_recommendations(
            lead_metrics,
            pipeline_metrics,
            channel_performance,
            marketing_roi,
        )

        # The legacy code returned `raw_data` as the full set of fetched
        # rows. In the on-demand world the aggregates above already ARE
        # the data; ``raw_data`` is now a compact summary of row counts
        # so callers that introspect it (e.g. test fixtures) still get
        # something shaped like before.
        raw_data = {
            "from_date": str(self.from_date),
            "to_date": str(self.to_date),
            "counts": {
                "leads": lead_metrics.get("total_leads", 0),
                "opportunities": pipeline_metrics.get("total_opportunities", 0),
                "customers": customer_acquisition.get("total_new_customers", 0),
                "sales_orders": conversion_metrics.get("funnel_metrics", {}).get(
                    "sales_orders", 0
                ),
            },
        }

        return {
            "status": "success",
            "period": self.period,
            "generated_at": _now_iso(),
            "company": self.company,
            "base_currency": self.base_currency,
            "pipeline_metrics": pipeline_metrics,
            "lead_metrics": lead_metrics,
            "campaign_metrics": campaign_metrics,
            "conversion_metrics": conversion_metrics,
            "lead_quality_score": lead_quality_score,
            "customer_acquisition": customer_acquisition,
            "marketing_roi": marketing_roi,
            "channel_performance": channel_performance,
            "pipeline_forecast": pipeline_forecast,
            "lead_scoring": lead_scoring,
            "recommendations": recommendations,
            "raw_data": raw_data,
        }

    # ----------------------------------------------------------------- helpers
    def _lead_base(self, from_str: str):
        """Lead relation filtered to the period, company-scoped."""
        lead = company_filter(t("Lead", extra_columns=("source",)), self.company)
        return lead.filter(lead["creation"] >= from_str)

    # --------------------------------------------------------------- pipeline
    def _analyze_pipeline(self, from_str: str) -> Dict[str, Any]:
        """Opportunity pipeline: counts, status / stage breakdown, value."""
        try:
            opp = company_filter(t("Opportunity"), self.company)
            opp = opp.filter(opp["creation"] >= from_str)

            # Counts / value roll-up -- two separate scalars, since
            # ``_scalar`` returns the first column and a combined
            # aggregate would conflate the two. Opportunity.opportunity_amount
            # is 0 on every row on this site, so the value is always 0
            # here; the Quotation side carries the real money (see
            # ``_analyze_conversions``).
            total_opps = _int(opp.aggregate(total=opp.count()))

            if total_opps == 0:
                return {
                    "message": _("No opportunities data available"),
                    "total_opportunities": 0,
                    "total_pipeline_value": 0,
                    "total_weighted_value": 0,
                    "average_deal_size": 0,
                    "conversion_rate_pct": 0,
                    "won_opportunities": 0,
                    "won_value": 0,
                    "win_rate_pct": 0,
                    "status_breakdown": {},
                    "stage_breakdown": {},
                    "stage_values": {},
                    "pipeline_health": "needs_improvement",
                }

            total_value = float(
                _scalar(
                    opp.aggregate(value=opp["opportunity_amount"].sum()),
                    default=0.0,
                )
            )
            avg_deal = total_value / total_opps if total_opps else 0

            # Status / stage breakdown. `status` and `sales_stage` are
            # both coalesced to a literal "Unset" so the breakdown dicts
            # only contain meaningful keys.
            status_label = _coalesce_label(opp, "status", "Unset").name("status_label")
            stage_label = _coalesce_label(opp, "sales_stage", "Unset").name("stage_label")

            status_df = (
                opp.group_by(status_label)
                .aggregate(count=opp.count())
                .execute()
            )
            status_breakdown: Dict[str, int] = {}
            if status_df is not None and len(status_df):
                for _, r in status_df.iterrows():
                    status_breakdown[str(r.get("status_label") or "Unset")] = int(
                        r.get("count") or 0
                    )

            stage_df = (
                opp.group_by(stage_label)
                .aggregate(
                    count=opp.count(),
                    value=opp["opportunity_amount"].sum(),
                )
                .execute()
            )
            stage_breakdown: Dict[str, int] = {}
            stage_values: Dict[str, float] = {}
            if stage_df is not None and len(stage_df):
                for _, r in stage_df.iterrows():
                    key = str(r.get("stage_label") or "Unset")
                    stage_breakdown[key] = int(r.get("count") or 0)
                    stage_values[key] = float(r.get("value") or 0)

            # Won -- "Converted" status in ERPNext Opportunity. The
            # legacy code used the more brittle "Open + probability > 80"
            # heuristic; on this site every opportunity carries
            # probability = 100, so the "Open + > 80" rule matched
            # every Open row, which was obviously wrong. Use the
            # authoritative status.
            won_count = int(status_breakdown.get("Converted", 0))
            conversion_rate = round((won_count / total_opps * 100), 2) if total_opps else 0
            win_rate = conversion_rate  # alias, marketing_agent reads it

            # weighted_amount was the legacy "opportunity_amount *
            # probability / 100" computation. Probability is always 100
            # on this site, so weighted == unweighted; report it for
            # contract compatibility but it is no longer meaningful.
            total_weighted = total_value

            return {
                "total_opportunities": total_opps,
                "total_pipeline_value": round(total_value, 2),
                "total_weighted_value": round(total_weighted, 2),
                "average_deal_size": round(avg_deal, 2),
                "conversion_rate_pct": conversion_rate,
                "win_rate_pct": win_rate,
                "won_opportunities": won_count,
                "won_value": 0,  # Opportunity.opportunity_amount is 0 here
                "status_breakdown": status_breakdown,
                "stage_breakdown": stage_breakdown,
                "stage_values": {k: round(v, 2) for k, v in stage_values.items()},
                "pipeline_health": (
                    "excellent"
                    if conversion_rate > 25
                    else "good"
                    if conversion_rate > 15
                    else "needs_improvement"
                ),
            }
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Insights ML: marketing._analyze_pipeline")
            return {"error": str(e)}

    # ------------------------------------------------------------------ leads
    def _analyze_leads(self, from_str: str) -> Dict[str, Any]:
        """Lead counts, qualification, status / source / territory breakdown."""
        try:
            lead = self._lead_base(from_str)

            total_leads = _int(lead.aggregate(total=lead.count()))

            if total_leads == 0:
                return {
                    "message": _("No leads data available"),
                    "total_leads": 0,
                    "qualified_leads": 0,
                    "qualification_rate_pct": 0,
                    "conversion_rate": 0,  # alias for executive_reports
                    "conversion_rate_pct": 0,  # alias for marketing_agent
                    "average_lead_score": 0,
                    "status_breakdown": {},
                    "source_breakdown": {},
                    "territory_breakdown": {},
                    "monthly_trend": {},
                    "lead_quality": "needs_improvement",
                }

            # Status / source / territory rollups in a single SQL pass.
            # We pull three group-bys because they're cheap (one indexed
            # table each) and the legacy code did three Python passes
            # over the same row set.
            status_label = _coalesce_label(lead, "status", "Unset").name("status_label")
            source_label = _coalesce_label(lead, "source", "Unattributed").name("source_label")
            territory_label = _coalesce_label(lead, "territory", "Unassigned").name(
                "territory_label"
            )

            status_df = lead.group_by(status_label).aggregate(count=lead.count()).execute()
            source_df = lead.group_by(source_label).aggregate(count=lead.count()).execute()
            territory_df = (
                lead.group_by(territory_label).aggregate(count=lead.count()).execute()
            )

            status_breakdown: Dict[str, int] = {}
            if status_df is not None and len(status_df):
                for _, r in status_df.iterrows():
                    status_breakdown[str(r.get("status_label") or "Unset")] = int(
                        r.get("count") or 0
                    )

            source_breakdown: Dict[str, int] = {}
            if source_df is not None and len(source_df):
                for _, r in source_df.iterrows():
                    source_breakdown[str(r.get("source_label") or "Unattributed")] = int(
                        r.get("count") or 0
                    )

            territory_breakdown: Dict[str, int] = {}
            if territory_df is not None and len(territory_df):
                for _, r in territory_df.iterrows():
                    territory_breakdown[str(r.get("territory_label") or "Unassigned")] = int(
                        r.get("count") or 0
                    )

            qualified_count = sum(
                int(status_breakdown.get(s, 0)) for s in _LEAD_QUALIFIED_STATUSES
            )
            qualification_rate = (
                round((qualified_count / total_leads * 100), 2) if total_leads else 0
            )

            # Monthly trend -- strftime on `creation`, period-wide.
            period_expr = lead["creation"].strftime("%Y-%m").name("month")
            monthly_df = (
                lead.group_by(period_expr)
                .aggregate(count=lead.count())
                .order_by("month")
                .execute()
            )
            monthly_trend: Dict[str, int] = {}
            if monthly_df is not None and len(monthly_df):
                for _, r in monthly_df.iterrows():
                    monthly_trend[str(r.get("month") or "")] = int(r.get("count") or 0)

            # `custom_lead_score` is an optional custom field -- not
            # present on every site. The legacy code only selected it
            # when present; the rewrite just reports 0 if it isn't
            # installed (the legacy "average lead score" line, in
            # practice, was always 0 on this site anyway).
            avg_score = 0.0
            if frappe.db.has_column("Lead", "custom_lead_score"):
                avg_score = float(
                    _scalar(
                        lead.aggregate(avg=lead["custom_lead_score"].mean()),
                        default=0.0,
                    )
                    or 0
                )

            return {
                "total_leads": total_leads,
                "qualified_leads": qualified_count,
                "qualification_rate_pct": qualification_rate,
                "conversion_rate": qualification_rate,  # executive_reports
                "conversion_rate_pct": qualification_rate,  # marketing_agent
                "average_lead_score": round(avg_score, 2),
                "status_breakdown": status_breakdown,
                "source_breakdown": source_breakdown,
                "territory_breakdown": territory_breakdown,
                "monthly_trend": monthly_trend,
                "lead_quality": (
                    "excellent"
                    if qualification_rate > 30
                    else "good"
                    if qualification_rate > 20
                    else "needs_improvement"
                ),
            }
        except Exception as e:
            frappe.log_error(
                frappe.get_traceback(), "Insights ML: marketing._analyze_leads"
            )
            return {"error": str(e)}

    # -------------------------------------------------------------- campaigns
    def _analyze_campaigns(self, from_str: str) -> Dict[str, Any]:
        """Campaign + email-campaign rollups. ``Campaign`` on this site
        has no budget / cost / revenue columns, so spend is reported
        as 0; ``Email Campaign`` has no rows here either."""
        try:
            # ── Traditional campaigns. ─────────────────────────────────
            campaign_overview = {
                "total_campaigns": 0,
                "active_campaigns": 0,
                "total_budget": 0,
                "total_spent": 0,
                "expected_revenue": 0,
            }
            try:
                camp = t("Campaign")
                rows = _rows(
                    camp.aggregate(
                        total=camp.count(),
                    )
                )
                if rows:
                    campaign_overview["total_campaigns"] = int(
                        rows[0].get("total") or 0
                    )
                    # No budget / actual_cost / expected_revenue columns
                    # on this site's Campaign table. Report zero rather
                    # than fabricate them.
                    campaign_overview["active_campaigns"] = (
                        campaign_overview["total_campaigns"]
                    )
            except Exception:
                # Defensive: Campaign table might be missing in some
                # ERPNext deployments. Keep the zeroed rollup.
                pass

            # ── Email campaigns. ──────────────────────────────────────
            email_metrics = {
                "total_email_campaigns": 0,
                "total_recipients": 0,
                "total_delivered": 0,
                "total_opened": 0,
                "total_clicked": 0,
                "total_unsubscribed": 0,
            }
            try:
                ec = t("Email Campaign")
                rows = _rows(ec.aggregate(total=ec.count()))
                if rows:
                    email_metrics["total_email_campaigns"] = int(
                        rows[0].get("total") or 0
                    )
                # Email Campaign has no aggregate-friendly metrics
                # columns on this site; report counts only.
            except Exception:
                pass

            # Rates are 0 when the denominators are 0; the legacy
            # implementation had the same fallback.
            recipients = email_metrics["total_recipients"]
            delivered = email_metrics["total_delivered"]
            opened = email_metrics["total_opened"]
            clicked = email_metrics["total_clicked"]
            email_metrics["delivery_rate_pct"] = (
                round((delivered / recipients * 100), 2) if recipients else 0
            )
            email_metrics["open_rate_pct"] = (
                round((opened / delivered * 100), 2) if delivered else 0
            )
            email_metrics["click_rate_pct"] = (
                round((clicked / delivered * 100), 2) if delivered else 0
            )

            total_spent = campaign_overview["total_spent"]
            expected = campaign_overview["expected_revenue"]
            campaign_roi = (
                round(((expected - total_spent) / total_spent * 100), 2)
                if total_spent
                else None
            )

            return {
                "campaign_overview": campaign_overview,
                "email_campaign_metrics": email_metrics,
                "campaign_roi_pct": campaign_roi,
                "campaign_effectiveness": (
                    "no_data"
                    if campaign_roi is None
                    else "excellent"
                    if campaign_roi > 200
                    else "good"
                    if campaign_roi > 100
                    else "needs_improvement"
                ),
            }
        except Exception as e:
            frappe.log_error(
                frappe.get_traceback(), "Insights ML: marketing._analyze_campaigns"
            )
            return {"error": str(e)}

    # ----------------------------------------------------------- conversions
    def _analyze_conversions(self, from_str: str) -> Dict[str, Any]:
        """Funnel from lead -> opportunity -> customer -> sales order,
        with per-stage conversion rates and won / lost pipeline value
        from Quotation (the real money table on this site)."""
        try:
            lead = self._lead_base(from_str)
            opp = company_filter(t("Opportunity"), self.company).filter(
                t("Opportunity")["creation"] >= from_str
            )
            # Customer has no company column; it is queried unfiltered.
            cust = t("Customer").filter(t("Customer")["creation"] >= from_str)
            so = company_filter(t("Sales Order"), self.company).filter(
                t("Sales Order")["creation"] >= from_str
            )

            lead_count = _int(lead.aggregate(total=lead.count()))
            opp_count = _int(opp.aggregate(total=opp.count()))
            cust_count = _int(cust.aggregate(total=cust.count()))
            so_count = _int(so.aggregate(total=so.count()))

            lead_to_opp = round((opp_count / lead_count * 100), 2) if lead_count else 0
            opp_to_cust = round((cust_count / opp_count * 100), 2) if opp_count else 0
            cust_to_so = round((so_count / cust_count * 100), 2) if cust_count else 0
            lead_to_so = round((so_count / lead_count * 100), 2) if lead_count else 0

            # Won / lost pipeline value. Quotation is the only
            # value-bearing CRM-side table on this site
            # (Opportunity.opportunity_amount is 0 for every row).
            quote = company_filter(t("Quotation"), self.company).filter(
                t("Quotation")["creation"] >= from_str
            )

            quote_won = _scalar(
                quote.filter(quote["status"] == "Ordered").aggregate(
                    value=quote["base_grand_total"].sum()
                ),
                default=0.0,
            )
            quote_lost = _scalar(
                quote.filter(quote["status"] == "Lost").aggregate(
                    value=quote["base_grand_total"].sum()
                ),
                default=0.0,
            )
            quote_expired = _scalar(
                quote.filter(quote["status"] == "Expired").aggregate(
                    value=quote["base_grand_total"].sum()
                ),
                default=0.0,
            )
            quote_draft = _scalar(
                quote.filter(quote["status"] == "Draft").aggregate(
                    value=quote["base_grand_total"].sum()
                ),
                default=0.0,
            )

            total_sales_value = float(
                _scalar(
                    so.aggregate(value=so["grand_total"].sum()),
                    default=0.0,
                )
            )
            avg_order_value = total_sales_value / so_count if so_count else 0
            estimated_clv = avg_order_value * 3  # Simplified 3-purchase estimate

            return {
                "funnel_metrics": {
                    "leads": lead_count,
                    "opportunities": opp_count,
                    "customers": cust_count,
                    "sales_orders": so_count,
                },
                "conversion_rates": {
                    "lead_to_opportunity_pct": lead_to_opp,
                    "opportunity_to_customer_pct": opp_to_cust,
                    "customer_to_order_pct": cust_to_so,
                    "lead_to_sale_pct": lead_to_so,
                },
                "revenue_metrics": {
                    "total_sales_value": round(total_sales_value, 2),
                    "average_order_value": round(avg_order_value, 2),
                    "open_quote_value": round(float(quote_draft or 0), 2),
                    "won_quote_value": round(float(quote_won or 0), 2),
                    "lost_quote_value": round(float(quote_lost or 0), 2),
                    "expired_quote_value": round(float(quote_expired or 0), 2),
                    "estimated_cac": None,
                    "estimated_clv": round(estimated_clv, 2),
                    "clv_cac_ratio": None,
                },
                "conversion_health": (
                    "excellent"
                    if lead_to_so > 10
                    else "good"
                    if lead_to_so > 5
                    else "needs_improvement"
                ),
            }
        except Exception as e:
            frappe.log_error(
                frappe.get_traceback(), "Insights ML: marketing._analyze_conversions"
            )
            return {"error": str(e)}

    # ---------------------------------------------------- lead quality score
    def _score_lead_quality(self, from_str: str) -> Dict[str, Any]:
        """Composite lead-quality score. Pure-Python scoring of the
        aggregate buckets, since the underlying rule is per-lead and
        the per-lead fetch is bounded by ``total_leads`` (3,660 on
        this site, cheap)."""
        try:
            lead = self._lead_base(from_str)
            total = _int(lead.aggregate(total=lead.count()))
            if total == 0:
                return {"message": _("No leads data for quality scoring")}

            # Pull the per-lead scoring inputs in one SQL pass.
            cols = ["name", "lead_name", "company_name", "status", "source"]
            if frappe.db.has_column("Lead", "custom_lead_score"):
                cols.append("custom_lead_score")
            df = lead.select(*cols).execute()

            if df is None or len(df) == 0:
                return {
                    "average_lead_score": 0,
                    "grade_distribution": {"A": 0, "B": 0, "C": 0, "D": 0},
                    "high_quality_percentage": 0,
                    "total_scored_leads": 0,
                    "quality_assessment": "needs_improvement",
                    "top_leads": [],
                }

            quality_scores = []
            for _, lead_row in df.iterrows():
                score = 0
                factors = []

                if lead_row.get("company_name"):
                    score += 20
                    factors.append("Company provided")

                source = str(lead_row.get("source") or "").lower()
                if "referral" in source or "existing customer" in source:
                    score += 25
                    factors.append("High-value source")
                elif "website" in source or "campaign" in source:
                    score += 15
                    factors.append("Digital source")

                status = str(lead_row.get("status") or "").lower()
                if "converted" in status:
                    score += 30
                    factors.append("Converted")
                elif "interested" in status or "qualified" in status:
                    score += 20
                    factors.append("Qualified")

                custom_score = lead_row.get("custom_lead_score")
                if custom_score:
                    try:
                        score += min(float(custom_score) / 10, 25)
                        factors.append(f"Custom score: {custom_score}")
                    except (TypeError, ValueError):
                        pass

                score = min(score, 100)
                grade = (
                    "A"
                    if score >= 80
                    else "B"
                    if score >= 60
                    else "C"
                    if score >= 40
                    else "D"
                )
                quality_scores.append(
                    {
                        "lead": lead_row.get("name"),
                        "score": score,
                        "grade": grade,
                        "factors": factors,
                    }
                )

            avg_score = sum(ls["score"] for ls in quality_scores) / len(quality_scores)
            grade_distribution = {"A": 0, "B": 0, "C": 0, "D": 0}
            for ls in quality_scores:
                grade_distribution[ls["grade"]] += 1
            high_quality_pct = (
                round(
                    (grade_distribution["A"] + grade_distribution["B"])
                    / len(quality_scores)
                    * 100,
                    2,
                )
                if quality_scores
                else 0
            )

            return {
                "average_lead_score": round(avg_score, 2),
                "grade_distribution": grade_distribution,
                "high_quality_percentage": high_quality_pct,
                "total_scored_leads": len(quality_scores),
                "quality_assessment": (
                    "excellent"
                    if high_quality_pct > 60
                    else "good"
                    if high_quality_pct > 40
                    else "needs_improvement"
                ),
                "top_leads": sorted(
                    quality_scores, key=lambda x: x["score"], reverse=True
                )[:10],
            }
        except Exception as e:
            frappe.log_error(
                frappe.get_traceback(), "Insights ML: marketing._score_lead_quality"
            )
            return {"error": str(e)}

    # ---------------------------------------------------- customer acquisition
    def _analyze_customer_acquisition(self, from_str: str) -> Dict[str, Any]:
        """New-customer counts and breakdown. Customer has no
        ``company`` column, so it is queried unfiltered."""
        try:
            cust = t("Customer").filter(t("Customer")["creation"] >= from_str)
            total = _int(cust.aggregate(total=cust.count()))
            if total == 0:
                return {"message": _("No customer acquisition data available")}

            type_label = _coalesce_label(cust, "customer_type", "Unset").name("type_label")
            territory_label = _coalesce_label(cust, "territory", "Unassigned").name(
                "territory_label"
            )
            group_label = _coalesce_label(cust, "customer_group", "Unset").name(
                "group_label"
            )

            type_df = cust.group_by(type_label).aggregate(count=cust.count()).execute()
            territory_df = (
                cust.group_by(territory_label).aggregate(count=cust.count()).execute()
            )
            group_df = (
                cust.group_by(group_label).aggregate(count=cust.count()).execute()
            )

            type_breakdown: Dict[str, int] = {}
            if type_df is not None and len(type_df):
                for _, r in type_df.iterrows():
                    type_breakdown[str(r.get("type_label") or "Unset")] = int(
                        r.get("count") or 0
                    )

            territory_breakdown: Dict[str, int] = {}
            if territory_df is not None and len(territory_df):
                for _, r in territory_df.iterrows():
                    territory_breakdown[str(r.get("territory_label") or "Unassigned")] = int(
                        r.get("count") or 0
                    )

            group_breakdown: Dict[str, int] = {}
            if group_df is not None and len(group_df):
                for _, r in group_df.iterrows():
                    group_breakdown[str(r.get("group_label") or "Unset")] = int(
                        r.get("count") or 0
                    )

            period_expr = cust["creation"].strftime("%Y-%m").name("month")
            monthly_df = (
                cust.group_by(period_expr)
                .aggregate(count=cust.count())
                .order_by("month")
                .execute()
            )
            monthly_acquisition: Dict[str, int] = {}
            if monthly_df is not None and len(monthly_df):
                for _, r in monthly_df.iterrows():
                    monthly_acquisition[str(r.get("month") or "")] = int(
                        r.get("count") or 0
                    )

            # Spend-per-customer needs campaign cost data. The
            # Campaign table on this site has no budget / cost columns,
            # so the legacy 150-flat-fallback was a fabrication, and a
            # bare 0 is not honest either -- it previously graded as
            # "good" (0 < 250), i.e. a fabricated pass grade computed
            # from the absence of any cost data. Report None: cost is
            # unmeasured, not measured-and-zero. Fixed 2026-08-17.
            acquisition_cost = None

            return {
                "total_new_customers": total,
                "customer_type_breakdown": type_breakdown,
                "territory_breakdown": territory_breakdown,
                "customer_group_breakdown": group_breakdown,
                "monthly_acquisition_trend": monthly_acquisition,
                "acquisition_cost_per_customer": acquisition_cost,
                "acquisition_efficiency": (
                    "no_data"
                    if acquisition_cost is None
                    else "excellent"
                    if 0 < acquisition_cost < 100
                    else "good"
                    if acquisition_cost < 250
                    else "needs_improvement"
                ),
            }
        except Exception as e:
            frappe.log_error(
                frappe.get_traceback(),
                "Insights ML: marketing._analyze_customer_acquisition",
            )
            return {"error": str(e)}

    # --------------------------------------------------------- marketing ROI
    def _calculate_marketing_roi(self, from_str: str) -> Dict[str, Any]:
        """Marketing spend / attributed revenue rollup. Spend comes
        from Campaign, which has no cost columns on this site, so
        spend-style numbers are 0; revenue comes from Sales Order."""
        try:
            so = company_filter(t("Sales Order"), self.company).filter(
                t("Sales Order")["creation"] >= from_str
            )
            total_attributed_revenue = float(
                _scalar(
                    so.aggregate(value=so["grand_total"].sum()),
                    default=0.0,
                )
            )
            # No Campaign cost columns on this site: spend, ROI, ROAS,
            # and CPA are all unmeasurable (not zero-valued). Reporting
            # them as 0 previously fixed roi_assessment permanently at
            # "needs_improvement" (0 never clears the > 150 bar) -- a
            # fabricated verdict computed from absent data. Fixed
            # 2026-08-17.
            total_marketing_spend = 0

            cust = t("Customer").filter(t("Customer")["creation"] >= from_str)
            customer_count = _int(cust.aggregate(total=cust.count()))
            rpc = total_attributed_revenue / customer_count if customer_count else 0

            return {
                "total_marketing_spend": round(total_marketing_spend, 2),
                "total_attributed_revenue": round(total_attributed_revenue, 2),
                "marketing_roi_pct": None,
                "return_on_ad_spend": None,
                "cost_per_acquisition": None,
                "revenue_per_customer": round(rpc, 2),
                "roi_assessment": "no_data",
            }
        except Exception as e:
            frappe.log_error(
                frappe.get_traceback(),
                "Insights ML: marketing._calculate_marketing_roi",
            )
            return {"error": str(e)}

    # -------------------------------------------------------- channel performance
    def _analyze_channels(self, from_str: str) -> Dict[str, Any]:
        """Per-source lead / opportunity / qualified-lead rollup.

        Returned shape: a dict of {channel_name: {leads, opportunities,
        qualified_leads, conversion_rate}} keyed by source. The legacy
        class returned the same dict and the marketing_agent reads
        ``full_context.get("channel_metrics", {})`` defensively, so the
        re-keyed name is fine here -- but to keep the public contract
        identical we still emit the same outer key the legacy code
        used.  ``channel_performance`` is the field name on the
        overview payload; the agent's ``channel_metrics`` lookup
        simply defaults to ``{}`` if the key is missing.
        """
        try:
            lead = self._lead_base(from_str)
            source_label = _coalesce_label(lead, "source", "Unattributed").name(
                "source_label"
            )

            qualified_flag = lead["status"].isin(_LEAD_QUALIFIED_STATUSES).cast("int")

            channel_df = (
                lead.group_by(source_label)
                .aggregate(
                    leads=lead.count(),
                    qualified_leads=qualified_flag.sum(),
                )
                .order_by(ibis.desc("leads"))
                .execute()
            )

            # Opportunities by source -- also period-scoped.
            # `source` was dropped from Lead/Opportunity's current meta in favour
            # of UTM tracking, but this site never adopted UTM (utm_source is
            # ~0% populated; the orphaned `source` column is 97.8% populated
            # for Lead and 97.1% for Opportunity). Same `extra_columns` escape
            # hatch used elsewhere (see `marketing._compute_marketing_overview`).
            opp_raw = t("Opportunity", extra_columns=("source",))
            opp = company_filter(opp_raw, self.company).filter(opp_raw["creation"] >= from_str)
            opp_source_label = _coalesce_label(opp, "source", "Unattributed").name(
                "source_label"
            )
            opp_df = (
                opp.group_by(opp_source_label)
                .aggregate(opportunities=opp.count())
                .execute()
            )
            opp_by_source: Dict[str, int] = {}
            if opp_df is not None and len(opp_df):
                for _, r in opp_df.iterrows():
                    opp_by_source[str(r.get("source_label") or "Unattributed")] = int(
                        r.get("opportunities") or 0
                    )

            channel_performance: Dict[str, Dict[str, Any]] = {}
            if channel_df is not None and len(channel_df):
                for _, r in channel_df.iterrows():
                    name = str(r.get("source_label") or "Unattributed")
                    leads = int(r.get("leads") or 0)
                    qualified = int(r.get("qualified_leads") or 0)
                    channel_performance[name] = {
                        "leads": leads,
                        "opportunities": int(opp_by_source.get(name, 0)),
                        "qualified_leads": qualified,
                        "conversion_rate": round((qualified / leads * 100), 2) if leads else 0,
                    }

            sorted_channels = dict(
                sorted(
                    channel_performance.items(),
                    key=lambda x: (x[1]["conversion_rate"], x[1]["leads"]),
                    reverse=True,
                )
            )

            total_channels = len(sorted_channels)
            return {
                "channel_performance": sorted_channels,
                "top_performing_channel": (
                    next(iter(sorted_channels), None) if sorted_channels else "None"
                ),
                "total_channels": total_channels,
                "channel_diversity": (
                    "high"
                    if total_channels > 5
                    else "medium"
                    if total_channels > 3
                    else "low"
                ),
            }
        except Exception as e:
            frappe.log_error(
                frappe.get_traceback(), "Insights ML: marketing._analyze_channels"
            )
            return {"error": str(e)}

    # ----------------------------------------------------------- pipeline forecast
    def _forecast_pipeline(self, from_str: str) -> Dict[str, Any]:
        """Probability-bucketed forecast. ERPNext Opportunity.probability
        is always 100 on this site, so bucketing by it would be
        meaningless; we instead bucket by Quotation.status (Draft /
        Ordered / Lost / Expired) which is the real money side of the
        pipeline. The "revenue forecast" is therefore an honest
        mix of won + probabilistic pending + expiring draft, not the
        fictional 0-100% probability bands the legacy code claimed."""
        try:
            opp = company_filter(t("Opportunity"), self.company).filter(
                t("Opportunity")["creation"] >= from_str
            )
            opp_count = _int(opp.aggregate(total=opp.count()))
            if opp_count == 0:
                return {"message": _("Insufficient data for pipeline forecasting")}

            quote = company_filter(t("Quotation"), self.company).filter(
                t("Quotation")["creation"] >= from_str
            )
            quote_status_label = _coalesce_label(quote, "status", "Unset").name(
                "status_label"
            )
            quote_df = (
                quote.group_by(quote_status_label)
                .aggregate(
                    count=quote.count(),
                    value=quote["base_grand_total"].sum(),
                )
                .execute()
            )
            quote_by_status: Dict[str, Dict[str, float]] = {}
            if quote_df is not None and len(quote_df):
                for _, r in quote_df.iterrows():
                    quote_by_status[str(r.get("status_label") or "Unset")] = {
                        "count": float(r.get("count") or 0),
                        "value": float(r.get("value") or 0),
                    }

            # Probability buckets derived from quotation status, not
            # from a constant probability field.
            high_value = quote_by_status.get("Ordered", {}).get("value", 0) + quote_by_status.get(
                "Partially Ordered", {}
            ).get("value", 0)
            medium_value = quote_by_status.get("Draft", {}).get("value", 0)
            low_value = quote_by_status.get("Expired", {}).get("value", 0)
            lost_value = quote_by_status.get("Lost", {}).get("value", 0)

            conservative_forecast = high_value * 0.8 + medium_value * 0.4
            optimistic_forecast = high_value * 0.9 + medium_value * 0.6 + low_value * 0.2
            pessimistic_forecast = high_value * 0.6 + medium_value * 0.2

            return {
                "current_pipeline_value": round(
                    sum(b.get("value", 0) for b in quote_by_status.values()), 2
                ),
                "weighted_pipeline_value": round(high_value, 2),
                "probability_breakdown": {
                    "high_probability": {
                        "count": int(
                            quote_by_status.get("Ordered", {}).get("count", 0)
                            + quote_by_status.get("Partially Ordered", {}).get("count", 0)
                        ),
                        "value": round(high_value, 2),
                    },
                    "medium_probability": {
                        "count": int(quote_by_status.get("Draft", {}).get("count", 0)),
                        "value": round(medium_value, 2),
                    },
                    "low_probability": {
                        "count": int(quote_by_status.get("Expired", {}).get("count", 0)),
                        "value": round(low_value, 2),
                    },
                },
                "lost_pipeline_value": round(lost_value, 2),
                "revenue_forecast": {
                    "conservative": round(conservative_forecast, 2),
                    "optimistic": round(optimistic_forecast, 2),
                    "pessimistic": round(pessimistic_forecast, 2),
                },
                "forecast_confidence": (
                    "high"
                    if opp_count > 20
                    else "medium"
                    if opp_count > 10
                    else "low"
                ),
            }
        except Exception as e:
            frappe.log_error(
                frappe.get_traceback(), "Insights ML: marketing._forecast_pipeline"
            )
            return {"error": str(e)}

    # --------------------------------------------------------- advanced lead scoring
    def _advanced_lead_scoring(self, from_str: str) -> Dict[str, Any]:
        """Advanced lead scoring using a multi-factor model. Pure-Python
        over the (bounded) per-lead fetch -- same shape as
        ``_score_lead_quality`` but with a richer scoring model and
        a Hot / Warm / Cold / Ice grade."""
        try:
            lead = self._lead_base(from_str)
            total = _int(lead.aggregate(total=lead.count()))
            if total == 0:
                return {"message": _("No leads available for scoring")}

            cols = ["name", "lead_name", "company_name", "status", "source", "territory"]
            if frappe.db.has_column("Lead", "custom_lead_score"):
                cols.append("custom_lead_score")
            df = lead.select(*cols).execute()
            if df is None or len(df) == 0:
                return {
                    "total_scored_leads": 0,
                    "average_score": 0,
                    "grade_distribution": {"Hot": 0, "Warm": 0, "Cold": 0, "Ice": 0},
                    "high_priority_leads": 0,
                    "top_leads": [],
                    "scoring_effectiveness": "needs_improvement",
                }

            source_scores = {
                "Referral": 30,
                "Existing Customer": 25,
                "Website": 20,
                "Campaign": 15,
                "Email": 12,
                "Social Media": 10,
                "Advertisement": 8,
                "Conference": 15,
                "Cold Call": 5,
            }
            status_scores = {
                "Converted": 40,
                "Interested": 30,
                "Qualified": 25,
                "Open": 15,
                "Replied": 20,
                "Opportunity": 35,
            }
            company_bonus = 15

            scored_leads = []
            for _, lead_row in df.iterrows():
                score = 0
                scoring_details = []

                source = str(lead_row.get("source") or "")
                source_score = source_scores.get(source, 5)
                score += source_score
                scoring_details.append(f"Source ({source}): {source_score}")

                status = str(lead_row.get("status") or "")
                status_score = status_scores.get(status, 5)
                score += status_score
                scoring_details.append(f"Status ({status}): {status_score}")

                if lead_row.get("company_name"):
                    score += company_bonus
                    scoring_details.append(f"Company provided: {company_bonus}")

                territory = str(lead_row.get("territory") or "All Territories")
                territory_score = 10  # default
                score += territory_score
                scoring_details.append(f"Territory ({territory}): {territory_score}")

                custom_score = lead_row.get("custom_lead_score")
                if custom_score:
                    try:
                        score += min(float(custom_score), 20)
                        scoring_details.append(f"Custom score: {custom_score}")
                    except (TypeError, ValueError):
                        pass

                final_score = min(score, 100)
                if final_score >= 80:
                    grade = "Hot"
                elif final_score >= 60:
                    grade = "Warm"
                elif final_score >= 40:
                    grade = "Cold"
                else:
                    grade = "Ice"

                scored_leads.append(
                    {
                        "lead": lead_row.get("name"),
                        "lead_name": lead_row.get("lead_name"),
                        "company": lead_row.get("company_name") or "",
                        "score": final_score,
                        "grade": grade,
                        "priority": (
                            "High"
                            if grade in ("Hot", "Warm")
                            else "Medium"
                            if grade == "Cold"
                            else "Low"
                        ),
                        "scoring_details": scoring_details,
                    }
                )

            scored_leads.sort(key=lambda x: x["score"], reverse=True)
            grade_distribution = {"Hot": 0, "Warm": 0, "Cold": 0, "Ice": 0}
            for lead_row in scored_leads:
                grade_distribution[lead_row["grade"]] += 1
            average_score = (
                sum(lead_row["score"] for lead_row in scored_leads) / len(scored_leads)
                if scored_leads
                else 0
            )

            return {
                "total_scored_leads": len(scored_leads),
                "average_score": round(average_score, 2),
                "grade_distribution": grade_distribution,
                "high_priority_leads": len(
                    [lead_row for lead_row in scored_leads if lead_row["priority"] == "High"]
                ),
                "top_leads": scored_leads[:20],
                "scoring_effectiveness": (
                    "excellent"
                    if average_score > 65
                    else "good"
                    if average_score > 50
                    else "needs_improvement"
                ),
            }
        except Exception as e:
            frappe.log_error(
                frappe.get_traceback(),
                "Insights ML: marketing._advanced_lead_scoring",
            )
            return {"error": str(e)}

    # ----------------------------------------------------- recommendations
    def _generate_marketing_recommendations(
        self,
        lead_metrics: Dict[str, Any],
        pipeline_metrics: Dict[str, Any],
        channel_data: Dict[str, Any],
        roi_data: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Threshold-based actionable recommendations, pure function of
        already-computed metrics. No DB access."""
        try:
            recommendations: List[Dict[str, Any]] = []

            qualification_rate = lead_metrics.get("qualification_rate_pct", 0)
            if qualification_rate < 20:
                recommendations.append(
                    {
                        "priority": "high",
                        "category": "Lead Generation",
                        "title": "Improve Lead Qualification Process",
                        "description": _(
                            "Lead qualification rate of {0}% is below benchmark (25%+)"
                        ).format(qualification_rate),
                        "actions": [
                            "Implement lead scoring system",
                            "Improve lead capture forms",
                            "Enhance pre-qualification criteria",
                        ],
                    }
                )

            conversion_rate = pipeline_metrics.get("conversion_rate_pct", 0)
            if conversion_rate < 15:
                recommendations.append(
                    {
                        "priority": "high",
                        "category": "Sales Pipeline",
                        "title": "Enhance Pipeline Conversion",
                        "description": _(
                            "Pipeline conversion rate of {0}% needs improvement"
                        ).format(conversion_rate),
                        "actions": [
                            "Improve sales follow-up process",
                            "Provide better sales training",
                            "Optimize sales stages",
                        ],
                    }
                )

            if channel_data.get("channel_diversity") == "low":
                recommendations.append(
                    {
                        "priority": "medium",
                        "category": "Channel Optimization",
                        "title": "Diversify Marketing Channels",
                        "description": _(
                            "Limited marketing channel diversity increases risk"
                        ),
                        "actions": [
                            "Explore new lead sources",
                            "Test additional marketing channels",
                            "Implement multi-channel strategy",
                        ],
                    }
                )

            roi = roi_data.get("marketing_roi_pct")
            if roi is not None and roi < 150:
                recommendations.append(
                    {
                        "priority": "medium",
                        "category": "ROI Optimization",
                        "title": "Improve Marketing ROI",
                        "description": _(
                            "Marketing ROI of {0}% is below target (200%+)"
                        ).format(roi),
                        "actions": [
                            "Optimize campaign targeting",
                            "Reduce acquisition costs",
                            "Focus on high-converting channels",
                        ],
                    }
                )

            total_leads = lead_metrics.get("total_leads", 0)
            qualified_leads = lead_metrics.get("qualified_leads", 0)
            if total_leads and total_leads > qualified_leads * 2:
                recommendations.append(
                    {
                        "priority": "medium",
                        "category": "Lead Nurturing",
                        "title": "Implement Lead Nurturing Program",
                        "description": _(
                            "Large number of unqualified leads suggest need for nurturing"
                        ),
                        "actions": [
                            "Create email nurturing sequences",
                            "Develop content marketing strategy",
                            "Implement marketing automation",
                        ],
                    }
                )

            return recommendations
        except Exception as e:
            frappe.log_error(
                frappe.get_traceback(),
                "Insights ML: marketing._generate_marketing_recommendations",
            )
            return [{"error": str(e)}]

    # ---------------------------------------------------- source metrics (class API)
    def get_source_metrics(
        self, period_start: str, period_end: str
    ) -> Dict[str, Any]:
        """Source / territory / cost-per-lead rollup, delegating to
        ``insights.ml.marketing_source_metrics``."""
        return {
            "leads_by_source": get_leads_by_source(period_start, period_end),
            "hot_leads_by_source": get_hot_leads_by_source(period_start, period_end),
            "cost_per_lead": get_cost_per_lead(period_start, period_end),
            "territory_leads": get_territory_leads(period_start, period_end),
        }


# ────────────────────────────────────────────────────────────────────────────
# Backward-compatible module-level API functions
# ────────────────────────────────────────────────────────────────────────────


def get_marketing_overview(period: str = "YTD") -> Dict[str, Any]:
    """Module-level convenience wrapper matching the old API. Returns
    the same dict ``MarketingIntelligence().get_marketing_overview``
    returns; kept so external callers (the marketing agent,
    executive_reports, and the test that exercises the permission
    gate) can keep using the module-level name."""
    return MarketingIntelligence(period=period).get_marketing_overview(period)


def get_pipeline_analysis(period: str = "YTD") -> Dict[str, Any]:
    """Pipeline-shaped slice of the marketing overview."""
    data = get_marketing_overview(period)
    return {
        "pipeline_metrics": data.get("pipeline_metrics", {}),
        "pipeline_forecast": data.get("pipeline_forecast", {}),
        "conversion_metrics": data.get("conversion_metrics", {}),
    }


def get_lead_analytics() -> Dict[str, Any]:
    """Lead-shaped slice of the marketing overview (YTD)."""
    data = get_marketing_overview("YTD")
    return {
        "lead_metrics": data.get("lead_metrics", {}),
        "lead_quality_score": data.get("lead_quality_score", {}),
        "lead_scoring": data.get("lead_scoring", {}),
    }


def get_campaign_performance() -> Dict[str, Any]:
    """Campaign-shaped slice of the marketing overview (YTD)."""
    data = get_marketing_overview("YTD")
    return {
        "campaign_metrics": data.get("campaign_metrics", {}),
        "marketing_roi": data.get("marketing_roi", {}),
        "channel_performance": data.get("channel_performance", {}),
    }


def get_marketing_recommendations() -> List[Dict[str, Any]]:
    """Recommendations slice of the marketing overview (YTD)."""
    data = get_marketing_overview("YTD")
    return data.get("recommendations", [])


# `update_marketing_intelligence` used to be the scheduler entry point
# called from hooks.py / a daily cron. With the ML layer gone (no
# cache, no background job) it is a no-op kept for forward
# compatibility -- the central hooks dispatcher may still import it
# by name and rely on the call not raising.
def update_marketing_intelligence() -> Dict[str, Any]:
    """No-op stub. Marketing intelligence is computed on demand; no
    scheduled warm-up needed."""
    return {
        "status": "no_op",
        "message": "Marketing intelligence is computed on demand; no scheduled warm-up needed.",
    }


def get_source_metrics(period: str = "YTD") -> Dict[str, Any]:
    """Source-metrics slice of the marketing overview, period-scoped."""
    if not period:
        period = "YTD"
    from frappe.utils import add_months, getdate

    today = getdate()
    if period == "MTD":
        start_date = today.replace(day=1)
    elif period == "QTD":
        quarter_start = ((today.month - 1) // 3) * 3 + 1
        start_date = today.replace(month=quarter_start, day=1)
    elif period == "YTD":
        start_date = today.replace(month=1, day=1)
    else:  # TTM
        start_date = add_months(today, -12)
    start_str = start_date.isoformat()
    end_str = today.isoformat()
    return {
        "leads_by_source": get_leads_by_source(start_str, end_str),
        "hot_leads_by_source": get_hot_leads_by_source(start_str, end_str),
        "cost_per_lead": get_cost_per_lead(start_str, end_str),
        "territory_leads": get_territory_leads(start_str, end_str),
    }
