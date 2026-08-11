from __future__ import annotations
# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Payment Risk Intelligence -- Ibis-native rewrite.

Was a scikit-learn ``RandomForestClassifier`` (with a hand-rolled
``_train_rule_based`` fallback) trained on paid Sales Invoices. The forest
needed ~50 examples per outcome before it stopped memorising the majority
class; below that floor the same rule-based scorer ran instead. The
``predict()`` path then assembled a feature row per outstanding invoice,
ran the model, and bolted on a hand-written ``_calculate_risk_score`` on top.

The classifier is gone. The whole module is now a transparent weighted rule
score, computed by MariaDB via Ibis on a single round trip per query:

  Risk (0-100) = w1 * days_overdue_component
               + w2 * customer_on_time_rate_component
               + w3 * invoice_vs_typical_amount_component
               + w4 * customer_late_history_component
               + w5 * high_days_to_pay_component

Each component is a normalised 0-100 signal that a finance team can read
and override; weights below sum to 100. No model, no train/test split, no
numpy/sklearn dependency, no fork-safety problem.

Weights (sum = 100):
  30 -- days already past due on the invoice (the strongest signal in
        AR collections; overdue is overdue).
  25 -- historical on-time payment rate of THIS customer (low on-time rate
        over a long history is a much stronger predictor than the same
        rate for a customer with two paid invoices).
  15 -- this invoice's size relative to the customer's typical invoice
        (one unusually large invoice is harder for a customer to absorb).
  15 -- share of this customer's prior invoices that were paid late
        (complements on-time rate but is more directional).
  15 -- average days-to-pay of this customer (if they always pay at day
        45, even a "Current" invoice is a moderate risk).

The score lands on the same 0-100 scale and the same Low/Medium/High
bucketing the frontend already renders, so Vue callers do not change.
"""

from datetime import datetime

import frappe
import ibis
from frappe import _

from insights.api.ml.ibis_source import company_filter, default_company, t

# Hard floors: no per-customer history -> neutral component; no paid
# invoices at all -> the customer is genuinely unknown, score everything
# from invoice-level signals only.
MIN_HISTORY_FOR_CUSTOMER_SCORE = 1

# A finance team can edit these in code review; they are intentionally
# explicit so the score is auditable, not learned.
WEIGHT_DAYS_OVERDUE = 30
WEIGHT_ON_TIME_RATE = 25
WEIGHT_AMOUNT_VS_TYPICAL = 15
WEIGHT_LATE_HISTORY_SHARE = 15
WEIGHT_AVG_DAYS_TO_PAY = 15


class PaymentPrediction:
    """Ibis-native risk scorer for outstanding Sales Invoices.

    Kept as a plain class (not a ``BaseMLModel``) on purpose: there is no
    training step, no cache, and no model to ship to the disk snapshot.
    The ``run_payment_prediction()`` and ``get_payment_predictions()``
    module-level helpers below are what the API endpoints and the
    scheduler call into; both answer synchronously.
    """

    def __init__(self) -> None:
        self.company = default_company()

    # -----------------------------------------------------------------
    # public surface
    # -----------------------------------------------------------------

    def train(self) -> dict:
        """No training is required for the rule scorer.

        Kept because the scheduler (``insights.ml.scheduler.train_payment_prediction``)
        and ``run_all_models`` still call ``model.train()`` -- returning a
        small health dict keeps them happy without faking a model fit.
        """
        closed = self._count_closed_invoices()
        return {
            "status": "success",
            "training_date": frappe.utils.now(),
            "training_samples": closed,
            "model": "weighted_rule_score",
            "weights": {
                "days_overdue": WEIGHT_DAYS_OVERDUE,
                "on_time_rate": WEIGHT_ON_TIME_RATE,
                "amount_vs_typical": WEIGHT_AMOUNT_VS_TYPICAL,
                "late_history_share": WEIGHT_LATE_HISTORY_SHARE,
                "avg_days_to_pay": WEIGHT_AVG_DAYS_TO_PAY,
            },
            "metrics": {
                "note": "rule-based scorer; no test set or accuracy metric",
            },
        }

    def predict(self) -> dict:
        """Score every outstanding invoice for the current company."""
        outstanding = self._fetch_outstanding_invoices()
        history = self._fetch_customer_history()

        if not outstanding:
            return {
                "status": "success",
                "prediction_date": datetime.now().isoformat(),
                "summary": {
                    "total_outstanding": 0.0,
                    "total_invoices": 0,
                    "high_risk_count": 0,
                    "high_risk_amount": 0.0,
                    "overdue_count": 0,
                    "overdue_amount": 0.0,
                },
                "predictions": [],
            }

        predictions = [self._score_invoice(row, history) for row in outstanding]
        predictions.sort(key=lambda p: p["risk_score"], reverse=True)

        summary = {
            "total_outstanding": float(sum(p["outstanding_amount"] for p in predictions)),
            "total_invoices": len(predictions),
            "high_risk_count": sum(1 for p in predictions if p["risk_level"] == "High"),
            "high_risk_amount": float(
                sum(p["outstanding_amount"] for p in predictions if p["risk_level"] == "High")
            ),
            "overdue_count": sum(1 for p in predictions if p["days_overdue"] > 0),
            "overdue_amount": float(
                sum(p["outstanding_amount"] for p in predictions if p["days_overdue"] > 0)
            ),
        }

        return {
            "status": "success",
            "prediction_date": datetime.now().isoformat(),
            "summary": summary,
            "predictions": predictions,
        }

    # -----------------------------------------------------------------
    # Ibis queries
    # -----------------------------------------------------------------

    def _count_closed_invoices(self) -> int:
        si = company_filter(t("Sales Invoice"), self.company).filter(
            t("Sales Invoice").docstatus == 1
        )
        row = si.aggregate(n=si.count()).execute().iloc[0]
        return int(row["n"] or 0)

    def _fetch_outstanding_invoices(self) -> list[dict]:
        """Every Sales Invoice that is still partly unpaid, for the current
        company (when there is one). One SQL round trip."""
        si = t("Sales Invoice")
        q = si.filter(si.docstatus == 1, si.outstanding_amount > 0)
        q = company_filter(q, self.company)
        today = datetime.now().date()
        q = q.mutate(
            invoice_id=q.name,
            days_overdue=ibis.ifelse(
                q.due_date.isnull(),
                ibis.literal(0),
                ibis.greatest(q.due_date.cast("date").delta(today, unit="day"), 0),
            ),
        )
        df = (
            q.select(
                "invoice_id",
                "customer",
                "customer_name",
                "grand_total",
                "outstanding_amount",
                "posting_date",
                "due_date",
                "days_overdue",
            )
            .order_by("due_date")
            .execute()
        )
        return [dict(r) for r in df.to_dict(orient="records")]

    def _fetch_customer_history(self) -> dict:
        """Per-customer aggregates from CLOSED Sales Invoices (paid in
        full). One group-by aggregate; never raw transactions in Python.
        """
        si = t("Sales Invoice")
        closed = si.filter(si.docstatus == 1, si.outstanding_amount == 0)
        closed = company_filter(closed, self.company)
        # MariaDB DATEDIFF on dates, returning NULL on null inputs.
        closed = closed.mutate(
            credit_days=ibis.ifelse(
                closed.due_date.isnull() | closed.posting_date.isnull(),
                ibis.null(),
                closed.due_date.cast("date").delta(closed.posting_date.cast("date"), unit="day"),
            ),
            days_to_pay=ibis.ifelse(
                closed.modified.isnull() | closed.posting_date.isnull(),
                ibis.null(),
                closed.modified.cast("date").delta(closed.posting_date.cast("date"), unit="day"),
            ),
        )
        closed = closed.mutate(
            is_late=ibis.ifelse(
                closed.days_to_pay.isnull() | closed.credit_days.isnull(),
                ibis.literal(False),
                closed.days_to_pay > closed.credit_days,
            )
        )
        agg = closed.group_by(closed.customer).aggregate(
            closed_invoices=closed.count(),
            on_time_payments=(~closed.is_late).sum(),
            late_payments=closed.is_late.sum(),
            avg_days_to_pay=closed.days_to_pay.mean(),
            avg_invoice_value=closed.grand_total.mean(),
        )
        df = agg.execute()
        out: dict = {}
        for r in df.to_dict(orient="records"):
            closed_n = int(r["closed_invoices"] or 0)
            on_time = int(r["on_time_payments"] or 0)
            late = int(r["late_payments"] or 0)
            r["on_time_rate"] = (on_time / closed_n) if closed_n else 0.0
            r["late_share"] = (late / closed_n) if closed_n else 0.0
            out[r["customer"]] = r
        return out

    # -----------------------------------------------------------------
    # per-invoice scoring
    # -----------------------------------------------------------------

    def _score_invoice(self, row: dict, history: dict) -> dict:
        customer = row["customer"]
        cust = history.get(customer, {})
        closed_n = int(cust.get("closed_invoices", 0) or 0)
        on_time_rate = float(cust.get("on_time_rate", 0.0) or 0.0)
        late_share = float(cust.get("late_share", 0.0) or 0.0)
        avg_days_to_pay = cust.get("avg_days_to_pay")
        avg_invoice_value = cust.get("avg_invoice_value")

        days_overdue = max(0, int(row.get("days_overdue") or 0))
        outstanding = float(row.get("outstanding_amount") or 0.0)
        this_amount = float(row.get("grand_total") or 0.0)

        # Each component is 0-100; the weighted sum is 0-100.
        c_days_overdue = _component_days_overdue(days_overdue)
        c_on_time = (
            _component_on_time_rate(on_time_rate)
            if closed_n >= MIN_HISTORY_FOR_CUSTOMER_SCORE
            else 50.0
        )
        c_amount = (
            _component_amount_vs_typical(this_amount, avg_invoice_value)
            if closed_n >= MIN_HISTORY_FOR_CUSTOMER_SCORE and avg_invoice_value
            else 50.0
        )
        c_late = (
            _component_late_share(late_share)
            if closed_n >= MIN_HISTORY_FOR_CUSTOMER_SCORE
            else 50.0
        )
        c_dtp = (
            _component_avg_days_to_pay(avg_days_to_pay)
            if closed_n >= MIN_HISTORY_FOR_CUSTOMER_SCORE and avg_days_to_pay is not None
            else 50.0
        )

        score = (
            WEIGHT_DAYS_OVERDUE * c_days_overdue / 100.0
            + WEIGHT_ON_TIME_RATE * c_on_time / 100.0
            + WEIGHT_AMOUNT_VS_TYPICAL * c_amount / 100.0
            + WEIGHT_LATE_HISTORY_SHARE * c_late / 100.0
            + WEIGHT_AVG_DAYS_TO_PAY * c_dtp / 100.0
        )
        score = max(0.0, min(100.0, score))
        risk_level = _risk_level(score)

        if closed_n >= MIN_HISTORY_FOR_CUSTOMER_SCORE and avg_days_to_pay is not None:
            posted = row.get("posting_date")
            try:
                elapsed = (datetime.now().date() - posted).days if posted else 0
            except Exception:
                elapsed = 0
            expected = max(0, int(avg_days_to_pay - elapsed))
        else:
            expected = 30

        return {
            "invoice_id": row["invoice_id"],
            "customer": customer,
            "customer_name": row.get("customer_name") or customer,
            "outstanding_amount": outstanding,
            "due_date": str(row.get("due_date")),
            "days_overdue": days_overdue,
            "risk_score": round(score, 1),
            "risk_level": risk_level,
            "expected_days_to_pay": expected,
            "recommended_action": _recommended_action(score, days_overdue),
            "components": {
                "days_overdue": round(c_days_overdue, 1),
                "on_time_rate": round(c_on_time, 1),
                "amount_vs_typical": round(c_amount, 1),
                "late_share": round(c_late, 1),
                "avg_days_to_pay": round(c_dtp, 1),
            },
        }


# ---------------------------------------------------------------------
# component curves
# ---------------------------------------------------------------------


def _component_days_overdue(days: int) -> float:
    """0 days -> 0, 30 days -> 50, 60 days -> 80, 90+ days -> 100.
    Linear ramp saturates -- 200 days overdue is not materially worse
    than 90 from a collections standpoint.
    """
    if days <= 0:
        return 0.0
    if days >= 90:
        return 100.0
    return min(100.0, days * (100.0 / 90.0))


def _component_on_time_rate(rate: float) -> float:
    """Inverted: 100% on time -> 0 risk, 0% on time -> 100 risk.
    rate is 0..1; bucketed so a near-perfect payer is rewarded more
    than a near-miss is penalised.
    """
    rate = max(0.0, min(1.0, rate))
    if rate >= 0.95:
        return 0.0
    if rate >= 0.80:
        return 20.0
    if rate >= 0.50:
        return 60.0
    return 100.0


def _component_late_share(late: float) -> float:
    """Share of prior invoices that were paid late. 0 -> 0, 0.5 -> 60,
    1.0 -> 100. Symmetric with on-time rate but additive so a customer
    who pays late AND late AND late gets a stronger signal than a single
    factor can express.
    """
    late = max(0.0, min(1.0, late))
    if late <= 0.05:
        return 0.0
    if late <= 0.20:
        return 25.0
    if late <= 0.50:
        return 60.0
    return 100.0


def _component_amount_vs_typical(this: float, typical: float | None) -> float:
    """If this invoice is 1x the customer's typical, score 0; 2x -> 50;
    3x+ -> 100. ``typical`` is the mean grand_total across their paid
    invoices. Unusually large invoices are harder to collect.
    """
    if not typical or typical <= 0 or not this:
        return 50.0
    this = float(this)
    typical = float(typical)
    if typical <= 0:
        return 50.0
    ratio = this / typical
    if ratio <= 1.0:
        return 0.0
    if ratio >= 3.0:
        return 100.0
    return (ratio - 1.0) * 50.0

def _component_avg_days_to_pay(avg: float | None) -> float:
    """A customer who always pays at day 45 is riskier than one at day
    15, even on a not-yet-overdue invoice. <15 days -> 0, 30 -> 30,
    60 -> 80, 90+ -> 100. The "credit terms" anchor is 30 days, the
    most common in B2B.
    """
    if avg is None or avg < 0:
        return 50.0
    if avg <= 15:
        return 0.0
    if avg <= 30:
        return 30.0
    if avg <= 60:
        return 60.0
    if avg <= 90:
        return 80.0
    return 100.0


def _risk_level(score: float) -> str:
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


def _recommended_action(score: float, days_overdue: int) -> str:
    if days_overdue > 60 or score > 80:
        return "Escalate to collections team immediately"
    if days_overdue > 30 or score > 60:
        return "Send formal demand letter and call customer"
    if days_overdue > 0 or score > 40:
        return "Send payment reminder email"
    return "Monitor - low risk"


# ---------------------------------------------------------------------
# API functions
# ---------------------------------------------------------------------


def run_payment_prediction() -> dict:
    """Train payment prediction model (now a no-op health check)."""
    return PaymentPrediction().train()


def get_payment_predictions() -> dict:
    """Get payment risk predictions for outstanding invoices."""
    return PaymentPrediction().predict()


def get_customer_payment_risk(customer: str) -> dict:
    """Get payment risk for a specific customer."""
    result = PaymentPrediction().predict()
    invoices = [p for p in result.get("predictions", []) if p.get("customer") == customer]
    if not invoices:
        return {"status": "success", "message": _("No outstanding invoices for customer")}

    return {
        "status": "success",
        "customer": customer,
        "total_outstanding": float(sum(p["outstanding_amount"] for p in invoices)),
        "invoices": invoices,
    }
