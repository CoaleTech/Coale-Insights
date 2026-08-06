# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt


import frappe


def after_migrate():
    try:
        create_admin_team()
    except Exception:
        frappe.log_error(title="Error creating Admin Team")

    try:
        warm_intelligence_caches()
    except Exception:
        frappe.log_error(title="Error scheduling intelligence cache warm-up")


def warm_intelligence_caches():
    """Compute the intelligence caches on a worker after install or migrate.

    The dashboards read a 24h cache and fall back to computing inline. On an
    established site the daily scheduler keeps that cache warm, but a freshly
    installed site has nothing until that job first runs, so the first visitor
    pays the full cost inside a web worker. Executive summary alone measured
    23s locally; past a gateway timeout that reaches the browser as a 502.

    Enqueue the same daily job so the work lands on a background worker, where
    long runtimes are expected, instead of on the request path.
    """
    if frappe.flags.in_test:
        return

    frappe.enqueue(
        "insights.ml.scheduler.run_daily_intelligence",
        queue="long",
        timeout=3600,
        job_id="insights_warm_intelligence",
        deduplicate=True,
    )


def create_admin_team():
    if not frappe.db.exists("Insights Team", "Admin"):
        frappe.get_doc(
            {
                "doctype": "Insights Team",
                "team_name": "Admin",
                "team_members": [{"user": "Administrator"}],
            }
        ).insert(ignore_permissions=True)
