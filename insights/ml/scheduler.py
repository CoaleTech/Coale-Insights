# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
ML Scheduler Tasks
Automated training of ML models on scheduled intervals
"""

import re

import frappe
from datetime import datetime


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

    # Warm the caches the dashboards actually read.
    #
    # This previously called `ExecutiveIntelligence().get_executive_summary(period)`
    # directly, which fills the model-level key `executive_summary:<period>` on a
    # 1-hour TTL. The dashboards read `insights_async:result:executive_summary:YTD`
    # on a 24-hour TTL, written only by `async_compute.run`. The warm-up therefore
    # populated a different key than the page reads, and its own entry expired an
    # hour later regardless. Driving `async_compute.run` fills the served key.
    # Fan out rather than warming inline: a work-horse killed by a signal takes
    # the whole process with it, so warming six payloads in this one job meant a
    # single crashing dashboard denied all of them their cache.
    try:
        enqueue_dashboard_warm_jobs()
    except Exception as e:
        frappe.log_error(f"Dashboard cache warmup failed: {str(e)}", "ML Scheduler")

    frappe.logger().info(f"Daily intelligence completed: {len(results)} models trained")
    return results


# (key, dotted compute path, kwargs) for every payload a dashboard blocks on.
# Keys must match the ones the API layer passes to `async_compute.serve`.
DASHBOARD_CACHE_TARGETS = (
    ("sales_intelligence:12m", "insights.api.ml.sales._compute_sales_intelligence", {"date_filter": "12m"}),
    ("customer_intelligence:12m", "insights.api.ml.customer._compute_customer_intelligence", {"date_filter": "12m"}),
    ("executive_summary:YTD", "insights.api.ml.executive._compute_executive_summary", {"period": "YTD"}),
    ("executive_summary:MTD", "insights.api.ml.executive._compute_executive_summary", {"period": "MTD"}),
    ("executive_summary:QTD", "insights.api.ml.executive._compute_executive_summary", {"period": "QTD"}),
    ("executive_summary:TTM", "insights.api.ml.executive._compute_executive_summary", {"period": "TTM"}),
    ("procurement_intelligence", "insights.api.ml.procurement._compute_procurement_intelligence", {}),
)


def warm_one_dashboard_cache(key: str):
    """Compute and cache exactly one dashboard payload.

    Isolated deliberately. A work-horse killed by a signal (SIGSEGV, OOM) takes
    its whole process down, so batching every dashboard into one job meant a
    single crashing computation denied all six their cache and stacked their
    peak memory into one process. One key per job contains the blast radius and
    makes the failure attributable.
    """
    from insights.api.ml import async_compute

    target = next((t for t in DASHBOARD_CACHE_TARGETS if t[0] == key), None)
    if target is None:
        frappe.log_error(f"Unknown dashboard cache key: {key}", "ML Scheduler")
        return None

    _, method, kwargs = target
    async_compute.invalidate(key)
    async_compute.run(key=key, compute_method=method, compute_kwargs=kwargs, ttl=async_compute.DEFAULT_TTL)
    # `run` fills RESULT but never META, and `async_status` refuses a key it
    # cannot attach a permission to. The static KEY_PERMISSIONS registry covers
    # the dashboards; record META too so any key added here later, but not to
    # that registry, still polls cleanly.
    permission = async_compute.permission_for(key)
    if permission:
        async_compute._cache().set_value(
            async_compute.META_KEY.format(key=key),
            {"doctype": permission[0], "ptype": permission[1]},
            expires_in_sec=async_compute.DEFAULT_TTL,
        )
    frappe.logger().info(f"Dashboard cache warmed: {key}")
    return key


def enqueue_dashboard_warm_jobs():
    """Fan the warm out to one background job per dashboard key."""
    from insights.api.ml import async_compute

    queue = async_compute.resolve_queue()
    timeout = async_compute.resolve_timeout()
    queued = []
    for key, _method, _kwargs in DASHBOARD_CACHE_TARGETS:
        safe = re.sub(r"\W+", "_", key)
        job_id = f"insights_warm_{safe}"
        try:
            # Same corpse problem as the dashboard keys: a job left STARTED by a
            # crash makes `deduplicate=True` skip the replacement silently.
            async_compute.reap_dead_job(job_id, queue_name=queue)
            frappe.enqueue(
                "insights.ml.scheduler.warm_one_dashboard_cache",
                queue=queue,
                timeout=timeout,
                job_id=job_id,
                deduplicate=True,
                key=key,
            )
            queued.append(key)
        except Exception as e:
            frappe.log_error(f"Could not queue dashboard warm for {key}: {str(e)}", "ML Scheduler")
    frappe.logger().info(f"Dashboard warm jobs queued: {', '.join(queued) or 'none'}")
    return queued


def warm_dashboard_caches():
    """Warm every dashboard payload in this process.

    The `bench --site <site> execute insights.ml.scheduler.warm_dashboard_caches`
    entry point. Each target is independent: one failure must not deny the rest
    their warm cache. Background callers should prefer
    `enqueue_dashboard_warm_jobs`, which isolates each key in its own work-horse.
    """
    warmed = []
    for key, _method, _kwargs in DASHBOARD_CACHE_TARGETS:
        try:
            if warm_one_dashboard_cache(key):
                warmed.append(key)
        except Exception as e:
            frappe.log_error(f"Dashboard cache warm failed for {key}: {str(e)}", "ML Scheduler")
    frappe.logger().info(f"Dashboard caches warmed: {', '.join(warmed) or 'none'}")
    return warmed


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


def train_customer_intelligence():
    """Daily: Train comprehensive customer intelligence model"""
    try:
        from insights.ml.customer_intelligence import CustomerIntelligence
        
        frappe.logger().info("Starting scheduled customer intelligence training")
        
        model = CustomerIntelligence()
        
        # Check customer count for async decision
        customer_count = frappe.db.count("Customer", {"disabled": 0})
        
        if customer_count > model.CUSTOMER_THRESHOLD:
            # Run async for large datasets
            frappe.enqueue(
                "insights.ml.customer_intelligence.api._run_customer_intelligence_job",
                queue="long",
                timeout=3600,
                update_customers=True
            )
            frappe.logger().info(
                f"Customer intelligence queued for async processing ({customer_count} customers)"
            )
            return {"status": "queued", "customers": customer_count}
        
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


def train_sales_intelligence():
    """Daily: Train comprehensive sales intelligence model"""
    try:
        from insights.ml.sales_intelligence import SalesIntelligence
        
        frappe.logger().info("Starting scheduled sales intelligence training")
        
        model = SalesIntelligence()
        result = model.train()
        
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
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Scheduled sales intelligence failed: {str(e)}", "ML Scheduler")
        return {"status": "error", "message": str(e)}



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
