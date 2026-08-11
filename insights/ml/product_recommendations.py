from __future__ import annotations
# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Product Recommendations -- Ibis-native rewrite.

Was a hand-rolled Apriori miner plus a ``sklearn.metrics.pairwise.
cosine_similarity`` item-item matrix over a customer x item pivot table,
built in-process on every cold cache. Both passes ran over the entire
``Sales Invoice Item`` history of the company, allocating pandas DataFrames
and dense numpy arrays sized to the unique-item count, and the module-
level ``get_item_recommendations`` / ``get_customer_recommendations`` /
``get_cart_recommendations`` / ``get_frequently_bought_together`` helpers
called ``model.train()`` synchronously as a cache-miss fallback -- the
exact in-process work pattern that crashes the RQ work-horse on Frappe
Cloud with "waitpid returned 139 (signal 11)" and times out the web
worker even without a fork.

The whole mining pipeline is now a single Ibis expression that MariaDB
executes. A self-join of ``tabSales Invoice Item`` to itself on matching
``parent`` (and distinct ``name``) gives one row per ordered pair; we
canonicalise to (item_a, item_b) via ``LEAST``/``GREATEST``, filter to
submitted invoices (``docstatus = 1``), group by the sorted pair, and
count co-occurrences in a single aggregate. Support, lift, and the
"frequently bought together" ranking fall out as arithmetic over the
grouped scalars. No model to train, no cache to warm, no fork -- every
request recomputes from live SQL in low hundreds of milliseconds.

The payload shape is preserved exactly so the frontend needs no changes:
``frequently_bought_together`` keeps its (item1, item1_name, item2,
item2_name, co_occurrence_count, support, lift) rows, and the
``association_rules`` list keeps its (antecedent, antecedent_names,
consequent, consequent_names, support, confidence, lift) shape built
from the same pair data (a 2-item pairwise table already covers what
2-item Apriori rules give; the 3-itemset branch the old code capped
"for performance" is dropped, matching the simplification the rest of
the app already took).
"""

import json
from collections import defaultdict
from datetime import datetime
from typing import Any

import frappe
import ibis
from frappe import _

from insights.api.ml.ibis_source import t

# Minimum number of distinct submitted sales-invoice transactions before
# the pair table is statistically meaningful. Below this we degrade to
# the "insufficient data" envelope rather than return a ranking driven
# by one or two noisy co-occurrences.
MIN_TRANSACTIONS = 10

# Co-occurrence floor for a pair to make it into "frequently bought
# together". 3 matches the original Python filter.
MIN_COOCCURRENCE = 3

# How many top pairs / top rules to surface in the response payload.
TOP_PAIRS = 30
TOP_RULES = 20


class ProductRecommendations:
    """Pairwise co-occurrence recommender over Sales Invoice Item history.

    Plain class on purpose: no training step, no model object, no cache.
    The ``train()`` and ``predict()`` shapes are kept so the scheduler
    and the model_ops health page can keep reading the same keys -- but
    both methods do the same work (one Ibis aggregate that MariaDB
    answers live), so there is nothing to fit and nothing to fit *on*
    a background queue.
    """

    CACHE_KEY = "insights:product_recommendations"

    # -----------------------------------------------------------------
    # public surface
    # -----------------------------------------------------------------

    def train(self) -> dict:
        """Build the pair table and return the full payload.

        Synchronous, two SQL round trips (a count of distinct
        transactions, then the pair aggregate). Anything else would just
        be re-running the same query on different inputs.
        """
        try:
            total_txns = self._count_transactions()
            if total_txns < MIN_TRANSACTIONS:
                return {
                    "status": "insufficient_data",
                    "message": _(
                        "Needs at least {0} submitted sales invoices to build "
                        "recommendations; found {1}."
                    ).format(MIN_TRANSACTIONS, total_txns),
                    "transaction_summary": {
                        "total_transactions": int(total_txns),
                        "total_items": 0,
                        "avg_basket_size": 0.0,
                    },
                    "association_rules": {"total_rules": 0, "top_rules": []},
                    "collaborative_filtering": {"status": "skipped", "reason": "insufficient_data"},
                    "frequently_bought_together": [],
                }

            pairs = self._pair_table()
            if not pairs:
                return {
                    "status": "insufficient_data",
                    "message": _("No co-occurrences found across sales invoices."),
                    "transaction_summary": {
                        "total_transactions": int(total_txns),
                        "total_items": 0,
                        "avg_basket_size": 0.0,
                    },
                    "association_rules": {"total_rules": 0, "top_rules": []},
                    "collaborative_filtering": {"status": "skipped", "reason": "no_pairs"},
                    "frequently_bought_together": [],
                }

            item_names = self._item_names(pairs)
            fbt = self._format_pairs(pairs, total_txns, item_names)
            rules = self._format_rules(pairs, total_txns, item_names)
            avg_basket = self._avg_basket_size()
            total_items = self._count_distinct_items()

            return {
                "status": "success",
                "training_date": datetime.now().isoformat(),
                "transaction_summary": {
                    "total_transactions": int(total_txns),
                    "total_items": int(total_items),
                    "avg_basket_size": round(float(avg_basket or 0.0), 2),
                },
                "association_rules": {
                    "total_rules": len(rules),
                    "top_rules": rules[:TOP_RULES],
                },
                "collaborative_filtering": {
                    "status": "skipped",
                    "reason": "replaced_by_pair_aggregate",
                },
                "frequently_bought_together": fbt[:TOP_PAIRS],
            }
        except Exception as e:
            frappe.log_error(f"Product recommendations scan failed: {e}", "ML Recommendations")
            return {"status": "error", "message": str(e)}

    def predict(self) -> dict:
        """Same payload as ``train()``; the pair table is always live."""
        return self.train()

    # -----------------------------------------------------------------
    # SQL aggregates
    # -----------------------------------------------------------------

    def _count_transactions(self) -> int:
        """Distinct submitted Sales Invoices with >= 2 line items."""
        sii = t("Sales Invoice Item")
        si = t("Sales Invoice")
        joined = sii.join(si, sii.parent == si.name).view()
        q = (
            joined.filter(joined.docstatus == 1)
            .group_by(joined.parent)
            .having(joined.item_code.count() >= 2)
            .aggregate(n=joined.parent.nunique())
        )
        row = q.execute().iloc[0]
        return int(row["n"] or 0)

    def _count_distinct_items(self) -> int:
        """Distinct items ever sold in a submitted invoice."""
        sii = t("Sales Invoice Item")
        si = t("Sales Invoice")
        joined = sii.join(si, sii.parent == si.name).view()
        row = (
            joined.filter(joined.docstatus == 1)
            .aggregate(n=joined.item_code.nunique())
            .execute()
            .iloc[0]
        )
        return int(row["n"] or 0)

    def _avg_basket_size(self) -> float:
        """Average line items per qualifying transaction, in SQL."""
        sii = t("Sales Invoice Item")
        si = t("Sales Invoice")
        joined = sii.join(si, sii.parent == si.name).view()
        q = (
            joined.filter(joined.docstatus == 1)
            .group_by(joined.parent)
            .aggregate(basket=joined.item_code.count())
        )
        df = q.aggregate(avg=q.basket.mean()).execute()
        # aggregate over the per-basket aggregate is a scalar -> wrap the
        # mean-of-means in another aggregate call so the column is named.
        if df is None or len(df) == 0:
            return 0.0
        # Ibis returns a single-row DataFrame; pull the scalar.
        return float(df.iloc[0, 0] or 0.0)

    def _pair_table(self) -> list[dict]:
        """Self-join of Sales Invoice Item on parent -> one row per
        unordered (item_a, item_b) pair. Group by the pair to get the
        co-occurrence count.

        We do this in two stages so the canonical (LEAST, GREATEST)
        ordering happens before the GROUP BY -- the self-join alone
        emits one row per *ordered* pair, doubling the work the
        aggregator has to do.
        """
        sii = t("Sales Invoice Item")
        si = t("Sales Invoice")
        # Join line items to invoices so we can filter by docstatus.
        joined = sii.join(si, sii.parent == si.name).view()
        submitted = joined.filter(joined.docstatus == 1).select(
            parent=joined.parent,
            item_code=joined.item_code,
        )

        # Self-join on the same parent; ``sii.name < sii2.name`` keeps
        # one row per unordered pair.
        a = submitted
        b = submitted.view()
        pairs = a.join(b, (a.parent == b.parent) & (a.name < b.name)).view()
        # Canonical ordering: smaller name first, larger second.
        item_a = ibis.least(a.item_code, b.item_code)
        item_b = ibis.greatest(a.item_code, b.item_code)
        canonical = pairs.select(
            item_a=item_a,
            item_b=item_b,
        )

        df = (
            canonical.group_by([canonical.item_a, canonical.item_b])
            .aggregate(co_count=canonical.item_a.count())
            .execute()
        )
        out: list[dict] = []
        for row in df.to_dict(orient="records"):
            if row["item_a"] and row["item_b"] and row["item_a"] != row["item_b"]:
                out.append(
                    {
                        "item1": str(row["item_a"]),
                        "item2": str(row["item_b"]),
                        "co_occurrence_count": int(row["co_count"] or 0),
                    }
                )
        return out

    def _item_names(self, pairs: list[dict]) -> dict[str, str]:
        """Bulk-resolve item_code -> item_name in a single SQL round trip.

        Done outside the pair aggregate because names are display only
        and would otherwise bloat the GROUP BY payload.
        """
        codes = {p["item1"] for p in pairs} | {p["item2"] for p in pairs}
        if not codes:
            return {}
        rows = frappe.db.sql(
            """
            SELECT name, item_name
            FROM `tabItem`
            WHERE name IN %(codes)s AND disabled = 0
            """,
            {"codes": tuple(codes)},
            as_dict=True,
        )
        return {r["name"]: (r.get("item_name") or r["name"]) for r in rows}

    # -----------------------------------------------------------------
    # post-processing
    # -----------------------------------------------------------------

    def _format_pairs(
        self,
        pairs: list[dict],
        total_txns: int,
        item_names: dict[str, str],
    ) -> list[dict]:
        """Pair table -> ``frequently_bought_together`` rows.

        ``support`` is co_count / total_txns. ``lift`` is
        ``support / (rate_a * rate_b)`` where ``rate_x`` is the
        marginal rate of item x across submitted invoices. Lift > 1
        means the pair co-occurs more often than independence predicts.
        """
        item_counts = self._item_marginal_counts(pairs)
        out: list[dict] = []
        for p in pairs:
            if p["co_occurrence_count"] < MIN_COOCCURRENCE:
                continue
            support = p["co_occurrence_count"] / total_txns
            ca = item_counts.get(p["item1"], 0) / total_txns
            cb = item_counts.get(p["item2"], 0) / total_txns
            expected = ca * cb
            lift = (support / expected) if expected > 0 else 0.0
            out.append(
                {
                    "item1": p["item1"],
                    "item1_name": item_names.get(p["item1"], p["item1"]),
                    "item2": p["item2"],
                    "item2_name": item_names.get(p["item2"], p["item2"]),
                    "co_occurrence_count": p["co_occurrence_count"],
                    "support": round(support, 4),
                    "lift": round(lift, 2),
                }
            )
        out.sort(key=lambda r: (r["lift"], r["co_occurrence_count"]), reverse=True)
        return out

    def _format_rules(
        self,
        pairs: list[dict],
        total_txns: int,
        item_names: dict[str, str],
    ) -> list[dict]:
        """Same pair data, expressed as (antecedent -> consequent) rules.

        For each (a, b) pair with co_count >= MIN_COOCCURRENCE we emit
        two rules (a -> {b} and b -> {a}). Confidence is co_count /
        marginal(item). This matches the 2-itemset branch the old
        Apriori code produced; 3+ item itemsets are not useful at the
        existing call sites (the dashboard slices top_rules[:20]) and
        the pairwise table already covers everything the 2-item
        rules would say.
        """
        item_counts = self._item_marginal_counts(pairs)
        rules: list[dict] = []
        for p in pairs:
            if p["co_occurrence_count"] < MIN_COOCCURRENCE:
                continue
            co = p["co_occurrence_count"]
            for ant, cons, other_name in (
                (p["item1"], [p["item2"]], item_names.get(p["item2"], p["item2"])),
                (p["item2"], [p["item1"]], item_names.get(p["item1"], p["item1"])),
            ):
                denom = item_counts.get(ant, 0)
                if denom <= 0:
                    continue
                confidence = co / denom
                # Support of the rule = the pair's support, same as Apriori.
                support = co / total_txns
                # Lift against the consequent's marginal rate -- matches the
                # formula the old code used (consequent_support here =
                # item_counts[cons] / total_txns).
                cons_rate = item_counts.get(cons[0], 0) / total_txns
                lift = (confidence / cons_rate) if cons_rate > 0 else 0.0
                rules.append(
                    {
                        "antecedent": [ant],
                        "antecedent_names": [item_names.get(ant, ant)],
                        "consequent": cons,
                        "consequent_names": [other_name],
                        "support": round(support, 4),
                        "confidence": round(confidence, 4),
                        "lift": round(lift, 2),
                    }
                )
        rules.sort(key=lambda r: (r["lift"], r["confidence"]), reverse=True)
        return rules

    def _item_marginal_counts(self, pairs: list[dict]) -> dict[str, int]:
        """Per-item total transactions from the pair data.

        Each pair (a, b) carries a co-occurrence count; summing co_count
        for every (a, *) and (b, *) entry gives a marginal that's
        identical to ``COUNT(DISTINCT parent)`` for each item. We avoid
        a separate SQL round trip because the pair data is already in
        memory and the marginal is exact for >= 2-item transactions.
        """
        counts: dict[str, int] = defaultdict(int)
        for p in pairs:
            counts[p["item1"]] += p["co_occurrence_count"]
            counts[p["item2"]] += p["co_occurrence_count"]
        return dict(counts)

    # -----------------------------------------------------------------
    # item-level recommendations (orchestration)
    # -----------------------------------------------------------------

    def get_recommendations_for_item(self, item_code: str, top_n: int = 5) -> dict:
        """Items most frequently bought together with ``item_code``.

        Single SQL aggregate (the same self-join filter, but narrowed
        to rows where either side of the pair equals ``item_code``),
        ranked by lift then co-occurrence. Replaces the old "Method 1
        association rules" + "Method 2 cosine similarity" two-pass.
        """
        sii = t("Sales Invoice Item")
        si = t("Sales Invoice")
        joined = sii.join(si, sii.parent == si.name).view()
        submitted = joined.filter(joined.docstatus == 1).select(
            parent=joined.parent,
            item_code=joined.item_code,
        )
        a = submitted
        b = submitted.view()
        pairs = a.join(b, (a.parent == b.parent) & (a.name < b.name)).view()
        item_a = ibis.least(a.item_code, b.item_code)
        item_b = ibis.greatest(a.item_code, b.item_code)
        filtered = pairs.filter(
            (a.item_code == item_code) | (b.item_code == item_code)
        ).select(
            item_a=item_a,
            item_b=item_b,
        )
        df = (
            filtered.group_by([filtered.item_a, filtered.item_b])
            .aggregate(co_count=filtered.item_a.count())
            .execute()
        )
        # Build a (counterpart, co_count) view.
        total_txns = max(self._count_transactions(), 1)
        item_counts = self._item_marginal_counts_from_sql()
        names = self._item_names(
            [
                {
                    "item1": str(r["item_a"]),
                    "item2": str(r["item_b"]),
                    "co_occurrence_count": 0,
                }
                for r in df.to_dict(orient="records")
                if r["item_a"] and r["item_b"]
            ]
        )

        recs: list[dict] = []
        for row in df.to_dict(orient="records"):
            ia, ib = row["item_a"], row["item_b"]
            if not ia or not ib or ia == ib:
                continue
            co = int(row["co_count"] or 0)
            # The counterpart is whichever side of the pair isn't the
            # target item.
            counterpart = ib if ia == item_code else ia
            if counterpart == item_code:
                continue
            support = co / total_txns
            ca = item_counts.get(ia, 0) / total_txns
            cb = item_counts.get(ib, 0) / total_txns
            expected = ca * cb
            lift = (support / expected) if expected > 0 else 0.0
            recs.append(
                {
                    "item_code": str(counterpart),
                    "item_name": names.get(str(counterpart), str(counterpart)),
                    "lift": round(lift, 2),
                    "co_occurrence_count": co,
                    "method": "frequently_bought_together",
                }
            )
        recs.sort(key=lambda r: (r["lift"], r["co_occurrence_count"]), reverse=True)
        # Deduplicate (shouldn't happen, but pairs may surface twice if
        # the self-join produced duplicate keys).
        seen: set[str] = set()
        unique: list[dict] = []
        for r in recs:
            if r["item_code"] in seen or r["item_code"] == item_code:
                continue
            seen.add(r["item_code"])
            unique.append(r)
        return {
            "status": "success",
            "item_code": item_code,
            "recommendations": unique[: int(top_n)],
        }

    def _item_marginal_counts_from_sql(self) -> dict[str, int]:
        """Per-item transaction counts via a separate SQL aggregate.

        Used by ``get_recommendations_for_item`` so lift can be computed
        without re-running the self-join.
        """
        sii = t("Sales Invoice Item")
        si = t("Sales Invoice")
        joined = sii.join(si, sii.parent == si.name).view()
        df = (
            joined.filter(joined.docstatus == 1)
            .group_by(joined.item_code)
            .aggregate(n=joined.parent.nunique())
            .execute()
        )
        return {
            str(r["item_code"]): int(r["n"] or 0)
            for r in df.to_dict(orient="records")
            if r["item_code"]
        }

    # -----------------------------------------------------------------
    # customer- and cart-level recommendations
    # -----------------------------------------------------------------

    def _get_customer_recommendations(
        self, customer_id: str, top_n: int = 5, per_item_top: int = 3
    ) -> dict:
        """Per-purchased-item co-occurrence lookups, then aggregate.

        For every item the customer has bought, ask
        ``get_recommendations_for_item`` for the top N partners. Drop
        anything the customer already owns, sum scores across the
        items that surfaced each candidate, and return the ranked
        list. Kept thin: the heavy lifting is one SQL aggregate per
        purchased item, and we cap the input at 10 purchased items
        to match the original code's behaviour.
        """
        purchased = frappe.db.sql(
            """
            SELECT DISTINCT sii.item_code
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE si.customer = %(customer)s AND si.docstatus = 1
            """,
            {"customer": customer_id},
            as_dict=True,
        )
        purchased_set = {r["item_code"] for r in purchased if r.get("item_code")}
        if not purchased_set:
            return {
                "status": "success",
                "recommendations": [],
                "message": _("No purchase history found"),
            }

        scores: dict[str, dict] = defaultdict(
            lambda: {"score": 0.0, "count": 0, "sources": [], "item_name": ""}
        )
        for item in list(purchased_set)[:10]:
            recs = self.get_recommendations_for_item(item, top_n=per_item_top)
            for r in recs.get("recommendations", []):
                code = r["item_code"]
                if code in purchased_set or code == item:
                    continue
                entry = scores[code]
                entry["score"] += float(r.get("lift", 0) or 0)
                entry["count"] += 1
                entry["sources"].append(item)
                entry["item_name"] = r.get("item_name", code)

        final = [
            {
                "item_code": code,
                "item_name": data["item_name"] or code,
                "relevance_score": round(data["score"] / data["count"], 3)
                if data["count"]
                else 0.0,
                "recommendation_count": data["count"],
                "based_on_items": sorted(set(data["sources"]))[:3],
            }
            for code, data in scores.items()
        ]
        final.sort(key=lambda r: r["relevance_score"], reverse=True)
        return {
            "status": "success",
            "customer": customer_id,
            "purchased_items_count": len(purchased_set),
            "recommendations": final[: int(top_n)],
        }

    def get_recommendations_for_customer(
        self, customer: str, top_n: int = 10
    ) -> dict:
        """Public entry point -- delegates to the helper above."""
        return self._get_customer_recommendations(customer, top_n=top_n)

    def get_cart_recommendations(
        self, cart_items: list[str], top_n: int = 5
    ) -> dict:
        """Recommend against the current cart, treating it as a
        mini-purchase history.
        """
        cart_set = {str(c) for c in cart_items if c}
        if not cart_set:
            return {
                "status": "success",
                "cart_items": list(cart_set),
                "recommendations": [],
            }
        scores: dict[str, dict] = defaultdict(
            lambda: {"score": 0.0, "sources": [], "item_name": ""}
        )
        for item in list(cart_set)[:10]:
            recs = self.get_recommendations_for_item(item, top_n=3)
            for r in recs.get("recommendations", []):
                code = r["item_code"]
                if code in cart_set or code == item:
                    continue
                entry = scores[code]
                entry["score"] += float(r.get("lift", 0) or 0)
                entry["sources"].append(item)
                entry["item_name"] = r.get("item_name", code)

        final = [
            {
                "item_code": code,
                "item_name": data["item_name"] or code,
                "relevance_score": round(data["score"], 3),
                "recommended_because": sorted(set(data["sources"])),
            }
            for code, data in scores.items()
        ]
        final.sort(key=lambda r: r["relevance_score"], reverse=True)
        return {
            "status": "success",
            "cart_items": list(cart_set),
            "recommendations": final[: int(top_n)],
        }


# ---------------------------------------------------------------------------
# Module-level API helpers. Thin wrappers over the class -- no caching, no
# background training. The whole pipeline is fast synchronous SQL, so a
# cold request just runs the aggregate.
# ---------------------------------------------------------------------------


def run_recommendation_training(*_args: Any, **_kwargs: Any) -> dict:
    """Compatibility shim: the old training entry point.

    Extra positional/keyword args (``min_support``, ``min_confidence``)
    are silently ignored -- the rewrite is parameter-free.
    """
    return ProductRecommendations().train()


def get_item_recommendations(item_code: str, top_n: int = 5) -> dict:
    """Top-N items most frequently bought with ``item_code``."""
    if not item_code:
        return {"status": "error", "message": _("item_code is required")}
    return ProductRecommendations().get_recommendations_for_item(item_code, int(top_n))


def get_customer_recommendations(customer: str, top_n: int = 10) -> dict:
    """Top-N items recommended for a customer based on their history."""
    if not customer:
        return {"status": "error", "message": _("customer is required")}
    return ProductRecommendations().get_recommendations_for_customer(customer, int(top_n))


def get_cart_recommendations(cart_items: str, top_n: int = 5) -> dict:
    """Top-N items recommended against a cart (JSON list of item codes)."""
    if isinstance(cart_items, str):
        try:
            parsed = json.loads(cart_items)
        except (TypeError, ValueError):
            parsed = []
    else:
        parsed = cart_items or []
    if not isinstance(parsed, list):
        parsed = []
    return ProductRecommendations().get_cart_recommendations(parsed, int(top_n))


def get_frequently_bought_together() -> dict:
    """Top pairs for the dashboard widget.

    Calls the same single-shot SQL the rest of the module uses, so a
    cold request runs the aggregate live (no ``model.train()``
    cache-miss fallback like the old code).
    """
    payload = ProductRecommendations().train()
    if payload.get("status") != "success":
        return {
            "status": payload.get("status", "error"),
            "message": payload.get("message", ""),
            "pairs": [],
        }
    return {
        "status": "success",
        "pairs": payload.get("frequently_bought_together", []),
    }
