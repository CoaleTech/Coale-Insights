# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Unsupervised anomaly detection over the general ledger.

78,104 GL entries is the largest table on this site and the only one where an
unsupervised method is clearly the right shape: there are no labels for "this
posting was a mistake", but mistakes are rare and look unlike their neighbours,
which is exactly what an isolation forest finds.

Deliberately framed as *review candidates*, never as "fraud". An isolation
forest ranks how unusual a row is; whether unusual is wrong is a human call, and
a legitimate year-end adjustment is unusual by design. The output is a queue to
look at, ordered by strangeness.
"""

from datetime import datetime
from typing import Any, Dict

import pandas as pd
import frappe
from frappe import _

from insights.ml.base import BaseMLModel

# An isolation forest needs enough rows for "unusual" to mean anything.
MIN_ENTRIES = 500

# Share of rows the model is told to treat as outliers. 1% of a year's ledger is
# a review queue someone can actually work through; 5% is a list nobody opens.
CONTAMINATION = 0.01


class GLAnomalyDetection(BaseMLModel):
    """Rank general-ledger entries by how unlike the rest of the ledger they are."""

    CACHE_KEY = "gl_anomaly"

    def __init__(self, months_back: int = 12):
        super().__init__()
        self.model_name = "GLAnomalyDetection"
        self.months_back = months_back

    def _get_entries(self) -> pd.DataFrame:
        return self.get_training_data(
            """
            SELECT
                gle.name,
                gle.posting_date,
                gle.account,
                gle.voucher_type,
                gle.voucher_no,
                COALESCE(gle.party_type, '') AS party_type,
                COALESCE(gle.debit, 0)  AS debit,
                COALESCE(gle.credit, 0) AS credit,
                COALESCE(gle.is_opening, 'No') AS is_opening
            FROM `tabGL Entry` gle
            WHERE gle.is_cancelled = 0
              AND gle.posting_date >= DATE_SUB(CURDATE(), INTERVAL %(months)s MONTH)
              AND gle.posting_date <= CURDATE()
            """,
            {"months": int(self.months_back)},
        )

    @staticmethod
    def _featurise(df: pd.DataFrame) -> pd.DataFrame:
        """Amount, calendar position, and how common the account/voucher type is.

        Categoricals are frequency-encoded rather than one-hot: a chart of
        accounts runs to hundreds of entries, and one-hot would produce a matrix
        wider than it is tall. Frequency also encodes the thing that matters --
        a posting to an account used twice all year is interesting; the account's
        identity is not.
        """
        import numpy as np

        amount = (df["debit"].astype(float) - df["credit"].astype(float))
        posting = pd.to_datetime(df["posting_date"])

        features = pd.DataFrame(
            {
                # Ledger amounts span several orders of magnitude; the log keeps
                # a large-but-ordinary invoice from swamping the scale.
                "log_amount": np.log1p(amount.abs()),
                "is_credit": (amount < 0).astype(float),
                "day_of_week": posting.dt.dayofweek.astype(float),
                "day_of_month": posting.dt.day.astype(float),
                "is_month_end": (posting.dt.is_month_end).astype(float),
                "is_weekend": (posting.dt.dayofweek >= 5).astype(float),
                "is_opening": (df["is_opening"] == "Yes").astype(float),
                "has_party": (df["party_type"] != "").astype(float),
                "account_frequency": df.groupby("account")["account"].transform("count").astype(float),
                "voucher_frequency": df.groupby("voucher_type")["voucher_type"].transform("count").astype(float),
            }
        )
        return features.fillna(0)

    def train(self) -> Dict[str, Any]:
        try:
            from sklearn.ensemble import IsolationForest
            from sklearn.preprocessing import StandardScaler
        except ImportError:
            return {"status": "error", "message": _("scikit-learn is not installed on this bench.")}

        df = self._get_entries()
        if len(df) < MIN_ENTRIES:
            return {
                "status": "insufficient_data",
                "message": _(
                    "Needs at least {0} ledger entries in the window to rank anomalies; found {1}."
                ).format(MIN_ENTRIES, len(df)),
                "entries": int(len(df)),
            }

        features = self._featurise(df)
        scaled = StandardScaler().fit_transform(features)

        forest = IsolationForest(
            n_estimators=200,
            contamination=CONTAMINATION,
            random_state=42,
            n_jobs=1,  # threads are pinned app-wide; see insights/__init__.py
        )
        labels = forest.fit_predict(scaled)
        # score_samples: lower is more anomalous. Flip it so bigger = stranger,
        # which is the direction a reader expects from a column called "score".
        strangeness = -forest.score_samples(scaled)

        df = df.assign(anomaly=labels == -1, score=strangeness)
        flagged = df[df["anomaly"]].sort_values("score", ascending=False)

        entries = [
            {
                "gl_entry": row["name"],
                "posting_date": str(row["posting_date"]),
                "account": row["account"],
                "voucher_type": row["voucher_type"],
                "voucher_no": row["voucher_no"],
                "debit": float(row["debit"]),
                "credit": float(row["credit"]),
                "score": round(float(row["score"]), 4),
            }
            for row in flagged.head(50).to_dict("records")
        ]

        by_voucher_type: Dict[str, int] = {}
        for row in flagged.to_dict("records"):
            key = row["voucher_type"] or "Unknown"
            by_voucher_type[key] = by_voucher_type.get(key, 0) + 1

        company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
            "Global Defaults", "default_company"
        )
        result = {
            "status": "success",
            "generated_at": datetime.now().isoformat(),
            # GL debit/credit are in company currency; the page has to say which.
            "base_currency": (
                frappe.db.get_value("Company", company, "default_currency")
                or frappe.db.get_single_value("System Settings", "default_currency")
                or "USD"
            ),
            "scanned": int(len(df)),
            "flagged": int(len(flagged)),
            "months_back": self.months_back,
            "contamination": CONTAMINATION,
            "by_voucher_type": [
                {"voucher_type": key, "count": value}
                for key, value in sorted(by_voucher_type.items(), key=lambda kv: kv[1], reverse=True)
            ],
            "entries": entries,
        }

        self.cache_results(self.CACHE_KEY, result)
        self.log_training({"scanned": len(df), "flagged": len(flagged)})
        return result

    def predict(self, allow_train: bool = False) -> Dict[str, Any]:
        """Cached ranking. Scanning the ledger is a worker's job."""
        cached = self.get_cached_results(self.CACHE_KEY)
        if cached:
            return cached
        if not allow_train:
            return self.get_last_good_results(self.CACHE_KEY) or {
                "status": "warming",
                "message": _("Ledger anomaly scan has not run yet."),
            }
        return self.train()
