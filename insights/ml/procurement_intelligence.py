# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Procurement Intelligence Model
Comprehensive procurement analytics with ML-powered insights for:
- Spend analysis and optimization
- Supplier performance scoring
- Purchase cycle analytics
- Price intelligence and savings
- Risk assessment
- Procurement forecasting
"""

import frappe
from frappe import _
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from insights.ml.base import BaseMLModel


class ProcurementIntelligence(BaseMLModel):
    """
    Comprehensive Procurement Intelligence Model
    
    Features:
    - Spend overview and trends
    - Supplier performance scorecards
    - Purchase cycle analytics
    - Price intelligence and variance
    - Risk assessment (concentration, single-source)
    - Procurement forecasting
    """
    
    def __init__(self):
        super().__init__()
        self.model_name = "ProcurementIntelligence"
        self.company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
        self.base_currency = (
            frappe.db.get_value("Company", self.company, "default_currency")
            or frappe.db.get_single_value("System Settings", "default_currency")
            or "USD"
        )
    
    def train(self) -> Dict[str, Any]:
        """Generate comprehensive procurement intelligence"""
        try:
            spend_overview = self._calculate_spend_overview()
            supplier_performance = self._calculate_supplier_performance()
            purchase_analytics = self._analyze_purchase_cycles()
            price_intelligence = self._calculate_price_intelligence()
            risk_analysis = self._assess_procurement_risks()
            forecasts = self._generate_procurement_forecast()
            
            result = {
                "status": "success",
                "generated_at": datetime.now().isoformat(),
                "company": self.company,
                "base_currency": self.base_currency,
                "spend_overview": spend_overview,
                "supplier_performance": supplier_performance,
                "purchase_analytics": purchase_analytics,
                "price_intelligence": price_intelligence,
                "risk_analysis": risk_analysis,
                "forecasts": forecasts
            }
            
            self.cache_results("procurement_intelligence", result)
            return result
            
        except Exception as e:
            frappe.log_error(f"Procurement Intelligence failed: {str(e)}", "ML Procurement")
            return {"status": "error", "message": str(e)}
    
    def predict(self, allow_train: bool = False) -> Dict[str, Any]:
        """Return cached results.

        `allow_train` is off by default so a cache miss cannot turn a web request
        into a full training pass. The worker-side
        `insights.api.ml.procurement._compute_procurement_intelligence` opts in.
        """
        cached = self.get_cached_results("procurement_intelligence")
        if cached:
            return cached
        if not allow_train:
            return {
                "status": "warming",
                "message": _("Procurement intelligence is being computed. Refresh shortly."),
            }
        return self.train()
    
    def _calculate_spend_overview(self) -> Dict[str, Any]:
        """Calculate overall procurement spend metrics"""
        # Total spend summary
        spend_summary = frappe.db.sql("""
            SELECT 
                COUNT(DISTINCT pi.name) as invoice_count,
                COUNT(DISTINCT pi.supplier) as supplier_count,
                SUM(pi.grand_total) as total_spend,
                AVG(pi.grand_total) as avg_invoice_value
            FROM `tabPurchase Invoice` pi
            WHERE pi.docstatus = 1
                AND pi.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
        """, as_dict=True)[0]
        
        # YTD spend
        ytd_spend = frappe.db.sql("""
            SELECT COALESCE(SUM(grand_total), 0) as ytd_spend
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1
                AND YEAR(posting_date) = YEAR(CURDATE())
        """, as_dict=True)[0]
        
        # Last year same period
        last_year_spend = frappe.db.sql("""
            SELECT COALESCE(SUM(grand_total), 0) as last_year_spend
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1
                AND YEAR(posting_date) = YEAR(CURDATE()) - 1
                AND DAYOFYEAR(posting_date) <= DAYOFYEAR(CURDATE())
        """, as_dict=True)[0]
        
        yoy_growth = 0
        if last_year_spend.get('last_year_spend', 0) > 0:
            yoy_growth = ((ytd_spend.get('ytd_spend', 0) - last_year_spend.get('last_year_spend', 0)) 
                         / last_year_spend.get('last_year_spend', 0)) * 100
        
        # Monthly spend trend
        monthly_trend = frappe.db.sql("""
            SELECT 
                DATE_FORMAT(posting_date, '%Y-%m') as period,
                COUNT(DISTINCT name) as invoice_count,
                COUNT(DISTINCT supplier) as supplier_count,
                SUM(grand_total) as spend
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1
                AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            GROUP BY DATE_FORMAT(posting_date, '%Y-%m')
            ORDER BY period
        """, as_dict=True)
        
        # Spend by item group/category
        spend_by_category = frappe.db.sql("""
            SELECT 
                COALESCE(i.item_group, 'Uncategorized') as category,
                COUNT(DISTINCT pii.parent) as invoice_count,
                SUM(pii.amount) as spend
            FROM `tabPurchase Invoice Item` pii
            JOIN `tabPurchase Invoice` pi ON pii.parent = pi.name
            LEFT JOIN `tabItem` i ON pii.item_code = i.name
            WHERE pi.docstatus = 1
                AND pi.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            GROUP BY i.item_group
            ORDER BY spend DESC
            LIMIT 15
        """, as_dict=True)
        
        total_category_spend = sum(float(c.get('spend') or 0) for c in spend_by_category)
        for cat in spend_by_category:
            cat['pct_of_total'] = round((float(cat.get('spend') or 0) / total_category_spend * 100), 1) if total_category_spend > 0 else 0
        
        # Top suppliers by spend
        top_suppliers = frappe.db.sql("""
            SELECT 
                pi.supplier,
                s.supplier_name,
                COUNT(DISTINCT pi.name) as invoice_count,
                SUM(pi.grand_total) as spend
            FROM `tabPurchase Invoice` pi
            LEFT JOIN `tabSupplier` s ON pi.supplier = s.name
            WHERE pi.docstatus = 1
                AND pi.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            GROUP BY pi.supplier, s.supplier_name
            ORDER BY spend DESC
            LIMIT 10
        """, as_dict=True)
        
        total_supplier_spend = sum(float(s.get('spend') or 0) for s in top_suppliers)
        for sup in top_suppliers:
            sup['pct_of_total'] = round((float(sup.get('spend') or 0) / total_supplier_spend * 100), 1) if total_supplier_spend > 0 else 0
        
        return {
            "total_spend_12m": float(spend_summary.get('total_spend') or 0),
            "ytd_spend": float(ytd_spend.get('ytd_spend') or 0),
            "yoy_growth": round(yoy_growth, 1),
            "invoice_count": int(spend_summary.get('invoice_count') or 0),
            "supplier_count": int(spend_summary.get('supplier_count') or 0),
            "avg_invoice_value": float(spend_summary.get('avg_invoice_value') or 0),
            "monthly_trend": monthly_trend,
            "by_category": spend_by_category,
            "top_suppliers": top_suppliers
        }
    
    def _calculate_supplier_performance(self) -> Dict[str, Any]:
        """Calculate supplier performance scores"""
        # Get all suppliers with purchase activity
        suppliers_data = frappe.db.sql("""
            SELECT 
                po.supplier,
                s.supplier_name,
                s.supplier_group,
                COUNT(DISTINCT po.name) as po_count,
                SUM(po.grand_total) as total_value,
                AVG(DATEDIFF(
                    COALESCE(pr.posting_date, CURDATE()),
                    po.transaction_date
                )) as avg_lead_time,
                COUNT(DISTINCT pr.name) as receipt_count
            FROM `tabPurchase Order` po
            LEFT JOIN `tabSupplier` s ON po.supplier = s.name
            LEFT JOIN `tabPurchase Receipt` pr ON pr.supplier = po.supplier 
                AND pr.docstatus = 1
                AND pr.posting_date >= po.transaction_date
            WHERE po.docstatus = 1
                AND po.transaction_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            GROUP BY po.supplier, s.supplier_name, s.supplier_group
            HAVING po_count >= 2
            ORDER BY total_value DESC
        """, as_dict=True)
        
        # Delivery performance, batched: one GROUP BY query instead of one
        # query per supplier (N suppliers = N extra round-trips previously —
        # confirmed root cause of insights.api.ml.procurement_intelligence
        # timing out in production: this single function alone issued 2
        # sequential queries per supplier on top of the queries in every
        # other train() sub-step. See plan-eng-review production-diagnosis
        # notes, 2026-08-04.
        delivery_by_supplier = frappe.db.sql("""
            SELECT
                po.supplier,
                COUNT(*) as total_orders,
                SUM(CASE
                    WHEN pr.posting_date <= po.schedule_date THEN 1
                    ELSE 0
                END) as on_time_count
            FROM `tabPurchase Order` po
            LEFT JOIN `tabPurchase Receipt` pr ON pr.supplier = po.supplier AND pr.docstatus = 1
            WHERE po.docstatus = 1
                AND po.transaction_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                AND po.schedule_date IS NOT NULL
            GROUP BY po.supplier
        """, as_dict=True)
        delivery_by_supplier_map = {row["supplier"]: row for row in delivery_by_supplier}

        # Quality/return rate: this was NOT supplier-scoped even before this
        # fix (no WHERE on supplier at all) -- it computed one company-wide
        # return figure and divided it by EACH supplier's own spend, so
        # every supplier's "quality_rate" was derived from a number that had
        # nothing to do with that supplier's actual returns. Hoisting it out
        # of the loop removes the redundant re-query; the score itself
        # remains a company-wide proxy until Stock Entry is actually linked
        # back to a specific Purchase Order/supplier (tracked in TODOS.md).
        rejection_data = frappe.db.sql("""
            SELECT
                COALESCE(SUM(CASE WHEN se.stock_entry_type = 'Material Transfer'
                    AND se.purpose LIKE '%%Return%%' THEN se.total_amount ELSE 0 END), 0) as return_value
            FROM `tabStock Entry` se
            WHERE se.docstatus = 1
                AND se.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
        """, as_dict=True)[0]
        return_value = float(rejection_data.get('return_value') or 0)

        for supplier in suppliers_data:
            supplier_code = supplier['supplier']

            delivery_data = delivery_by_supplier_map.get(supplier_code, {"total_orders": 0, "on_time_count": 0})
            total_orders = int(delivery_data.get('total_orders') or 1)
            on_time = int(delivery_data.get('on_time_count') or 0)
            supplier['on_time_rate'] = round((on_time / total_orders * 100), 1) if total_orders > 0 else 0

            total_value = float(supplier.get('total_value') or 1)
            quality_rate = 100 - ((return_value / total_value * 100) if total_value > 0 else 0)
            supplier['quality_rate'] = round(max(0, min(100, quality_rate)), 1)
            
            # Calculate overall score (weighted)
            # On-time: 40%, Quality: 30%, Lead time: 20%, Volume: 10%
            on_time_score = supplier['on_time_rate']
            quality_score = supplier['quality_rate']
            
            # Lead time score (inverse - lower is better, max 30 days = 0 score)
            avg_lead = float(supplier.get('avg_lead_time') or 30)
            lead_time_score = max(0, 100 - (avg_lead / 30 * 100))
            
            # Volume consistency score
            volume_score = min(100, (supplier['po_count'] / 12 * 100))  # 12 orders/year = 100%
            
            supplier['overall_score'] = round(
                (on_time_score * 0.40) + 
                (quality_score * 0.30) + 
                (lead_time_score * 0.20) + 
                (volume_score * 0.10),
                1
            )
            
            supplier['avg_lead_time'] = round(float(supplier.get('avg_lead_time') or 0), 1)
        
        # Sort by overall score
        suppliers_data.sort(key=lambda x: x['overall_score'], reverse=True)
        
        # Top and bottom performers
        top_performers = suppliers_data[:10]
        bottom_performers = sorted(suppliers_data, key=lambda x: x['overall_score'])[:5]
        
        # Average scores
        if suppliers_data:
            avg_score = sum(s['overall_score'] for s in suppliers_data) / len(suppliers_data)
            avg_on_time = sum(s['on_time_rate'] for s in suppliers_data) / len(suppliers_data)
            avg_quality = sum(s['quality_rate'] for s in suppliers_data) / len(suppliers_data)
            avg_lead_time = sum(s['avg_lead_time'] for s in suppliers_data) / len(suppliers_data)
        else:
            avg_score = avg_on_time = avg_quality = avg_lead_time = 0
        
        return {
            "total_suppliers": len(suppliers_data),
            "avg_score": round(avg_score, 1),
            "avg_on_time_rate": round(avg_on_time, 1),
            "avg_quality_rate": round(avg_quality, 1),
            "avg_lead_time": round(avg_lead_time, 1),
            "top_performers": top_performers,
            "bottom_performers": bottom_performers,
            "all_suppliers": suppliers_data[:50]
        }
    
    def _analyze_purchase_cycles(self) -> Dict[str, Any]:
        """Analyze purchase order cycles and processing times"""
        # PO status summary
        po_status = frappe.db.sql("""
            SELECT 
                status,
                COUNT(*) as count,
                SUM(grand_total) as value
            FROM `tabPurchase Order`
            WHERE docstatus = 1
                AND transaction_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            GROUP BY status
        """, as_dict=True)
        
        # Pending POs
        pending_pos = frappe.db.sql("""
            SELECT 
                name,
                supplier,
                transaction_date,
                grand_total,
                DATEDIFF(CURDATE(), transaction_date) as days_pending,
                status
            FROM `tabPurchase Order`
            WHERE docstatus = 1
                AND status NOT IN ('Completed', 'Closed', 'Cancelled')
            ORDER BY days_pending DESC
            LIMIT 20
        """, as_dict=True)
        
        # Average cycle times.
        #
        # Fixed 2026-08-04: this previously joined Purchase Receipt/Purchase
        # Invoice to Purchase Order on `supplier` alone (not on the actual
        # PO/receipt/invoice relationship), and joined Material Request via
        # a non-correlated `po.name IN (subquery)` condition unrelated to
        # `mr`. Every PO was cross-joined against every receipt and every
        # invoice from the same supplier (and, for POs with a linked
        # material request, against every material request in the system) --
        # a combinatorial explosion, not a relational join. Confirmed via
        # live profiling: this single query alone hung for 5+ minutes on
        # production-scale data, the direct cause of the
        # procurement_intelligence 502s. Rewritten to join through the real
        # FK chain: Purchase Order Item.material_request, Purchase Receipt
        # Item.purchase_order, Purchase Invoice Item.purchase_receipt.
        cycle_times = frappe.db.sql("""
            SELECT
                AVG(DATEDIFF(po.transaction_date, mr.transaction_date)) as mr_to_po_days,
                AVG(DATEDIFF(pr.posting_date, po.transaction_date)) as po_to_grn_days,
                AVG(DATEDIFF(pi.posting_date, pr.posting_date)) as grn_to_invoice_days
            FROM `tabPurchase Order` po
            LEFT JOIN `tabPurchase Order Item` poi ON poi.parent = po.name
            LEFT JOIN `tabMaterial Request` mr ON mr.name = poi.material_request
            LEFT JOIN `tabPurchase Receipt Item` pri ON pri.purchase_order = po.name
            LEFT JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent AND pr.docstatus = 1
            LEFT JOIN `tabPurchase Invoice Item` pii ON pii.purchase_receipt = pr.name
            LEFT JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent AND pi.docstatus = 1
            WHERE po.docstatus = 1
                AND po.transaction_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
        """, as_dict=True)[0]
        
        # Monthly PO trends
        monthly_pos = frappe.db.sql("""
            SELECT 
                DATE_FORMAT(transaction_date, '%Y-%m') as period,
                COUNT(*) as po_count,
                SUM(grand_total) as po_value,
                AVG(grand_total) as avg_po_value
            FROM `tabPurchase Order`
            WHERE docstatus = 1
                AND transaction_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            GROUP BY DATE_FORMAT(transaction_date, '%Y-%m')
            ORDER BY period
        """, as_dict=True)
        
        # GRN completion rate.
        #
        # Fixed 2026-08-04: same same-supplier-join bug as cycle_times above
        # -- joined on pr.supplier = po.supplier instead of the actual
        # PO<->Receipt relationship, so "received_pos" counted ANY receipt
        # from a supplier with a recent PO, not receipts actually fulfilling
        # those POs. Wrong number, not just slow.
        grn_rate = frappe.db.sql("""
            SELECT
                COUNT(DISTINCT po.name) as total_pos,
                COUNT(DISTINCT CASE WHEN pr.docstatus = 1 THEN pri.purchase_order END) as received_pos
            FROM `tabPurchase Order` po
            LEFT JOIN `tabPurchase Receipt Item` pri ON pri.purchase_order = po.name
            LEFT JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
            WHERE po.docstatus = 1
                AND po.transaction_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
        """, as_dict=True)[0]
        
        total_pos = int(grn_rate.get('total_pos') or 1)
        received = int(grn_rate.get('received_pos') or 0)
        grn_completion = round((received / total_pos * 100), 1) if total_pos > 0 else 0
        
        return {
            "po_status_summary": po_status,
            "pending_pos": pending_pos,
            "pending_count": len(pending_pos),
            "pending_value": sum(float(p.get('grand_total') or 0) for p in pending_pos),
            "avg_mr_to_po_days": round(float(cycle_times.get('mr_to_po_days') or 0), 1),
            "avg_po_to_grn_days": round(float(cycle_times.get('po_to_grn_days') or 0), 1),
            "avg_grn_to_invoice_days": round(float(cycle_times.get('grn_to_invoice_days') or 0), 1),
            "monthly_trend": monthly_pos,
            "grn_completion_rate": grn_completion
        }
    
    def _calculate_price_intelligence(self) -> Dict[str, Any]:
        """Calculate price trends and savings opportunities"""
        # Price variance by item (last purchase vs average)
        price_variance = frappe.db.sql("""
            SELECT 
                pii.item_code,
                i.item_name,
                i.item_group,
                COUNT(DISTINCT pii.parent) as purchase_count,
                AVG(pii.rate) as avg_rate,
                MIN(pii.rate) as min_rate,
                MAX(pii.rate) as max_rate,
                (
                    SELECT rate FROM `tabPurchase Invoice Item` pii2
                    JOIN `tabPurchase Invoice` pi2 ON pii2.parent = pi2.name
                    WHERE pii2.item_code = pii.item_code AND pi2.docstatus = 1
                    ORDER BY pi2.posting_date DESC LIMIT 1
                ) as last_rate
            FROM `tabPurchase Invoice Item` pii
            JOIN `tabPurchase Invoice` pi ON pii.parent = pi.name
            LEFT JOIN `tabItem` i ON pii.item_code = i.name
            WHERE pi.docstatus = 1
                AND pi.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            GROUP BY pii.item_code, i.item_name, i.item_group
            HAVING purchase_count >= 3
            ORDER BY purchase_count DESC
            LIMIT 50
        """, as_dict=True)
        
        # Calculate variance percentage
        for item in price_variance:
            avg_rate = float(item.get('avg_rate') or 1)
            last_rate = float(item.get('last_rate') or avg_rate)
            min_rate = float(item.get('min_rate') or avg_rate)
            max_rate = float(item.get('max_rate') or avg_rate)
            
            item['price_variance_pct'] = round(((last_rate - avg_rate) / avg_rate * 100), 1) if avg_rate > 0 else 0
            item['price_range_pct'] = round(((max_rate - min_rate) / avg_rate * 100), 1) if avg_rate > 0 else 0
            item['potential_savings'] = round((last_rate - min_rate) * float(item.get('purchase_count') or 0), 2)
        
        # Items with price increases
        price_increases = [i for i in price_variance if i['price_variance_pct'] > 5]
        price_increases.sort(key=lambda x: x['price_variance_pct'], reverse=True)
        
        # Items with high price variance (volatile)
        volatile_items = [i for i in price_variance if i['price_range_pct'] > 20]
        volatile_items.sort(key=lambda x: x['price_range_pct'], reverse=True)
        
        # Best price suppliers by item
        best_prices = frappe.db.sql("""
            SELECT 
                pii.item_code,
                i.item_name,
                pi.supplier,
                s.supplier_name,
                MIN(pii.rate) as best_rate,
                COUNT(*) as purchase_count
            FROM `tabPurchase Invoice Item` pii
            JOIN `tabPurchase Invoice` pi ON pii.parent = pi.name
            LEFT JOIN `tabItem` i ON pii.item_code = i.name
            LEFT JOIN `tabSupplier` s ON pi.supplier = s.name
            WHERE pi.docstatus = 1
                AND pi.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            GROUP BY pii.item_code, pi.supplier
            ORDER BY pii.item_code, best_rate
        """, as_dict=True)
        
        # Group by item and get best supplier
        item_best_suppliers = {}
        for row in best_prices:
            item_code = row['item_code']
            if item_code not in item_best_suppliers:
                item_best_suppliers[item_code] = row
        
        # Calculate total potential savings
        total_potential_savings = sum(float(i.get('potential_savings') or 0) for i in price_variance)
        
        return {
            "price_variance_items": price_variance[:20],
            "price_increases": price_increases[:10],
            "volatile_items": volatile_items[:10],
            "best_price_suppliers": list(item_best_suppliers.values())[:20],
            "total_potential_savings": round(total_potential_savings, 2),
            "items_analyzed": len(price_variance)
        }
    
    def _assess_procurement_risks(self) -> Dict[str, Any]:
        """Assess procurement and supplier risks"""
        # Supplier concentration risk
        supplier_concentration = frappe.db.sql("""
            SELECT 
                pi.supplier,
                s.supplier_name,
                SUM(pi.grand_total) as spend,
                (SELECT SUM(grand_total) FROM `tabPurchase Invoice` 
                 WHERE docstatus = 1 AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)) as total_spend
            FROM `tabPurchase Invoice` pi
            LEFT JOIN `tabSupplier` s ON pi.supplier = s.name
            WHERE pi.docstatus = 1
                AND pi.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            GROUP BY pi.supplier, s.supplier_name
            ORDER BY spend DESC
            LIMIT 10
        """, as_dict=True)
        
        for sup in supplier_concentration:
            total = float(sup.get('total_spend') or 1)
            spend = float(sup.get('spend') or 0)
            sup['concentration_pct'] = round((spend / total * 100), 1) if total > 0 else 0
            sup['risk_level'] = 'High' if sup['concentration_pct'] > 30 else ('Medium' if sup['concentration_pct'] > 15 else 'Low')
        
        # Single source items (items with only 1 supplier)
        single_source = frappe.db.sql("""
            SELECT 
                pii.item_code,
                i.item_name,
                i.item_group,
                COUNT(DISTINCT pi.supplier) as supplier_count,
                SUM(pii.amount) as total_spend,
                MAX(pi.supplier) as only_supplier
            FROM `tabPurchase Invoice Item` pii
            JOIN `tabPurchase Invoice` pi ON pii.parent = pi.name
            LEFT JOIN `tabItem` i ON pii.item_code = i.name
            WHERE pi.docstatus = 1
                AND pi.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            GROUP BY pii.item_code, i.item_name, i.item_group
            HAVING supplier_count = 1 AND total_spend > 10000
            ORDER BY total_spend DESC
            LIMIT 20
        """, as_dict=True)
        
        # Payment exposure (outstanding payables)
        payment_exposure = frappe.db.sql("""
            SELECT 
                pi.supplier,
                s.supplier_name,
                SUM(pi.outstanding_amount) as outstanding,
                COUNT(*) as invoice_count,
                MIN(pi.due_date) as earliest_due
            FROM `tabPurchase Invoice` pi
            LEFT JOIN `tabSupplier` s ON pi.supplier = s.name
            WHERE pi.docstatus = 1
                AND pi.outstanding_amount > 0
            GROUP BY pi.supplier, s.supplier_name
            ORDER BY outstanding DESC
            LIMIT 15
        """, as_dict=True)
        
        # Get actual total outstanding (not limited to top 15)
        total_outstanding_result = frappe.db.sql("""
            SELECT SUM(outstanding_amount) as total
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1 AND outstanding_amount > 0
        """, as_dict=True)[0]
        total_outstanding = float(total_outstanding_result.get('total') or 0)
        
        # Overdue invoices
        overdue_invoices = frappe.db.sql("""
            SELECT 
                name,
                supplier,
                posting_date,
                due_date,
                grand_total,
                outstanding_amount,
                DATEDIFF(CURDATE(), due_date) as days_overdue
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1
                AND outstanding_amount > 0
                AND due_date < CURDATE()
            ORDER BY days_overdue DESC
            LIMIT 20
        """, as_dict=True)
        
        # Get actual total overdue count and value (not limited to 20)
        overdue_totals = frappe.db.sql("""
            SELECT COUNT(*) as count, COALESCE(SUM(outstanding_amount), 0) as value
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1
                AND outstanding_amount > 0
                AND due_date < CURDATE()
        """, as_dict=True)[0]
        
        overdue_count = int(overdue_totals.get('count') or 0)
        overdue_value = float(overdue_totals.get('value') or 0)
        
        # Risk score calculation
        high_concentration_count = len([s for s in supplier_concentration if s['concentration_pct'] > 30])
        single_source_value = sum(float(s.get('total_spend') or 0) for s in single_source)
        
        # Overall risk score (0-100, lower is better)
        risk_score = min(100, (
            (high_concentration_count * 15) +  # Each high concentration supplier adds 15
            (len(single_source) * 2) +  # Each single source item adds 2
            (overdue_value / 100000)  # Overdue value impact
        ))
        
        return {
            "risk_score": round(risk_score, 1),
            "supplier_concentration": supplier_concentration,
            "high_concentration_count": high_concentration_count,
            "single_source_items": single_source,
            "single_source_count": len(single_source),
            "single_source_value": single_source_value,
            "payment_exposure": payment_exposure,
            "total_outstanding": total_outstanding,
            "overdue_invoices": overdue_invoices,
            "overdue_count": overdue_count,
            "overdue_value": overdue_value
        }
    
    def _generate_procurement_forecast(self) -> Dict[str, Any]:
        """Generate procurement spend forecasts"""
        # Historical monthly spend for forecasting
        historical = frappe.db.sql("""
            SELECT 
                DATE_FORMAT(posting_date, '%Y-%m') as period,
                SUM(grand_total) as spend
            FROM `tabPurchase Invoice`
            WHERE docstatus = 1
                AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 24 MONTH)
            GROUP BY DATE_FORMAT(posting_date, '%Y-%m')
            ORDER BY period
        """, as_dict=True)
        
        if len(historical) < 6:
            return {
                "status": "insufficient_data",
                "message": "Need at least 6 months of data for forecasting",
                "historical": [dict(h) for h in historical] if historical else []
            }
        
        # Convert frappe dicts to regular dicts for pandas compatibility
        historical_data = [{'period': h['period'], 'spend': float(h['spend'] or 0)} for h in historical]
        
        # Simple moving average forecast
        df = pd.DataFrame(historical_data)
        df['spend'] = pd.to_numeric(df['spend'])
        
        # Calculate 3-month moving average
        avg_spend = float(df['spend'].tail(6).mean())
        trend = float((df['spend'].tail(3).mean() - df['spend'].head(3).mean()) / 3)
        
        # Generate 3-month forecast
        forecasts = []
        today = datetime.now()
        for i in range(1, 4):
            future_date = today + timedelta(days=30*i)
            period = future_date.strftime('%Y-%m')
            predicted = avg_spend + (trend * i)
            forecasts.append({
                'period': period,
                'predicted_spend': float(round(max(0, predicted), 2)),
                'confidence': 'Medium' if i <= 2 else 'Low'
            })
        
        # Seasonal analysis
        df['month'] = pd.to_datetime(df['period'] + '-01').dt.month
        seasonal = df.groupby('month')['spend'].mean().to_dict()
        
        # Category-wise forecast
        category_forecast = frappe.db.sql("""
            SELECT 
                COALESCE(i.item_group, 'Uncategorized') as category,
                AVG(pii.amount) as avg_monthly_spend,
                SUM(pii.amount) as total_12m
            FROM `tabPurchase Invoice Item` pii
            JOIN `tabPurchase Invoice` pi ON pii.parent = pi.name
            LEFT JOIN `tabItem` i ON pii.item_code = i.name
            WHERE pi.docstatus = 1
                AND pi.posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            GROUP BY i.item_group
            ORDER BY total_12m DESC
            LIMIT 10
        """, as_dict=True)
        
        for cat in category_forecast:
            avg = float(cat.get('avg_monthly_spend') or 0)
            cat['forecast_3m'] = round(avg * 3 * 1.02, 2)  # 2% growth assumption
        
        return {
            "status": "success",
            "historical": historical,
            "forecasts": forecasts,
            "avg_monthly_spend": round(avg_spend, 2),
            "trend_direction": "up" if trend > 0 else "down",
            "trend_amount": round(abs(trend), 2),
            "seasonal_pattern": {str(k): round(v, 2) for k, v in seasonal.items()},
            "category_forecast": category_forecast
        }


def run_procurement_intelligence(refresh: bool = False) -> Dict[str, Any]:
    """Run procurement intelligence analysis"""
    model = ProcurementIntelligence()
    if not refresh:
        cached = model.get_cached_results("procurement_intelligence")
        if cached:
            return cached
    return model.train()
