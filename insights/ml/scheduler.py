# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
ML Scheduler Tasks
Manual training of ML models via `bench execute`.

Design: every trainer function is invoked directly from the foreground
process (e.g. `bench execute insights.ml.scheduler.run_all_ml_models`).
These functions are NO LONGER registered in `hooks.py` `scheduler_events`
-- every dashboard now computes its own data fresh via Ibis on each
request instead of training then caching a model (see `insights.ml.base`).
There is no cache for these functions to warm; they remain useful for
one-off manual runs and operational tooling only.
"""

import frappe


# ── Individual model trainers ──────────────────────────────────────────────
# Each follows the same pattern:
#   1. Lazy import of the model function/class (inside the function body)
#   2. Compute fresh -- there is no cache to fill; every ML module is pure
#      Ibis now and answers synchronously (see `insights.ml.base`)
#   3. frappe.log_error on failure (standard Frappe error logging)
#   4. Return dict with status key



def train_customer_segmentation():
    """Daily: Train customer segmentation model"""
    try:
        from insights.ml.customer import compute_rfm_segmentation

        frappe.logger().info("Starting scheduled customer segmentation training")
        result = compute_rfm_segmentation()

        if result.get('status') == 'success':
            frappe.logger().info(
                f"Customer segmentation completed: "
                f"{result.get('total_customers', 0)} customers, "
                f"{len(result.get('segments') or [])} segments"
            )

        return result

    except Exception as e:
        frappe.log_error(f"Scheduled customer segmentation failed: {str(e)}", "ML Scheduler")
        return {"status": "error", "message": str(e)}


def train_sales_forecast():
    """Daily: Train sales forecasting model"""
    try:
        from insights.ml.sales_forecasting import run_sales_forecast

        frappe.logger().info("Starting scheduled sales forecast training")
        result = run_sales_forecast()

        if result.get('status') == 'success':
            frappe.logger().info(
                f"Sales forecast completed: method={result.get('method', 'unknown')}"
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
                f"Payment prediction completed: "
                f"{result.get('training_samples', 0)} training samples scored"
            )

        return result

    except Exception as e:
        frappe.log_error(f"Scheduled payment prediction failed: {str(e)}", "ML Scheduler")
        return {"status": "error", "message": str(e)}


def train_abc_xyz_classification():
    """Daily: Train ABC/XYZ inventory classification"""
    try:
        from insights.ml.inventory_intelligence import ABCXYZClassification

        frappe.logger().info("Starting scheduled ABC/XYZ classification")
        model = ABCXYZClassification()
        result = model.train()

        if result.get('status') == 'success':
            frappe.logger().info(
                f"ABC/XYZ classification completed: "
                f"{result.get('total_items', 0)} items classified"
            )

        return result

    except Exception as e:
        frappe.log_error(f"Scheduled ABC/XYZ classification failed: {str(e)}", "ML Scheduler")
        return {"status": "error", "message": str(e)}


def train_demand_forecast():
    """Daily: Train demand forecasting model"""
    try:
        from insights.ml.demand_forecasting import DemandForecasting

        frappe.logger().info("Starting scheduled demand forecast training")
        model = DemandForecasting()
        result = model.train()

        if result.get('status') == 'success':
            frappe.logger().info(
                f"Demand forecast completed: "
                f"{result.get('total_items_analyzed', 0)} items analyzed"
            )
            # Send reorder alerts if items need reordering
            _send_reorder_alert(result)

        return result

    except Exception as e:
        frappe.log_error(f"Scheduled demand forecast failed: {str(e)}", "ML Scheduler")
        return {"status": "error", "message": str(e)}


def train_product_recommendations():
    """Daily: Train product recommendation model"""
    try:
        from insights.ml.product_recommendations import ProductRecommendations

        frappe.logger().info("Starting scheduled product recommendation training")
        model = ProductRecommendations()
        result = model.train()

        if result.get('status') == 'success':
            summary = result.get('transaction_summary', {})
            frappe.logger().info(
                f"Product recommendations completed: "
                f"{summary.get('total_items', 0)} items across "
                f"{summary.get('total_transactions', 0)} transactions"
            )

        return result

    except Exception as e:
        frappe.log_error(f"Scheduled product recommendations failed: {str(e)}", "ML Scheduler")
        return {"status": "error", "message": str(e)}


def _send_reorder_alert(forecast_result: dict):
    """Send reorder alert notification"""
    try:
        reorder_items = [
            f for f in forecast_result.get('reorder_alerts', [])
            if f.get('status') == 'reorder_now'
        ]
        if not reorder_items:
            return

        items_list = "\n".join([
            f"- {item.get('item_code', 'Unknown')}: "
            f"Current stock: {item.get('current_stock', 0)}, "
            f"Monthly forecast: {item.get('monthly_forecast', 0)}, "
            f"Stock covers {item.get('months_cover', 0)} months"
            for item in reorder_items[:10]
        ])

        subject = f"Reorder Alert: {len(reorder_items)} items need reordering"
        message = (
            f"The following items need to be reordered based on demand forecasting:\n\n"
            f"{items_list}"
        )
        if len(reorder_items) > 10:
            message += f"\n\n... and {len(reorder_items) - 10} more items"

        stock_managers = frappe.get_all(
            "Has Role",
            filters={"role": "Stock Manager", "parenttype": "User"},
            fields=["parent"],
            pluck="parent",
        )
        for user in stock_managers[:5]:
            try:
                frappe.sendmail(
                    recipients=[user],
                    subject=subject,
                    message=message,
                )
            except Exception:
                pass

    except Exception as e:
        frappe.log_error(f"Failed to send reorder alert: {str(e)}", "ML Scheduler")


def _send_churn_risk_alert(intelligence_result: dict):
    """Send churn risk alert notification"""
    try:
        at_risk = intelligence_result.get('at_risk_customers', [])
        if not at_risk:
            return

        high_risk = sorted(
            at_risk, key=lambda c: float(c.get('churn_score') or 0), reverse=True
        )[:10]
        items_list = "\n".join([
            f"- {c.get('customer_name', c.get('customer_id', 'Unknown'))}: "
            f"Churn Score: {c.get('churn_score', 0):.0f}%, "
            f"Last order: {c.get('recency_days', 'N/A')} days ago"
            for c in high_risk
        ])

        if not items_list:
            return

        subject = f"Churn Risk Alert: {len(at_risk)} customers at risk"
        message = (
            f"The following customers are at risk of churning based on AI analysis:\n\n"
            f"{items_list}"
        )
        if len(at_risk) > 10:
            message += f"\n\n... and {len(at_risk) - 10} more customers"

        accounts_managers = frappe.get_all(
            "Has Role",
            filters={"role": ["in", ["Accounts Manager", "Sales Manager"]], "parenttype": "User"},
            fields=["parent"],
            pluck="parent",
        )
        for user in accounts_managers[:5]:
            try:
                frappe.sendmail(
                    recipients=[user],
                    subject=subject,
                    message=message,
                )
            except Exception:
                pass

    except Exception as e:
        frappe.log_error(f"Failed to send churn risk alert: {str(e)}", "ML Scheduler")


# ── Composite trainers ─────────────────────────────────────────────────────


def run_daily_intelligence():
    """Single daily job: trains all daily models and warms executive cache.

    Manually invoked via `bench execute insights.ml.scheduler.run_daily_intelligence`.
    Each sub-trainer is independent: one failure must not deny the rest.
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

    # Warm executive summary cache (separate 1h TTL)
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


def warm_dashboard_caches():
    """Train every model the dashboards read, in this process.

    Entry point for ``bench --site <site> execute
    insights.ml.scheduler.warm_dashboard_caches``.
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


def run_all_ml_models():
    """Run all ML models — can be triggered manually via bench execute."""
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


    # ── Intelligence trainers (larger models) ──────────────────────────────────


def train_customer_intelligence():
    """Daily: Train comprehensive customer intelligence model"""
    try:
        from insights.ml.customer import compute_customer_intelligence

        frappe.logger().info("Starting scheduled customer intelligence training")
        result = compute_customer_intelligence()

        if result.get('status') == 'success':
            summary = result.get('summary', {})
            at_risk = len(result.get('at_risk_customers', []))
            frappe.logger().info(
                f"Customer intelligence completed: "
                f"{summary.get('total_customers', 0)} customers analyzed, "
                f"{at_risk} at risk"
            )
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


def train_sales_intelligence():
    """Daily: Train comprehensive sales intelligence model"""
    try:
        from insights.ml.sales_intelligence import run_sales_intelligence

        frappe.logger().info("Starting scheduled sales intelligence training")
        result = run_sales_intelligence()

        if result.get('status') == 'success':
            summary = result.get('summary', {})
            frappe.logger().info(
                f"Sales intelligence completed: "
                f"{summary.get('total_transactions', 0)} transactions analyzed, "
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
    """Daily: Train procurement intelligence model."""
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
