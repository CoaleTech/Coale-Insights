from __future__ import annotations
# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""
Cash flow forecasting functions for Strategic Finance Intelligence.
Includes 90-day forecast, 13-week forecast, and cashflow scenario generation.
"""

import frappe
from datetime import datetime, timedelta
from typing import Dict, Any, List, TYPE_CHECKING

from frappe.query_builder import Case, DocType
from frappe.query_builder.functions import Coalesce, Count, Sum

if TYPE_CHECKING:
    import numpy as np


from .data import (
    get_cash_balance,
    get_historical_cash_transactions,
    get_ar_collections_by_week,
    get_ap_payments_by_week,
    get_payroll_for_week,
    estimate_other_receipts,
    estimate_operating_expenses,
    get_scheduled_taxes,
    get_original_forecast_for_week,
    get_week_label,
)
from .analysis import detect_payroll_pattern, generate_variance_analysis


def forecast_cash_flow(intelligence) -> Dict[str, Any]:
    """Generate 90-day cash flow forecast with scenarios"""
    import numpy as np
    current_cash = get_cash_balance(intelligence)

    # Get historical daily cash flows (last 90 days). The legacy SQL used
    # DATE_SUB(CURDATE(), INTERVAL 90 DAY); we resolve that on the Python
    # side so PyPika can emit the bound parameter directly.
    ninety_days_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

    gle = DocType("GL Entry")
    acc = DocType("Account")
    historical = (
        frappe.qb.from_(gle)
        .join(acc)
        .on(gle.account == acc.name)
        .select(
            gle.posting_date.as_("date"),
            Sum(
                Case()
                .when(acc.account_type.isin(["Cash", "Bank"]), gle.debit - gle.credit)
                .else_(0)
            ).as_("net_flow"),
        )
        .where(gle.posting_date >= ninety_days_ago)
        .where(gle.company == intelligence.company)
        .where(gle.is_cancelled == 0)
        .groupby(gle.posting_date)
        .orderby(gle.posting_date)
        .run(as_dict=True)
    )

    # Calculate average daily flow
    if historical:
        daily_flows = [float(h.net_flow or 0) for h in historical]
        avg_daily_flow = float(np.mean(daily_flows)) if daily_flows else 0
        std_daily_flow = float(np.std(daily_flows)) if len(daily_flows) > 1 else abs(avg_daily_flow) * 0.3
    else:
        avg_daily_flow = 0
        std_daily_flow = 0

    # Expected receivables (outstanding invoices)
    si = DocType("Sales Invoice")
    expected_inflows_rows = (
        frappe.qb.from_(si)
        .select(
            Coalesce(Sum(si.outstanding_amount), 0).as_("total"),
            Count("*").as_("count"),
        )
        .where(si.company == intelligence.company)
        .where(si.docstatus == 1)
        .where(si.outstanding_amount > 0)
        .run(as_dict=True)
    )
    expected_inflows = expected_inflows_rows[0] if expected_inflows_rows else {"total": 0, "count": 0}

    # Expected payables (outstanding bills)
    pi = DocType("Purchase Invoice")
    expected_outflows_rows = (
        frappe.qb.from_(pi)
        .select(
            Coalesce(Sum(pi.outstanding_amount), 0).as_("total"),
            Count("*").as_("count"),
        )
        .where(pi.company == intelligence.company)
        .where(pi.docstatus == 1)
        .where(pi.outstanding_amount > 0)
        .run(as_dict=True)
    )
    expected_outflows = expected_outflows_rows[0] if expected_outflows_rows else {"total": 0, "count": 0}

    # Generate 90-day forecast
    forecast_days = 90
    base_forecast = []
    optimistic_forecast = []
    pessimistic_forecast = []

    running_balance = current_cash
    optimistic_balance = current_cash
    pessimistic_balance = current_cash

    # Distribute expected receivables over 45 days (average collection)
    daily_ar_inflow = float(expected_inflows.total or 0) / 45
    # Distribute payables over 30 days
    daily_ap_outflow = float(expected_outflows.total or 0) / 30

    for day in range(1, forecast_days + 1):
        date = (datetime.now() + timedelta(days=day)).strftime('%Y-%m-%d')

        # Base case: average historical + AR/AP adjustments
        ar_adjustment = daily_ar_inflow if day <= 45 else 0
        ap_adjustment = daily_ap_outflow if day <= 30 else 0

        base_flow = avg_daily_flow + ar_adjustment - ap_adjustment
        running_balance += base_flow

        # Optimistic: +20% inflows
        opt_flow = base_flow * 1.2 if base_flow > 0 else base_flow * 0.8
        optimistic_balance += opt_flow

        # Pessimistic: -20% inflows, +20% outflows
        pess_flow = base_flow * 0.8 if base_flow > 0 else base_flow * 1.2
        pessimistic_balance += pess_flow

        base_forecast.append({
            "date": date,
            "day": day,
            "balance": round(running_balance, 2)
        })
        optimistic_forecast.append({
            "date": date,
            "day": day,
            "balance": round(optimistic_balance, 2)
        })
        pessimistic_forecast.append({
            "date": date,
            "day": day,
            "balance": round(pessimistic_balance, 2)
        })

    # Calculate runway for each scenario
    def calculate_runway(forecast):
        for i, f in enumerate(forecast):
            if f["balance"] <= 0:
                return i
        return 999  # More than forecast period

    base_runway = calculate_runway(base_forecast)
    opt_runway = calculate_runway(optimistic_forecast)
    pess_runway = calculate_runway(pessimistic_forecast)

    # Weekly summary
    weekly_summary = []
    for week in range(1, 14):  # 13 weeks
        week_start = (week - 1) * 7
        week_end = min(week * 7, 90)
        if week_start < len(base_forecast):
            weekly_summary.append({
                "week": week,
                "base_balance": base_forecast[min(week_end - 1, len(base_forecast) - 1)]["balance"],
                "optimistic_balance": optimistic_forecast[min(week_end - 1, len(optimistic_forecast) - 1)]["balance"],
                "pessimistic_balance": pessimistic_forecast[min(week_end - 1, len(pessimistic_forecast) - 1)]["balance"]
            })

    return {
        "current_cash": current_cash,
        "avg_daily_flow": round(avg_daily_flow, 2),
        "expected_ar_inflows": float(expected_inflows.total or 0),
        "expected_ap_outflows": float(expected_outflows.total or 0),
        "net_expected": float(expected_inflows.total or 0) - float(expected_outflows.total or 0),
        "base_forecast": base_forecast,
        "optimistic_forecast": optimistic_forecast,
        "pessimistic_forecast": pessimistic_forecast,
        "base_runway_days": base_runway,
        "optimistic_runway_days": opt_runway,
        "pessimistic_runway_days": pess_runway,
        "weekly_summary": weekly_summary,
        "end_of_period": {
            "base": base_forecast[-1]["balance"] if base_forecast else current_cash,
            "optimistic": optimistic_forecast[-1]["balance"] if optimistic_forecast else current_cash,
            "pessimistic": pessimistic_forecast[-1]["balance"] if pessimistic_forecast else current_cash
        }
    }


def generate_thirteen_week_forecast(intelligence, min_cash_threshold: float = 0) -> Dict[str, Any]:
    """
    Generate detailed 13-week rolling cash flow forecast with:
    - Categorized inflows/outflows (AR, AP, Payroll, Operating, Taxes)
    - Historical actuals for past weeks with variance tracking
    - Forecast for future weeks based on due dates
    - Threshold alerts for weeks below minimum cash
    - Auto-detected payroll patterns
    """
    today = datetime.now().date()

    # Calculate the start of the 13-week period (start of current week - 1 week for historical comparison)
    # Week starts on Monday
    days_since_monday = today.weekday()
    current_week_start = today - timedelta(days=days_since_monday)

    # Include 1 week of history for variance comparison
    period_start = current_week_start - timedelta(weeks=1)
    period_end = current_week_start + timedelta(weeks=13) - timedelta(days=1)

    # Get current cash balance
    current_cash = get_cash_balance(intelligence)

    # Auto-detect payroll pattern
    payroll_pattern = detect_payroll_pattern(intelligence)

    # Get threshold from Company settings or use provided value
    if min_cash_threshold <= 0:
        try:
            min_cash_threshold = frappe.db.get_value(
                "Company", intelligence.company, "custom_min_cash_threshold"
            ) or 0
        except Exception:
            # Field doesn't exist
            min_cash_threshold = 0

    # Get historical cash transactions for actuals (last 2 weeks)
    historical_transactions = get_historical_cash_transactions(
        intelligence, period_start, today
    )

    # Get expected AR inflows by due date
    ar_by_week = get_ar_collections_by_week(intelligence, current_week_start, period_end)

    # Get expected AP outflows by due date
    ap_by_week = get_ap_payments_by_week(intelligence, current_week_start, period_end)

    # Build week-by-week forecast
    weeks = []
    running_balance = current_cash

    # Calculate opening balance for the period
    # For historical weeks, we need to back-calculate from current balance
    historical_net_flow = sum(
        t.get('net_flow', 0) for t in historical_transactions.values()
    )
    opening_balance = current_cash - historical_net_flow

    for week_num in range(14):  # -1 (historical) to 12 (forecast) = 14 weeks total
        week_start = current_week_start + timedelta(weeks=week_num - 1)
        week_end = week_start + timedelta(days=6)
        week_key = week_start.strftime('%Y-%m-%d')

        is_historical = week_end < today
        is_current = week_start <= today <= week_end
        is_forecast = week_start > today

        # Determine if this week has actuals
        is_actual = is_historical or (is_current and today.weekday() >= 3)  # After Thursday, use actuals

        # Convert to native Python bools for JSON serialization
        is_historical = bool(is_historical)
        is_current = bool(is_current)
        is_forecast = bool(is_forecast)
        is_actual = bool(is_actual)

        if is_actual and week_key in historical_transactions:
            # Use actual transactions
            week_data = historical_transactions[week_key]
            inflows = week_data.get('inflows', {})
            outflows = week_data.get('outflows', {})
        else:
            # Use forecast based on due dates and patterns
            inflows = {
                'ar_collections': ar_by_week.get(week_key, {}).get('amount', 0),
                'other_receipts': estimate_other_receipts(intelligence, week_start),
                'total': 0
            }
            inflows['total'] = inflows['ar_collections'] + inflows['other_receipts']

            outflows = {
                'ap_payments': ap_by_week.get(week_key, {}).get('amount', 0),
                'payroll': get_payroll_for_week(intelligence, week_start, payroll_pattern),
                'operating_expenses': estimate_operating_expenses(intelligence, week_start),
                'taxes': get_scheduled_taxes(intelligence, week_start, week_end),
                'total': 0
            }
            outflows['total'] = (
                outflows['ap_payments'] +
                outflows['payroll'] +
                outflows['operating_expenses'] +
                outflows['taxes']
            )

        net_flow = inflows.get('total', 0) - outflows.get('total', 0)

        # Calculate opening balance for this week
        if week_num == 0:
            week_opening = opening_balance
        else:
            week_opening = weeks[-1]['closing_balance'] if weeks else opening_balance

        closing_balance = week_opening + net_flow

        # Check variance for historical weeks that also had forecasts
        variance = None
        if is_actual and not is_forecast:
            original_forecast = get_original_forecast_for_week(intelligence, week_key)
            if original_forecast:
                variance = {
                    'inflows': inflows.get('total', 0) - original_forecast.get('inflows', 0),
                    'outflows': outflows.get('total', 0) - original_forecast.get('outflows', 0),
                    'net': net_flow - original_forecast.get('net_flow', 0)
                }

        week_record = {
            'week_number': week_num,  # -1 = last week, 0 = current, 1-12 = future
            'week_start': str(week_start),
            'week_end': str(week_end),
            'week_label': get_week_label(intelligence, week_start, week_num),
            'is_actual': is_actual,
            'is_forecast': not is_actual,
            'is_current': is_current,
            'opening_balance': round(week_opening, 2),
            'inflows': {
                'ar_collections': round(inflows.get('ar_collections', 0), 2),
                'other_receipts': round(inflows.get('other_receipts', 0), 2),
                'total': round(inflows.get('total', 0), 2)
            },
            'outflows': {
                'ap_payments': round(outflows.get('ap_payments', 0), 2),
                'payroll': round(outflows.get('payroll', 0), 2),
                'operating_expenses': round(outflows.get('operating_expenses', 0), 2),
                'taxes': round(outflows.get('taxes', 0), 2),
                'total': round(outflows.get('total', 0), 2)
            },
            'net_flow': round(net_flow, 2),
            'closing_balance': round(closing_balance, 2),
            'below_threshold': bool(closing_balance < min_cash_threshold),
            'variance': variance
        }

        weeks.append(week_record)
        running_balance = closing_balance

    # Calculate summary statistics
    future_weeks = [w for w in weeks if w['is_forecast']]
    all_weeks = weeks[1:]  # Exclude historical week from summary

    total_inflows = sum(w['inflows']['total'] for w in future_weeks)
    total_outflows = sum(w['outflows']['total'] for w in future_weeks)
    ending_cash = weeks[-1]['closing_balance'] if weeks else current_cash

    min_balance_week = min(all_weeks, key=lambda w: w['closing_balance']) if all_weeks else None
    weeks_below_threshold = sum(1 for w in all_weeks if w['below_threshold'])

    # Generate scenario analysis for the 13-week forecast
    scenarios = generate_cashflow_scenarios(intelligence, weeks, current_cash, min_cash_threshold)

    # Generate variance analysis for historical weeks
    variance_analysis = generate_variance_analysis(intelligence, weeks)

    return {
        'opening_balance': round(opening_balance, 2),
        'current_cash': round(current_cash, 2),
        'min_cash_threshold': round(min_cash_threshold, 2),
        'currency': intelligence.base_currency,
        'generated_at': datetime.now().isoformat(),
        'cache_expires': (datetime.now() + timedelta(days=1)).isoformat(),
        'payroll_detection': payroll_pattern,
        'weeks': weeks,
        'scenarios': scenarios,
        'variance_analysis': variance_analysis,
        'summary': {
            'total_inflows': round(total_inflows, 2),
            'total_outflows': round(total_outflows, 2),
            'net_cash_flow': round(total_inflows - total_outflows, 2),
            'ending_cash': round(ending_cash, 2),
            'minimum_balance': round(min_balance_week['closing_balance'], 2) if min_balance_week else current_cash,
            'minimum_balance_week': min_balance_week['week_number'] if min_balance_week else 0,
            'minimum_balance_date': min_balance_week['week_start'] if min_balance_week else str(today),
            'weeks_below_threshold': weeks_below_threshold,
            'avg_weekly_inflow': round(total_inflows / len(future_weeks), 2) if future_weeks else 0,
            'avg_weekly_outflow': round(total_outflows / len(future_weeks), 2) if future_weeks else 0
        }
    }


def generate_cashflow_scenarios(intelligence, base_weeks: List[Dict], current_cash: float, threshold: float) -> Dict[str, Any]:
    """
    Generate what-if scenarios for 13-week cash flow forecast
    Scenarios: AR delay, AP acceleration, revenue drop, expense increase, etc.
    """
    forecast_weeks = [w for w in base_weeks if w.get('is_forecast')]
    if not forecast_weeks:
        return {'scenarios': [], 'quick_actions': []}

    base_ending = forecast_weeks[-1]['closing_balance'] if forecast_weeks else current_cash
    base_min = min(w['closing_balance'] for w in forecast_weeks) if forecast_weeks else current_cash

    # Calculate scenario impacts
    scenarios = []

    # Scenario 1: AR Collections Delayed 2 weeks
    ar_delayed = apply_scenario(intelligence, forecast_weeks, ar_delay_weeks=2)
    scenarios.append({
        'id': 'ar_delay_2w',
        'name': 'AR Collections Delayed 2 Weeks',
        'description': 'What if customer payments are delayed by 2 weeks?',
        'type': 'risk',
        'icon': 'clock',
        'ending_balance': ar_delayed['ending_balance'],
        'min_balance': ar_delayed['min_balance'],
        'impact': ar_delayed['ending_balance'] - base_ending,
        'weeks_below_threshold': ar_delayed['weeks_below_threshold'],
        'risk_level': 'high' if ar_delayed['min_balance'] < threshold else 'medium'
    })

    # Scenario 2: AR Collections Improved 20%
    ar_improved = apply_scenario(intelligence, forecast_weeks, ar_change_pct=20)
    scenarios.append({
        'id': 'ar_improve_20',
        'name': 'AR Collections +20%',
        'description': 'What if we improve collections by 20%?',
        'type': 'opportunity',
        'icon': 'trending-up',
        'ending_balance': ar_improved['ending_balance'],
        'min_balance': ar_improved['min_balance'],
        'impact': ar_improved['ending_balance'] - base_ending,
        'weeks_below_threshold': ar_improved['weeks_below_threshold'],
        'risk_level': 'low'
    })

    # Scenario 3: AP Payments Accelerated (paid early)
    ap_accelerated = apply_scenario(intelligence, forecast_weeks, ap_delay_weeks=-1)
    scenarios.append({
        'id': 'ap_accelerate',
        'name': 'AP Payments Accelerated',
        'description': 'What if we pay suppliers 1 week early for discounts?',
        'type': 'decision',
        'icon': 'fast-forward',
        'ending_balance': ap_accelerated['ending_balance'],
        'min_balance': ap_accelerated['min_balance'],
        'impact': ap_accelerated['ending_balance'] - base_ending,
        'weeks_below_threshold': ap_accelerated['weeks_below_threshold'],
        'risk_level': 'medium' if ap_accelerated['min_balance'] < threshold else 'low'
    })

    # Scenario 4: AP Payments Delayed 2 weeks
    ap_delayed = apply_scenario(intelligence, forecast_weeks, ap_delay_weeks=2)
    scenarios.append({
        'id': 'ap_delay_2w',
        'name': 'AP Payments Delayed 2 Weeks',
        'description': 'What if we negotiate extended payment terms?',
        'type': 'opportunity',
        'icon': 'pause',
        'ending_balance': ap_delayed['ending_balance'],
        'min_balance': ap_delayed['min_balance'],
        'impact': ap_delayed['ending_balance'] - base_ending,
        'weeks_below_threshold': ap_delayed['weeks_below_threshold'],
        'risk_level': 'low'
    })

    # Scenario 5: Revenue/Inflows Drop 30%
    revenue_drop = apply_scenario(intelligence, forecast_weeks, ar_change_pct=-30)
    scenarios.append({
        'id': 'revenue_drop_30',
        'name': 'Revenue Drop 30%',
        'description': 'Stress test: What if revenue drops 30%?',
        'type': 'risk',
        'icon': 'alert-triangle',
        'ending_balance': revenue_drop['ending_balance'],
        'min_balance': revenue_drop['min_balance'],
        'impact': revenue_drop['ending_balance'] - base_ending,
        'weeks_below_threshold': revenue_drop['weeks_below_threshold'],
        'risk_level': 'critical' if revenue_drop['min_balance'] < 0 else 'high'
    })

    # Scenario 6: Operating Expenses Increase 20%
    opex_increase = apply_scenario(intelligence, forecast_weeks, opex_change_pct=20)
    scenarios.append({
        'id': 'opex_increase_20',
        'name': 'Operating Expenses +20%',
        'description': 'What if operating costs increase 20%?',
        'type': 'risk',
        'icon': 'trending-up',
        'ending_balance': opex_increase['ending_balance'],
        'min_balance': opex_increase['min_balance'],
        'impact': opex_increase['ending_balance'] - base_ending,
        'weeks_below_threshold': opex_increase['weeks_below_threshold'],
        'risk_level': 'high' if opex_increase['min_balance'] < threshold else 'medium'
    })

    # Scenario 7: Best Case (AR +20%, AP delayed, OpEx -10%)
    best_case = apply_scenario(intelligence, forecast_weeks, ar_change_pct=20, ap_delay_weeks=1, opex_change_pct=-10)
    scenarios.append({
        'id': 'best_case',
        'name': 'Best Case Scenario',
        'description': 'Optimistic: Better collections, delayed AP, lower costs',
        'type': 'opportunity',
        'icon': 'sun',
        'ending_balance': best_case['ending_balance'],
        'min_balance': best_case['min_balance'],
        'impact': best_case['ending_balance'] - base_ending,
        'weeks_below_threshold': best_case['weeks_below_threshold'],
        'risk_level': 'low'
    })

    # Scenario 8: Worst Case (AR -30%, AR delayed, OpEx +20%)
    worst_case = apply_scenario(intelligence, forecast_weeks, ar_change_pct=-30, ar_delay_weeks=2, opex_change_pct=20)
    scenarios.append({
        'id': 'worst_case',
        'name': 'Worst Case Scenario',
        'description': 'Pessimistic: Poor collections, delayed payments, higher costs',
        'type': 'risk',
        'icon': 'cloud-rain',
        'ending_balance': worst_case['ending_balance'],
        'min_balance': worst_case['min_balance'],
        'impact': worst_case['ending_balance'] - base_ending,
        'weeks_below_threshold': worst_case['weeks_below_threshold'],
        'risk_level': 'critical' if worst_case['min_balance'] < 0 else 'high'
    })

    # Quick action recommendations based on scenarios
    quick_actions = []

    # Calculate impacts for recommendations
    ar_delayed_impact = ar_delayed['ending_balance'] - base_ending
    ap_delayed_impact = ap_delayed['ending_balance'] - base_ending

    if ar_delayed['min_balance'] < threshold:
        quick_actions.append({
            'action': 'Accelerate AR Collections',
            'priority': 'high',
            'potential_impact': abs(ar_delayed['min_balance'] - base_min),
            'description': 'Focus on collecting overdue invoices to avoid cash shortfall'
        })

    if ap_delayed_impact > 0 and base_min < threshold * 1.5:
        quick_actions.append({
            'action': 'Negotiate Extended Payment Terms',
            'priority': 'medium',
            'potential_impact': ap_delayed_impact,
            'description': 'Extend AP terms to improve cash position'
        })

    if worst_case['min_balance'] < 0:
        quick_actions.append({
            'action': 'Secure Credit Line',
            'priority': 'high',
            'potential_impact': abs(worst_case['min_balance']),
            'description': 'Consider establishing or increasing credit facility as backup'
        })

    return {
        'base_ending_balance': round(base_ending, 2),
        'base_min_balance': round(base_min, 2),
        'threshold': round(threshold, 2),
        'scenarios': scenarios,
        'quick_actions': quick_actions
    }


def apply_scenario(
    intelligence,
    base_weeks: List[Dict],
    ar_change_pct: float = 0,
    ar_delay_weeks: int = 0,
    ap_change_pct: float = 0,
    ap_delay_weeks: int = 0,
    opex_change_pct: float = 0,
    payroll_change_pct: float = 0
) -> Dict[str, Any]:
    """Apply scenario adjustments to forecast weeks and calculate results"""
    if not base_weeks:
        return {'ending_balance': 0, 'min_balance': 0, 'weeks_below_threshold': 0}

    adjusted_weeks = []
    running_balance = base_weeks[0]['opening_balance']

    for i, week in enumerate(base_weeks):
        # Get base values
        ar = week['inflows'].get('ar_collections', 0)
        other_receipts = week['inflows'].get('other_receipts', 0)
        ap = week['outflows'].get('ap_payments', 0)
        payroll = week['outflows'].get('payroll', 0)
        opex = week['outflows'].get('operating_expenses', 0)
        taxes = week['outflows'].get('taxes', 0)

        # Apply AR changes
        if ar_change_pct != 0:
            ar = ar * (1 + ar_change_pct / 100)

        # Apply AR delay (shift collections forward)
        if ar_delay_weeks > 0 and i < ar_delay_weeks:
            # Early weeks lose some AR
            ar = ar * 0.3
        elif ar_delay_weeks < 0 and i < len(base_weeks) + ar_delay_weeks:
            # Early weeks gain AR from future
            ar = ar * 1.3

        # Apply AP changes
        if ap_change_pct != 0:
            ap = ap * (1 + ap_change_pct / 100)

        # Apply AP delay (shift payments forward)
        if ap_delay_weeks > 0 and i < ap_delay_weeks:
            ap = ap * 0.3  # Early weeks pay less
        elif ap_delay_weeks < 0 and i < len(base_weeks) + ap_delay_weeks:
            ap = ap * 1.5  # Early weeks pay more

        # Apply OpEx changes
        if opex_change_pct != 0:
            opex = opex * (1 + opex_change_pct / 100)

        # Apply payroll changes
        if payroll_change_pct != 0:
            payroll = payroll * (1 + payroll_change_pct / 100)

        total_inflows = ar + other_receipts
        total_outflows = ap + payroll + opex + taxes
        net_flow = total_inflows - total_outflows
        closing = running_balance + net_flow

        adjusted_weeks.append({
            'closing_balance': closing,
            'net_flow': net_flow
        })
        running_balance = closing

    min_balance = min(w['closing_balance'] for w in adjusted_weeks) if adjusted_weeks else 0
    ending_balance = adjusted_weeks[-1]['closing_balance'] if adjusted_weeks else 0
    threshold = base_weeks[0].get('threshold', 0) if base_weeks else 0

    return {
        'ending_balance': round(ending_balance, 2),
        'min_balance': round(min_balance, 2),
        'weeks_below_threshold': sum(1 for w in adjusted_weeks if w['closing_balance'] < threshold)
    }
