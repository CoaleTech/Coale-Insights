# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Tax Intelligence Model - Kenya Corporate Tax
Comprehensive tax analytics with ML-powered insights for:
- Corporate tax computation (30% rate)
- Allowable vs non-allowable expense segregation
- Capital allowances tracking (wear & tear, investment deduction)
- KRA quarterly instalment scheduling
- Withholding Tax (WHT) tracking
- Tax forecasting and optimization
"""

import frappe
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from typing import Dict, Any, List, Optional, Tuple
from insights.ml.base import BaseMLModel


# Kenya Tax Constants
CORPORATE_TAX_RATE = 0.30  # 30% corporate tax rate
RESIDENT_WHT_RATE = 0.05  # 5% WHT on dividends, interest (resident)
NON_RESIDENT_WHT_RATE = 0.15  # 15% WHT for non-residents
MANAGEMENT_FEE_WHT_RATE = 0.05  # 5% WHT on management fees
PROFESSIONAL_FEE_WHT_RATE = 0.05  # 5% WHT on professional fees
CONTRACTOR_WHT_RATE = 0.03  # 3% WHT on contractors

# Capital Allowances Rates (Kenya Income Tax Act)
WEAR_TEAR_RATES = {
    "Class I": 0.375,  # 37.5% - Heavy earth moving equipment
    "Class II": 0.30,  # 30% - Vehicles, aircraft
    "Class III": 0.25,  # 25% - Computers, machinery
    "Class IV": 0.125,  # 12.5% - Buildings, furniture
}
INVESTMENT_DEDUCTION_RATE = 1.00  # 100% first year for qualifying assets
INDUSTRIAL_BUILDING_DEDUCTION = 0.10  # 10% for industrial buildings


class TaxIntelligence(BaseMLModel):
    """
    Kenya Corporate Tax Intelligence Model
    
    Features:
    - GL-based tax computation
    - Expense categorization (allowable/non-allowable)
    - Capital allowances calculation from Asset doctype
    - KRA instalment scheduling (4th, 6th, 9th, 12th month)
    - WHT tracking and compliance
    - Tax forecasting
    """
    
    def __init__(self):
        super().__init__()
        self.model_name = "TaxIntelligence"
        self.company = frappe.defaults.get_user_default("company") or frappe.db.get_single_value("Global Defaults", "default_company")
        self.base_currency = frappe.db.get_value("Company", self.company, "default_currency") or "KES"
        self.fiscal_year = self._get_current_fiscal_year()
        
    def _get_current_fiscal_year(self) -> Dict[str, Any]:
        """Get current fiscal year for the company from Fiscal Year doctype"""
        today = datetime.now().date()
        
        # First try to get fiscal year for the company
        fiscal_year = frappe.db.sql("""
            SELECT fy.name, fy.year_start_date, fy.year_end_date
            FROM `tabFiscal Year` fy
            LEFT JOIN `tabFiscal Year Company` fyc ON fyc.parent = fy.name
            WHERE fy.disabled = 0
                AND %s BETWEEN fy.year_start_date AND fy.year_end_date
                AND (fyc.company = %s OR fyc.company IS NULL)
            ORDER BY fy.year_start_date DESC
            LIMIT 1
        """, (today, self.company), as_dict=True)
        
        if fiscal_year:
            return fiscal_year[0]
        
        # Fallback: Get any active fiscal year
        fiscal_year = frappe.db.sql("""
            SELECT name, year_start_date, year_end_date
            FROM `tabFiscal Year`
            WHERE disabled = 0
                AND %s BETWEEN year_start_date AND year_end_date
            ORDER BY year_start_date DESC
            LIMIT 1
        """, (today,), as_dict=True)
        
        if fiscal_year:
            return fiscal_year[0]
        
        # Default to calendar year if no fiscal year found
        return {
            "name": str(today.year),
            "year_start_date": datetime(today.year, 1, 1).date(),
            "year_end_date": datetime(today.year, 12, 31).date()
        }
    
    def train(self) -> Dict[str, Any]:
        """Generate comprehensive tax intelligence"""
        try:
            tax_overview = self._calculate_tax_overview()
            income_analysis = self._analyze_income()
            expense_analysis = self._analyze_expenses()
            capital_allowances = self._calculate_capital_allowances()
            kra_schedule = self._generate_kra_schedule(tax_overview)
            wht_analysis = self._analyze_wht()
            tax_forecast = self._generate_tax_forecast(tax_overview)
            yoy_analysis = self._calculate_yoy_variance()
            optimization_insights = self._generate_optimization_insights(tax_overview, expense_analysis, capital_allowances)
            
            result = {
                "status": "success",
                "generated_at": datetime.now().isoformat(),
                "company": self.company,
                "base_currency": self.base_currency,
                "fiscal_year": {
                    "name": self.fiscal_year["name"],
                    "year_start_date": str(self.fiscal_year["year_start_date"]),
                    "year_end_date": str(self.fiscal_year["year_end_date"])
                },
                "tax_overview": tax_overview,
                "income_analysis": income_analysis,
                "expense_analysis": expense_analysis,
                "capital_allowances": capital_allowances,
                "kra_schedule": kra_schedule,
                "wht_analysis": wht_analysis,
                "tax_forecast": tax_forecast,
                "yoy_analysis": yoy_analysis,
                "optimization_insights": optimization_insights
            }
            
            self.cache_results("tax_intelligence", result)
            return result
            
        except Exception as e:
            frappe.log_error(f"Tax Intelligence failed: {str(e)}", "ML Tax")
            return {"status": "error", "message": str(e)}
    
    def predict(self) -> Dict[str, Any]:
        """Return cached results or generate new ones"""
        cached = self.get_cached_results("tax_intelligence")
        if cached:
            return cached
        return self.train()
    
    def _calculate_tax_overview(self) -> Dict[str, Any]:
        """Calculate overall tax position"""
        fy_start = self.fiscal_year["year_start_date"]
        fy_end = self.fiscal_year["year_end_date"]
        
        # Get total revenue (Income accounts)
        revenue = frappe.db.sql("""
            SELECT COALESCE(SUM(credit - debit), 0) as total
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.is_cancelled = 0
                AND acc.root_type = 'Income'
        """, (self.company, fy_start, fy_end), as_dict=True)[0]
        
        # Get total expenses (Expense accounts)
        expenses = frappe.db.sql("""
            SELECT COALESCE(SUM(debit - credit), 0) as total
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.is_cancelled = 0
                AND acc.root_type = 'Expense'
        """, (self.company, fy_start, fy_end), as_dict=True)[0]
        
        total_revenue = float(revenue.get('total') or 0)
        total_expenses = float(expenses.get('total') or 0)
        
        # Calculate allowable and non-allowable expenses
        allowable_expenses = self._get_allowable_expenses()
        non_allowable_expenses = self._get_non_allowable_expenses()
        
        # Get capital allowances from Asset doctype
        capital_allowances = self._get_total_capital_allowances()
        
        # Calculate taxable income per Kenya Income Tax Act
        gross_profit = total_revenue - total_expenses
        add_back = non_allowable_expenses  # Add back non-allowable expenses
        less_capital_allowances = capital_allowances
        
        taxable_income = gross_profit + add_back - less_capital_allowances
        taxable_income = max(0, taxable_income)  # Cannot be negative
        
        # Calculate tax liability
        tax_liability = taxable_income * CORPORATE_TAX_RATE
        
        # Get instalments paid
        instalments_paid = self._get_instalments_paid()
        
        # Net tax position
        net_tax_position = tax_liability - instalments_paid
        
        # Effective tax rate
        effective_rate = (tax_liability / total_revenue * 100) if total_revenue > 0 else 0
        
        return {
            "total_revenue": total_revenue,
            "total_expenses": total_expenses,
            "gross_profit": gross_profit,
            "allowable_expenses": allowable_expenses,
            "non_allowable_expenses": non_allowable_expenses,
            "add_backs": add_back,
            "capital_allowances": capital_allowances,
            "taxable_income": taxable_income,
            "corporate_tax_rate": CORPORATE_TAX_RATE * 100,
            "tax_liability": tax_liability,
            "instalments_paid": instalments_paid,
            "net_tax_position": net_tax_position,
            "effective_tax_rate": round(effective_rate, 2),
            "fiscal_year": self.fiscal_year["name"]
        }
    
    def _get_allowable_expenses(self) -> float:
        """Get total allowable expenses for tax purposes"""
        fy_start = self.fiscal_year["year_start_date"]
        fy_end = self.fiscal_year["year_end_date"]
        
        # Get all expenses first
        total = frappe.db.sql("""
            SELECT COALESCE(SUM(debit - credit), 0) as total
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.is_cancelled = 0
                AND acc.root_type = 'Expense'
        """, (self.company, fy_start, fy_end), as_dict=True)[0]
        
        total_expenses = float(total.get('total') or 0)
        non_allowable = self._get_non_allowable_expenses()
        
        return total_expenses - non_allowable
    
    def _get_non_allowable_expenses(self) -> float:
        """Get total non-allowable expenses (add-backs) per Kenya Income Tax Act"""
        fy_start = self.fiscal_year["year_start_date"]
        fy_end = self.fiscal_year["year_end_date"]
        
        # Non-allowable expense patterns in Kenya:
        # - Entertainment expenses (not for staff welfare)
        # - Donations (unless to approved institutions)
        # - Penalties and fines
        # - Personal expenses
        # - Capital expenditure (claimed as capital allowances instead)
        # - Provisions (general)
        
        # Bound, not embedded. These are literals today, so the old
        # f"... LIKE '{p}'" was not exploitable -- but it put values in the SQL
        # text, which is the shape that becomes an injection the moment someone
        # makes the list configurable. `%` is the LIKE wildcard here, not a
        # format specifier, so it is single not doubled once bound.
        non_allowable_patterns = [
            "%entertainment%",
            "%donation%",
            "%penalty%",
            "%fine%",
            "%personal%",
            "%gift%",
            "%political%",
            "%provision%bad%debt%",
        ]

        like_conditions = " OR ".join(["LOWER(acc.account_name) LIKE %s"] * len(non_allowable_patterns))

        result = frappe.db.sql(
            f"""
            SELECT COALESCE(SUM(debit - credit), 0) as total
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.is_cancelled = 0
                AND acc.root_type = 'Expense'
                AND ({like_conditions})
            """,
            (self.company, fy_start, fy_end, *non_allowable_patterns),
            as_dict=True,
        )[0]
        
        return float(result.get('total') or 0)
    
    def _get_total_capital_allowances(self) -> float:
        """Calculate total capital allowances from Asset doctype"""
        fy_start = self.fiscal_year["year_start_date"]
        fy_end = self.fiscal_year["year_end_date"]
        
        # Get depreciation from Asset doctype's Depreciation Schedule
        depreciation = frappe.db.sql("""
            SELECT COALESCE(SUM(ds.depreciation_amount), 0) as total
            FROM `tabAsset` a
            JOIN `tabDepreciation Schedule` ds ON ds.parent = a.name
            WHERE a.company = %s
                AND a.docstatus = 1
                AND a.status NOT IN ('Scrapped', 'Sold')
                AND ds.schedule_date BETWEEN %s AND %s
                AND ds.journal_entry IS NOT NULL
        """, (self.company, fy_start, fy_end), as_dict=True)[0]
        
        return float(depreciation.get('total') or 0)
    
    def _get_instalments_paid(self) -> float:
        """Get corporate tax instalments paid during the year"""
        fy_start = self.fiscal_year["year_start_date"]
        fy_end = self.fiscal_year["year_end_date"]
        
        # Look for payments to tax liability accounts
        result = frappe.db.sql("""
            SELECT COALESCE(SUM(debit), 0) as total
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.is_cancelled = 0
                AND (
                    LOWER(acc.account_name) LIKE '%%corporate tax%%'
                    OR LOWER(acc.account_name) LIKE '%%income tax%%'
                    OR LOWER(acc.account_name) LIKE '%%kra%%'
                    OR LOWER(acc.account_name) LIKE '%%tax payable%%'
                )
                AND acc.root_type = 'Liability'
        """, (self.company, fy_start, fy_end), as_dict=True)[0]
        
        return float(result.get('total') or 0)
    
    def _analyze_income(self) -> Dict[str, Any]:
        """Analyze income by category for tax purposes"""
        fy_start = self.fiscal_year["year_start_date"]
        fy_end = self.fiscal_year["year_end_date"]
        
        # Income by account
        income_by_account = frappe.db.sql("""
            SELECT 
                acc.account_name,
                acc.parent_account,
                COALESCE(SUM(credit - debit), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.is_cancelled = 0
                AND acc.root_type = 'Income'
            GROUP BY acc.account_name, acc.parent_account
            HAVING amount > 0
            ORDER BY amount DESC
        """, (self.company, fy_start, fy_end), as_dict=True)
        
        # Convert to serializable format
        income_list = [
            {"account_name": r["account_name"], "parent_account": r["parent_account"], "amount": float(r["amount"])}
            for r in income_by_account
        ]
        
        # Monthly income trend
        monthly_income = frappe.db.sql("""
            SELECT 
                DATE_FORMAT(gle.posting_date, '%%Y-%%m') as period,
                COALESCE(SUM(credit - debit), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.is_cancelled = 0
                AND acc.root_type = 'Income'
            GROUP BY DATE_FORMAT(gle.posting_date, '%%Y-%%m')
            ORDER BY period
        """, (self.company, fy_start, fy_end), as_dict=True)
        
        monthly_list = [{"period": r["period"], "amount": float(r["amount"])} for r in monthly_income]
        
        # Categorize income types
        operating_income = sum(float(i.get('amount') or 0) for i in income_list 
                              if 'sales' in i.get('account_name', '').lower() or 
                                 'revenue' in i.get('account_name', '').lower() or
                                 'service' in i.get('account_name', '').lower())
        
        other_income = sum(float(i.get('amount') or 0) for i in income_list 
                          if 'interest' in i.get('account_name', '').lower() or
                             'dividend' in i.get('account_name', '').lower() or
                             'other' in i.get('account_name', '').lower() or
                             'gain' in i.get('account_name', '').lower())
        
        return {
            "by_account": income_list[:20],
            "monthly_trend": monthly_list,
            "operating_income": operating_income,
            "other_income": other_income,
            "total_income": sum(i['amount'] for i in income_list)
        }
    
    def _analyze_expenses(self) -> Dict[str, Any]:
        """Analyze expenses with allowable/non-allowable categorization"""
        fy_start = self.fiscal_year["year_start_date"]
        fy_end = self.fiscal_year["year_end_date"]
        
        # Expenses by account with classification
        expenses = frappe.db.sql("""
            SELECT 
                acc.account_name,
                acc.parent_account,
                acc.account_type,
                COALESCE(SUM(debit - credit), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.is_cancelled = 0
                AND acc.root_type = 'Expense'
            GROUP BY acc.account_name, acc.parent_account, acc.account_type
            HAVING amount > 0
            ORDER BY amount DESC
        """, (self.company, fy_start, fy_end), as_dict=True)
        
        # Classify each expense
        allowable_list = []
        non_allowable_list = []
        
        non_allowable_patterns = ['entertainment', 'donation', 'penalty', 'fine', 'personal', 'gift', 'political']
        
        for exp in expenses:
            account_name = exp.get('account_name', '').lower()
            is_non_allowable = any(p in account_name for p in non_allowable_patterns)
            
            expense_item = {
                "account_name": exp['account_name'],
                "amount": float(exp['amount']),
                "account_type": exp.get('account_type') or 'Expense'
            }
            
            if is_non_allowable:
                expense_item["reason"] = self._get_disallowance_reason(account_name)
                non_allowable_list.append(expense_item)
            else:
                allowable_list.append(expense_item)
        
        # Monthly expense trend
        monthly_expenses = frappe.db.sql("""
            SELECT 
                DATE_FORMAT(gle.posting_date, '%%Y-%%m') as period,
                COALESCE(SUM(debit - credit), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.is_cancelled = 0
                AND acc.root_type = 'Expense'
            GROUP BY DATE_FORMAT(gle.posting_date, '%%Y-%%m')
            ORDER BY period
        """, (self.company, fy_start, fy_end), as_dict=True)
        
        monthly_list = [{"period": r["period"], "amount": float(r["amount"])} for r in monthly_expenses]
        
        return {
            "allowable_expenses": allowable_list[:30],
            "non_allowable_expenses": non_allowable_list,
            "total_allowable": sum(e['amount'] for e in allowable_list),
            "total_non_allowable": sum(e['amount'] for e in non_allowable_list),
            "monthly_trend": monthly_list,
            "add_back_amount": sum(e['amount'] for e in non_allowable_list)
        }
    
    def _get_disallowance_reason(self, account_name: str) -> str:
        """Get reason for expense disallowance"""
        if 'entertainment' in account_name:
            return "Entertainment expenses are non-deductible (Section 16(2)(a) ITA)"
        elif 'donation' in account_name:
            return "Donations are non-deductible unless to approved institutions"
        elif 'penalty' in account_name or 'fine' in account_name:
            return "Penalties and fines are non-deductible (Section 16(2)(e) ITA)"
        elif 'personal' in account_name:
            return "Personal expenses are non-deductible (Section 16(2)(b) ITA)"
        elif 'gift' in account_name:
            return "Gifts are non-deductible unless for business promotion"
        elif 'political' in account_name:
            return "Political contributions are non-deductible"
        return "Non-deductible expense per Kenya Income Tax Act"
    
    def _calculate_capital_allowances(self) -> Dict[str, Any]:
        """Calculate capital allowances from Asset doctype with Kenya rates"""
        fy_start = self.fiscal_year["year_start_date"]
        fy_end = self.fiscal_year["year_end_date"]
        
        # Get assets with their categories
        assets = frappe.db.sql("""
            SELECT 
                a.name,
                a.asset_name,
                a.asset_category,
                a.gross_purchase_amount,
                a.purchase_date,
                a.opening_accumulated_depreciation,
                a.status,
                a.location
            FROM `tabAsset` a
            WHERE a.company = %s
                AND a.docstatus = 1
                AND a.status NOT IN ('Scrapped', 'Sold')
        """, (self.company,), as_dict=True)
        
        # Get current year depreciation for each asset
        asset_depreciation = frappe.db.sql("""
            SELECT 
                a.name as asset,
                COALESCE(SUM(ds.depreciation_amount), 0) as depreciation
            FROM `tabAsset` a
            LEFT JOIN `tabDepreciation Schedule` ds ON ds.parent = a.name
            WHERE a.company = %s
                AND a.docstatus = 1
                AND ds.schedule_date BETWEEN %s AND %s
            GROUP BY a.name
        """, (self.company, fy_start, fy_end), as_dict=True)
        
        depreciation_map = {d['asset']: float(d['depreciation']) for d in asset_depreciation}
        
        # Calculate allowances by category
        allowances_by_category = {}
        total_wear_tear = 0
        total_investment_deduction = 0
        asset_details = []
        
        for asset in assets:
            category = asset.get('asset_category') or 'Uncategorized'
            gross_amount = float(asset.get('gross_purchase_amount') or 0)
            purchase_date = asset.get('purchase_date')
            current_depreciation = depreciation_map.get(asset['name'], 0)
            
            # Determine wear and tear class based on category name
            wear_tear_rate = self._get_wear_tear_rate(category)
            wear_tear_class = self._get_wear_tear_class(category)
            
            # Calculate wear and tear allowance (using book depreciation as proxy)
            wear_tear = current_depreciation
            
            # Check if eligible for investment deduction (first year, qualifying asset)
            is_first_year = purchase_date and purchase_date >= fy_start
            # Investment deduction only for manufacturing/industrial assets
            is_qualifying = 'machine' in category.lower() or 'plant' in category.lower() or 'equipment' in category.lower()
            investment_deduction = gross_amount * INVESTMENT_DEDUCTION_RATE if (is_first_year and is_qualifying) else 0
            
            # Total allowance for this asset
            total_allowance = wear_tear + investment_deduction
            
            total_wear_tear += wear_tear
            total_investment_deduction += investment_deduction
            
            if category not in allowances_by_category:
                allowances_by_category[category] = {
                    "asset_count": 0,
                    "gross_value": 0,
                    "wear_tear": 0,
                    "investment_deduction": 0,
                    "total_allowance": 0,
                    "wear_tear_class": wear_tear_class,
                    "wear_tear_rate": wear_tear_rate * 100
                }
            
            allowances_by_category[category]["asset_count"] += 1
            allowances_by_category[category]["gross_value"] += gross_amount
            allowances_by_category[category]["wear_tear"] += wear_tear
            allowances_by_category[category]["investment_deduction"] += investment_deduction
            allowances_by_category[category]["total_allowance"] += total_allowance
            
            asset_details.append({
                "name": asset['name'],
                "asset_name": asset['asset_name'],
                "category": category,
                "gross_amount": gross_amount,
                "wear_tear_class": wear_tear_class,
                "wear_tear_rate": wear_tear_rate * 100,
                "wear_tear_allowance": wear_tear,
                "investment_deduction": investment_deduction,
                "total_allowance": total_allowance,
                "is_first_year": is_first_year,
                "status": asset.get('status', '')
            })
        
        return {
            "by_category": [
                {"category": k, **v} for k, v in allowances_by_category.items()
            ],
            "asset_details": asset_details[:50],
            "total_wear_tear": total_wear_tear,
            "total_investment_deduction": total_investment_deduction,
            "total_allowances": total_wear_tear + total_investment_deduction,
            "asset_count": len(assets),
            "rates_reference": {
                "Class I (Heavy Equipment)": "37.5%",
                "Class II (Vehicles, Aircraft)": "30%",
                "Class III (Computers, Machinery)": "25%",
                "Class IV (Buildings, Furniture)": "12.5%",
                "Investment Deduction (Manufacturing)": "100% first year"
            }
        }
    
    def _get_wear_tear_rate(self, category: str) -> float:
        """Determine wear and tear rate based on asset category"""
        category_lower = category.lower()
        
        if any(k in category_lower for k in ['heavy', 'earth', 'excavator', 'bulldozer']):
            return 0.375  # Class I
        elif any(k in category_lower for k in ['vehicle', 'car', 'truck', 'aircraft', 'motor']):
            return 0.30  # Class II
        elif any(k in category_lower for k in ['computer', 'laptop', 'server', 'machine', 'equipment', 'plant']):
            return 0.25  # Class III
        elif any(k in category_lower for k in ['building', 'furniture', 'fixture', 'office']):
            return 0.125  # Class IV
        else:
            return 0.25  # Default to Class III
    
    def _get_wear_tear_class(self, category: str) -> str:
        """Get wear and tear class name"""
        category_lower = category.lower()
        
        if any(k in category_lower for k in ['heavy', 'earth', 'excavator', 'bulldozer']):
            return "Class I"
        elif any(k in category_lower for k in ['vehicle', 'car', 'truck', 'aircraft', 'motor']):
            return "Class II"
        elif any(k in category_lower for k in ['computer', 'laptop', 'server', 'machine', 'equipment', 'plant']):
            return "Class III"
        elif any(k in category_lower for k in ['building', 'furniture', 'fixture', 'office']):
            return "Class IV"
        else:
            return "Class III"
    
    def _generate_kra_schedule(self, overview: Dict) -> Dict[str, Any]:
        """Generate KRA quarterly instalment schedule per Section 12A ITA"""
        fy_start = self.fiscal_year["year_start_date"]
        fy_end = self.fiscal_year["year_end_date"]
        
        # Estimated annual tax from overview
        annual_tax = overview.get("tax_liability", 0)
        
        # KRA instalment due dates (20th day of 4th, 6th, 9th, 12th month from fiscal year start)
        instalment_schedule = [
            {"month_offset": 3, "label": "1st Instalment (4th Month)"},
            {"month_offset": 5, "label": "2nd Instalment (6th Month)"},
            {"month_offset": 8, "label": "3rd Instalment (9th Month)"},
            {"month_offset": 11, "label": "4th Instalment (12th Month)"}
        ]
        
        instalments = []
        today = datetime.now().date()
        
        for i, sched in enumerate(instalment_schedule):
            # Due by 20th of the respective month
            due_date = fy_start + relativedelta(months=sched["month_offset"])
            due_date = due_date.replace(day=20)
            
            # Each instalment is 25% of estimated tax
            instalment_amount = annual_tax / 4
            
            # Calculate period for checking payments
            period_start = fy_start + relativedelta(months=i*3)
            period_end = period_start + relativedelta(months=3) - timedelta(days=1)
            
            # Check payments made in this period
            paid_amount = self._get_instalment_paid_for_period(period_start, period_end)
            
            # Determine status
            if paid_amount >= instalment_amount * 0.95:  # Allow 5% tolerance
                status = "Paid"
                status_color = "green"
            elif today > due_date:
                status = "Overdue"
                status_color = "red"
            elif today >= due_date - timedelta(days=14):
                status = "Due Soon"
                status_color = "amber"
            else:
                status = "Upcoming"
                status_color = "gray"
            
            instalments.append({
                "quarter": i + 1,
                "label": sched["label"],
                "due_date": due_date.isoformat(),
                "due_date_formatted": due_date.strftime("%d %b %Y"),
                "amount_due": instalment_amount,
                "amount_paid": paid_amount,
                "balance": max(0, instalment_amount - paid_amount),
                "status": status,
                "status_color": status_color
            })
        
        # Calculate totals
        total_due = sum(i["amount_due"] for i in instalments)
        total_paid = sum(i["amount_paid"] for i in instalments)
        total_balance = sum(i["balance"] for i in instalments)
        overdue_count = sum(1 for i in instalments if i["status"] == "Overdue")
        
        # Next payment info
        next_payment = None
        for inst in instalments:
            if inst["status"] in ["Upcoming", "Due Soon", "Overdue"]:
                next_payment = inst
                break
        
        # Compliance status
        if overdue_count > 0:
            compliance_status = "Non-Compliant"
            compliance_color = "red"
        elif total_balance == 0:
            compliance_status = "Fully Compliant"
            compliance_color = "green"
        else:
            compliance_status = "On Track"
            compliance_color = "blue"
        
        return {
            "instalments": instalments,
            "total_annual_tax": annual_tax,
            "total_due": total_due,
            "total_paid": total_paid,
            "total_balance": total_balance,
            "next_payment": next_payment,
            "compliance_status": compliance_status,
            "compliance_color": compliance_color,
            "overdue_count": overdue_count,
            "note": "Instalments are due by 20th of the 4th, 6th, 9th and 12th month of the accounting period (Section 12A ITA)"
        }
    
    def _get_instalment_paid_for_period(self, start_date, end_date) -> float:
        """Get tax instalment payments made in a period"""
        result = frappe.db.sql("""
            SELECT COALESCE(SUM(debit), 0) as total
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.is_cancelled = 0
                AND (
                    LOWER(acc.account_name) LIKE '%%corporate tax%%'
                    OR LOWER(acc.account_name) LIKE '%%income tax%%'
                    OR LOWER(acc.account_name) LIKE '%%kra%%'
                )
                AND acc.root_type = 'Liability'
        """, (self.company, start_date, end_date), as_dict=True)[0]
        
        return float(result.get('total') or 0)
    
    def _analyze_wht(self) -> Dict[str, Any]:
        """Analyze Withholding Tax (WHT) position per Kenya WHT regulations"""
        fy_start = self.fiscal_year["year_start_date"]
        fy_end = self.fiscal_year["year_end_date"]
        
        # WHT deducted on supplier payments (we are the payer/withholder)
        wht_deducted = frappe.db.sql("""
            SELECT 
                pi.supplier,
                pi.supplier_name,
                SUM(pit.tax_amount) as wht_amount,
                COUNT(DISTINCT pi.name) as invoice_count
            FROM `tabPurchase Invoice` pi
            JOIN `tabPurchase Taxes and Charges` pit ON pit.parent = pi.name
            WHERE pi.company = %s
                AND pi.posting_date BETWEEN %s AND %s
                AND pi.docstatus = 1
                AND pit.add_deduct_tax = 'Deduct'
                AND (
                    LOWER(pit.account_head) LIKE '%%withholding%%'
                    OR LOWER(pit.account_head) LIKE '%%wht%%'
                )
            GROUP BY pi.supplier, pi.supplier_name
            ORDER BY wht_amount DESC
        """, (self.company, fy_start, fy_end), as_dict=True)
        
        # If no WHT from taxes table, check GL directly
        if not wht_deducted:
            wht_deducted = frappe.db.sql("""
                SELECT 
                    gle.party as supplier,
                    gle.party as supplier_name,
                    COALESCE(SUM(gle.credit), 0) as wht_amount,
                    COUNT(DISTINCT gle.voucher_no) as invoice_count
                FROM `tabGL Entry` gle
                JOIN `tabAccount` acc ON gle.account = acc.name
                WHERE gle.company = %s
                    AND gle.posting_date BETWEEN %s AND %s
                    AND gle.is_cancelled = 0
                    AND (
                        LOWER(acc.account_name) LIKE '%%withholding%%'
                        OR LOWER(acc.account_name) LIKE '%%wht%%'
                    )
                    AND gle.party_type = 'Supplier'
                GROUP BY gle.party
                ORDER BY wht_amount DESC
            """, (self.company, fy_start, fy_end), as_dict=True)
        
        # WHT suffered on our income (we are the payee)
        wht_suffered = frappe.db.sql("""
            SELECT COALESCE(SUM(debit), 0) as total
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.is_cancelled = 0
                AND (
                    LOWER(acc.account_name) LIKE '%%withholding%%receivable%%'
                    OR LOWER(acc.account_name) LIKE '%%wht%%receivable%%'
                    OR LOWER(acc.account_name) LIKE '%%wht%%asset%%'
                )
        """, (self.company, fy_start, fy_end), as_dict=True)[0]
        
        # Format supplier list
        supplier_list = [
            {
                "supplier": w['supplier'],
                "supplier_name": w['supplier_name'],
                "wht_amount": float(w['wht_amount'] or 0),
                "invoice_count": w['invoice_count']
            }
            for w in wht_deducted
        ]
        
        total_deducted = sum(w['wht_amount'] for w in supplier_list)
        total_suffered = float(wht_suffered.get('total') or 0)
        
        # Monthly WHT trend
        monthly_wht = frappe.db.sql("""
            SELECT 
                DATE_FORMAT(gle.posting_date, '%%Y-%%m') as period,
                COALESCE(SUM(gle.credit), 0) as amount
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.is_cancelled = 0
                AND (
                    LOWER(acc.account_name) LIKE '%%withholding%%'
                    OR LOWER(acc.account_name) LIKE '%%wht%%'
                )
                AND acc.root_type = 'Liability'
            GROUP BY DATE_FORMAT(gle.posting_date, '%%Y-%%m')
            ORDER BY period
        """, (self.company, fy_start, fy_end), as_dict=True)
        
        monthly_list = [{"period": r["period"], "amount": float(r["amount"])} for r in monthly_wht]
        
        # WHT liability (amount to remit to KRA)
        wht_liability = frappe.db.sql("""
            SELECT COALESCE(SUM(credit - debit), 0) as balance
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.company = %s
                AND gle.posting_date <= %s
                AND gle.is_cancelled = 0
                AND (
                    LOWER(acc.account_name) LIKE '%%withholding%%'
                    OR LOWER(acc.account_name) LIKE '%%wht%%'
                )
                AND acc.root_type = 'Liability'
        """, (self.company, fy_end), as_dict=True)[0]
        
        return {
            "wht_deducted_by_supplier": supplier_list[:20],
            "total_wht_deducted": total_deducted,
            "total_wht_suffered": total_suffered,
            "wht_liability_balance": float(wht_liability.get('balance') or 0),
            "net_wht_position": total_suffered - total_deducted,
            "monthly_trend": monthly_list,
            "wht_rates": {
                "Dividends (Resident)": {"rate": "5%", "section": "Section 35(1)(a)"},
                "Dividends (Non-Resident)": {"rate": "15%", "section": "Section 35(1)(b)"},
                "Interest": {"rate": "15%", "section": "Section 35(1)(c)"},
                "Royalties": {"rate": "5%", "section": "Section 35(1)(d)"},
                "Management/Professional Fees": {"rate": "5%", "section": "Section 35(1)(e)"},
                "Contractual Fees": {"rate": "3%", "section": "Section 35(1)(f)"},
                "Rent (Non-Resident)": {"rate": "30%", "section": "Section 35(1)(g)"}
            },
            "remittance_note": "WHT must be remitted to KRA by 20th of the following month"
        }
    
    def _generate_tax_forecast(self, overview: Dict) -> Dict[str, Any]:
        """Generate tax liability forecasts"""
        today = datetime.now().date()
        fy_start = self.fiscal_year["year_start_date"]
        fy_end = self.fiscal_year["year_end_date"]
        
        # Days elapsed in fiscal year
        days_elapsed = (today - fy_start).days
        total_days = (fy_end - fy_start).days + 1
        progress_pct = days_elapsed / total_days if total_days > 0 else 0
        
        # Project full year based on YTD (simple linear projection)
        if progress_pct > 0.1:  # At least 10% of year elapsed
            projected_revenue = overview["total_revenue"] / progress_pct
            projected_expenses = overview["total_expenses"] / progress_pct
            projected_taxable_income = max(0, (overview["taxable_income"] / progress_pct))
            projected_tax = projected_taxable_income * CORPORATE_TAX_RATE
        else:
            projected_revenue = overview["total_revenue"] * 12  # Assume monthly data
            projected_expenses = overview["total_expenses"] * 12
            projected_taxable_income = overview["taxable_income"] * 12
            projected_tax = overview["tax_liability"] * 12
        
        # Variance from current estimate
        current_estimate = overview["tax_liability"]
        variance = projected_tax - current_estimate
        variance_pct = (variance / current_estimate * 100) if current_estimate > 0 else 0
        
        # Monthly projections for remaining months
        months_remaining = []
        current_month = today.replace(day=1)
        monthly_tax = projected_tax / 12
        
        while current_month <= fy_end:
            months_remaining.append({
                "month": current_month.strftime("%b %Y"),
                "projected_revenue": projected_revenue / 12,
                "projected_expense": projected_expenses / 12,
                "projected_tax": monthly_tax
            })
            current_month = current_month + relativedelta(months=1)
        
        # Tax savings potential
        savings_potential = self._calculate_savings_potential(overview)
        
        return {
            "ytd_progress_pct": round(progress_pct * 100, 1),
            "days_remaining": max(0, total_days - days_elapsed),
            "ytd_tax": overview["tax_liability"],
            "projected_annual_revenue": projected_revenue,
            "projected_annual_expenses": projected_expenses,
            "projected_taxable_income": projected_taxable_income,
            "projected_annual_tax": projected_tax,
            "variance_from_ytd": variance,
            "variance_pct": round(variance_pct, 1),
            "monthly_projections": months_remaining[-6:] if months_remaining else [],
            "tax_savings_potential": savings_potential
        }
    
    def _calculate_savings_potential(self, overview: Dict) -> Dict[str, Any]:
        """Calculate potential tax savings opportunities"""
        savings = []
        
        # Check if capital allowances are being maximized
        capital_allowances = overview.get("capital_allowances", 0)
        total_expenses = overview.get("total_expenses", 1)
        
        if capital_allowances < total_expenses * 0.05:
            potential_saving = total_expenses * 0.05 * CORPORATE_TAX_RATE
            savings.append({
                "opportunity": "Capital Allowances Optimization",
                "description": "Consider investing in qualifying assets (machinery, equipment) to claim wear & tear allowances",
                "potential_saving": potential_saving,
                "action": "Review asset acquisition timing to maximize capital allowances"
            })
        
        # Check for high non-allowable expenses
        non_allowable = overview.get("non_allowable_expenses", 0)
        if non_allowable > total_expenses * 0.05:
            potential_saving = non_allowable * CORPORATE_TAX_RATE * 0.5  # Assume 50% could be restructured
            savings.append({
                "opportunity": "Expense Restructuring",
                "description": "Review non-allowable expenses for potential reclassification to deductible categories",
                "potential_saving": potential_saving,
                "action": "Restructure entertainment as staff welfare, donations to approved institutions"
            })
        
        # Investment deduction opportunity
        if capital_allowances == 0:
            potential_saving = overview.get("tax_liability", 0) * 0.15
            savings.append({
                "opportunity": "Investment Deduction (100%)",
                "description": "Manufacturing investments qualify for 100% first-year deduction",
                "potential_saving": potential_saving,
                "action": "Plan capital investments in manufacturing plant and machinery"
            })
        
        total_potential = sum(s["potential_saving"] for s in savings)
        
        return {
            "opportunities": savings,
            "total_potential_saving": total_potential,
            "effective_rate_after_savings": max(0, overview.get("effective_tax_rate", 30) - (total_potential / max(1, overview.get("total_revenue", 1)) * 100))
        }
    
    def _calculate_yoy_variance(self) -> Dict[str, Any]:
        """Calculate year-over-year tax variance"""
        current_fy = self.fiscal_year
        
        # Get previous fiscal year
        prev_fy = frappe.db.sql("""
            SELECT name, year_start_date, year_end_date
            FROM `tabFiscal Year`
            WHERE year_end_date < %s
            ORDER BY year_end_date DESC
            LIMIT 1
        """, (current_fy["year_start_date"],), as_dict=True)
        
        if prev_fy:
            prev_fy = prev_fy[0]
            prev_fy_start = prev_fy["year_start_date"]
            prev_fy_end = prev_fy["year_end_date"]
            prev_fy_name = prev_fy["name"]
        else:
            # Fallback to previous calendar year
            prev_fy_start = current_fy["year_start_date"] - relativedelta(years=1)
            prev_fy_end = current_fy["year_end_date"] - relativedelta(years=1)
            prev_fy_name = f"{prev_fy_start.year}"
        
        # Current year metrics
        current_revenue = self._get_revenue_for_period(current_fy["year_start_date"], current_fy["year_end_date"])
        current_expenses = self._get_expenses_for_period(current_fy["year_start_date"], current_fy["year_end_date"])
        current_taxable = max(0, current_revenue - current_expenses)
        current_tax = current_taxable * CORPORATE_TAX_RATE
        
        # Previous year metrics
        prev_revenue = self._get_revenue_for_period(prev_fy_start, prev_fy_end)
        prev_expenses = self._get_expenses_for_period(prev_fy_start, prev_fy_end)
        prev_taxable = max(0, prev_revenue - prev_expenses)
        prev_tax = prev_taxable * CORPORATE_TAX_RATE
        
        # Calculate variances
        def calc_variance(current, previous):
            if previous == 0:
                return 100 if current > 0 else 0
            return round(((current - previous) / previous) * 100, 1)
        
        return {
            "current_year": {
                "fiscal_year": current_fy["name"],
                "revenue": current_revenue,
                "expenses": current_expenses,
                "taxable_income": current_taxable,
                "tax_liability": current_tax
            },
            "previous_year": {
                "fiscal_year": prev_fy_name,
                "revenue": prev_revenue,
                "expenses": prev_expenses,
                "taxable_income": prev_taxable,
                "tax_liability": prev_tax
            },
            "variance": {
                "revenue_change": current_revenue - prev_revenue,
                "revenue_pct": calc_variance(current_revenue, prev_revenue),
                "expenses_change": current_expenses - prev_expenses,
                "expenses_pct": calc_variance(current_expenses, prev_expenses),
                "taxable_income_change": current_taxable - prev_taxable,
                "taxable_income_pct": calc_variance(current_taxable, prev_taxable),
                "tax_change": current_tax - prev_tax,
                "tax_liability_pct": calc_variance(current_tax, prev_tax)
            }
        }
    
    def _get_revenue_for_period(self, start_date, end_date) -> float:
        """Get total revenue for a period"""
        result = frappe.db.sql("""
            SELECT COALESCE(SUM(credit - debit), 0) as total
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.is_cancelled = 0
                AND acc.root_type = 'Income'
        """, (self.company, start_date, end_date), as_dict=True)[0]
        return float(result.get('total') or 0)
    
    def _get_expenses_for_period(self, start_date, end_date) -> float:
        """Get total expenses for a period"""
        result = frappe.db.sql("""
            SELECT COALESCE(SUM(debit - credit), 0) as total
            FROM `tabGL Entry` gle
            JOIN `tabAccount` acc ON gle.account = acc.name
            WHERE gle.company = %s
                AND gle.posting_date BETWEEN %s AND %s
                AND gle.is_cancelled = 0
                AND acc.root_type = 'Expense'
        """, (self.company, start_date, end_date), as_dict=True)[0]
        return float(result.get('total') or 0)
    
    def _generate_optimization_insights(self, overview: Dict, expense_analysis: Dict, capital_allowances: Dict) -> List[Dict[str, Any]]:
        """Generate AI-powered tax optimization insights"""
        insights = []
        
        # Effective tax rate analysis
        effective_rate = overview.get("effective_tax_rate", 0)
        if effective_rate > 30:
            insights.append({
                "type": "warning",
                "icon": "alert-triangle",
                "title": "High Effective Tax Rate",
                "description": f"Your effective tax rate of {effective_rate}% exceeds the statutory 30%. This may indicate missed deductions or capital allowances.",
                "recommendation": "Review expense classifications and ensure all allowable deductions are claimed",
                "priority": "high"
            })
        elif effective_rate > 0 and effective_rate < 15:
            insights.append({
                "type": "success",
                "icon": "check-circle",
                "title": "Tax Efficient Operations",
                "description": f"Your effective tax rate of {effective_rate}% indicates excellent tax planning.",
                "recommendation": "Continue current tax planning strategies",
                "priority": "low"
            })
        
        # Non-allowable expenses alert
        total_expenses = overview.get("total_expenses", 1)
        non_allowable = overview.get("non_allowable_expenses", 0)
        non_allowable_ratio = (non_allowable / total_expenses * 100) if total_expenses > 0 else 0
        
        if non_allowable_ratio > 10:
            insights.append({
                "type": "warning",
                "icon": "alert-circle",
                "title": "High Non-Allowable Expenses",
                "description": f"{non_allowable_ratio:.1f}% of expenses (KES {non_allowable:,.0f}) are non-deductible, increasing your tax burden.",
                "recommendation": "Restructure entertainment expenses as staff welfare; route donations through approved charitable institutions",
                "priority": "medium"
            })
        
        # Capital allowances opportunity
        ca_total = capital_allowances.get("total_allowances", 0)
        if ca_total < total_expenses * 0.03:
            insights.append({
                "type": "info",
                "icon": "info",
                "title": "Capital Allowances Opportunity",
                "description": "Low capital allowances claimed relative to your expense base. Asset investments could reduce tax liability.",
                "recommendation": "Consider timing asset purchases before year-end to claim immediate wear & tear allowances",
                "priority": "medium"
            })
        
        # Investment deduction reminder
        first_year_assets = [a for a in capital_allowances.get("asset_details", []) if a.get("is_first_year")]
        if first_year_assets:
            total_investment = sum(a.get("gross_amount", 0) for a in first_year_assets)
            insights.append({
                "type": "success",
                "icon": "trending-up",
                "title": "Investment Deduction Available",
                "description": f"KES {total_investment:,.0f} in new assets qualify for investment deduction consideration.",
                "recommendation": "Ensure manufacturing/industrial assets are filed for 100% investment deduction",
                "priority": "high"
            })
        
        # KRA instalment reminder
        if overview.get("net_tax_position", 0) > 0:
            balance = overview["net_tax_position"]
            insights.append({
                "type": "info",
                "icon": "calendar",
                "title": "Tax Balance Pending",
                "description": f"KES {balance:,.0f} corporate tax balance for the year. Ensure quarterly instalments are up to date.",
                "recommendation": "Review KRA instalment schedule and make timely payments to avoid penalties",
                "priority": "medium"
            })
        
        # Year-end planning
        today = datetime.now().date()
        fy_end = self.fiscal_year["year_end_date"]
        days_to_end = (fy_end - today).days
        
        if 0 < days_to_end <= 60:
            insights.append({
                "type": "warning",
                "icon": "clock",
                "title": "Year-End Tax Planning",
                "description": f"Only {days_to_end} days remaining in the fiscal year. Time-sensitive tax planning actions needed.",
                "recommendation": "Accelerate allowable expenses; defer income where possible; complete asset acquisitions",
                "priority": "critical"
            })
        
        return insights


def run_tax_intelligence(refresh: bool = False) -> Dict[str, Any]:
    """Run tax intelligence analysis"""
    model = TaxIntelligence()
    if refresh:
        return model.train()
    return model.predict()
