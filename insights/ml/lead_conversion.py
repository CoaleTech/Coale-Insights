from __future__ import annotations

# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Lead Conversion -- Ibis-native rewrite.

Was a scikit-learn ``RandomForestClassifier`` (with class-weight balancing
and a held-out 25% test set) trained on closed Leads. The forest gave
accuracy/precision/recall/AUC and a feature-importance table.

The classifier is gone. The win-probability for an open lead is now a
transparent weighted rule score, computed by MariaDB via Ibis:

  Score (0-100) = w1 * source_win_rate
                + w2 * territory_win_rate
                + w3 * industry_win_rate
                + w4 * engagement_component
                + w5 * size_component
                + w6 * age_component

Each component is a 0-100 signal. The historical win rates are one Ibis
``group_by().aggregate()`` per dimension; the open-lead table is a single
``SELECT`` joined back to the dimension rates. No model, no train/test
split, no numpy/sklearn dependency.

Weights (sum = 100):
  25 -- historical win rate of the lead's source
  20 -- historical win rate of the lead's territory
  20 -- historical win rate of the lead's industry
  15 -- engagement: opportunity_count (Leads with at least one Opportunity
        are much more likely to close)
  10 -- size: bucket of the lead's annual_revenue
  10 -- age in days, capped; very old open leads are usually cold, not
        warm

The historical win-rate components are guarded by MIN_HISTORY_PER_GROUP;
buckets below that fall back to the global win rate rather than quoting
a rate from three leads.

The data-sufficiency gate (>= 50 won AND >= 50 lost closed leads) still
trips a graceful ``insufficient_data`` response. The gate is now an Ibis
count, not sklearn's own data check.
"""

from datetime import datetime, timedelta

import frappe
import ibis
from frappe import _

from insights.api.ml.ibis_source import company_filter, default_company, t

MIN_CLASS_EXAMPLES = 50
MIN_HISTORY_PER_GROUP = 10

WON_STATUSES = ("Converted",)
LOST_STATUSES = ("Lost Quotation", "Do Not Contact")

WEIGHT_SOURCE = 25
WEIGHT_TERRITORY = 20
WEIGHT_INDUSTRY = 20
WEIGHT_ENGAGEMENT = 15
WEIGHT_SIZE = 10
WEIGHT_AGE = 10


class LeadConversion:
    """Ibis-native scorer for open Leads.

    Plain class on purpose: no training step, no cache, no model. The
    ``train()`` and ``predict()`` shapes are kept so the scheduler and
    the model_ops health page can keep reading the same keys.
    """

    CACHE_KEY = "lead_conversion"

    def __init__(self, months_back: int = 24) -> None:
        self.months_back = months_back
        self.company = default_company()

    # -----------------------------------------------------------------
    # public surface
    # -----------------------------------------------------------------

    def train(self) -> dict:
        """Compute the win rates and the open-lead scoring. Synchronous,
        a handful of SQL round trips."""
        try:
            counts = self._count_outcomes()
            if counts is None:
                return {"status": "error", "message": _("No leads found.")}
            won, lost = counts
            if min(won, lost) < MIN_CLASS_EXAMPLES:
                return {
                    "status": "insufficient_data",
                    "message": _(
                        "Needs at least {0} won and {0} lost leads to score; this site has "
                        "{1} won and {2} lost."
                    ).format(MIN_CLASS_EXAMPLES, won, lost),
                    "won": won,
                    "lost": lost,
                }

            source_rates = self._win_rates_by("source")
            territory_rates = self._win_rates_by("territory")
            industry_rates = self._win_rates_by("industry")
            global_rate = (won / max(1, won + lost)) * 100.0
            top_open = self._score_open_leads(
                source_rates, territory_rates, industry_rates, global_rate
            )

            return {
                "status": "success",
                "generated_at": datetime.now().isoformat(),
                "training": {
                    "won": won,
                    "lost": lost,
                    "closed_total": won + lost,
                    "open_scored": len(top_open),
                    "months_back": self.months_back,
                },
                # The old forest's metric keys. None for a rule scorer;
                # the model_health page already treats them as advisory.
                "metrics": {
                    "accuracy": None,
                    "precision": None,
                    "recall": None,
                    "roc_auc": None,
                    "note": "weighted rule score; no test set",
                },
                "feature_importance": [
                    {"feature": "source_win_rate", "importance": WEIGHT_SOURCE / 100.0},
                    {"feature": "territory_win_rate", "importance": WEIGHT_TERRITORY / 100.0},
                    {"feature": "industry_win_rate", "importance": WEIGHT_INDUSTRY / 100.0},
                    {"feature": "engagement", "importance": WEIGHT_ENGAGEMENT / 100.0},
                    {"feature": "size", "importance": WEIGHT_SIZE / 100.0},
                    {"feature": "age", "importance": WEIGHT_AGE / 100.0},
                ],
                "conversion_rate": round(global_rate, 1),
                "by_source": [
                    {"source": k, "closed": v["closed"], "won": v["won"], "win_rate": v["win_rate"]}
                    for k, v in source_rates.items()
                ],
                "top_open_leads": top_open,
            }
        except Exception as e:
            frappe.log_error(f"Lead conversion scoring failed: {e}", "ML Leads")
            return {"status": "error", "message": str(e)}

    def predict(self, allow_train: bool = False) -> dict:
        """Same payload as ``train()``; the score is always live."""
        return self.train()

    # -----------------------------------------------------------------
    # queries
    # -----------------------------------------------------------------

    def _count_outcomes(self) -> tuple[int, int] | None:
        lead = t("Lead")
        cutoff = _months_ago(self.months_back)
        q = company_filter(
            lead.filter(lead.docstatus < 2, lead.creation >= cutoff),
            self.company,
        )
        # Inline the boolean cast *inside* the aggregate call -- Ibis on
        # MariaDB doesn't allow referencing a column created in a
        # previous .mutate() in a following .aggregate() because each
        # reduction is bound to its own relation.
        df = q.aggregate(
            won=lead.status.isin(list(WON_STATUSES)).cast("int").sum(),
            lost=lead.status.isin(list(LOST_STATUSES)).cast("int").sum(),
        ).execute()
        if df.empty:
            return None
        r = df.iloc[0]
        return int(r["won"] or 0), int(r["lost"] or 0)

    def _win_rates_by(self, column: str) -> dict:
        """One Ibis aggregate per dimension. Returns a dict keyed by
        bucket name with closed/won/win_rate entries. Win rate is
        computed in Python on the small aggregate result; SQL only
        returns the two integer aggregates per bucket.
        """
        lead = t("Lead")
        cutoff = _months_ago(self.months_back)
        q = company_filter(
            lead.filter(lead.docstatus < 2, lead.creation >= cutoff),
            self.company,
        )
        df = (
            q.group_by(column)
            .aggregate(
                closed=q.count(),
                won=lead.status.isin(list(WON_STATUSES)).cast("int").sum(),
            )
            .execute()
        )
        out: dict = {}
        for r in df.to_dict(orient="records"):
            closed_n = int(r["closed"] or 0)
            won_n = int(r["won"] or 0)
            win_rate = (won_n / closed_n) * 100.0 if closed_n else 0.0
            out[r[column]] = {
                "closed": closed_n,
                "won": won_n,
                "win_rate": round(win_rate, 1),
            }
        return out

    def _score_open_leads(
        self,
        source_rates: dict,
        territory_rates: dict,
        industry_rates: dict,
        global_rate: float,
    ) -> list[dict]:
        lead = t("Lead")
        cutoff = _months_ago(self.months_back)
        q = company_filter(
            lead.filter(lead.docstatus < 2, lead.creation >= cutoff),
            self.company,
        )
        won_expr = lead.status.isin(list(WON_STATUSES))
        lost_expr = lead.status.isin(list(LOST_STATUSES))
        q = q.filter(~(won_expr | lost_expr))

        # opportunity_count: aggregate opportunities per party_name, then
        # left-join back to Leads. The mutate-then-aggregate dance is
        # needed because Ibis on MariaDB rejects projecting a reduction
        # (opp.count()) that was bound to the source table onto a
        # different relation; rebinding it through a literal column on
        # the same table makes the reduction group-by-aware.
        opp = t("Opportunity")
        opp_with_flag = opp.filter(opp.opportunity_from == "Lead").mutate(
            _one=ibis.literal(1)
        )
        opp_per_lead = opp_with_flag.group_by(opp_with_flag.party_name).aggregate(
            n=opp_with_flag._one.sum()
        )
        q = q.mutate(
            source_bucket=lead.source.fill_null("Unknown").replace("", "Unknown"),
            territory_bucket=lead.territory.fill_null("Unknown").replace("", "Unknown"),
            industry_bucket=lead.industry.fill_null("Unknown").replace("", "Unknown"),
            age_days=ibis_days_since(lead.creation),
        )
        q = q.left_join(opp_per_lead, q.name == opp_per_lead.party_name).mutate(
            opportunity_count=opp_per_lead.n.fill_null(0),
        )
        df = (
            q.select(
                "name",
                "lead_name",
                "company_name",
                "status",
                "source",
                "territory",
                "industry",
                "annual_revenue",
                "age_days",
                "opportunity_count",
                "source_bucket",
                "territory_bucket",
                "industry_bucket",
            )
            .order_by("name")
            .limit(500)
            .execute()
        )
        scored = []
        for r in df.to_dict(orient="records"):
            score, components = _score_one(
                r, source_rates, territory_rates, industry_rates, global_rate
            )
            scored.append(
                {
                    "lead": r["name"],
                    "lead_name": r.get("lead_name") or r.get("company_name") or r["name"],
                    "status": r.get("status"),
                    "source": r.get("source") or "Unknown",
                    "territory": r.get("territory") or "Unknown",
                    "industry": r.get("industry") or "Unknown",
                    "annual_revenue": float(r.get("annual_revenue") or 0),
                    "age_days": int(r.get("age_days") or 0),
                    "opportunity_count": int(r.get("opportunity_count") or 0),
                    "win_probability": score,
                    "band": _band(score),
                    "components": components,
                }
            )
        scored.sort(key=lambda r: r["win_probability"], reverse=True)
        return scored[:50]


# ---------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------


def _months_ago(months: int):
    return (datetime.now() - timedelta(days=int(months) * 30)).date()


def ibis_days_since(date_col):
    """MariaDB DATEDIFF(CURDATE(), <col>) as an integer (days)."""
    today = datetime.now().date()
    return ibis.ifelse(
        date_col.isnull(),
        ibis.literal(0),
        date_col.cast("date").delta(today, unit="day"),
    )


def _rate_with_fallback(table: dict, key: str, fallback: float) -> tuple[float, bool]:
    """Look up a historical win rate by bucket; fall back to the global
    rate if the bucket is too thin to quote (or missing)."""
    row = table.get(key) or table.get("Unknown")
    if not row or row["closed"] < MIN_HISTORY_PER_GROUP:
        return fallback, False
    return row["win_rate"], True


def _component_engagement(opp_count: int) -> float:
    if opp_count >= 2:
        return 100.0
    if opp_count == 1:
        return 70.0
    return 0.0


def _component_size(annual_revenue: float) -> float:
    """A coarse bucket: bigger deals are harder but also more visible.
    Mild signal (max weight 10)."""
    if not annual_revenue or annual_revenue <= 0:
        return 30.0
    if annual_revenue < 1_000_000:
        return 40.0
    if annual_revenue < 10_000_000:
        return 60.0
    if annual_revenue < 100_000_000:
        return 75.0
    return 90.0


def _component_age(age_days: int) -> float:
    """Very young leads are uncertain, very old are usually cold. The
    sweet spot is 7-30 days."""
    if age_days <= 0:
        return 50.0
    if age_days <= 7:
        return 30.0
    if age_days <= 30:
        return 80.0
    if age_days <= 90:
        return 60.0
    if age_days <= 180:
        return 30.0
    return 10.0


def _band(probability: float) -> str:
    if probability >= 60:
        return "High"
    if probability >= 30:
        return "Medium"
    return "Low"


def _score_one(
    row: dict,
    source_rates: dict,
    territory_rates: dict,
    industry_rates: dict,
    fallback: float,
) -> tuple[float, dict]:
    src_rate, _ = _rate_with_fallback(source_rates, row.get("source_bucket", "Unknown"), fallback)
    ter_rate, _ = _rate_with_fallback(territory_rates, row.get("territory_bucket", "Unknown"), fallback)
    ind_rate, _ = _rate_with_fallback(industry_rates, row.get("industry_bucket", "Unknown"), fallback)
    c_eng = _component_engagement(int(row.get("opportunity_count") or 0))
    c_size = _component_size(float(row.get("annual_revenue") or 0))
    c_age = _component_age(int(row.get("age_days") or 0))

    score = (
        WEIGHT_SOURCE * src_rate / 100.0
        + WEIGHT_TERRITORY * ter_rate / 100.0
        + WEIGHT_INDUSTRY * ind_rate / 100.0
        + WEIGHT_ENGAGEMENT * c_eng / 100.0
        + WEIGHT_SIZE * c_size / 100.0
        + WEIGHT_AGE * c_age / 100.0
    )
    score = max(0.0, min(100.0, score))
    components = {
        "source_win_rate": round(src_rate, 1),
        "territory_win_rate": round(ter_rate, 1),
        "industry_win_rate": round(ind_rate, 1),
        "engagement": round(c_eng, 1),
        "size": round(c_size, 1),
        "age": round(c_age, 1),
    }
    return round(score, 1), components
