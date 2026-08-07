# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt


import frappe


def after_migrate():
    try:
        create_admin_team()
    except Exception:
        frappe.log_error(title="Error creating Admin Team")

    # Order matters. The dashboard warm is the short, targeted job that makes
    # Overview / Revenue & Customers / Procurement usable; the full training pass
    # behind it takes minutes. Queue the fast one first so a migration does not
    # leave the dashboards cold while six models retrain.
    try:
        enqueue_dashboard_warm()
    except Exception:
        frappe.log_error(title="Error scheduling dashboard cache warm-up")

    try:
        enqueue_daily_training()
    except Exception:
        frappe.log_error(title="Error scheduling intelligence cache warm-up")


def _enqueue_once(method: str, job_id: str, queue: str, timeout: int):
    """Enqueue a deduplicated job, clearing a dead one first.

    `frappe.enqueue(deduplicate=True)` returns silently when a job with this id
    is QUEUED or STARTED. A work-horse killed by OOM or a deploy leaves its job
    STARTED in redis forever, so without reaping, every later migration would
    enqueue nothing and still report success.
    """
    from insights.api.ml import async_compute

    async_compute.reap_dead_job(job_id, queue_name=queue)
    frappe.enqueue(method, queue=queue, timeout=timeout, job_id=job_id, deduplicate=True)


def enqueue_dashboard_warm():
    """Populate the dashboard payload caches after install or migrate.

    The direct equivalent of
    `bench --site <site> execute insights.ml.scheduler.warm_dashboard_caches`,
    run on a worker so a migration never blocks on it. Fills the
    `insights_async:result:*` keys the dashboards actually read, training any
    model whose own cache is cold on the way through.
    """
    if frappe.flags.in_test:
        return

    from insights.api.ml import async_compute

    _enqueue_once(
        "insights.ml.scheduler.warm_dashboard_caches",
        job_id="insights_warm_dashboard_caches",
        queue=async_compute.resolve_queue(),
        timeout=async_compute.resolve_timeout(),
    )


def enqueue_daily_training():
    """Train every daily model after install or migrate.

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

    _enqueue_once(
        "insights.ml.scheduler.run_daily_intelligence",
        job_id="insights_warm_intelligence",
        queue="long",
        timeout=3600,
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
