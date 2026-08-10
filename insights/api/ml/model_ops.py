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

import json
import os
from typing import Any, Dict, List

import frappe
from frappe import _

from insights.api.response import error, success

# Every model the app trains, with the precondition that decides whether it is
# allowed to run at all. This is the health page's data source; it exists
# because something reads it, not as scaffolding.
#
#   key       cache key the model writes via BaseMLModel.cache_results
#   trainer   dotted path a worker calls; also what the Retrain button queues
#   gate      human-readable precondition, checked in the model itself
MODELS: List[Dict[str, str]] = [
    {
        "key": "sales_forecast",
        "label": "Sales Forecast",
        "kind": "Time series",
        "trainer": "insights.ml.scheduler.train_sales_forecast",
        "gate": "Prophet needs 730 days of history; below that, Holt-Winters",
    },
    {
        "key": "demand_forecast",
        "label": "Demand Forecast",
        "kind": "Time series",
        "trainer": "insights.ml.scheduler.train_demand_forecast",
        "gate": "Holt-Winters per item; needs 12+ weeks of sales per item",
    },
    {
        "key": "lead_conversion",
        "label": "Lead Conversion",
        "kind": "Classifier",
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
        "kind": "Classifier",
        "trainer": "insights.ml.scheduler.train_payment_prediction",
        "gate": "50+ late and 50+ on-time invoices, else a rule-based score",
    },
    {
        "key": "product_recommendations",
        "label": "Product Recommendations",
        "kind": "Similarity",
        "trainer": "insights.ml.scheduler.train_product_recommendations",
        "gate": "None; cosine similarity over co-purchased items",
    },
    {
        "key": "customer_segmentation",
        "label": "Customer Segmentation",
        "kind": "Clustering",
        "trainer": "insights.ml.scheduler.train_customer_segmentation",
        "gate": "None; RFM scoring",
    },
]


def _snapshot_for(cache_key: str) -> Dict[str, Any]:
    """Last-good payload written to disk by `BaseMLModel.cache_results`."""
    import re

    directory = frappe.get_site_path("private", "files", "insights_ml_snapshots")
    path = os.path.join(directory, re.sub(r"\W+", "_", cache_key) + ".json")
    if not os.path.exists(path):
        return {}
    try:
        # Path is built from a module constant reduced by re.sub(r"\W+", "_"),
        # so no caller input reaches it.
        # nosemgrep: frappe-security-file-traversal
        with open(path, encoding="utf-8") as handle:
            return json.load(handle) or {}
    except Exception:
        return {}


def _describe(spec: Dict[str, str]) -> Dict[str, Any]:
    """One row of the health table: is it trained, when, on what, how well."""
    cached = frappe.cache.get_value(spec["key"])
    snapshot = {} if cached else _snapshot_for(spec["key"])
    envelope = cached or snapshot
    payload = (envelope or {}).get("data") or {}

    row: Dict[str, Any] = {
        "key": spec["key"],
        "label": spec["label"],
        "kind": spec["kind"],
        "trainer": spec["trainer"],
        "gate": spec["gate"],
        "trained_at": (envelope or {}).get("cached_at"),
        "source": "cache" if cached else ("snapshot" if snapshot else None),
        "state": "never_trained",
        "method": None,
        "rows": None,
        "quality": None,
        "detail": None,
    }

    if not payload:
        return row

    status = payload.get("status")
    if status == "insufficient_data":
        row["state"] = "blocked_on_data"
        row["detail"] = payload.get("message")
        return row
    if status == "error":
        row["state"] = "error"
        row["detail"] = payload.get("message")
        return row

    row["state"] = "trained"

    # Each model reports its shape differently; read what it actually emits
    # rather than forcing a common envelope none of them was written to.
    if spec["key"] == "sales_forecast":
        row["method"] = payload.get("method")
        row["rows"] = len(payload.get("forecast") or [])
        metrics = payload.get("metrics") or {}
        # sMAPE, not MAPE: daily sales is zero on non-trading days, and dividing
        # by a zero actual sends MAPE to hundreds of percent however good the
        # forecast is. sMAPE is bounded at 200% and defined at zero.
        if metrics.get("smape") is not None:
            row["quality"] = f"sMAPE {metrics['smape']}% over {metrics.get('horizon_days')}d"
        elif metrics.get("mape") is not None:
            row["quality"] = f"MAPE {metrics['mape']}%"
    elif spec["key"] == "demand_forecast":
        forecasts = payload.get("forecasts") or []
        row["rows"] = len(forecasts)
        methods: Dict[str, int] = {}
        for item in forecasts:
            key = item.get("forecast_method") or "unknown"
            methods[key] = methods.get(key, 0) + 1
        row["method"] = ", ".join(f"{k} {v}" for k, v in sorted(methods.items(), key=lambda kv: -kv[1]))
    elif spec["key"] == "lead_conversion":
        training = payload.get("training") or {}
        metrics = payload.get("metrics") or {}
        row["method"] = "RandomForest"
        row["rows"] = training.get("closed_total")
        if metrics.get("roc_auc") is not None:
            row["quality"] = f"ROC-AUC {metrics['roc_auc']}%"
    elif spec["key"] == "gl_anomaly":
        row["method"] = "IsolationForest"
        row["rows"] = payload.get("scanned")
        row["quality"] = _("{0} flagged").format(payload.get("flagged"))
    elif spec["key"] == "payment_model":
        metrics = payload.get("metrics") or {}
        row["method"] = payload.get("model_type") or "RandomForest"
        if metrics.get("accuracy") is not None:
            row["quality"] = f"Accuracy {metrics['accuracy']}%"
    else:
        row["rows"] = payload.get("total") or payload.get("count")

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
    """Queue one model's training run. Never fits in the request."""
    try:
        frappe.has_permission("Insights Settings", "write", throw=True)
        spec = next((item for item in MODELS if item["key"] == model), None)
        if not spec:
            frappe.throw(_("Unknown model: {0}").format(model))

        from insights.api.ml.utils import enqueue_training

        return enqueue_training(
            spec["trainer"],
            job_id=f"insights_train_{spec['key']}",
            label=spec["label"],
        )
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def lead_conversion(refresh: bool = False) -> Dict[str, Any]:
    """Win probability for open leads, and historical win rate by source."""
    try:
        frappe.has_permission("Lead", "read", throw=True)
        if refresh:
            from insights.api.ml.utils import enqueue_training

            return enqueue_training(
                "insights.ml.scheduler.train_lead_conversion",
                job_id="insights_train_lead_conversion",
                label=_("Lead conversion"),
            )

        from insights.ml.lead_conversion import LeadConversion

        return success(LeadConversion().predict())
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))


@frappe.whitelist()
def gl_anomalies(refresh: bool = False) -> Dict[str, Any]:
    """Ledger entries ranked by how unlike the rest of the ledger they are."""
    try:
        frappe.has_permission("GL Entry", "read", throw=True)
        if refresh:
            from insights.api.ml.utils import enqueue_training

            return enqueue_training(
                "insights.ml.scheduler.train_gl_anomaly",
                job_id="insights_train_gl_anomaly",
                label=_("Ledger anomaly scan"),
            )

        from insights.ml.gl_anomaly import GLAnomalyDetection

        return success(GLAnomalyDetection().predict())
    except frappe.PermissionError:
        raise
    except Exception as e:
        return error(str(e))
