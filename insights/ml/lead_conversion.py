# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Lead → win probability.

The only place on this site with thousands of labelled outcomes and no model.
ERPNext's own CRM records the answer for every closed lead:

    Lead.status         Converted / Lost Quotation
    Opportunity.status  Converted / Lost

Everything else in the ML layer forecasts a series or scores a rule. This is a
straight supervised classification problem with real labels, so it is the one
place a classifier is clearly the right tool rather than decoration.

Features are deliberately only what exists at creation time plus elapsed age --
nothing derived from the outcome. `converted_on` or a won Quotation would leak
the label and produce a model that scores 100% and predicts nothing.
"""

from frappe import _
import pandas as pd
from datetime import datetime
from typing import Any, Dict

from insights.ml.base import BaseMLModel

# Below this many examples of the minority outcome a classifier memorises rather
# than learns. Same floor and same reasoning as payment_prediction.
MIN_CLASS_EXAMPLES = 50

# Statuses that end a lead's life, mapped to the label.
WON_STATUSES = ("Converted",)
LOST_STATUSES = ("Lost Quotation", "Do Not Contact")


class LeadConversion(BaseMLModel):
    """Probability that an open lead converts, learned from closed ones."""

    CACHE_KEY = "lead_conversion"

    def __init__(self, months_back: int = 24):
        super().__init__()
        self.model_name = "LeadConversion"
        self.months_back = months_back

    # ---------------------------------------------------------------- data

    def _get_leads(self) -> pd.DataFrame:
        """Closed and open leads with only creation-time attributes."""
        return self.get_training_data(
            """
            SELECT
                l.name,
                l.lead_name,
                l.status,
                l.source,
                l.territory,
                l.industry,
                l.company_name,
                l.creation,
                l.modified,
                COALESCE(l.annual_revenue, 0) AS annual_revenue,
                COALESCE(l.no_of_employees, '') AS no_of_employees,
                (SELECT COUNT(*) FROM `tabOpportunity` o
                  WHERE o.opportunity_from = 'Lead' AND o.party_name = l.name) AS opportunity_count
            FROM `tabLead` l
            WHERE l.docstatus < 2
              AND l.creation >= DATE_SUB(CURDATE(), INTERVAL %(months)s MONTH)
            """,
            {"months": int(self.months_back)},
        )

    @staticmethod
    def _label(status: str):
        if status in WON_STATUSES:
            return 1
        if status in LOST_STATUSES:
            return 0
        return None

    def _featurise(self, df: pd.DataFrame) -> pd.DataFrame:
        """One-hot the categoricals, keep the numerics, add lead age in days.

        `age_days` has to mean one thing for both halves of the frame. Measured
        as "now minus creation" it means time-to-close for a lead that is closed
        and time-so-far for one that is open -- and since closed leads are older
        by construction, the model learns the difference between the two
        populations rather than anything about winning. It dominated feature
        importance on the first run for exactly that reason.

        Defined here as days from creation to the decision point: `modified` for
        a closed lead, now for an open one.
        """
        df = df.copy()
        created = pd.to_datetime(df["creation"])
        closed_at = pd.to_datetime(df["modified"])
        now = pd.Timestamp(datetime.now())
        decision_point = closed_at.where(df["label"].notna(), now)
        df["age_days"] = (decision_point - created).dt.days.clip(lower=0)
        df["annual_revenue"] = pd.to_numeric(df["annual_revenue"], errors="coerce").fillna(0)
        df["opportunity_count"] = pd.to_numeric(df["opportunity_count"], errors="coerce").fillna(0)

        categoricals = ["source", "territory", "industry"]
        for col in categoricals:
            df[col] = df[col].fillna("Unknown").replace("", "Unknown")

        encoded = pd.get_dummies(df[categoricals], prefix=categoricals, dtype=float)
        numeric = df[["age_days", "annual_revenue", "opportunity_count"]].astype(float)
        return pd.concat([numeric, encoded], axis=1)

    # ---------------------------------------------------------------- train

    def train(self) -> Dict[str, Any]:
        """Fit on closed leads, then score the open ones. Worker-side only."""
        try:
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
        except ImportError:
            return {
                "status": "error",
                "message": _("scikit-learn is not installed on this bench."),
            }

        df = self._get_leads()
        if df.empty:
            return {"status": "error", "message": _("No leads found.")}

        df["label"] = df["status"].apply(self._label)
        closed = df[df["label"].notna()].copy()
        won = int((closed["label"] == 1).sum())
        lost = int((closed["label"] == 0).sum())

        if min(won, lost) < MIN_CLASS_EXAMPLES:
            return {
                "status": "insufficient_data",
                "message": _(
                    "Needs at least {0} won and {0} lost leads to train; this site has "
                    "{1} won and {2} lost."
                ).format(MIN_CLASS_EXAMPLES, won, lost),
                "won": won,
                "lost": lost,
            }

        # Featurise closed and open together so both end up with identical
        # columns; splitting first would give the open frame a different set of
        # one-hot categories and the model would refuse to score it.
        open_leads = df[df["label"].isna()].copy()
        features = self._featurise(pd.concat([closed, open_leads], ignore_index=True))
        x_closed = features.iloc[: len(closed)]
        x_open = features.iloc[len(closed) :]
        y = closed["label"].astype(int)

        x_train, x_test, y_train, y_test = train_test_split(
            x_closed, y, test_size=0.25, random_state=42, stratify=y
        )
        model = RandomForestClassifier(
            n_estimators=200, max_depth=8, random_state=42, class_weight="balanced"
        )
        model.fit(x_train, y_train)

        predicted = model.predict(x_test)
        probabilities = model.predict_proba(x_test)[:, 1]
        metrics = {
            "accuracy": round(float(accuracy_score(y_test, predicted)) * 100, 1),
            "precision": round(float(precision_score(y_test, predicted, zero_division=0)) * 100, 1),
            "recall": round(float(recall_score(y_test, predicted, zero_division=0)) * 100, 1),
            "roc_auc": round(float(roc_auc_score(y_test, probabilities)) * 100, 1),
        }

        importance = sorted(
            (
                {"feature": name, "importance": round(float(value), 4)}
                for name, value in zip(features.columns, model.feature_importances_, strict=False)
            ),
            key=lambda row: row["importance"],
            reverse=True,
        )[:15]

        scored = []
        if not open_leads.empty:
            open_probabilities = model.predict_proba(x_open)[:, 1]
            open_leads = open_leads.assign(win_probability=open_probabilities)
            for row in open_leads.sort_values("win_probability", ascending=False).head(50).to_dict("records"):
                probability = round(float(row["win_probability"]) * 100, 1)
                scored.append(
                    {
                        "lead": row["name"],
                        "lead_name": row.get("lead_name") or row.get("company_name") or row["name"],
                        "status": row["status"],
                        "source": row.get("source") or "Unknown",
                        "territory": row.get("territory") or "Unknown",
                        "age_days": int(row.get("age_days") or 0),
                        "win_probability": probability,
                        "band": self._band(probability),
                    }
                )

        result = {
            "status": "success",
            "generated_at": datetime.now().isoformat(),
            "training": {
                "won": won,
                "lost": lost,
                "closed_total": int(len(closed)),
                "open_scored": len(scored),
                "months_back": self.months_back,
            },
            "metrics": metrics,
            "feature_importance": importance,
            "conversion_rate": round(won / len(closed) * 100, 1) if len(closed) else 0,
            "by_source": self._by_source(closed),
            "top_open_leads": scored,
        }

        self.cache_results(self.CACHE_KEY, result)
        self.log_training({"won": won, "lost": lost, **metrics})
        return result

    @staticmethod
    def _band(probability: float) -> str:
        if probability >= 60:
            return "High"
        if probability >= 30:
            return "Medium"
        return "Low"

    @staticmethod
    def _by_source(closed: pd.DataFrame) -> list:
        """Historical win rate per lead source -- the answer marketing asks for."""
        grouped = closed.groupby(closed["source"].fillna("Unknown").replace("", "Unknown"))
        rows = []
        for source, frame in grouped:
            total = int(len(frame))
            won = int((frame["label"] == 1).sum())
            if total < 10:  # too thin to quote a rate for
                continue
            rows.append(
                {
                    "source": source,
                    "closed": total,
                    "won": won,
                    "win_rate": round(won / total * 100, 1),
                }
            )
        return sorted(rows, key=lambda row: row["win_rate"], reverse=True)

    # -------------------------------------------------------------- predict

    def predict(self, allow_train: bool = False) -> Dict[str, Any]:
        """Cached scores. Training is a worker's job -- see `allow_train`."""
        cached = self.get_cached_results(self.CACHE_KEY)
        if cached:
            return cached
        if not allow_train:
            return self.get_last_good_results(self.CACHE_KEY) or {
                "status": "warming",
                "message": _("Lead conversion model has not been trained yet."),
            }
        return self.train()
