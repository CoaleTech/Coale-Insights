# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Kenya Tax Intelligence orchestrator: builds the 9-tab envelope the dashboard renders."""

from __future__ import annotations

import importlib
from datetime import datetime
from typing import Any, Dict

from frappe import _

from insights.ml.kenya_tax_intelligence import rules
from insights.ml.kenya_tax_intelligence.common import TaxContext, build_context, safe, unavailable

# section tabs computed straight from the books; overview and actions are derived from these
SECTIONS = ("vat", "etims", "payroll", "wht", "income", "legal", "customs")
DERIVED = ("overview", "actions")
BADGES = {"etims": "exceptions", "payroll": "exceptions", "wht": "exceptions", "legal": "exceptions", "actions": "rows"}
FAILED = "Section failed; see Error Log"


def section_module(name: str):
    """Import a section module lazily, so one broken file only fails its own tab."""
    return importlib.import_module(f"insights.ml.kenya_tax_intelligence.{name}")


class KenyaTaxIntelligence:
    def __init__(self, period: str = "fy"):
        self.period = period

    def _run(self, name: str, ctx: TaxContext, *extra) -> Dict[str, Any]:
        fn = lambda: section_module(name).compute(ctx, *extra)  # noqa: E731
        fn.__name__ = name
        return safe(fn, default=None) or unavailable(_(FAILED))

    def train(self) -> Dict[str, Any]:
        ctx = build_context(self.period)
        tabs = {name: self._run(name, ctx) for name in SECTIONS}
        tabs["overview"] = self._run("overview", ctx, tabs)
        tabs["actions"] = self._run("actions", ctx, {**tabs})
        order = ("overview", "vat", "etims", "payroll", "wht", "income", "legal", "customs", "actions")
        return {
            "status": "success",
            "generated_at": datetime.now().isoformat(),
            "company": ctx.company,
            "base_currency": ctx.base_currency,
            "period": ctx.window(),
            "today": ctx.today.isoformat(),
            "rates": rules.rates_in_force(),
            "tabs": {k: tabs[k] for k in order},
            "badges": {tab: int(tabs[tab].get("exception_total") or len(tabs[tab].get(key) or [])) for tab, key in BADGES.items()},
        }
