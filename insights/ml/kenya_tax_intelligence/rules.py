# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Kenya tax rules in force at 22 Oct 2026 (Finance Act 2026, Act No. 19 of 2026).

Pure Python: no frappe, no I/O. Every number a dashboard section needs from law
lives here, so the rest of the package only does data access and arithmetic on
these results.

Sources: KRA site (PAYE, TOT, WHT pages), Income Tax Act Cap. 470, VAT Act Cap. 476,
Tax Procedures Act Cap. 469B, NSSF Year 4 notice (Feb 2026), Finance Acts 2023-2026.

Known source conflicts (rates are kept configurable here, not buried in queries):
  * Resident dividend WHT: statute 5%, KRA FAQ table shows 10%. 5% used.
  * Rent WHT (resident): 10% used, KRA FAQ; 7.5% is the separate residential rental regime.
  * NSSF remittance: 9th used (NSSF Year 4 notice); older practice was the 15th.
  * SHIF remittance: 9th is assumed, not primary-sourced.
  * IDF: 3.5% of CIF; KRA's motor-vehicle FAQ says 2%.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

# --------------------------------------------------------------------------- rates
VAT_RATE = 0.16
VAT_REG_THRESHOLD = 5_000_000.0
INPUT_VAT_WINDOW_MONTHS = 6
WHVAT_RATE = 0.02  # VAT withholding by appointed agents, remit in 5 working days
CIT_RATE = 0.30
TOT_RATE = 0.015
TOT_MIN = 1_000_000.0
TOT_MAX = 25_000_000.0
SEP_RATE = 0.03
CGT_RATE = 0.15
IDF_RATE = 0.035
RDL_RATE = 0.02

INSTALMENT_PRIOR_FACTOR = 1.10  # each instalment = 25% of 110% of prior-year tax (the safe harbour), else of the current estimate
INSTALMENT_PENALTY = 0.20  # of the shortfall
LATE_PAYMENT_PENALTY = 0.05  # one-off, on tax unpaid at the due date
INTEREST_PER_MONTH = 0.01  # per month or part month, capped at the principal
ETIMS_MISSING_PENALTY_MULTIPLE = 2.0  # 2x the tax, failure to issue an eTIMS invoice
RECORDS_YEARS = 5
LOSS_CARRY_FORWARD_YEARS = 5  # cut from 10 by Finance Act 2025

AMNESTY_PERIOD_END = date(2025, 12, 31)  # liabilities up to this date are in scope
AMNESTY_DEADLINE = date(2026, 12, 31)  # principal must be fully paid by this date

SHIF_RATE = 0.0275
SHIF_MIN = 300.0
AHL_RATE = 0.015
NITA_PER_EMPLOYEE = 50.0
NSSF_RATE = 0.06
PERSONAL_RELIEF = 2_400.0
INSURANCE_RELIEF_RATE = 0.15
INSURANCE_RELIEF_CAP = 5_000.0
PENSION_DEDUCTION_CAP = 30_000.0
MORTGAGE_DEDUCTION_CAP = 30_000.0

# Monthly PAYE bands: (upper bound of band, rate). Finance Act 2023, unchanged by FA 2026.
PAYE_BANDS: Tuple[Tuple[float, float], ...] = (
    (24_000.0, 0.10),
    (32_333.0, 0.25),
    (500_000.0, 0.30),
    (800_000.0, 0.325),
    (float("inf"), 0.35),
)

# NSSF contribution years: (effective from, lower earnings limit, upper earnings limit).
# Year 4 is current; a future Gazette notice adds a row here.
NSSF_YEARS: Tuple[Tuple[date, float, float], ...] = (
    (date(2023, 2, 1), 6_000.0, 18_000.0),
    (date(2024, 2, 1), 7_000.0, 36_000.0),
    (date(2025, 2, 1), 8_000.0, 72_000.0),
    (date(2026, 2, 1), 9_000.0, 108_000.0),
)

# Withholding tax: (resident rate, non-resident rate). ITA s.35, Third Schedule, FA 2026.
WHT_RATES: Dict[str, Tuple[float, float]] = {
    "management_professional": (0.05, 0.20),  # management, professional, training fees
    "contractual": (0.03, 0.20),
    "royalty": (0.05, 0.20),
    "rent": (0.10, 0.30),
    "dividend": (0.05, 0.15),
    "interest": (0.15, 0.15),
    "scrap_metal": (0.015, 0.015),  # FA 2026
    "card_merchant_fee": (0.05, 0.20),  # FA 2026: interchange/merchant fees = management fees
    "winnings": (0.20, 0.20),  # FA 2026
}
WHT_LABELS: Dict[str, str] = {
    "management_professional": "Management & professional fees",
    "contractual": "Contractual fees",
    "royalty": "Royalties",
    "rent": "Rent",
    "dividend": "Dividends",
    "interest": "Interest",
    "scrap_metal": "Scrap metal",
    "card_merchant_fee": "Card and merchant fees",
    "winnings": "Winnings",
}
WHT_WORKING_DAYS = 5
AHL_WORKING_DAYS = 9

# Statutory reference text surfaced by the dashboard (never hard-coded in the frontend).
PENALTY_REFERENCE: List[Dict[str, str]] = [
    {"breach": "Fail to issue an eTIMS invoice", "penalty": "2x the tax"},
    {"breach": "Late payment", "penalty": "5% plus 1% per month"},
    {"breach": "Late PAYE return", "penalty": "25% of tax or KES 10,000"},
    {"breach": "Late company return", "penalty": "5% of tax or KES 20,000"},
    {"breach": "Records retention", "penalty": f"{RECORDS_YEARS} years"},
]

# Objection chain (Tax Procedures Act): days allowed for each step.
OBJECTION_DAYS = 30  # taxpayer objects within 30 days of the assessment
DECISION_DAYS = 60  # KRA decides within 60 days of a valid objection
APPEAL_DAYS = 30  # appeal to the Tax Appeals Tribunal within 30 days of the decision


# --------------------------------------------------------------------------- dates
def add_months(d: date, months: int) -> date:
    """`d` shifted by whole months, day clamped to the target month's length."""
    idx = d.year * 12 + (d.month - 1) + months
    year, month = divmod(idx, 12)
    return date(year, month + 1, min(d.day, calendar.monthrange(year, month + 1)[1]))


def month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def is_working_day(d: date, holidays: Iterable[date] = ()) -> bool:
    return d.weekday() < 5 and d not in set(holidays)


def add_working_days(start: date, n: int, holidays: Iterable[date] = ()) -> date:
    """The date `n` working days after `start` (start itself not counted).

    Saturdays, Sundays and the supplied public holidays are skipped. Callers pass
    holidays from the ERPNext Holiday List; with none given only weekends skip.
    """
    hol = set(holidays)
    d = start
    left = n
    while left > 0:
        d += timedelta(days=1)
        if is_working_day(d, hol):
            left -= 1
    return d


def working_days_between(start: date, end: date, holidays: Iterable[date] = ()) -> int:
    """Working days after `start` up to and including `end` (0 if end <= start)."""
    hol = set(holidays)
    n = 0
    d = start
    while d < end:
        d += timedelta(days=1)
        if is_working_day(d, hol):
            n += 1
    return n


def wht_due_date(paid_on: date, holidays: Iterable[date] = ()) -> date:
    """WHT must reach KRA within 5 working days of the payment (ITA s.35)."""
    return add_working_days(paid_on, WHT_WORKING_DAYS, holidays)


def monthly_due_dates(period_end: date, holidays: Iterable[date] = ()) -> Dict[str, date]:
    """Statutory due dates for the monthly obligations of the month ending `period_end`.

    Nominal dates: a due date that lands on a weekend is NOT rolled forward, so the
    dashboard never shows a deadline later than the safe one.
    """
    nxt = add_months(period_end.replace(day=1), 1)
    ninth = nxt.replace(day=9)
    twentieth = nxt.replace(day=20)
    return {
        "paye": ninth,
        "nssf": ninth,
        "shif": ninth,
        "nita": ninth,
        "ahl": add_working_days(month_end(period_end), AHL_WORKING_DAYS, holidays),
        "vat": twentieth,
        "excise": twentieth,
        "tot": twentieth,
        "sep": twentieth,
    }


def instalment_dates(year_start: date) -> List[date]:
    """CIT instalments: the 20th of the 4th, 6th, 9th and 12th month of the income year."""
    return [add_months(year_start, m - 1).replace(day=20) for m in (4, 6, 9, 12)]


def cit_balance_due(year_end: date) -> date:
    """Balance of tax: last day of the 4th month after the income year ends."""
    return month_end(add_months(year_end, 4))


def cit_return_due(year_end: date) -> date:
    """Company return: last day of the 6th month after the income year ends."""
    return month_end(add_months(year_end, 6))


def input_vat_window_closes(invoice_date: date) -> date:
    """Input VAT must be claimed within 6 months of the invoice date."""
    return add_months(invoice_date, INPUT_VAT_WINDOW_MONTHS)


def loss_lapse_date(loss_year: int) -> date:
    """A tax loss from calendar income year `loss_year` is usable through year + 5."""
    return date(loss_year + LOSS_CARRY_FORWARD_YEARS, 12, 31)


def objection_deadline(notice_date: date) -> date:
    return notice_date + timedelta(days=OBJECTION_DAYS)


def decision_deadline(objection_date: date) -> date:
    return objection_date + timedelta(days=DECISION_DAYS)


def appeal_deadline(decision_date: date) -> date:
    return decision_date + timedelta(days=APPEAL_DAYS)


# --------------------------------------------------------------------------- penalties
def months_late(due: date, paid_or_today: date) -> int:
    """Whole months or part months late (interest runs per month or part month)."""
    if paid_or_today <= due:
        return 0
    return (paid_or_today.year - due.year) * 12 + (paid_or_today.month - due.month) + (
        1 if paid_or_today.day > due.day else 0
    )


def late_payment_cost(unpaid: float, due: date, today: date) -> Dict[str, float]:
    """One-off 5% penalty plus 1% per month interest (capped at the principal)."""
    if unpaid <= 0 or today <= due:
        return {"penalty": 0.0, "interest": 0.0, "total": 0.0}
    penalty = unpaid * LATE_PAYMENT_PENALTY
    interest = min(unpaid * INTEREST_PER_MONTH * months_late(due, today), unpaid)
    return {"penalty": round(penalty, 2), "interest": round(interest, 2), "total": round(penalty + interest, 2)}


def instalment_required(prior_year_tax: Optional[float], current_estimate: Optional[float] = None) -> Optional[float]:
    """Annual instalment base: 110% of prior-year tax when known, else the current-year estimate.

    KRA allows the lower of 110% of prior-year tax and the estimate. The estimate here is
    year-to-date profit, which understates the year, so the prior-year figure is used as the
    conservative safe-harbour base whenever it exists.
    """
    if prior_year_tax is not None:
        return prior_year_tax * INSTALMENT_PRIOR_FACTOR
    return current_estimate


# --------------------------------------------------------------------------- VAT / customs
def import_vat(cif: float, duty: float, excise: float = 0.0) -> float:
    """Import VAT base is customs value plus duty and excise."""
    return round((cif + duty + excise) * VAT_RATE, 2)


def landed_import_taxes(cif: float, duty: float, excise: float = 0.0) -> Dict[str, float]:
    return {
        "duty": round(duty, 2),
        "idf": round(cif * IDF_RATE, 2),
        "rdl": round(cif * RDL_RATE, 2),
        "vat": import_vat(cif, duty, excise),
    }


def etims_exposure(spend_without_invoice: float, input_vat: float) -> Dict[str, float]:
    """Cost of purchases lacking an eTIMS invoice: lost deduction at CIT rate plus lost input VAT."""
    return {
        "income_tax_disallowance": round(spend_without_invoice * CIT_RATE, 2),
        "input_vat_lost": round(input_vat, 2),
        "total": round(spend_without_invoice * CIT_RATE + input_vat, 2),
    }


# --------------------------------------------------------------------------- payroll
def paye_before_relief(taxable_monthly: float) -> float:
    """Progressive PAYE on monthly taxable pay, before personal and insurance relief."""
    tax = 0.0
    lower = 0.0
    for upper, rate in PAYE_BANDS:
        if taxable_monthly <= lower:
            break
        tax += (min(taxable_monthly, upper) - lower) * rate
        lower = upper
    return round(tax, 2)


def paye_band_index(taxable_monthly: float) -> int:
    """0-based index into PAYE_BANDS for a monthly taxable figure."""
    for i, (upper, _) in enumerate(PAYE_BANDS):
        if taxable_monthly <= upper:
            return i
    return len(PAYE_BANDS) - 1


PAYE_BAND_LABELS: Tuple[str, ...] = (
    "Up to 24,000",
    "24,001 - 32,333",
    "32,334 - 500,000",
    "500,001 - 800,000",
    "Above 800,000",
)


def nssf_limits(on: date) -> Tuple[float, float]:
    """(LEL, UEL) in force on `on`; before Year 1 the Year 1 limits, after the table the latest year."""
    chosen = NSSF_YEARS[0]
    for row in NSSF_YEARS:
        if on >= row[0]:
            chosen = row
    return chosen[1], chosen[2]


def nssf(gross: float, on: date) -> Dict[str, float]:
    """Employee NSSF for one month. The employer matches it, so employer == employee."""
    lel, uel = nssf_limits(on)
    tier1 = NSSF_RATE * min(gross, lel)
    tier2 = NSSF_RATE * max(min(gross, uel) - lel, 0.0)
    return {"tier1": round(tier1, 2), "tier2": round(tier2, 2), "employee": round(tier1 + tier2, 2)}


def shif(gross: float) -> float:
    return round(max(gross * SHIF_RATE, SHIF_MIN), 2) if gross > 0 else 0.0


def ahl(gross: float) -> float:
    return round(gross * AHL_RATE, 2)


def paye(
    gross: float,
    on: date,
    *,
    resident: bool = True,
    pension: float = 0.0,
    mortgage_interest: float = 0.0,
    insurance_premium: float = 0.0,
    benefits: float = 0.0,
) -> Dict[str, float]:
    """Expected monthly PAYE for one employee.

    Taxable pay = gross + benefits - NSSF - SHIF - AHL - capped pension - capped mortgage interest.
    Personal relief applies to residents only. Floors at zero.
    """
    n = nssf(gross, on)["employee"]
    s = shif(gross)
    h = ahl(gross)
    taxable = max(
        gross + benefits - n - s - h - min(pension, PENSION_DEDUCTION_CAP) - min(mortgage_interest, MORTGAGE_DEDUCTION_CAP),
        0.0,
    )
    before = paye_before_relief(taxable)
    relief = PERSONAL_RELIEF if resident else 0.0
    relief += min(insurance_premium * INSURANCE_RELIEF_RATE, INSURANCE_RELIEF_CAP)
    return {
        "taxable": round(taxable, 2),
        "before_relief": before,
        "relief": round(relief, 2),
        "paye": round(max(before - relief, 0.0), 2),
        "nssf": n,
        "shif": s,
        "ahl": h,
    }


# --------------------------------------------------------------------------- withholding
def wht_rate(kind: str, resident: bool) -> Optional[float]:
    """Expected WHT rate for a payment kind, or None if the kind is not in the table."""
    pair = WHT_RATES.get(kind)
    if pair is None:
        return None
    return pair[0] if resident else pair[1]


def wht_rate_card() -> List[Dict[str, object]]:
    """Rows for the dashboard's rate card (resident and non-resident, as percentages)."""
    return [
        {"kind": k, "payment": WHT_LABELS[k], "resident": round(v[0] * 100, 2), "non_resident": round(v[1] * 100, 2)}
        for k, v in WHT_RATES.items()
    ]


def classify_wht_text(text: str) -> Optional[str]:
    """Map a free-text account/item/expense name to a WHT kind, or None.

    Heuristic on names only. Order matters: more specific kinds first.
    """
    t = (text or "").lower()
    rules = (
        ("scrap_metal", ("scrap",)),
        ("card_merchant_fee", ("merchant", "interchange", "payment gateway", "card fee", "card processing")),
        ("royalty", ("royalt",)),
        ("rent", ("rent", "lease")),
        ("dividend", ("dividend",)),
        ("interest", ("interest",)),
        ("winnings", ("winning", "prize")),
        ("management_professional", ("consult", "professional", "management fee", "legal", "audit", "advisory", "training", "technical fee")),
        ("contractual", ("contract", "subcontract", "construction", "labour only", "labor only")),
    )
    for kind, needles in rules:
        if any(n in t for n in needles):
            return kind
    return None


# --------------------------------------------------------------------------- account matching
# Name fragments used to find Kenya tax accounts / salary components in a chart of accounts.
# Lower-case substrings matched against the account_name or salary component name.
ACCOUNT_PATTERNS: Dict[str, Tuple[str, ...]] = {
    "vat_output": ("vat output", "output vat", "vat payable", "vat on sales"),
    "vat_input": ("vat input", "input vat", "vat receivable", "vat on purchases"),
    "paye": ("paye", "pay as you earn"),
    "nssf": ("nssf",),
    "shif": ("shif", "sha ", "social health", "nhif"),
    "ahl": ("housing levy", "ahl", "affordable housing"),
    "nita": ("nita",),
    "wht": ("withholding", "wht"),
    "income_tax": ("income tax", "corporation tax", "corporate tax", "instalment tax", "installment tax"),
    "excise": ("excise",),
    "customs": ("customs", "import duty", "idf", "railway development", "rdl"),
    "turnover_tax": ("turnover tax", "tot "),
}

# Salary component names that carry the statutory deductions on a Salary Slip.
SALARY_COMPONENT_PATTERNS: Dict[str, Tuple[str, ...]] = {
    "paye": ("paye", "pay as you earn", "income tax"),
    "nssf": ("nssf",),
    "shif": ("shif", "social health", "sha", "nhif"),
    "ahl": ("housing levy", "ahl", "affordable housing"),
    "nita": ("nita",),
    "pension": ("pension", "provident"),
    "mortgage": ("mortgage",),
}


def match_kind(name: str, patterns: Dict[str, Tuple[str, ...]]) -> Optional[str]:
    """First pattern key whose any fragment occurs in `name` (case-insensitive)."""
    n = f" {(name or '').lower()} "
    for key, frags in patterns.items():
        if any(f in n for f in frags):
            return key
    return None


def rates_in_force() -> Dict[str, object]:
    """Reference block embedded in the payload so the frontend never hard-codes law."""
    lel, uel = nssf_limits(date.today())
    return {
        "law_basis": "Finance Act 2026 (Act No. 19 of 2026), in force from 1 Jul 2026",
        "vat_rate": VAT_RATE,
        "vat_registration_threshold": VAT_REG_THRESHOLD,
        "input_vat_window_months": INPUT_VAT_WINDOW_MONTHS,
        "cit_rate": CIT_RATE,
        "tot_rate": TOT_RATE,
        "tot_min": TOT_MIN,
        "tot_max": TOT_MAX,
        "sep_rate": SEP_RATE,
        "cgt_rate": CGT_RATE,
        "idf_rate": IDF_RATE,
        "rdl_rate": RDL_RATE,
        "shif_rate": SHIF_RATE,
        "shif_min": SHIF_MIN,
        "ahl_rate": AHL_RATE,
        "nita_per_employee": NITA_PER_EMPLOYEE,
        "nssf_lel": lel,
        "nssf_uel": uel,
        "personal_relief": PERSONAL_RELIEF,
        "amnesty_deadline": AMNESTY_DEADLINE.isoformat(),
        "wht_rate_card": wht_rate_card(),
        "penalty_reference": PENALTY_REFERENCE,
    }
