# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""The Machine Learning dashboard's API: model health, and the two models that
have no home on a domain dashboard.

Model health is the page worth centralising. Duplicating the domain charts here
would make a forecast less useful by moving it away from the revenue it
forecasts; what genuinely has nowhere to live is the answer to "is this model
trained, on what, by which method, and how well". Every model in the app
silently degrades when its data or its library is missing -- the forecasters
fell back to a moving average for months without anyone seeing it -- so a page
that states each model's actual method and precondition is the fix for the class
of problem, not decoration.
"""

from typing import Any, Dict, List

import frappe
from frappe import _
from frappe.utils import now

from insights.api.response import error, success
from insights.api.serialization import sanitize_for_json

# Every model the app trains, with the precondition that decides whether it is
# allowed to run at all. This is the health page's data source; it exists
# because something reads it, not as scaffolding.
#
#   trainer   dotted path `retrain`/`_describe` import and call, with no args,
#             to get this model's current payload -- there is no cache or
#             disk snapshot behind any of these (see `insights.ml.base`)
#   gate      human-readable precondition, checked in the model itself
MODELS: List[Dict[str, str]] = [
    {
        "key": "sales_forecast",
        "label": "Sales Forecast",
        "kind": "Time series",
        "trainer": "insights.ml.scheduler.train_sales_forecast",
        "gate": "None; closed-form linear trend over daily sales, 0 forecast rows below 2 days of history",
    },
    {
        "key": "demand_forecast",
        "label": "Demand Forecast",
        "kind": "Time series",
        "trainer": "insights.ml.scheduler.train_demand_forecast",
        "gate": "Needs item-level sales history in the last 24 months",
    },
    {
        "key": "lead_conversion",
        "label": "Lead Conversion",
        "kind": "Weighted score",
        "trainer": "insights.ml.scheduler.train_lead_conversion",
        "gate": "50+ won and 50+ lost leads",
    },
    {
        "key": "gl_anomaly",
        "label": "Ledger Anomalies",
        "kind": "Anomaly detection",
        "trainer": "insights.ml.scheduler.train_gl_anomaly",
        "gate": "500+ ledger entries in the window",
    },
    {
        "key": "payment_model",
        "label": "Payment Default",
        "kind": "Weighted score",
        "trainer": "insights.ml.scheduler.train_payment_prediction",
        "gate": "None; weighted rule score over invoice and customer signals",
    },
    {
        "key": "product_recommendations",
        "label": "Product Recommendations",
        "kind": "Co-occurrence",
        "trainer": "insights.ml.scheduler.train_product_recommendations",
        "gate": "10+ submitted sales invoices with 2+ line items",
    },
    {
        "key": "customer_segmentation",
        "label": "Customer Segmentation",
        "kind": "Segmentation",
        "trainer": "insights.ml.scheduler.train_customer_segmentation",
        "gate": "None; RFM quintile scoring",
    },
]


def _resolve_trainer(dotted_path: str):
    """Import and return the callable a `MODELS` trainer path names."""
    import importlib

    module_path, _sep, attr = dotted_path.rpartition(".")
    return getattr(importlib.import_module(module_path), attr)


def _describe(spec: Dict[str, str]) -> Dict[str, Any]:
    """One row of the health table: is it trained, when, on what, how well.

    There is no cache or disk snapshot to read anymore -- every domain model
    computes fresh per call (see `insights.ml.base`) -- so this runs the exact
    trainer the Retrain button queues and reports what it returns right now.
    "Trained" means this call just succeeded against this site's real data,
    not that someone clicked Retrain at some point in the past.
    """
    row: Dict[str, Any] = {
        "key": spec["key"],
        "label": spec["label"],
        "kind": spec["kind"],
        "trainer": spec["trainer"],
        "gate": spec["gate"],
        "trained_at": None,
        "state": "never_trained",
        "method": None,
        "rows": None,
        "quality": None,
        "detail": None,
    }

    try:
        payload = _resolve_trainer(spec["trainer"])() or {}
    except Exception as e:
        row["state"] = "error"
        row["detail"] = str(e)
        return row

    if not payload:
        return row

    status = payload.get("status")
    if status == "insufficient_data":
        row["state"] = "blocked_on_data"
        row["detail"] = payload.get("message") or _("Not enough data yet.")
        return row
    if status == "error":
        row["state"] = "error"
        row["detail"] = payload.get("message") or _("Unknown error.")
        return row

    row["state"] = "trained"
    row["trained_at"] = now()

    # Each model reports its shape differently; read what it actually emits
    # rather than forcing a common envelope none of them was written to.
    if spec["key"] == "sales_forecast":
        row["method"] = payload.get("method")
        row["rows"] = len(payload.get("forecast") or [])
        metrics = payload.get("metrics") or {}
        if metrics.get("rmse") is not None:
            row["quality"] = f"RMSE {metrics['rmse']} over {metrics.get('n_points')} days"
    elif spec["key"] == "demand_forecast":
        row["method"] = "Weighted 3-month average + trend"
        row["rows"] = payload.get("total_items_analyzed")
        row["quality"] = _("{0} reorder now, {1} monitor").format(
            payload.get("reorder_now_count", 0), payload.get("monitor_count", 0)
        )
    elif spec["key"] == "lead_conversion":
        training = payload.get("training") or {}
        metrics = payload.get("metrics") or {}
        row["method"] = "Weighted rule score"
        row["rows"] = training.get("closed_total")
        row["quality"] = metrics.get("note")
    elif spec["key"] == "gl_anomaly":
        row["method"] = "Z-score vs ledger distribution"
        row["rows"] = payload.get("scanned")
        row["quality"] = _("{0} flagged").format(payload.get("flagged"))
    elif spec["key"] == "payment_model":
        metrics = payload.get("metrics") or {}
        row["method"] = payload.get("model") or "weighted_rule_score"
        row["rows"] = payload.get("training_samples")
        row["quality"] = metrics.get("note")
    elif spec["key"] == "product_recommendations":
        summary = payload.get("transaction_summary") or {}
        rules = payload.get("association_rules") or {}
        row["method"] = "Co-occurrence pairs"
        row["rows"] = summary.get("total_transactions")
        row["quality"] = _("{0} rules, {1} pairs").format(
            rules.get("total_rules", 0), len(payload.get("frequently_bought_together") or [])
        )
    elif spec["key"] == "customer_segmentation":
        row["method"] = "RFM quintiles"
        row["rows"] = payload.get("total_customers")
        row["quality"] = _("{0} segments").format(len(payload.get("segments") or []))

    return row


# The tables every model reads, and which module depends on each. Row counts
# against this list are what "profile the data volumes on production" was
# asking for: whether the four modules that compute over empty tables here are
# empty on the site you are actually looking at. Answering it in the page beats
# answering it once, by hand, over a bench shell.
SOURCE_TABLES: List[Dict[str, str]] = [
    {"doctype": "Sales Invoice", "used_by": "Sales, revenue, forecasts"},
    {"doctype": "Sales Invoice Item", "used_by": "Demand forecast, product mix"},
    {"doctype": "Purchase Invoice", "used_by": "Procurement spend"},
    {"doctype": "Purchase Order", "used_by": "Procurement cycle times"},
    {"doctype": "Lead", "used_by": "Lead conversion"},
    {"doctype": "GL Entry", "used_by": "Ledger anomalies, financials"},
    {"doctype": "Work Order", "used_by": "Manufacturing intelligence"},
    {"doctype": "Employee", "used_by": "HR intelligence"},
    {"doctype": "Salary Slip", "used_by": "HR payroll analytics"},
    {"doctype": "Budget", "used_by": "Budget variance"},
    {"doctype": "Delivery Note", "used_by": "ESG intelligence"},
]


def _data_volumes() -> List[Dict[str, Any]]:
    """Row count per source table, so an empty module is visibly empty.

    A missing DocType is reported as such rather than as zero: an app that is
    not installed and a table with no rows look identical on a dashboard, and
    they call for opposite responses.
    """
    volumes = []
    for spec in SOURCE_TABLES:
        doctype = spec["doctype"]
        if not frappe.db.exists("DocType", doctype):
            rows, state = None, "absent"
        else:
            try:
                rows = frappe.db.count(doctype)
                state = "populated" if rows else "empty"
            except Exception:
                rows, state = None, "absent"
        volumes.append(
            {"doctype": doctype, "used_by": spec["used_by"], "rows": rows, "state": state}
        )
    return volumes


@frappe.whitelist()
def model_health() -> Dict[str, Any]:
    """State of every model the app trains, and the two things that decide it.

    A model is only as good as the library that fits it and the table it reads,
    so both ship in the same payload: `libraries` reports what this interpreter
    can import and at what version, `data` reports the row count behind each
    module. Between them they answer, from inside whichever site is asking,
    the two questions that otherwise need a bench shell -- did the ML packages
    land on this host, and does this site actually hold the data its dashboards
    claim to analyse.
    """
    try:
        frappe.has_permission("Insights Settings", "read", throw=True)
        from insights.ml.base import ensure_dependencies

        rows = [_describe(spec) for spec in MODELS]
        libraries = ensure_dependencies()
        return success(
            {
                "models": rows,
                "trained": sum(1 for row in rows if row["state"] == "trained"),
                "total": len(rows),
                "libraries": libraries,
                "libraries_missing": sorted(k for k, v in libraries.items() if v is None),
                "data": _data_volumes(),
            }
        )
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def retrain(model: str) -> Dict[str, Any]:
    """Retrain one model synchronously and return its fresh result.

    There is no cache to fill; this recomputes the model the same way the
    domain dashboard that owns it would, on demand.
    """
    try:
        frappe.has_permission("Insights Settings", "write", throw=True)
        spec = next((item for item in MODELS if item["key"] == model), None)
        if not spec:
            frappe.throw(_("Unknown model: {0}").format(model))
        assert spec is not None  # frappe.throw always raises; narrows the type for the checker

        from insights.api.ml.utils import run

        return sanitize_for_json(run(_resolve_trainer(spec["trainer"]), spec["label"]))
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def lead_conversion(refresh: bool = False) -> Dict[str, Any]:
    """Win probability for open leads, and historical win rate by source.

    ``refresh`` is kept for backward compatibility with older frontend
    callers; the score is always computed live, so it has no effect.
    """
    try:
        frappe.has_permission("Lead", "read", throw=True)
        from insights.ml.lead_conversion import LeadConversion

        return success(LeadConversion().predict())
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def gl_anomalies(refresh: bool = False) -> Dict[str, Any]:
    """Ledger entries ranked by how unlike the rest of the ledger they are.

    ``refresh`` is kept for backward compatibility with older frontend
    callers; the ranking is always computed live, so it has no effect.
    """
    try:
        frappe.has_permission("GL Entry", "read", throw=True)
        from insights.ml.gl_anomaly import GLAnomalyDetection

        return success(GLAnomalyDetection().predict())
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))
