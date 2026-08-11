# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
ML Scheduler Tasks
Automated training of ML models on scheduled intervals
"""

import frappe
from datetime import datetime
import functools


def _single_threaded(fn):
    """Run a forked ML job with BLAS/OpenMP pinned to one thread.

    Three layers of fork-safety, innermost first:

    1. **Env vars (forced, not setdefault).** ``OPENBLAS_NUM_THREADS=1`` etc.
       are set *before* the decorator imports numpy/pandas, so OpenBLAS on
       Linux never creates a multi-thread pool.  ``insights/__init__.py``
       already does this, but only when ``insights`` is imported — if a
       third-party app or a pre-import pulled numpy in first, those vars
       arrived too late.  Setting them here covers that gap because the
       decorator runs *after* the fork, *before* any model code.

    2. **Pre-import numpy/pandas.** Importing them here (after the env vars
       are pinned) means the BLAS pool is created single-threaded in the
       child.  If the job function then imports them again, Python reuses
       the cached module — no second initialization, no new pool.

    3. **threadpool_limits(1).** Belt-and-suspenders: if a library created
       a pool despite the env vars, this clamps it to one thread in-process.
       Degrades to a plain call when threadpoolctl is absent.

    On Linux (Frappe Cloud), OpenBLAS creates a pthread pool at ``import
    numpy`` time.  That pool cannot survive ``rq``'s ``os.fork()`` — the
    work-horse dies as ``waitpid returned 139 (signal 11)`` with no Python
    traceback.  On macOS, numpy uses Accelerate which does not create a
    pool, so the fork is always safe and the crash never reproduces
    locally.  Layer 1 is the fix that actually matters on Linux; 2 and 3
    are defense-in-depth.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        import os

        # Layer 1 — force env vars before any numpy import in this child.
        for _var in (
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS",
            "NUMEXPR_NUM_THREADS",
        ):
            os.environ[_var] = "1"

        # Layer 2 — import numpy/pandas here so BLAS initialises single-
        # threaded in the child, before the job function touches them.
        try:
            import numpy  # noqa: F401 — side effect: init BLAS with 1 thread
            import pandas  # noqa: F401
        except Exception:
            pass

        # Layer 3 — clamp any pool that slipped through.
        try:
            from threadpoolctl import threadpool_limits
        except Exception:
            return fn(*args, **kwargs)
        with threadpool_limits(limits=1):
            return fn(*args, **kwargs)

    return wrapper

def _crash_marker_path(job_name: str) -> str:
    """On-disk marker file that proves a job started but did not finish.

    A SIGSEGV (signal 11) kills the work-horse before Python's ``except``
    runs, so ``frappe.log_error`` never fires and the failure is invisible —
    the job simply vanishes from the RQ dashboard as "failed" with no
    traceback.  Writing a marker *before* the job starts and removing it on
    *success* leaves evidence: if the marker exists on the next run, the
    previous run crashed.  The next run logs that fact to Error Log so the
    operator can see it in Desk.
    """
    import os
    directory = os.path.join(frappe.get_site_path(), "private", "files", "ml_crash_markers")
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, f"{job_name}.crash")


def _mark_crash_start(job_name: str):
    """Record that a job is starting — to be cleared on success."""
    import json
    import os
    from datetime import datetime
    path = _crash_marker_path(job_name)
    try:
        # If a marker from a previous run exists, the previous run crashed.
        if os.path.exists(path):
            with open(path) as f:
                prev = json.load(f)
            frappe.log_error(
                f"ML job '{job_name}' appears to have crashed on its previous run "
                f"(started {prev.get('started_at', 'unknown')}). "
                f"This is likely a signal-11 (SIGSEGV) fork crash — the work-horse "
                f"was killed before Python could log the error. "
                f"Check worker.error.log on the server for 'waitpid returned 139'.",
                "ML Scheduler — crash detected",
            )
    except Exception:
        pass
    try:
        with open(path, "w") as f:
            json.dump({"job": job_name, "started_at": datetime.now().isoformat()}, f)
    except Exception:
        pass


def _clear_crash_marker(job_name: str):
    """Remove the crash marker — the job finished successfully."""
    import os
    try:
        os.unlink(_crash_marker_path(job_name))
    except Exception:
        pass


@_single_threaded
def train_customer_segmentation():
    """Daily: Train customer segmentation model"""
    try:
        from insights.ml.customer_segmentation import CustomerSegmentation
        
        frappe.logger().info("Starting scheduled customer segmentation training")
        
        model = CustomerSegmentation()
        result = model.train()
        
        if result.get('status') == 'success':
            frappe.logger().info(
                f"Customer segmentation completed: {result.get('total_customers', 0)} customers segmented"
            )
        else:
            frappe.logger().warning(
                f"Customer segmentation failed: {result.get('message', 'Unknown error')}"
            )
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Scheduled customer segmentation failed: {str(e)}", "ML Scheduler")
        return {"status": "error", "message": str(e)}


@_single_threaded
def train_sales_forecast():
    """Daily: Train sales forecasting model"""
    try:
        from insights.ml.sales_forecasting import SalesForecasting
        
        frappe.logger().info("Starting scheduled sales forecast training")
        
        model = SalesForecasting(method="auto")
        result = model.train(periods=30)
        
        if result.get('status') == 'success':
            frappe.logger().info(
                f"Sales forecast completed: {result.get('data_range', {}).get('days', 0)} days of data analyzed"
            )
        else:
            frappe.logger().warning(
                f"Sales forecast failed: {result.get('message', 'Unknown error')}"
            )
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Scheduled sales forecast failed: {str(e)}", "ML Scheduler")
        return {"status": "error", "message": str(e)}


@_single_threaded
def train_payment_prediction():
    """Daily: Train payment prediction model"""
    try:
        from insights.ml.payment_prediction import PaymentPrediction
        
        frappe.logger().info("Starting scheduled payment prediction training")
        
        model = PaymentPrediction()
        result = model.train()
        
        if result.get('status') == 'success':
            frappe.logger().info(
                f"Payment prediction completed: {result.get('training_samples', 0)} samples used"
            )
            
            # Also run predictions for outstanding invoices
            predictions = model.predict()
            high_risk = predictions.get('summary', {}).get('high_risk_count', 0)
            if high_risk > 0:
                frappe.logger().warning(
                    f"Payment prediction: {high_risk} high-risk invoices detected"
                )
        else:
            frappe.logger().warning(
                f"Payment prediction failed: {result.get('message', 'Unknown error')}"
            )
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Scheduled payment prediction failed: {str(e)}", "ML Scheduler")
        return {"status": "error", "message": str(e)}


@_single_threaded
def train_abc_xyz_classification():
    """Weekly: Train ABC/XYZ inventory classification"""
    try:
        from insights.ml.abc_xyz_classification import ABCXYZClassification
        
        frappe.logger().info("Starting scheduled ABC/XYZ classification training")
        
        model = ABCXYZClassification()
        result = model.train()
        
        if result.get('status') == 'success':
            frappe.logger().info(
                f"ABC/XYZ classification completed: {result.get('total_items', 0)} items classified"
            )
        else:
            frappe.logger().warning(
                f"ABC/XYZ classification failed: {result.get('message', 'Unknown error')}"
            )
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Scheduled ABC/XYZ classification failed: {str(e)}", "ML Scheduler")
        return {"status": "error", "message": str(e)}


@_single_threaded
def train_demand_forecast():
    """Weekly: Train demand forecasting model"""
    try:
        from insights.ml.demand_forecasting import DemandForecasting
        
        frappe.logger().info("Starting scheduled demand forecast training")
        
        model = DemandForecasting()
        result = model.train(periods=4, top_items=100)
        
        if result.get('status') == 'success':
            reorder_count = result.get('summary', {}).get('reorder_now_count', 0)
            frappe.logger().info(
                f"Demand forecast completed: {result.get('summary', {}).get('total_items_analyzed', 0)} items analyzed"
            )
            
            if reorder_count > 0:
                frappe.logger().warning(
                    f"Demand forecast: {reorder_count} items need reordering"
                )
                # Optionally send alert
                _send_reorder_alert(result)
        else:
            frappe.logger().warning(
                f"Demand forecast failed: {result.get('message', 'Unknown error')}"
            )
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Scheduled demand forecast failed: {str(e)}", "ML Scheduler")
        return {"status": "error", "message": str(e)}


@_single_threaded
def train_product_recommendations():
    """Weekly: Train product recommendation model"""
    try:
        from insights.ml.product_recommendations import ProductRecommendations
        
        frappe.logger().info("Starting scheduled product recommendations training")
        
        model = ProductRecommendations()
        result = model.train()
        
        if result.get('status') == 'success':
            rules_count = result.get('association_rules', {}).get('total_rules', 0)
            frappe.logger().info(
                f"Product recommendations completed: {rules_count} association rules generated"
            )
        else:
            frappe.logger().warning(
                f"Product recommendations failed: {result.get('message', 'Unknown error')}"
            )
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Scheduled product recommendations failed: {str(e)}", "ML Scheduler")
        return {"status": "error", "message": str(e)}


def _send_reorder_alert(forecast_result: dict):
    """Send reorder alert notification"""
    try:
        reorder_items = [
            f for f in forecast_result.get('forecasts', []) 
            if f['stock_status'] == 'Reorder Now'
        ]
        
        if not reorder_items:
            return
        
        # Get users with Stock Manager role
        stock_managers = frappe.get_all(
            "Has Role",
            filters={"role": "Stock Manager", "parenttype": "User"},
            pluck="parent"
        )
        
        if not stock_managers:
            return
        
        # Create summary
        items_list = "\n".join([
            f"- {item['item_name']} ({item['item_code']}): Current Stock {item['current_stock']}, Reorder Point {item['inventory_params']['reorder_point']}"
            for item in reorder_items[:10]
        ])
        
        message = f"""
        <h3>🚨 Inventory Reorder Alert</h3>
        <p>{len(reorder_items)} items need to be reordered:</p>
        <pre>{items_list}</pre>
        {"<p><em>Showing top 10 items. Check Insights ML Dashboard for full list.</em></p>" if len(reorder_items) > 10 else ""}
        """
        
        for user in stock_managers[:5]:  # Limit to 5 users
            try:
                frappe.sendmail(
                    recipients=[user],
                    subject=f"Inventory Reorder Alert: {len(reorder_items)} items need attention",
                    message=message
                )
            except:
                pass
                
    except Exception as e:
        frappe.log_error(f"Failed to send reorder alert: {str(e)}", "ML Scheduler")


@_single_threaded
def run_daily_intelligence():
    """Single daily job: trains all daily models and warms executive cache.

    Replaces individual scheduler entries for better coordination.
    """
    results = {}

    daily_tasks = [
        ("customer_segmentation", train_customer_segmentation),
        ("sales_forecast", train_sales_forecast),
        ("payment_prediction", train_payment_prediction),
        ("customer_intelligence", train_customer_intelligence),
        ("sales_intelligence", train_sales_intelligence),
        ("procurement_intelligence", train_procurement_intelligence),
    ]

    for name, fn in daily_tasks:
        try:
            results[name] = fn()
        except Exception as e:
            frappe.log_error(f"Daily intelligence {name} failed: {str(e)}", "ML Scheduler")
            results[name] = {"status": "error", "message": str(e)}

    # Warm the cache the dashboards now read.
    #
    # The endpoints compute inline and read the *model-level* cache
    # (`BaseMLModel.get_cached_results`, 24h), so warming means training the
    # models — which `daily_tasks` above already did — plus the executive
    # summary, whose own cache is separate and only 1 hour.
    #
    # The async result cache (`insights_async:result:*`) is no longer read by any
    # endpoint, so filling it would repeat the mistake this warm-up was written to
    # fix: populating a key nothing serves.
    try:
        from insights.ml.executive_intelligence import ExecutiveIntelligence

        executive = ExecutiveIntelligence()
        for period in ("MTD", "QTD", "YTD", "TTM"):
            executive.get_executive_summary(period)
        frappe.logger().info("Executive intelligence cache warmed for all periods")
    except Exception as e:
        frappe.log_error(f"Executive cache warmup failed: {str(e)}", "ML Scheduler")

    frappe.logger().info(f"Daily intelligence completed: {len(results)} models trained")
    return results


@_single_threaded
def warm_dashboard_caches():
    """Train every model the dashboards read, in this process.

    The `bench --site <site> execute insights.ml.scheduler.warm_dashboard_caches`
    entry point, kept because the migrate hook and operators both call it.

    The dashboards compute inline and read the model-level cache, so warming is
    exactly "train the models" — there is no separate payload cache to fill any
    more. Each target is independent: one failure must not deny the rest.
    """
    warmed = []
    for name, fn in (
        ("customer_intelligence", train_customer_intelligence),
        ("sales_intelligence", train_sales_intelligence),
        ("procurement_intelligence", train_procurement_intelligence),
    ):
        try:
            fn()
            warmed.append(name)
        except Exception as e:
            frappe.log_error(f"Dashboard cache warm failed for {name}: {str(e)}", "ML Scheduler")

    try:
        from insights.ml.executive_intelligence import ExecutiveIntelligence

        executive = ExecutiveIntelligence()
        for period in ("MTD", "QTD", "YTD", "TTM"):
            executive.get_executive_summary(period)
        warmed.append("executive_summary")
    except Exception as e:
        frappe.log_error(f"Executive cache warm failed: {str(e)}", "ML Scheduler")

    frappe.logger().info(f"Dashboard caches warmed: {', '.join(warmed) or 'none'}")
    return warmed


@_single_threaded
def run_all_ml_models():
    """Run all ML models - can be triggered manually"""
    results = {}

    results['customer_segmentation'] = train_customer_segmentation()
    results['sales_forecast'] = train_sales_forecast()
    results['payment_prediction'] = train_payment_prediction()
    results['abc_xyz_classification'] = train_abc_xyz_classification()
    results['demand_forecast'] = train_demand_forecast()
    results['product_recommendations'] = train_product_recommendations()
    results['customer_intelligence'] = train_customer_intelligence()
    results['procurement_intelligence'] = train_procurement_intelligence()

    frappe.logger().info("All ML models training completed")

    return results


@_single_threaded
def train_customer_intelligence():
    """Daily: Train comprehensive customer intelligence model"""
    _mark_crash_start("train_customer_intelligence")
    try:
        from insights.ml.customer_intelligence import CustomerIntelligence

        frappe.logger().info("Starting scheduled customer intelligence training")

        model = CustomerIntelligence()

        # Train inline. This function already runs on the `long` worker (the
        # dashboard's serve_or_warm and the daily scheduler enqueue it), so the
        # old >5000-customer re-enqueue only added a second, un-deduplicated
        # heavy job -- repeated board opens stacked concurrent customer trains
        # and OOM'd the work-horse, killing the queue.
        result = model.train(update_customers=True)

        if result.get('status') == 'success':
            summary = result.get('summary', {})
            at_risk = len(result.get('at_risk_customers', []))
            frappe.logger().info(
                f"Customer intelligence completed: {summary.get('total_customers', 0)} customers analyzed, "
                f"{at_risk} at risk"
            )

            # Send alert if high-risk customers detected
            if at_risk > 0:
                _send_churn_risk_alert(result)
        else:
            frappe.logger().warning(
                f"Customer intelligence failed: {result.get('message', 'Unknown error')}"
            )

        _clear_crash_marker("train_customer_intelligence")
        return result

    except Exception as e:
        frappe.log_error(f"Scheduled customer intelligence failed: {str(e)}", "ML Scheduler")
        return {"status": "error", "message": str(e)}


def _send_churn_risk_alert(intelligence_result: dict):
    """Send churn risk alert notification"""
    try:
        at_risk = intelligence_result.get('at_risk_customers', [])
        
        if not at_risk:
            return
        
        # Get users with Sales Manager role
        managers = frappe.get_all(
            "Has Role",
            filters={"role": ("in", ["Sales Manager", "Sales Master Manager"]), "parenttype": "User"},
            pluck="parent"
        )
        
        if not managers:
            return
        
        # Create summary
        critical = [c for c in at_risk if c.get('churn_risk') == 'Critical']
        high = [c for c in at_risk if c.get('churn_risk') == 'High']
        
        items_list = "\n".join([
            f"- {c['customer_name']}: {c.get('churn_risk')} risk, "
            f"CLV: {c.get('historical_clv', 0):,.0f}, Last order: {int(c.get('recency_days', 0))} days ago"
            for c in (critical + high)[:10]
        ])
        
        message = f"""
        <h3>🚨 Customer Churn Risk Alert</h3>
        <p><strong>{len(critical)} Critical</strong> and <strong>{len(high)} High</strong> risk customers detected:</p>
        <pre>{items_list}</pre>
        {"<p><em>Showing top 10. Check Customer Intelligence Dashboard for full list.</em></p>" if len(at_risk) > 10 else ""}
        <p><a href="/insights/customer-intelligence">View Customer Intelligence Dashboard →</a></p>
        """
        
        for user in list(set(managers))[:5]:  # Limit to 5 unique users
            try:
                frappe.sendmail(
                    recipients=[user],
                    subject=f"Customer Churn Alert: {len(critical)} Critical, {len(high)} High Risk",
                    message=message
                )
            except:
                pass
                
    except Exception as e:
        frappe.log_error(f"Failed to send churn risk alert: {str(e)}", "ML Scheduler")


@_single_threaded
def train_breakeven_engine():
    """Weekly: Train break-even engine and warm caches."""
    try:
        from insights.ml.breakeven_engine import BreakevenEngine

        frappe.logger().info("Starting scheduled break-even engine training")

        engine = BreakevenEngine()
        result = engine.train()

        if result.get('status') == 'success':
            data = result.get('data', {})
            frappe.logger().info(
                f"Break-even engine completed: "
                f"coverage={data.get('coverage', 0):.2f}, "
                f"items={len(data.get('item_breakeven', {}).get('items', []))}, "
                f"ROCE={data.get('roce', {}).get('roce', 0):.2f}%"
            )
        else:
            frappe.logger().warning(
                f"Break-even engine failed: {result.get('message', 'Unknown error')}"
            )

        return result

    except Exception as e:
        frappe.log_error(f"Scheduled break-even engine failed: {str(e)}", "ML Scheduler")
        return {"status": "error", "message": str(e)}


@_single_threaded
def train_sales_intelligence():
    """Daily: Train comprehensive sales intelligence model"""
    _mark_crash_start("train_sales_intelligence")
    try:
        from insights.ml.sales_intelligence import SalesIntelligence

        frappe.logger().info("Starting scheduled sales intelligence training")

        model = SalesIntelligence()
        result = model.train(refresh_forecasts=False)

        if result.get('status') == 'success':
            summary = result.get('summary', {})
            frappe.logger().info(
                f"Sales intelligence completed: {summary.get('total_transactions', 0)} transactions analyzed, "
                f"Revenue: {summary.get('total_revenue', 0):,.0f}, "
                f"MoM: {summary.get('mom_growth', 0):+.1f}%, "
                f"Margin: {summary.get('overall_margin', 0):.1f}%"
            )
        else:
            frappe.logger().warning(
                f"Sales intelligence failed: {result.get('message', 'Unknown error')}"
            )

        _clear_crash_marker("train_sales_intelligence")
        return result

    except Exception as e:
        frappe.log_error(f"Scheduled sales intelligence failed: {str(e)}", "ML Scheduler")
        return {"status": "error", "message": str(e)}



@_single_threaded
def train_procurement_intelligence():
    """Daily: Train procurement intelligence model.

    Added 2026-08-04: this function did not exist. procurement_intelligence
    was never scheduled anywhere (grep of hooks.py scheduler_events and this
    file confirmed zero references), so ProcurementIntelligence.train() --
    ~17 sequential frappe.db.sql() queries executed synchronously -- ran
    cold on every single production request that missed cache, with no
    warming ever happening. This is the confirmed root cause of the
    insights.api.ml.procurement_intelligence 502s: a request that cold-runs
    17 sequential queries synchronously in a web worker is a timeout
    waiting to happen. See plan-eng-review production-diagnosis notes.
    """
    try:
        from insights.ml.procurement_intelligence import ProcurementIntelligence

        frappe.logger().info("Starting scheduled procurement intelligence training")

        model = ProcurementIntelligence()
        result = model.train()

        if result.get("status") == "success" or "spend_overview" in result:
            frappe.logger().info("Procurement intelligence training completed")
        else:
            frappe.logger().warning(
                f"Procurement intelligence failed: {result.get('message', 'Unknown error')}"
            )

        return result

    except Exception as e:
        frappe.log_error(f"Scheduled procurement intelligence failed: {str(e)}", "ML Scheduler")
        return {"status": "error", "message": str(e)}


@_single_threaded
def train_india_tax_intelligence():
    """Daily: Train India tax intelligence and warm caches."""
    try:
        from insights.ml.india_tax_intelligence import IndiaTaxIntelligence

        frappe.logger().info("Starting scheduled India tax intelligence training")

        model = IndiaTaxIntelligence()
        result = model.train()

        if result.get("status") == "success":
            frappe.logger().info(
                f"India tax intelligence completed: "
                f"gst_summary={len(result.get('gst_summary', []))} months, "
                f"compliance_score={result.get('compliance_score', 0):.1f}"
            )
        else:
            frappe.logger().warning(
                f"India tax intelligence failed: {result.get('message', 'Unknown error')}"
            )

        return result

    except Exception as e:
        frappe.log_error(f"Scheduled India tax intelligence failed: {str(e)}", "ML Scheduler")
        return {"status": "error", "message": str(e)}


@_single_threaded
def train_lead_conversion():
    """Daily: fit the lead → win classifier on closed leads and score open ones."""
    try:
        from insights.ml.lead_conversion import LeadConversion

        frappe.logger().info("Starting scheduled lead conversion training")
        result = LeadConversion().train()
        frappe.logger().info(f"Lead conversion training: {result.get('status')}")
        return result
    except Exception as e:
        frappe.log_error(f"Scheduled lead conversion training failed: {str(e)}", "ML Scheduler")
        return {"status": "error", "message": str(e)}


@_single_threaded
def train_gl_anomaly():
    """Daily: rank ledger entries by how unlike the rest of the ledger they are."""
    try:
        from insights.ml.gl_anomaly import GLAnomalyDetection

        frappe.logger().info("Starting scheduled ledger anomaly scan")
        result = GLAnomalyDetection().train()
        frappe.logger().info(f"Ledger anomaly scan: {result.get('status')}")
        return result
    except Exception as e:
        frappe.log_error(f"Scheduled ledger anomaly scan failed: {str(e)}", "ML Scheduler")
        return {"status": "error", "message": str(e)}
