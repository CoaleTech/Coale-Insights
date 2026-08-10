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
    """Enqueue a job, replacing one wedged by a dead work-horse.

    `deduplicate=True` returns silently when a job with this id is QUEUED or
    STARTED, and a work-horse killed by a signal or a deploy leaves its job
    STARTED in redis forever — so without clearing the corpse every later
    migration would enqueue nothing and still report success.
    """
    try:
        from frappe.utils.background_jobs import get_job

        job = get_job(job_id)
        if job and job.get_status(refresh=True) in ("started", "queued"):
            job.delete()
    except Exception:
        pass

    frappe.enqueue(method, queue=queue, timeout=timeout, job_id=job_id, deduplicate=True)


def enqueue_dashboard_warm():
    """Train the dashboard models after install or migrate.

    The direct equivalent of
    `bench --site <site> execute insights.ml.scheduler.warm_dashboard_caches`,
    run on a worker so a migration never blocks on it.

    The dashboards now compute inline and read the model-level cache, so this
    trains the three models they depend on plus the executive summary. It is
    queued ahead of the full daily pass so those surfaces become usable first.
    """
    if frappe.flags.in_test:
        return

    _enqueue_once(
        "insights.ml.scheduler.warm_dashboard_caches",
        job_id="insights_warm_dashboard_caches",
        queue="long",
        timeout=1500,
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
