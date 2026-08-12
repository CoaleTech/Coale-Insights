from __future__ import annotations
# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
GL Anomaly Detection -- Ibis-native rewrite.

Was a scikit-learn ``IsolationForest`` ranking ledger entries by how unlike
the rest of the ledger they were. The forest ran in-process on every cold
cache, was trained on amount/calendar/account-frequency features, and used
``n_jobs=1`` because OpenBLAS threads are pinned app-wide. The model
itself is gone; the entire detection is a single ``SELECT ... ORDER BY
|zscore| DESC`` that MariaDB executes and returns to Python.

For each GL Entry we compute a *z-score* against the global mean / standard
deviation of the (debit - credit) net amount in the same date window. We
also compute a *per-account* z-score (entries that look ordinary globally
but are extreme within their own account) and pick the larger of the two.
Top N by absolute z-score become the anomaly list.

This is the same statistical intuition an IsolationForest encodes for a
univariate amount, but explicit, audit-able, and free of sklearn. The
feature engineering beyond amount is not needed: per-account z-scoring
already captures "this entry is large for that account".
"""

from datetime import datetime

import frappe
import ibis
from frappe import _

from insights.api.ml.ibis_source import company_filter, default_company, t

# An anomaly ranking needs enough rows for "unusual" to mean anything.
# Below this floor the z-scores are noise, so we degrade gracefully.
MIN_ENTRIES = 500

# How many top entries to return in the ranked list. 50 is what the old
# IsolationForest payload was sized to.
TOP_N = 50


class GLAnomalyDetection:
    """Rank GL entries by z-score against the ledger's amount distribution.

    Plain class on purpose: no training step, no cache, no model. The
    ``train()`` and ``predict()`` shapes are kept so the scheduler and
    the model_ops health page can keep reading the same keys.
    """

    CACHE_KEY = "gl_anomaly"

    def __init__(self, months_back: int = 12) -> None:
        self.months_back = months_back
        self.company = default_company()

    # -----------------------------------------------------------------
    # public surface
    # -----------------------------------------------------------------

    def train(self) -> dict:
        """Compute the anomaly ranking. Synchronous, one SQL round trip
        (plus a per-account aggregate)."""
        try:
            n = self._count_entries()
            if n < MIN_ENTRIES:
                return {
                    "status": "insufficient_data",
                    "message": _(
                        "Needs at least {0} ledger entries in the window to rank anomalies; found {1}."
                    ).format(MIN_ENTRIES, n),
                    "entries": int(n),
                }

            entries = self._rank_entries()
            return {
                "status": "success",
                "generated_at": datetime.now().isoformat(),
                "base_currency": self._base_currency(),
                "scanned": int(n),
                "flagged": len(entries),
                "months_back": self.months_back,
                "by_voucher_type": self._by_voucher_type(entries),
                "entries": entries,
            }
        except Exception as e:
            frappe.log_error(f"GL Anomaly scan failed: {e}", "ML Anomaly")
            return {"status": "error", "message": str(e)}

    def predict(self, allow_train: bool = False) -> dict:
        """Same payload as ``train()``; the rank is always live.

        ``allow_train`` is kept for backward compatibility with the
        scheduler but the behaviour is now identical with or without it:
        there is no training pass, every call computes the ranking
        fresh.
        """
        return self.train()

    # -----------------------------------------------------------------
    # queries
    # -----------------------------------------------------------------

    def _count_entries(self) -> int:
        gle = t("GL Entry")
        q = gle.filter(gle.is_cancelled == 0)
        # The MariaDB date window is computed in SQL so the count is right
        # at the source, not estimated.
        from datetime import datetime, timedelta

        cutoff = (datetime.now() - timedelta(days=int(self.months_back) * 30)).date()
        q = q.filter(gle.posting_date >= cutoff, gle.posting_date <= datetime.now().date())
        q = company_filter(q, self.company)
        row = q.aggregate(n=q.count()).execute().iloc[0]
        return int(row["n"] or 0)

    def _rank_entries(self) -> list[dict]:
        """Compute global + per-account mean/stddev, join back to entries,
        rank by the larger of the two |z-scores|.

        One single SQL statement (CTE) executed by MariaDB. Python only
        materialises the top-N rows.
        """
        gle = t("GL Entry")
        q = gle.filter(gle.is_cancelled == 0)
        from datetime import datetime, timedelta

        cutoff = (datetime.now() - timedelta(days=int(self.months_back) * 30)).date()
        q = q.filter(gle.posting_date >= cutoff, q.posting_date <= datetime.now().date())
        q = company_filter(q, self.company)
        # Net amount = debit - credit. MariaDB returns 0 for NULL in arithmetic.
        q = q.mutate(
            net=gle.debit.fill_null(0) - gle.credit.fill_null(0),
            party_type=gle.party_type.fill_null(""),
            is_opening=gle.is_opening.fill_null("No"),
        )

        # Subquery aliases for global stats.
        global_stats = q.aggregate(
            g_mean=q.net.mean(),
            g_std=q.net.std(),
        )
        per_account_stats = q.group_by(q.account).aggregate(
            a_mean=q.net.mean(),
            a_std=q.net.std(),
        )

        joined = q.join(global_stats, how="inner").view()
        joined = joined.join(per_account_stats, joined.account == per_account_stats.account).view()

        # Z-score. ``SafeZ`` guards against zero-variance populations:
        # stddev = 0 -> z = 0 (a constant series has no anomalies).
        def _safe_z(value, mean, std):
            return ibis.ifelse(
                std.isnull() | (std == 0),
                ibis.literal(0.0),
                (value - mean) / std,
            )

        z_global = _safe_z(joined.net, joined.g_mean, joined.g_std)
        z_account = _safe_z(joined.net, joined.a_mean, joined.a_std)
        # Pick the larger-magnitude z; sign is on the "strangeness" side
        # (huge positive or huge negative both interesting).
        max_abs = ibis.greatest(z_global.abs(), z_account.abs())
        joined = joined.mutate(
            z_global=z_global,
            z_account=z_account,
            z_max=ibis.ifelse(z_global.abs() >= z_account.abs(), z_global, z_account),
            z_max_abs=max_abs,
        )
        ranked = (
            joined.select(
                "name",
                "posting_date",
                "account",
                "voucher_type",
                "voucher_no",
                "debit",
                "credit",
                "net",
                "z_global",
                "z_account",
                "z_max",
                "z_max_abs",
            )
            .order_by(ibis.desc("z_max_abs"))
            .limit(TOP_N)
            .execute()
        )

        out = []
        for r in ranked.to_dict(orient="records"):
            out.append(
                {
                    "gl_entry": r["name"],
                    "posting_date": str(r["posting_date"]),
                    "account": r["account"],
                    "voucher_type": r["voucher_type"],
                    "voucher_no": r["voucher_no"],
                    "debit": float(r["debit"] or 0),
                    "credit": float(r["credit"] or 0),
                    "net_amount": float(r["net"] or 0),
                    "z_global": round(float(r["z_global"] or 0), 4),
                    "z_account": round(float(r["z_account"] or 0), 4),
                    "score": round(float(r["z_max"] or 0), 4),
                }
            )
        return out

    # -----------------------------------------------------------------
    # helpers
    # -----------------------------------------------------------------

    def _by_voucher_type(self, entries: list[dict]) -> list[dict]:
        counts: dict = {}
        for r in entries:
            key = r.get("voucher_type") or "Unknown"
            counts[key] = counts.get(key, 0) + 1
        return [
            {"voucher_type": k, "count": v}
            for k, v in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        ]

    def _base_currency(self) -> str:
        company = self.company
        if company:
            cur = frappe.db.get_value("Company", company, "default_currency")
            if cur:
                return cur
        return (
            frappe.db.get_single_value("Global Defaults", "default_currency") or "USD"
        )
