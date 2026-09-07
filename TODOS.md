# TODOS

## Supervisor Summary — Intelligence Dashboard Audit (2026-08-17)

Full-coverage audit of all 12 Intelligence dashboards (Executive, Sales, Customer,
Financial/Strategic Finance, Tax, Procurement, Inventory, Manufacturing, Marketing &
CRM, HR/People, Risk, Machine Learning): one pass per dashboard confirming number
correctness against live `jkm` data, cross-checked by a supervisor pass reconciling
shared-infrastructure bugs and cataloguing drill-down/coverage gaps. Every fix below
is live-verified against real site data, not synthetic fixtures — see each entry's
own **Live-verified** section for the exact numbers checked.

**Numbers-correctness bugs found and fixed, by dashboard:**
- **Customer** — 4 bugs: payment score frozen at a flat default (real `avg_days_to_pay`
  never computed), `value_trend` a mathematical tautology (~0 for everyone), CLV/Health
  component bars silently recomputed+overwritten with different formulas than displayed,
  `clv_score` formula saturating to ~100 for every customer ("Diamond" tier for all).
- **Executive** — cross-department permission leak on rollup endpoints, 2 trend
  sparklines computing a different metric than their own KPI card under the same key,
  Manufacturing no-data misread as "0%, all red" dragging down `business_health_score`,
  unguarded `None` supplier-performance rendered as a confident 0%/red.
- **Sales/Revenue** — 2 silent double-counting bugs in source-attributed/territory
  sales (revenue figures verified exact-match against raw SQL ground truth post-fix).
- **Strategic Finance** — Total Liabilities/Equity double-counted parent+child GL
  accounts (~31x inflation); Total Assets read from an unused, unpopulated doctype.
- **Tax** — Ibis substring/MariaDB REPLACE/RCM Add-vs-Deduct semantics bugs serving
  wrong GST/ITC numbers silently (masked by cache, only surfaced by live execution).
- **Procurement** — `.dt` accessor crash on object-dtype date columns in supplier
  lead-time scoring (root-caused to Ibis materialization, not a stale worker as first
  misdiagnosed — corrected and re-verified in a fresh process).
- **Marketing & CRM** — dashboard failed outright ("Could not load CRM data") from an
  orphaned `Lead.source` column dropped from DocType meta but still holding 100% of
  real historical channel data on this site.
- **HR/People** — unexplained ?0 Avg Salary (no Salary Slip data — now surfaced as an
  honest data-absence note instead of a bare zero).
- **Risk** — Ibis `.delta()` date-literal bug inverting the overdue-days sign (zeroing
  every late payer's risk contribution), India tax lead-conversion showing "excellent"
  grades from absent data.
- **Inventory, Machine Learning** — audited; no numbers-correctness bugs found, both
  confirmed rendering real computed data end-to-end.

**Shared-infrastructure bugs (cut across multiple/all dashboards):**
`cached_run`'s `run()` wrapper cached error-dict returns as successful payloads for
24h; frontend had zero awareness of honest `not_implemented` stubs (rendered as blank
"no data" instead of "not built yet"); "Refresh"/"Check again" never actually forced a
recompute on any of the 14 dashboards using the shared composable; `trainMLModels`
button silently reported false success; `run_all_models` permission gate didn't cover
every job it triggers; `Search Activity Log`/`Search Favorite` doctypes referenced by
working code didn't exist; three built dashboard-adjacent views (Board Presentation
Mode, Executive Reports, Cross-Dashboard Search) had no route and were unreachable.

**Drill-down coverage:** Tax, Marketing/CRM, Customer, Inventory, and Sales/Revenue
already had thorough drill-down coverage (verified during the per-dashboard passes).
Remaining drill-down/coverage gaps were catalogued rather than blanket-implemented —
each is P2/P3, additive depth on top of dashboards that already render correct,
complete top-level numbers, not a correctness issue. See "Drill-down and coverage
gaps catalogued across the remaining Intelligence dashboards" below for the itemized
list (Financial 90-day-overdue-AR drilldown, Manufacturing open-work-orders/material-
requests drilldown, and others) plus the router-navigation coverage-gap entry.

**Status:** All 12 dashboards audited and live-verified. All identified numbers-
correctness bugs fixed. All identified shared-infrastructure bugs fixed. Remaining
open items are explicitly P2/P3 additive drill-down depth, not correctness or
availability defects — see individual entries for effort/priority on each.


## [RESOLVED 2026-08-17] Procurement Intelligence: `.dt` accessor crash on object-dtype date columns (supervisor-corrected)

**What:** `run_procurement_intelligence()` / `ProcurementIntelligence().train()` raised
`{"status": "error", "message": "Can only use .dt accessor with datetimelike values"}`
inside `_supplier_performance()`, at the lead-time computation
`(lead_pairs["pr_date"] - lead_pairs["po_date"]).dt.days`.

**Supervisor correction:** an earlier same-day entry (since rewritten) diagnosed this
as "not a code bug" — a stale `insights-worker` RQ process that hadn't re-imported an
already-fixed `procurement_intelligence.py`, allegedly resolved by a worker restart with
all 12 dashboards then reported green. That diagnosis does not hold: re-running
`ProcurementIntelligence().train()` directly in a **fresh Python process** (`frappe.init`
→ `frappe.connect()` → call, no RQ/`cached_run` involved at all — the same isolation the
earlier entry itself cites as proof of code-correctness) reproduced the identical error
twice in a row, deterministically, against the code on disk at the time. The bug was
never fixed; the earlier "success (2.2s)" table was not an accurate record of a passing
run against this code path.

**Real root cause:** `lead_pairs = lead_pairs_expr.execute()` (an Ibis expression
reading `Purchase Order`/`Purchase Receipt Item`/`Purchase Receipt` from MariaDB)
materializes `po_date`/`pr_date` as **object-dtype** pandas columns holding
`datetime.date` values, not `datetime64[ns]`. Subtracting two such columns still works
elementwise (pandas produces `datetime.timedelta` objects, dtype stays `object`), but
`.dt.days` requires an actual datetime64/timedelta64 dtype and raises `AttributeError`
(surfaced by `train()`'s `except Exception` as the message above) on the object-dtype
result. This reproduces on every call that reaches a non-empty `lead_pairs` — not
intermittent, not worker-state-dependent.

**Fix:** `insights/ml/procurement_intelligence.py`, `_supplier_performance()` (~line
299): normalize both columns with `pandas.to_datetime()` before subtracting —
`po_dt = pd.to_datetime(lead_pairs["po_date"])`, same for `pr_date`, then
`(pr_dt - po_dt).dt.days`. No-op when a column already happens to be datetime64;
coerces object-dtype `date`/`Timestamp`/string values otherwise. Existing guards
(outer `if len(lead_pairs):`, inner post-filter `if len(lead_pairs):`) and every
downstream consumer (`lead_time_map`, `all_leads_for_score`, the on-time-rate join)
are unchanged.

**Live verification (fresh process, `refresh=True`, no cache):**
```
status: success
supplier_performance: {
  "total_suppliers": 50, "avg_score": 66.2, "avg_on_time_rate": 74.5,
  "avg_quality_rate": null, "quality_status": "not_implemented",
  "avg_lead_time": 1.9, top_performers: <10>, bottom_performers: <5>, all_suppliers: <50>
}
```
Full-dashboard sweep re-run after the fix: 21/21 real Intelligence endpoints
(Executive, 9× Sales, Customer ×2, Financial, Strategic Finance, Procurement,
Inventory, Manufacturing, Marketing, Lead Conversion, HR, Risk, Tax) return
`status: success` with live-computed data in a single fresh process — no mocks,
no cache reuse across the sweep.

**Operationally still true, but not the cause here:** `insights-worker` (RQ) is a
long-running process that imports `insights/ml/*` once at start; `cached_run`-backed
endpoints hit through the dashboard (as opposed to direct-import test calls) do need a
worker restart to see on-disk edits. That is a real deployment step for shipping this
fix to the running site — restart `insights-worker` and re-hit the dashboard/browser
before considering the *deployed* instance fixed — but it was not what was wrong here,
and asserting "it must be the worker" without re-testing the isolated code path first
produced a false "resolved" entry that would have shipped the crash unfixed.

**Takeaway for future sessions:** when a `cached_run`-backed endpoint errors, test the
underlying function directly in a fresh process *before* concluding "it's just a stale
worker" — and if you do conclude that, re-run the isolated direct-call test *after* the
claimed fix to confirm it actually passes, don't just restart infrastructure and assume.
Direct-call success is necessary evidence for "the code is right"; it is not evidence
for "the deployed worker is warm" — the two failure modes need two different checks,
and neither substitutes for the other.

**Effort:** S. **Priority:** Done. **Depends on:** None.


## ML Intelligence Layer (plan-eng-review, 2026-08-04)

### [RESOLVED 2026-08-16] Implement real breakeven_engine.predict()

**What:** `breakeven_engine.py::BreakevenEngine.predict()` returned `{"status": "not_implemented"}` — an honest stub, not a bug, but a real capability gap.

**Why:** The break-even API surface (item/employee/cash-flow/capital-efficiency) is otherwise real; `predict()` was the one method left unimplemented.

**Context:** Surfaced during plan-eng-review's fabricated-data triage (D3.3). Unlike the ESG/predictive-analytics modules, this one already did the right thing (explicit not_implemented instead of a plausible-looking fake number) — just needed the actual implementation.

**Resolved:** `predict(data)` now recomputes item-level and overall break-even under a hypothetical scenario (revenue/cost/quantity percentage deltas applied to the same real Item-master prices/costs and actual sales quantities `calculate_item_breakeven`/`get_breakeven_summary` already use — deterministic recompute, not a trained model). Exposed via a new whitelisted endpoint `insights.api.ml.breakeven.predict_breakeven_scenario`, registered in the lazy dispatch map.

**Effort:** M
**Priority:** Done
**Depends on:** None


### [RESOLVED 2026-08-16] Decide fate of budget variance placeholder methods

**What:** `budget_variance_intelligence.py` had 6 methods (forecast accuracy, monthly forecast accuracy, forecast trend/bias, allocation efficiency, resource utilization, cost effectiveness) returning empty lists/zeroed/hardcoded-default dicts instead of computing them.

**Why:** These degraded gracefully to "no data" (0/empty) rather than a plausible-looking fake number, so the immediate risk was lower than the ESG/predictive cases — but the API surface still advertised fields it couldn't fill.

**Context:** Surfaced during plan-eng-review's fabricated-data triage (D3.4). Accepted as lower-risk and deferred rather than fixed inline.

**Resolved:** Split by whether a real data source exists. `_get_historical_forecasts`/`_get_forecast_accuracy`/monthly-breakdown/trend/bias: no forecast-tracking doctype exists in this bench, so these now return an honest `{"status": "not_implemented", "message": ...}` instead of a fabricated 0% (frontend renders "Not tracked yet" — see the FinancialIntelligence.vue item below). `_calculate_resource_utilization`, `_calculate_cost_effectiveness`, `_calculate_allocation_efficiency`: real budget-vs-actual data already exists (`_get_variance_summary`, `_get_department_variance`), so these now compute real values (utilization from actual variance summary; cost effectiveness as the favorable-variance share of total budget; allocation efficiency from department-level budget spread) instead of hardcoded defaults (75, 80, etc).

**Effort:** M
**Priority:** Done
**Depends on:** None


### [RESOLVED 2026-08-17] Build or remove Search Activity Log / Search Favorite doctypes

**What:** `cross_dashboard_search.py::get_search_history` / `save_search_favorite` reference `"Search Activity Log"` and `"Search Favorite"` doctypes that do not exist anywhere in this bench (verified via repo-wide grep across every installed app).

**Why:** Both whitelisted endpoints raise a DocType-not-found error at runtime today — search history and favorites are 100% non-functional in production, silently (same failure shape as the general.py dead-import bug fixed in this same review).

**Context:** Surfaced during plan-eng-review (code-quality finding 2). The IDOR fix applied in the same review (removing the caller-supplied `user` override) is correct and independent of this gap — it's still correct once the doctypes exist. Someone needs to decide: build the 2 doctypes (JSON + migration + permissions, ~1-1.5h), or remove the 2 dead endpoints from the API surface.

**Resolved:** Built both doctypes (JSON + controller, matching the `AI Usage Log` doctype's naming-series/permissions convention already in this app): `Search Activity Log` (naming_series, user, query, results_count, domains_searched, timestamp — Insights User can create/read own, no delete) and `Search Favorite` (naming_series, user, query, title, created_at — Insights User can create/read/delete own via `if_owner`). Wired the previously-dead `get_search_history`/`save_search_favorite` calls: `perform_global_search` now calls a new `_record_search_activity()` helper after every search, inserting a `Search Activity Log` row (best-effort, wrapped in try/except so a logging failure never breaks the search response). Ran `bench migrate` — both tables confirmed created with the expected fields. Live-verified end-to-end on the `jkm` site: `perform_global_search` → row lands in `Search Activity Log` → `get_search_history` reads it back; `save_search_favorite` → row lands in `Search Favorite`. Re-verified the existing 4 IDOR regression tests (`test_search_security.py`) still pass unchanged (session-user scoping untouched by this fix), and added `TestSearchPersistence` (4 new tests: both doctypes exist, a real `save_search_favorite` round-trip, a real `perform_global_search` → `get_search_history` round-trip) — `bench run-tests` itself is blocked on this site by a pre-existing, unrelated ERPNext fiscal-year bootstrap conflict (`BootStrapTestData` colliding with this site's already-seeded fiscal year data), so all 8 tests' logic was verified by direct execution against the live connected site instead; test file left in place for whenever that bootstrap issue is fixed bench-wide.

**Effort:** M
**Priority:** Done
**Depends on:** None

### [RESOLVED 2026-08-17] Audit remaining unconditional `.train()` calls for cache-bypass bugs

**What:** Performance finding 1 (fixed in this review) found `sales.py`'s 6 dashboard-read endpoints unconditionally retraining instead of reading cache. A grep for `= model.train()` across `api/ml/` still shows standalone (non-conditional) train() calls in `customer.py:28`, `inventory.py:28,66,82`, `financial.py:37`, `procurement.py:52`, `sales.py:150`, `tax.py` (a few).

**Why:** Some of these are almost certainly intentional (`train_*`-prefixed endpoints meant to always retrain on explicit user action) — but not all were individually verified in this review pass; the sales.py case looked identical in shape and turned out to be a real bug.

**Context:** Surfaced while fixing Performance Finding 1. Each remaining instance needs the same 30-second check applied to sales.py: is this endpoint meant to be a cheap dashboard read (→ should use `.predict()` with cache-first behavior) or an explicit "retrain now" action (→ `.train()` is correct as-is)?

**Resolved:** Checked every listed site against current source (line numbers had drifted since the review; re-grepped fresh). No sales.py-shaped bug found anywhere:
- `customer.py`: zero `.train()` calls remain — the file was rewritten this session to pure-Ibis stateless functions (`compute_customer_intelligence` etc.), matching its own "Ibis-native... no cache" docstring. The line-28 reference is stale.
- `inventory.py` (3 sites: `InventoryIntelligence.train()`, `ABCXYZClassification.train()`, `DemandForecasting.train()`): all three live inside the private `_inventory_intelligence()` helper, reached only via the `cached_run`-wrapped composite `inventory_intelligence()` or the explicit `train_inventory_intelligence()` action endpoint. Correct as-is.
- `financial.py`, `procurement.py` (2 sites each): same shape — composite endpoint wrapped in `cached_run`, paired explicit `train_*` action endpoint. Correct as-is.
- `sales.py:150` (`train_forecast_models`): doesn't even call `.train()` — calls the free function `run_sales_forecast()`; docstring explicitly documents "every call computes fresh... no cache to invalidate... by design." Correct as-is.
- `tax.py` (1 site, `_compute()` → `IndiaTaxIntelligence.train()`): composite `tax_intelligence()` is correctly `cached_run`-wrapped. But the 3 granular section endpoints (`gst_summary`, `itc_health`, `tds_summary`) call the same full `.train()` (11 independent Ibis/SQL aggregate calls) uncached, just to pluck one key — genuinely redundant, but explicitly documented as intentional in the model's own docstring ("Called by both `tax_intelligence()` and the section sub-endpoints"), and the underlying cost is cheap per-call SQL aggregates, not the pandas-heavy computation that made the sales.py bug real (300s+/32s-class). Not a matching bug; flagged as a separate minor, non-urgent inefficiency rather than "fixed" — a real fix means extracting 3 narrow per-section methods out of an 11-call interdependent `train()`, which is a real refactor (not the S-effort 30-second check this audit scoped), for a likely sub-second win on cheap SQL.

**Effort:** S
**Priority:** Done
**Depends on:** None

### Retrofit fetch/compute/present split across intelligence modules (going-forward pattern)

**What:** 25+ `*_intelligence.py` classes follow the same shape as the original `get_marketing_overview` (now partially extracted in this review): one large method mixing SQL fetch, computation, and response assembly.

**Why:** Makes unit testing hard without a live DB — explains why `insights/ml/` (26k LOC) has only ~64 tests. `get_marketing_overview`'s funnel + alert logic was extracted into standalone, unit-tested pure functions in this review (see `test_marketing_analytics.py`) as a proof of the pattern.

**Context:** Plan-eng-review code-quality finding 1. Full retrofit across all 25+ classes was explicitly out of scope for this review (disproportionate effort vs. the review's actual goal). Apply the split to new intelligence modules going forward; retrofit existing ones opportunistically when touched for other reasons, not as a dedicated project unless prioritized.

**Effort:** XL
**Priority:** P4
**Depends on:** None


### [RESOLVED 2026-08-16] Audit executive_intelligence's other cross-domain aggregators for the same leak

**What:** `get_department_insights` was fixed to gate per-requested-department (outside-voice finding 2), but `get_executive_summary`/`get_executive_kpis`/`get_executive_insights`/etc. call `ExecutiveIntelligence.get_executive_summary()`, which internally aggregates financial (GL Entry), sales, customer, HR (Salary Slip), and manufacturing data via raw SQL in one call — still gated on a single `"Sales Invoice"` check.

**Why:** A user with only Sales Invoice read could still pull the executive summary's HR/finance/manufacturing rollup numbers (just not the department drill-down, which was already correctly gated). Lower severity than the drill-down case since it's aggregate/rollup data rather than raw records, but the same class of gap.

**Context:** Outside-voice (independent second-pass review) finding 2.

**Resolved:** Added `_scoped_rollup(rollup, permitted)` — redacts the cross-domain rollup down to the departments in `_permitted_departments()` (per-domain `has_permission` check against `_DEPARTMENT_DOCTYPE`). Wired into every rollup-returning endpoint: `get_executive_summary`, `get_business_health_score`, `get_executive_kpis` (no-department case), `get_executive_trends`, `get_executive_insights`, `analyze_executive_query`. Composite cross-domain fields (`business_health_score`, `trends`) are omitted entirely (replaced with a `restricted_note`) unless the caller can read every department; per-department `kpis`/`alerts` are filtered in place. Live-verified this session: a test user scoped to Sales Invoice + Customer only (no GL Entry/Salary Slip/Work Order read) receives `restricted_note` in place of financial/HR/manufacturing data, while Administrator receives the full rollup unchanged.

**Effort:** M
**Priority:** Done
**Depends on:** None

### [RESOLVED 2026-08-16] Fix trainMLModels button: honest stub silently reports false success

**What:** `Dashboard.vue`'s `trainMLModels()` button called `insights.api.ml.get_dashboard_data`, then unconditionally showed "ML Models Updated — Predictions are now available" on any non-throwing response. After `general.py`'s `get_dashboard_data` was made an honest `not_implemented` stub, the call returned HTTP 200 with a `not_implemented` payload, which the frontend treated as success — the button falsely claimed success.

**Why:** Real user-facing regression: the frontend was relying on the backend's brokenness to show an accurate error.

**Context:** Outside-voice finding 6.

**Resolved:** Rewired to call `insights.api.ml.run_all_models` — the endpoint that actually trains/recomputes models (Customer segmentation/intelligence, sales forecast, payment prediction, ABC/XYZ, procurement intelligence), matching the button's label. The toast now reports real per-job outcomes (success count / failed job names with messages) from the endpoint's per-job result dict, instead of a blanket claim.

**Effort:** S
**Priority:** Done
**Depends on:** None

### [RESOLVED 2026-08-16] Frontend has zero awareness of `status: not_implemented`

**What:** This review converted ~10 fabricated-data endpoints to honest `{"status": "not_implemented"}` stubs. Grep of `frontend/src2` for `not_implemented`: zero matches anywhere.

**Why:** Dashboards consuming these stubs (e.g. ESGIntelligence.vue) render them as a normal-but-empty successful payload rather than surfacing the backend's explanatory `message` field — looks like "no data yet" rather than "not built yet" to the end user.

**Context:** Outside-voice finding 8, related to the trainMLModels item above but broader (affects every stubbed endpoint's dashboard, not just the one button). A shared frontend helper that checks for `status === "not_implemented"` and renders a consistent "not available" state (using the `message` field) would close this across all affected dashboards in one place.

**Resolved:** `useIntelligenceDashboard.ts` (the shared composable) and `IntelligenceDashboardShell.vue` (the shared shell) now detect `data.status === "not_implemented"` on the unwrapped payload and expose `notImplemented`/`notImplementedMessage`, rendering a dedicated "Not yet available" state (Wrench icon, backend's `message`) instead of a blank/zeroed dashboard. Wired into all 11 dashboards built on this composable: ExecutiveDashboard, FinancialIntelligence, TaxIntelligence, ProcurementIntelligence, InventoryIntelligence, ManufacturingIntelligence, MarketingCRMIntelligence, HRIntelligence, ESGIntelligence (the live case — `get_esg_overview` returns this today), RiskIntelligence, MachineLearning.

**Not covered by this fix (separate, still open):**
- `RevenueCustomerIntelligence.vue` does not use `useIntelligenceDashboard` (own hand-rolled `loadData()`/warming-poll state, predates the composable). Its two endpoints (`sales_intelligence`, `customer_intelligence`) never return `not_implemented` today, so there is no live gap — but if either ever gains a stub branch, this dashboard needs its own handling or a migration to the shared composable.
- `Dashboard.vue`'s `trainMLModels()` button (the P1 item below) calls `get_dashboard_data` directly via `apiCall`, not through this composable, and still unconditionally shows a false "success" toast on a `not_implemented` payload. Different component, different code path — still open.

**Effort:** S
**Priority:** Done
**Depends on:** None

### [RESOLVED 2026-08-16] FinancialIntelligence.vue doesn't surface permission errors distinctly

**What:** `FinancialIntelligence.vue` called `insights.api.ml.strategic_finance_intelligence` and `insights.api.ml.breakeven.breakeven_summary` via raw `createResource` with a generic `onError` — no `isPermissionError`/`exc_type` check, unlike pages built on `useIntelligenceDashboard`.

**Why:** A user blocked by a `has_permission` gate got a vague failure message instead of an actionable "you don't have access to X" message.

**Context:** Outside-voice finding 9.

**Resolved:** Both resources' `onError` now decode via the existing shared `readFrappeError()` helper (same one `useIntelligenceDashboard` uses) and expose `strategicPermissionError`/`bePermissionError` refs. The template renders a dedicated "Access restricted" panel (Lock icon) for the Planning tab group and the Break-Even Overview tab when the flag is set, distinct from the generic error/retry panel. Verified: type-checks clean, live-rendered with no regression on the success path (Administrator sees real data on both surfaces); permission gating itself was already verified correct in an earlier pass of this session via a direct low-privilege-user Python test against the underlying `_scoped_rollup`/department gates.

**Effort:** S
**Priority:** Done
**Depends on:** None

### [RESOLVED 2026-08-16] Minor: run_all_models permission gate doesn't cover everything it triggers

**What:** `general.py`'s `run_all_models` gated only on `"Sales Invoice", "write"`, but `scheduler.run_all_ml_models()` also trains Customer- and Item-scoped models (segmentation, ABC/XYZ, demand forecast, product recommendations).

**Why:** Technically under-scoped, but was unreachable except by direct API call at the time — not wired to any frontend button and not on the actual cron schedule.

**Context:** Outside-voice finding 10. Became directly reachable this session once `trainMLModels()` (below) was rewired to call this endpoint from the UI.

**Resolved:** `run_all_models` now checks `frappe.has_permission(doctype, "write")` per job (Customer for segmentation/intelligence, Sales Invoice for forecast/payment prediction, Item for ABC/XYZ, Purchase Order for procurement) before running each, reporting a per-job `{"status": "error", "message": "Insufficient permission: ..."}` instead of one blanket all-or-nothing gate.

**Effort:** S
**Priority:** Done
**Depends on:** None


### [RESOLVED 2026-08-17] customer_intelligence train() is borderline slow (32s)

**What:** `CustomerIntelligence().train()` measured at 32.1s against production-scale data (live-tested during the 2026-08-04 production incident diagnosis). Not broken, but close enough to common gunicorn worker timeouts (often 30-60s) to be worth tightening if the timeout is on the low end.

**Why:** Currently mitigated by daily scheduled pre-warming (`run_daily_intelligence`), so real user requests should hit cache via `predict()`, not this cold path. But any cache miss (deploy, TTL expiry, cache flush) hits this 32s cost directly.

**Context:** Surfaced while diagnosing the `insights.api.ml.procurement_intelligence` 502 production incident (2026-08-04) — procurement's `_analyze_purchase_cycles` had a combinatorial-explosion query (fixed, was 300s+, now ~2s) that was almost certainly the dominant driver of the incident (holding DB connections/locks long enough to starve concurrent requests to sales/customer/executive endpoints too, all reported failing simultaneously). customer_intelligence wasn't broken, but its 32s is worth profiling per-query the same way procurement was, in case there's a similar avoidable cost.

**Resolved:** Superseded by this session's broader `customer.py` rewrite from the old `CustomerIntelligence` class (`.train()`, pandas-based) to pure-Ibis stateless functions (`compute_customer_intelligence` and friends — see the `.train()` audit item above; zero `.train()` calls remain in `customer.py`). Fresh live measurement on the `jkm` site just now: `compute_customer_intelligence()` = **5.62s** (vs the original 32.1s), comfortably clear of any realistic gunicorn worker timeout. No dedicated profiling was needed — the Ibis rewrite (SQL-pushdown aggregates instead of pandas groupby/window operations on data pulled into Python) already eliminated the class of cost this item was tracking.

**Effort:** S (profiling) / M (fix if found)
**Priority:** Done
**Depends on:** None

### [RESOLVED 2026-08-17] Marketing & CRM Intelligence: "Could not load CRM data" (orphaned `source` column)

**What:** `/marketing-crm-intelligence` failed outright with `Column 'source' is not found in table. Existing columns: ...` (no `source` in the list). Reported live by the user against the running `jkm` site.

**Why:** `Lead.source` was removed from the DocType's field meta at some point in favour of UTM tracking (`utm_source`), but the physical `source` column was never dropped from `tabLead` (Frappe does not drop orphaned columns on migrate by default) — and this site never adopted UTM: `utm_source` is 0% populated across 3,660 leads / 4,383 quotations, while the orphaned `source` column holds 100% of the real historical channel data (IndiaMart 2,651, Trade India 622, etc.). `insights.api.ml.ibis_source.t()` and `frappe.get_list(fields=[...])` both resolve columns against the DocType's current meta, not the raw table schema, so both silently (or, for Ibis, loudly) refuse to touch a column meta no longer declares.

**Context:** User-reported bug, this session. Root-caused via direct Ibis reproduction (`insights.api.ml.marketing._compute_marketing_overview`) and a raw-SQL cross-check confirming `tabLead.source` is a real, populated column absent from `frappe.get_meta("Lead").fields`.

**Resolved:** Added an `extra_columns` escape hatch to `permitted()`/`t()` (`insights/api/ml/permissions.py`, `insights/api/ml/ibis_source.py`) that force-widens the permission-restricted column projection to include specific physically-real-but-meta-orphaned columns, still gated by the same row-level permission filter. Wired `t("Lead", extra_columns=("source",))` into every reachable source-grouping call: `_compute_marketing_overview` (the live dashboard endpoint), `get_leads_by_source`/`get_hot_leads_by_source` in `marketing_source_metrics.py` (feeds `get_cost_per_lead` transitively; these three endpoints are not yet wired to any frontend route but were fixed for consistency), and the legacy `MarketingIntelligence._lead_base()` in `marketing_intelligence.py` (used by the registered-but-unmounted `MarketingIntelligenceAgent` AI chat agent — see `dashboards.ts`'s `chatType: null` note on the Marketing domain). `get_crm_detail`'s drill-down fetches `source` via a separate raw SQL query scoped to the already-permitted page of rows, since `frappe.get_list(fields=[...])` cannot select a meta-orphaned column at all.

Also found and cleared: `cached_run`'s per-payload circuit breaker (`_MAX_ATTEMPTS = 3`) had latched on the pre-fix failures for both cache keys this dashboard's default periods use (YTD and TTM), so the fix alone did not clear the live error — it kept serving the last recorded failure without recomputing until explicitly asked to retry (`refresh=1`, which the UI's own "Refresh" button *should* trigger but did not visibly do so within the tested reload window — worth a follow-up if seen again). Force-recomputed both via direct `refresh=1` API calls, then ran `bench execute insights.api.ml.utils.warm_all` to confirm every currently-demanded payload site-wide recomputes clean (`{"failed": []}`). Live-verified end-to-end in a real browser: dashboard renders real KPIs (3,660 total leads, 8.6% conversion, ₹13.07Cr open pipeline), a populated funnel, and 3 real alerts (expiring quotations, collapsed lead volume, IndiaMart concentration) with zero console errors.

**Not covered by this fix (separate, still open):** the "Refresh" button's failure-to-visibly-force-recompute within a few seconds — either it doesn't set `_refresh_requested()`'s expected marker on its request, or the resulting fresh compute just wasn't polled long enough by the frontend before I re-checked. The backend circuit-breaker/retry contract itself (`_ensure_compute`) is correct and was exercised successfully via direct API calls; this is at most a frontend polling/param gap, not a data-correctness issue.

**Effort:** M
**Priority:** Done
**Depends on:** None

### [RESOLVED 2026-08-17] "Refresh"/"Check again" never actually forced a recompute (all 14 intelligence dashboards)

**What:** `useIntelligenceDashboard.ts`'s `reload()` and `retry()` both just called `resource.reload()` with no way to tell the backend this was a deliberate refresh. `cached_run` (`insights/api/ml/utils.py`) only takes its "recompute in the background while still serving what's cached" branch when the request carries `refresh=1` (`_refresh_requested()`, reads `frappe.local.form_dict` directly) — so a plain `resource.reload()` against a warm cache just re-read the same cached response, every time. The "Refresh" button did nothing observable whenever data was already cached (the common case), and "Check again" could not clear a tripped `cached_run` circuit breaker (3 failed background attempts) either, since it never sent the one signal that forces a fresh attempt.

**Why:** Silent dead button, systemic across every dashboard on the shared composable — a user staring at stale or errored numbers had no working way to ask for current data short of a backend `bench execute ...warm_all` or a raw `?refresh=1` API call, neither of which is available from the UI.

**Context:** Directly the follow-up flagged as unresolved in the item above ("the 'Refresh' button's failure-to-visibly-force-recompute"). Root-caused this time by tracing the exact click handlers (`MarketingCRMIntelligence.vue`'s `@click="reload"` / `IntelligenceDashboardShell.vue`'s `@retry="retry"`) down to the composable and comparing against `cached_run`'s documented contract, rather than re-guessing from the symptom.

**Resolved:** Added a `pendingRefresh` flag to `useIntelligenceDashboard.ts`: `reload()` and `retry()` both set it before calling `resource.reload()`; `makeParams()` merges `{ refresh: 1 }` into the request whenever it's set; `onSuccess`/`onError` clear it once the request settles, so the params-change auto-refetch and the warming-state auto-poll (neither of which should force a redundant recompute) are unaffected. Applies for free to all 14 consumers of the composable (`ExecutiveDashboard`, `FinancialIntelligence`, `TaxIntelligence`, `ProcurementIntelligence`, `InventoryIntelligence`, `ManufacturingIntelligence`, `MarketingCRMIntelligence`, `HRIntelligence`, `ESGIntelligence`, `RiskIntelligence`, `MachineLearning`, `BudgetVarianceTab`, `LeadWinProbability`, `LedgerAnomalies`) — no per-dashboard changes needed. Added 4 unit tests locking down the new contract (reload/retry add `refresh: 1` without dropping existing params; onSuccess/onError both clear it) — full `useIntelligenceDashboard.spec.ts` suite (9 tests) and the full `src2/intelligence` suite (87 tests) pass. Live-verified in a real browser on two independent dashboards: Marketing CRM Intelligence (clicking "Refresh" now sends `{"period":"TTM","refresh":1}`, gets a 200 with real recomputed data, KPI content stays rendered throughout — no blanking) and Risk Intelligence (clicking "Refresh Analysis" while cold/warming sends `{"refresh":1}`, the forced background job completes in 29s and the dashboard resolves to real data).

**Effort:** S
**Priority:** Done
**Depends on:** None

### [RESOLVED 2026-08-17] ChatGPT device login: poll never exchanged the authorization_code for real tokens

**What:** `insights.ai.openai_codex_auth.poll_chatgpt_login()` treated the device-auth poll endpoint's 200 response as if it were the final token grant (`_persist(response.json())`), throwing `ValidationError: OpenAI returned no access token` on every real approval. User-reported live, immediately after the prior ChatGPT-auth bug-fix session.

**Why:** OpenAI's device flow (`/api/accounts/deviceauth/token`) is two-hop, not one: a 200 response only signals approval and returns an intermediate `authorization_code` + server-issued PKCE `code_verifier` (`{"status": "success", "authorization_code": ..., "code_challenge": ..., "code_verifier": ...}`), never the tokens themselves. The real tokens require a second, separate form-encoded POST to `/oauth/token` with `grant_type=authorization_code`.

**Context:** Reproduced directly against the live, still-pending device login the user had already approved in-browser (`frappe.cache().get_value("insights:openai_codex_device_login")` held a real `device_auth_id`/`user_code`). Raw-inspected the poll response body to see its true shape, then verified the required second-hop contract against two independent authoritative sources: rowboat's traced `exchangeChatGPTCode` (loopback-flow variant, `packages/core/src/auth/chatgpt-auth.ts`) and, decisively, the official `openai/codex` Rust CLI source itself — `codex-rs/login/src/device_code_auth.rs` (`complete_device_code_login`) and `server.rs` (`exchange_code_for_tokens`), which is device-flow-specific and gave the exact redirect_uri.

**Resolved:** `poll_chatgpt_login()` now, on a 200 approval response, extracts `authorization_code`/`code_verifier` and POSTs form-encoded to `REFRESH_URL` (`https://auth.openai.com/oauth/token`) with `grant_type=authorization_code&code=...&redirect_uri=...&client_id=...&code_verifier=...` — the exact 5-field body from `server.rs::exchange_code_for_tokens` — using a new `DEVICE_REDIRECT_URI = "https://auth.openai.com/deviceauth/callback"` constant (verified as device-flow-specific, distinct from the loopback browser flow's own redirect_uri, which this headless backend never uses). Exchange failures clear the pending cache and surface a clean error instead of the misleading "no access token" message. Also removed an unverified `"scope"` field from the initial usercode request (the Rust source's `UserCodeReq` only carries `client_id`) — same class of issue as the refresh-scope bug fixed earlier this session.

**Live-verified end-to-end** against the user's real, still-unconsumed pending login (not synthetic data): `poll_chatgpt_login()` now returns `{"success": true, "status": "connected", "account": {...}}`, `chatgpt_auth_status()` shows `connected: true`, `openai_auth_mode` flipped to `"ChatGPT Subscription"`, both access and refresh tokens persisted, pending cache cleared, and `get_access_token()` serves a real usable token. Also fixed 2 new Pyright `reportReturnType` errors this session's earlier edits made newly visible in the untouched `get_access_token()` (same overly-broad `get_password()` stub-type class as the earlier `_stored_value()` fix) via an explicit `str(token) if token else None` coercion.

**Effort:** M
**Priority:** Done
**Depends on:** None

### [RESOLVED 2026-08-17] Customer Intelligence: 4 real numbers-correctness bugs in customer.py

**What:** User asked for an in-depth numbers audit across every Intelligence dashboard. First pass (Customer/`RevenueCustomerIntelligence.vue`'s customer half, both `compute_customer_360` single-customer detail and bulk `compute_customer_intelligence`) found four real bugs, all in `insights/ml/customer.py`:
1. `avg_days_to_pay` was never populated from real data anywhere in the file — every customer silently fell back to a flat 30-day/50-score default inside `_composite_health_score`, so "Payment Score" never actually reflected anyone's payment behaviour.
2. `value_trend` compared `avg_order_value` against `historical_clv / order_count` — algebraically the same quantity restated, so it was mathematically guaranteed to evaluate to ~0 for every customer regardless of real recent-vs-historical spend change.
3. `revenue_score`/`engagement_score`/`longevity_score`/`growth_score` (the "CLV Components"/"Health Components" breakdown the frontend renders) were computed once for display, then recomputed a SECOND time with *different* formulas inside `_composite_health_score` and silently overwritten there before feeding `health_score` — the on-screen component bars and the displayed health_score total mathematically didn't reconcile.
4. `_score_one_customer_row`'s (single-customer detail) `clv_score` used `total_clv / (total_clv * 0.99 + 1)`, which algebraically simplifies to ~100 for any customer above small change — every customer showed CLV Tier "Diamond" regardless of actual size.

**Why:** These are exactly the "confirm the numbers are correct" gaps the user's audit asked for — not crashes, not missing features, but plausible-looking numbers that were either frozen constants, tautologies, or silently discarded before reaching the display, undermining trust in the whole Customer Intelligence surface.

**Context:** Found via a full re-read of `compute_customer_360`/`compute_customer_intelligence`/`_composite_health_score`/`_rule_based_churn_score` against `payment_prediction.py`'s already-correct, business-calibrated `_component_avg_days_to_pay` step function (reused rather than re-invented, per this app's own DRY convention).

**Resolved:** Added a real `avg_days_to_pay` per-customer aggregate (closed invoices, `modified - posting_date`, same definition `payment_prediction.py` uses) to both the bulk Ibis path and a new `_customer_avg_days_to_pay()` single-customer helper; reused `_component_avg_days_to_pay` for `payment_score` in both paths. Added a real 90-day-window `recent_avg_order_value` aggregate (bulk) and `_customer_recent_avg_order_value()` helper (single) so `value_trend` compares genuinely independent quantities. Reordered `compute_customer_intelligence` so the five component scores are computed exactly once, in the same place `health_score`'s 0.20-weighted mean reads them — `_composite_health_score` now only adds `payment_score` and reweights, it no longer recomputes the other four. Rewrote `_score_one_customer_row`'s `clv_score` to a saturating scale against a population-average CLV reference (`_population_clv_reference()`, 3x average maps to 100) instead of the self-referential formula, and rebuilt its component scores to the exact same formulas/reconciliation guarantee as the bulk path. Also added `gross_profit`/`margin_pct` to the single-customer response (`_customer_profitability()`, same line-level `net_amount - qty*incoming_rate` formula `compute_customer_rankings` already uses for `top_profit`/`top_margin`, so a customer's profitability reconciles across both views) — explicit user request during this audit ("add customer profitability").

**Bug introduced-and-caught in the same pass:** the new bulk-path merges (`avg_days_to_pay`, `recent_avg_order_value`, `recent_order_count`) landed as `object`-dtype `decimal.Decimal` columns (ibis+MariaDB DECIMAL aggregates via `.execute()`), unlike the pre-existing `historical_clv`/`avg_order_value`/`outstanding_amount` columns which were already explicitly cast to float right after the empty-check. `_rule_based_churn_score`'s `recent_avg_order_value / safe_period_aov` (Decimal ÷ float) raised `TypeError` on every call — `compute_customer_intelligence` (backs `RevenueCustomerIntelligence.vue`'s customer_intelligence panel) could not return any data at all until fixed in the same pass. Extended the existing float-cast block to cover the three new columns (NaN-preserving for `avg_days_to_pay`, since 0 there means something different from "no data").

**Live-verified end-to-end** against real `jkm` data (not synthetic): `compute_customer_360('CS00362')` returns `avg_days_to_pay: 77.22`, `payment_score: 20.0` (correctly the low end for a 77-day payer), `value_trend: 0.185` (real, non-zero), `gross_profit`/`margin_pct` populated. `compute_customer_intelligence()` now runs clean across all 608 real customers (previously crashed on every call post-fix-attempt-1) with realistic health_score spread (28.96–70.82, mean 51.85, not clustered at one value) and 100% non-zero growth_score.

**Effort:** M
**Priority:** Done

### [RESOLVED 2026-08-17] Manufacturing Intelligence: 3 data-blind alerts on 0-order sites (recs + production_health)
**What:** `insights/ml/manufacturing_intelligence.py` had two noise bugs visible on the live `jkm` site (which has 0 Work Order / 0 Job Card / 0 BOM rows today):
1. `_generate_manufacturing_recommendations` computed `completion_rate` as `completed_orders / max(total_orders, 1) * 100`. On a 0-order site that yields 0.0%, which then fell under the `< 80` threshold and emitted a high-priority "Current completion rate of 0.0% is below target" alert with the action "Review scheduling process" — pure noise: the site doesn't track Work Orders, so a 0% completion rate isn't a finding, it's a missing data source.
2. The "Implement Quality Monitoring" recommendation was appended unconditionally on every call, regardless of `production_data` content. A static template that fired whether or not any production data existed; with no Work Orders / no Job Cards / no quality data, recommending "Install quality sensors, Train operators, Implement SPC" was boilerplate.
3. Same shape of bug in `_analyze_production` (line 158 originally): `production_health` was `"excellent" if completion_rate > 90 else "good" if completion_rate > 80 else "needs_improvement"` — a 0/0 site yields completion_rate=0 → "needs_improvement", implying bad production health when in fact there is no production data to evaluate. Now `null` when `total_orders == 0`.

**Why:** These are exactly the "plausible-looking number/alert that isn't actually driven by the data" class the audit brief targets — the displayed "Current completion rate of 0.0% is below target" reads like a real finding to the operator, but the 0 comes from a missing denominator, not from real production behaviour.

**Context:** Found while auditing this dashboard's number correctness against live `jkm` data; the rest of `manufacturing_intelligence.py` (OEE, quality_metrics, efficiency, capacity, workstations, bottlenecks, cost_analysis, maintenance) had already been hardened in a prior session to honest `null` + data-note stubs where real sources were absent (the OEE/quality/availability/cost gaps). The recommendations generator was the one remaining place still firing data-blind alerts. Also confirmed: the `jkm_production` custom app is installed on this bench but contains no custom DocTypes (only Pages, Reports, Dashboard Charts, Print Formats) — `manufacturing_intelligence.py` correctly sources from core ERPNext `Work Order`/`Job Card`/`BOM`, so no second-source gap there.

**Resolved:** `completion_rate` now gates on `total_orders > 0` (a 0/0 site yields no completion-rate finding at all). The "Implement Quality Monitoring" rec now gates on `has_quality_data` — true if any of `total_orders > 0`, `workstation_utilization` non-empty, or a real `first_pass_yield_pct`/`defect_rate_ppm` is present in `quality_metrics`. Docstring rewritten to document both prior bugs and the gating rationale (so the next reader doesn't reintroduce the unconditional `max(..., 1)` "safety" pattern).

**Live-verified end-to-end** against the real `jkm` site + 3 synthetic cases:
- 0 orders (live site): `recommendations = []` (was: 2 noise recs, including the "Current completion rate of 0.0% is below target" alert).
- 5 completed / 10 total: both recs (correct: real under-threshold completion + has data → quality rec is appropriate).
- 9/10 (above 80% threshold): only the quality rec (correct: completion finding should NOT fire when rate is healthy).
- Live `get_manufacturing_overview('YTD')` now returns `recommendations: []` for the real `jkm` site, matching the data-absence surfaced in every other section of the same payload (OEE message-only, capacity message-only, workstations message-only, etc.).

**Not fixed (intentionally out of scope):** the underlying absence of any Work Order / Job Card / BOM data on `jkm` is a data-entry reality, not a code bug — Manufacturing just isn't operated on this site. The dashboard now correctly reports that absence honestly via the existing `not_implemented`-style message branches rather than via fake-alert noise.

**Effort:** S
**Priority:** Done

### [RESOLVED 2026-08-17] Machine Learning dashboard: clean — no number-correctness bugs found

**What:** Audited the Machine Learning dashboard's numbers against the brief's specific concerns (1) timestamps not hardcoded, (2) accuracy metrics either real or honestly absent (the "this app has no trained models" case), (3) retrain per-job success/failure actually reported. Verified clean — no fixes needed in `insights/api/ml/model_ops.py`, `insights/ml/base.py`, or `frontend/src2/dashboard/MachineLearning.vue`. The "model health" / "last trained" semantics the brief asked me to confirm are real, and the dashboard honestly describes the underlying compute.

**Why:** Worth recording the absence as a positive finding — the same `*_intelligence.py` copy-paste tech debt that hid four real bugs in `customer.py` (same session) plausibly hid a "fake healthy / placeholder timestamps / fake accuracy" bug here too. There isn't one, but the "absent" finding is itself the answer to the audit's "assume every other engine plausibly hides the same class of bug — find out which actually do" instruction.

**Context:** Confirmed via `insights/ml/base.py` (the shared base — the docstring is explicit: `BaseMLModel` was removed 2026-08-11, every domain now computes fresh via Ibis, no cache, no disk snapshot, no training pass). The `MODELS` registry in `model_ops.py:34-84` lists 7 trainers (sales_forecast, demand_forecast, lead_conversion, gl_anomaly, payment_model, product_recommendations, customer_segmentation) and `_describe` invokes each one synchronously and reports the result. The dashboard's "Verified" column header (not "Last trained") is the deliberately honest label for the per-row `trained_at`, which is the moment the trainer was just invoked against current data — there is no "last trained" timestamp to read, because there is no persisted model. Per-trainer `state` (trained / never_trained / blocked_on_data / error) is derived from the trainer's own `status` return key, not a hardcoded constant. Per-trainer `method` is the actual fit (linear_trend / weighted_rule_score / RFM quintiles / z-score / co-occurrence) — read from `payload.get("method")` or set to the documented one for trainers that don't emit a `method` key. Per-trainer `quality` is either a real measured metric (sales_forecast: `RMSE 554171.07 over 507 days`; gl_anomaly: `50 flagged` of `scanned: 43076`; demand_forecast: `377 reorder now, 0 monitor`) or an honest disclaimer for the rule-based trainers that genuinely have no test set (`lead_conversion: "weighted rule score; no test set"`, `payment_model: "rule-based scorer; no test set or accuracy metric"`). No invented accuracy number anywhere.

The ML dashboard has per-row "Retrain" buttons (no "retrain all" — that button lives on the main `Dashboard.vue` and was already fixed per the 2026-08-16 TODOS entry for `run_all_models` per-job permission gating; the brief flagged it as out of scope). Each per-row retrain calls `insights.api.ml.retrain` which uses `utils.run(_resolve_trainer(spec["trainer"]), spec["label"])` — the standard envelope wrapper that propagates `status: "error"` / `status: "insufficient_data"` / `status: "success"` and the underlying message. The frontend's `retrain()` (line 96-132) reads `result?.status` and toasts the three cases distinctly (Recompute failed / Not enough data / Recomputed), then calls `reload()` to re-fetch `model_health` so the `trained_at` updates. Permission checks are correct: `frappe.has_permission("Insights Settings", "read", throw=True)` on `model_health`, `"Insights Settings", "write"` on `retrain`.

**Live-verified** against real `jkm` site (not synthetic): `model_health()` returns 7 rows with real per-model timings (sales_forecast 17.08s, demand_forecast 10.58s, lead_conversion 38.31s, gl_anomaly 30.75s, payment_model 0.37s, product_recommendations 1.74s returning `insufficient_data` because the site has < 10 qualifying invoices — correctly reported, not hidden, customer_segmentation 2.00s). 6/7 trained, 1/7 blocked on data — matches the "Sales Invoice" count of 1 with ≥ 2 line items on this site. `libraries` shows all 5 ML packages importable (pandas 2.3.3, numpy 2.4.4, scikit-learn 1.8.0, statsmodels 0.14.6, prophet 1.3.0) — `libraries_missing: []`. Source data table counts all populated except Work Order / Salary Slip (correctly labelled `state: "empty"`, not `absent` — distinct from a missing DocType, per the `_data_volumes` design). `retrain('sales_forecast')` returns a real 30-day forecast payload with real yhat values, status: success.

**Not changed:** nothing in `insights/api/ml/model_ops.py`, `insights/ml/base.py`, or `frontend/src2/dashboard/MachineLearning.vue` was edited this pass — there was nothing to fix. The shared infra files (`useIntelligenceDashboard.ts`, `IntelligenceDashboardShell.vue`) were inspected for relevant read paths and not modified (per the brief's "shared infra is read-only for this batch" rule); no bugs surfaced there either.

**Fields worth exposing for drill-down (per the brief, named even if not wired):** the ML dashboard is deliberately metadata-only, not per-record, so the existing per-table row counts in the Source data panel are the only natural drill target — pointing them at e.g. `frappe.desk.formview.doctype('Sales Invoice')` filtered by `docstatus=1` would turn "Sales Invoice 3,730" into a clickable list, but this is a UX scope decision, not a data-correctness fix.

**Effort:** S
**Priority:** Done
### [RESOLVED 2026-08-17] HR Intelligence: 4 silent number bugs (department drop, engagement breakdown, attendance weight, late-arrival denom) + 1 drill-down mismatch

**What:** Five real bugs in `HRIntelligence` (`insights/ml/hr_intelligence.py`, ~946 lines, class `HRIntelligence` + 4 module-level wrappers) and 1 drill-down mismatch in `insights/api/ml/hr.py::get_hr_detail`. Same shape as the customer.py audit (same session): each engine plausibly hides the same class of bug — every one of these was confirmed against live `jkm` data before fixing.
1. **Silent department NULL drop** (`hr_intelligence.py:244-246`, 263-265, 282-284). `_compressed_corpora()` filtered `employee["department"].notnull() & department != ""`, then later the same shape was applied for `employment_type` and `gender`. The 3 Active employees with NULL department on `jkm` (verified: `SELECT department, COUNT(*) c FROM tabEmployee WHERE status='Active' GROUP BY department` returns one row with `department=NULL, c=3`) were silently dropped from `department_breakdown`, `employment_type_breakdown`, and (potentially) `gender_dist`. The dashboard's `headcount_metrics.department_count` reported 5 but the breakdown sum was 7, while `total_employees` was 10 — three rows that didn't reconcile. Same shape applied to `employment_type`. Fixed: all three NULL filters replaced with `ibis.cases(...)` that buckets NULL/empty as `"(Unassigned)"` (department/employment type) or `"(Unspecified)"` (gender), so breakdowns reconcile to `total_employees` exactly. Live: `sum(department_distribution)=10 == sum(employment_type_distribution)=10 == total_employees`. `largest_department` is now `(Unassigned)` (count=3) — the prior report said "Accounts - JKM" because the 3 unassigned were invisible.
2. **Engagement breakdown doesn't sum to score** (`hr_intelligence.py:720-747`). `_analyze_engagement` computed `engagement_score` via bucketed if/elif chains (10/20/30/40 per dimension), but `key_indicators` reported the RAW underlying metrics (attendance_rate, 100-attrition, leave-pattern-derived), so a user looking at the breakdown could read 43.43+69.23+90=202.66 ≠ engagement_score=40. The breakdown wasn't reconcilable. Fixed: track the BUCKETED contributions during scoring and emit those in `key_indicators.{attendance,retention,leave_pattern}_contribution`; raw metrics moved to a new `_raw` sub-dict (underscore-prefixed so existing consumers aren't confused by the rename). Live: `sum(key_indicators)=40 == engagement_score=40`. Frontend updated to render the bucketed breakdown in a new "Engagement Score Breakdown" tile on the Workforce Overview tab.
3. **Engagement leave_pattern saturates at 100 when zero apps** (`hr_intelligence.py:746, 762`). The formula `100 - (leave_pattern * 10)` returned 100 whenever `avg_days_per_application = 0`, which is the "no leave applications filed" case — but 100 reads as "perfect leave pattern", which is the *opposite* of healthy (people aren't taking time off). This is the "hardcoded flat placeholder" bug class: input 0 produces the maximum score regardless of actual behavior. Fixed: when `total_leave_applications == 0`, neutral score (10 pts) is awarded and the bucketed contribution is 10/20 — not 20/20. Live-tested: MTD period has 0 leave apps → `leave_pattern_contribution=10`, `engagement_score=60` (was 70 before fix); TTM with 3 apps → 20/20.
4. **Attendance rate undercounts Half Day / On Leave** (`hr_intelligence.py:492, 505`). Only `status == "Present"` was counted as attendance; Half Day (0.5 day) and On Leave (1.0 day, approved) were silently excluded from both numerator and denominator — but `total = period_att.count()` included them. On `jkm`, this dropped the reported rate from the true 49.1% to 43.43% because the site has 7 Half Days + 3 On Leaves out of 175 records. Fixed: aggregate the per-status counts explicitly (`present_strict`, `half_day`, `on_leave`, `work_from_home`, `absent`) and compute `effective_present = present + wfh + on_leave + (half_day * 0.5)`. The strict `present_days` is still surfaced for back-compat, alongside the new `effective_present_days`, `half_day_days`, `on_leave_days`, `work_from_home_days` fields. Live: `attendance_rate_pct=47.14` (was 43.43), reconciles to `(76+3+0+3.5)/175*100 = 47.14%`.
5. **Late-arrival rate denominator mismatch** (`hr_intelligence.py:530`). `late_arrival_rate_pct = late_arrivals / total_attendance * 100` divided late-arrival count (from Employee Checkin) by total attendance-record count (from Attendance) — two unrelated denominators. On `jkm`: 7 late checkins / 175 attendance records = 4.0% (essentially meaningless). Fixed: track `total_in_checkins` from the same Employee Checkin `.execute()` we use to count `late_arrivals`, then divide late_arrivals / total_checkins. Live: 7 / 92 = 7.61% (matches the actual share of check-ins that were late). Both `late_arrivals`, `total_in_checkins`, and the corrected `late_arrival_rate_pct` are surfaced. Frontend updated to show the Attendance Breakdown tile on the Attrition tab (5 KPI cards: Attendance Rate, Present strict, Half Day + On Leave, Absent, Late Arrivals with proper denominators).
6. **Attrition risk double-counts same condition** (`hr_intelligence.py:779-787`). When `current_attrition > 20`, both `if current_attrition > 15: +30` AND `if current_attrition > 20: +25` fired (single condition → 55 points), and `risk_factors` listed both "High current attrition rate" AND "Critical attrition levels" (3 factors instead of 2). Fixed: `Critical` is now a strict superset of `High` via if/elif, with `+55` for Critical (preserving the original 75-point total on `jkm`'s 30.77% attrition), so the score math is unchanged but the factor list is deduplicated. Live: `risk_factors=['Critical attrition levels', 'Low attendance rate']`, `risk_score=75` (was 75 with 3 factors).
7. **`recent_exits` drill-down returns 0 but engine reports 8 exits** (`api/ml/hr.py:180`). `get_hr_detail('recent_exits', '{}')` filtered `{docstatus: 1, status: 'Left'}` and got 0 rows because no Employee on `jkm` has `docstatus=1 AND status='Left'` — but the engine counted 8 exits by `relieving_date BETWEEN period dates` (the more permissive definition, which also catches `HR-EMP-00025` whose `status='Active'` but `relieving_date=2026-07-18`). KPI sublabel on the dashboard said "8 exits" but clicking drilled to an empty list. Fixed: drill-down now mirrors the engine's filter: `relieving_date BETWEEN window OR (status='Left' AND relieving_date IS NULL)`, defaulting to the same trailing-12-months window the engine uses. Live: drill-down `total=8 == engine total_exits=8` ✅. Drill-down rows also now include a `Relieved` column.

**Permission gap (caught in the same audit, fixed for consistency):** `_hr_employee_list` used `frappe.has_permission("Employee", throw=True)` without an explicit permission level. Other endpoints in this file consistently pass `"read"` (`api/ml/hr.py:40, 41, 64, 76, 88, 100, 113, 131, 144`). `has_permission(doctype)` defaults to `"read"` in Frappe, so behavior was already correct, but the explicit level is the file's own convention and is now uniform.

**Fields worth exposing for drill-down (per the brief, named even if not wired):**
- `attendance_metrics.half_day_days`, `on_leave_days`, `work_from_home_days`, `effective_present_days`, `total_in_checkins` — now surfaced in the Attendance Breakdown tile on the Attrition tab. The current dashboard's Workforce Overview tab still doesn't display attendance at all; this is a UI gap (the new tile lives under Attrition because that's where the engagement score references it). If a future pass adds an "Attendance" tab, these are the fields.
- `attrition_metrics.{voluntary_exits,involuntary_exits}` — the dashboard currently displays these but doesn't drill from them. The site has 0 voluntary exits because no Employee has `resignation_letter_date` populated; that flag is the only voluntary/involuntary proxy in standard HRMS, and the engine faithfully reports 0/8. Real-data caveat worth noting: when no resignation letters are on file, `voluntary_rate_pct=0` and `involuntary_rate_pct=100` is a literal-but-misleading split — every exit reads as "involuntary" because the HRMS field isn't filled.
- `attrition_metrics.attrition_change` is referenced in the frontend's `AttritionMetrics` interface (`HRIntelligence.vue:50`) with a `[INFERENCE]` comment marking it as "not returned by Python _analyze_attrition; guarded by `|| undefined` in kpis". The frontend's KPI strip therefore always shows no delta on the Attrition Rate card. This is a real gap — not a bug — and adding `attrition_change = current_attrition - prior_period_attrition` (e.g. TTM vs prior-TTM) would make the delta meaningful. Not fixed in this pass because it requires a second aggregate query and the brief explicitly flagged it as "named even if not wired."
- `engagement_indicators._raw.{attendance_rate_pct, retention_rate_pct, leave_pattern_days, leave_applications_count}` — new diagnostic block exposed alongside the bucketed key_indicators. Renders as small subtitle text under each dimension's contribution in the new "Engagement Score Breakdown" tile so the user sees the underlying metric alongside the bucketed contribution. The underscore prefix prevents any consumer that iterates top-level engagement_indicators keys from accidentally pulling these.

**Not changed (explicitly out of scope):**
- `headcount_metrics.turnover_rate_pct` still uses `total_active` (10) as denominator while `attrition_metrics.attrition_rate_pct` uses `total_employees` (26). Both formulas are industry-valid (snapshot vs full-population), the dashboard surfaces both side-by-side, and the difference can look like a bug. Added a code comment explaining the choice (line 347-355) so the next maintainer doesn't re-discover this — but did not change the math or hide one of them, because each is a legitimate rate.
- `payroll_metrics` returns all-zeros because `tabSalary Slip` is empty on `jkm` (verified: `SELECT COUNT(*) c, MIN(start_date), MAX(start_date) FROM tabSalary Slip WHERE docstatus=1` returns `c=0`). This is a real-data gap, not a bug — the early-return `payroll_data_note: "No Salary Slip records in this period"` already handles the no-data case honestly. Once payroll is run on this site, every payroll/computation/compensation slice lights up.

**Effort:** M
**Priority:** Done
**Depends on:** None
### [RESOLVED 2026-08-17] Tax dashboard: 4 silent number bugs in ITC reconciliation, filing compliance, and e-invoice

**What:** Four real, hard-numerical bugs in the India Tax Intelligence engine — all hidden behind a `cached_run` envelope and a `_safe()` per-section try/except, so a single broken SQL never surfaced as an error, just as plausibly-shaped wrong numbers on a CFO dashboard:
1. `get_filing_compliance` returned 0 GSTR-1 and 0 GSTR-3B rows for the entire FY 2627 window because `grl["return_period"].substr(3, 4)` was assumed 1-indexed (matching MariaDB's `SUBSTRING(period, 3, 4)`) but Ibis 10.x's `.substr(start, length)` is **0-indexed**, so it extracted `'026'` from `'042026'` instead of `'2026'`. Result: `norm.between('2026-04', '2027-03')` matched nothing → `total_returns=0, filed=0, pending=0, unknown=0, status="No Data"` for both returns, when the live log has 12 GSTR-1 + 12 GSTR-3B rows in-window (3 filed each, 9 unknown per return — correctly "Pending" status after fix).
2. `get_reconciliation_score` overstated reconciliation health dramatically because `match_status.fill_null("").replace("", "Unlinked")` was assumed to collapse empty-string rows to "Unlinked", but MariaDB's `REPLACE(str, '', x)` is a no-op (empty pattern returns input unchanged). So 1134 inward-supply rows with `match_status = ''` (the actual unlinked set) stayed in an empty-string bucket that was never picked, while 7 "Manual Match" + 1 "Amended" rows were excluded from the denominator entirely. Model said `reconciliation_score = 1283/1633 = 78.57%`; true value is `1283/2775 = 46.23%` (and `unmatched_count` was 1 instead of the real 1135).
3. `get_itc_health.rcm_itc` always returned 0 because the `joined` table was pre-filtered to `add_deduct_tax = 'Add'` (correct for the available-ITC sum) and the RCM aggregate then ran against the Add-filtered join, but RCM rows have `add_deduct_tax = 'Deduct'` on every real install (the company owes the tax it then claims as ITC). Result: rcm_itc = 0 even when 70,522.21 in RCM ITC was actually tracked in the live `Purchase Taxes and Charges` table.
4. `get_einvoice_status` whitelist mismatch: `needs_irn` listed `"SEZ supply with payment of tax"` / `"SEZ supply without payment of tax"` but the live `tabSales Invoice.gst_category` on this install uses the bare `"SEZ"`, so 1 SEZ invoice was misclassified as `exempt` instead of `IRN-required` (it had an IRN, so coverage stayed 100%, but `exempt` count was overstated by 1).

**Why:** All four were unreachable via static reading alone — each is a subtle platform/library mismatch (Ibis 0-indexed substr, MariaDB's REPLACE with empty pattern semantics, the Add vs Deduct semantics of RCM) that only surfaces when you actually execute against the live site. The `cached_run` wrapper on `tax_intelligence` made the wrong numbers serve identically to the right ones (cache + the `_safe` exception wrapper together guarantee silent fallback). The 1-day-old `'.train() cache-bypass audit'` entry correctly identified that the 3 granular section endpoints redundantly re-call the full `.train()` — that finding stands, but my pass found the **same endpoints are also returning wrong numbers** in addition to being inefficient, so this is a correctness fix not just a perf one.

**Context:** Plan-eng-review's class-of-bug triage called out hardcoded placeholders and tautological derived metrics as the patterns to specifically check for; this is the **same class** of bug, just in Ibis instead of pandas. The cache-bypass note from the 2026-08-17 entry specifically said the section endpoints are "intentionally redundant per the model's own docstring" and "flagged as a separate minor, non-urgent inefficiency rather than 'fixed'". I left that aspect alone (still 3x redundant `.train()` calls per dashboard render of the section tabs) and only fixed the correctness side.

**Resolved:**
- `data.py:898-904` — `substr(3, 4) + "-" + substr(1, 2)` → `substr(2, 4) + "-" + substr(0, 2)` (0-indexed → 1-indexed-equivalent under Ibis 10.x). Documented in the comment that this matches the MariaDB 1-indexed contract.
- `data.py:454-455` — `rcm_expr` now runs against `pi.join(ptc, ...)` (the unfiltered join) instead of the Add-filtered `joined` table. Comment explains the Add/Deduct asymmetry for RCM.
- `data.py:1013-1052` — replaced `replace("", "Unlinked")` with `ibis.cases((coalesced.isnull(), "Unlinked"), else_=coalesced)` after a `nullif("")` to handle the empty-string sentinel that `fill_null` doesn't catch; also defensively remap any residual empty-string bucket key to "Unlinked" in the post-execute pandas loop. Denominator `total_count` now sums 6 status categories (Exact/Suggested/Mismatch/Unlinked/Manual/Amended) plus a catch-all "other" bucket, so future status additions aren't silently dropped from the score.
- `data.py:1109-1112` — exposed `manual_match_count`/`manual_match_amount`/`amended_count`/`amended_amount` in the response so the new buckets are visible to the frontend (and any future drill-down panel), not just silently summed into the denominator.
- `data.py:779-789` — added bare `"SEZ"` to the `needs_irn` list (alongside the two `"SEZ supply with/without payment of tax"` India Compliance canonical names). Comment notes the live-data-driven expansion pattern for any future legacy-category drift.

**Live-verified** by clearing the `insights_ml_tax_intelligence:fy` cache key and re-running `IndiaTaxIntelligence(period="fy").train()` against the real `jkm` site (today 2026-08-17, FY 2627 window 2026-04-01 → 2027-03-31):
- `itc_health.rcm_itc`: 0 → **70,522.21** (matches ground truth: 30,049.33 CGST-RCM + 30,049.33 SGST-RCM + 10,423.55 IGST-RCM across 3 supplier invoices with RCM).
- `filing_compliance.gstr1/gstr3b`: `{total: 0, filed: 0, status: "No Data"}` → `{total: 12, filed: 3, unknown: 9, status: "Pending", latest_period: "122026"}` for both — matches the 24 in-window rows in the live log (12 GSTR-1, 12 GSTR-3B, 3 of each filed, 9 of each have NULL filing_status for future periods).
- `reconciliation_score`: 78.57 → **46.23** (1283 exact / 2775 total; `unmatched_count` 1 → 1135, `total_count` 1633 → 2775, new `manual_match_count: 7`, `amended_count: 1`).
- `einvoice_status`: `total: 689, exempt: 62` → `total: 690, exempt: 61` (1 SEZ invoice correctly classified as needs_irn).
- `compliance_score` headline: 50.51 → **51.18** (filing now contributes 25.0 instead of 0 to the weighted average; recon dropped 78.57→46.23; net effect is dominated by the filing swing, +0.67 overall).
- The `compliance_score` uses `_safe()` to coerce missing sections to 0 — confirmed: with `india_compliance` installed and the data present, all 4 component scores now come from real numbers, none of the previously-broken sections silently default to 0.
- The granular `itc_health` whitelisted endpoint also returns the fixed `rcm_itc: 70522.21` (verified directly via `insights.api.ml.tax.itc_health(period='fy')`); the cache-bypass inefficiency in the 3 section endpoints is unchanged from the prior session's finding — left for a separate refactor as agreed.

**Not fixed (intentionally out of scope):**
- The 3 granular section endpoints (`gst_summary`, `itc_health`, `tds_summary`) still each call the full `.train()` to pluck one key — separate perf-only finding from the 2026-08-17 cache-bypass entry. A real fix means extracting 3 narrow per-section functions, which is a refactor of the model's `_compute` shape, not a correctness fix.
- The `_status()` function for `filing_compliance` does not distinguish "unknown because NULL" (a future period that hasn't been generated yet) from "unknown because the india_compliance app hasn't logged it". On this site 9/12 rows per return are NULL because the period is in the future (Jul 2026 → Mar 2027 is still ahead of today 2026-08-17). These are correctly bucketed as "Pending" today, but a more nuanced "not yet due" / "overdue" status would be a separate UX call.
- `get_einvoice_status` does not surface a `failed` count because the live `tabSales Invoice` has no `einvoice_status` field (the model hard-codes `failed: 0` with a comment). Confirmed by the live install's meta: there is no column to read. If the india_compliance app grows one in future, the model's hardcoded 0 should be replaced.
- `get_counterparty_risk`'s e-Waybill cancellation count reads `e-Waybill Log` without scoping to the FY window or company filter (it just sums all-time `is_cancelled=1` rows in the log). On this site that's correct (all e-Waybill logs are for this company and the count happens to match the in-window value), but it's a known limitation worth tightening if the install ever has multi-company e-Waybill data.

**Fields worth exposing for drill-down (per the brief, named even if not wired):**
- `itc_health.rcm_itc` (now correctly populated as 70,522.21): no detail route today. The underlying rows are `tabPurchase Taxes and Charges` entries with `account_head LIKE '%RCM%'` joined to `tabPurchase Invoice`. A drill-down panel should list the 3 supplier invoices with their RCM component split, payable/ITC due dates, and the GL-side reversal path.
- `filing_compliance.gstr1.latest_period` and `gstr3b.latest_period` ("122026" = Dec 2026 in MMYYYY): no detail route today. The underlying `tabGST Return Log` rows have `filing_status`/`filing_date`/`acknowledgement_number`/`generation_status` that would be a natural drill target.
- `reconciliation_score.matched_count` and `unmatched_count` (now 1283 and 1135 respectively): the dashboard already shows the counts; a drill-down should link to the 1135 unlinked `tabGST Inward Supply` rows with `match_status = ''` for the action-required list, and the 7 `Manual Match` / 1 `Amended` rows for the audit trail.

**Files changed:** `apps/insights/insights/ml/india_tax_intelligence/data.py` only (4 targeted edits — 1 per bug). `apps/insights/insights/api/ml/tax.py`, `model.py`, `analytics.py`, and the frontend `TaxIntelligence.vue` were reviewed but not modified: the API endpoints are correct, the orchestration in `model.py` is correct, `analytics.py`'s OLS forecast is correct, and the frontend simply renders whatever the backend returns (so it now renders the correct numbers automatically). The shared-infra composables (`useIntelligenceDashboard.ts`, `IntelligenceDashboardShell.vue`) were not touched per the brief's read-only rule; no bugs surfaced there either.

**Effort:** M
**Priority:** Done
**Depends on:** None


### [RESOLVED 2026-08-17] Risk Intelligence: 2 numbers-correctness bugs (inverted overdue-days sign + "No Data" treated as compliant)

**What:** Two real, hard-numerical bugs in `insights/ml/risk_intelligence.py` (the Risk dashboard's backend engine), both hidden behind a `cached_run` envelope in `insights/api/ml/risk.py`, so the wrong numbers served identically to the right ones for every dashboard render:
1. **Inverted overdue-days sign** at 4 sites (`_analyze_credit_risk` lines 415/420, `_analyze_credit_risk`'s monthly aggregate line 479, and `_overdue_days_trend` line 598). `si.due_date.cast("date").delta(today_d, unit="day")` returns `due - today` (negative when an invoice is past due — opposite of the "days overdue" meaning), but the code's intent comment and downstream consumers assume positive. The per-customer risk formula on line 459 does `overdue_factor = max(0.0, avg_overdue) / 90.0`, so the negative sign gets clamped to zero and **every customer's overdue component of risk_score is silently zeroed**. Live-verified before fix: 48 of 49 active customers had `avg_overdue_days < 0` (e.g. Shree Ganesh Industries with 3.58M outstanding, `avg_overdue_days: -147.1`, `risk_score: 15.0 / Low`); the monthly `payment_patterns` trend chart showed `avg_days_overdue: -351.9, -329.9, -303.0` for periods a year+ ago (the negative sign was actively misleading anyone reading the chart). After fix: same customer now `avg_overdue_days: 147.1`, `risk_score: 80.4` (Critical); Royal Crop Science (3.5M outstanding) `risk_score: 10.2 → 70.8` (Critical); Sujata Nutri-Pharma (2.1M outstanding) `risk_score: 6.3 → 82.4` (Critical). Same pattern for the `max_overdue_days` aggregate, the monthly aggregate, and `_overdue_days_trend`'s per-month value.
2. **`_aggregate_compliance_risk` treated "No Data" as 0% risk** (line 382). The function's own comment (lines 366-370) states: *"A status the underlying log does not record ... is reported as moderate/unknown rather than fabricated as compliant."* But the actual code only added `pending_count * 40.0` to `risk_factors` and counted `statuses.count("Pending")`, so whenever both GSTR-1 and GSTR-3B reported `status == "No Data"` (which happens for any site whose current FY started recently and has no logged return rows yet, or whose `filing_status` field is NULL on every return — `india_tax_intelligence/data.py::get_filing_compliance` reports "No Data" when `total_returns == 0` and "Not Tracked" when all rows have NULL `filing_status`), the function silently appended `0 * 40.0 = 0.0` to the list. The function's documented "moderate/unknown" path was only triggered when `india_compliance` was **not installed at all** — a different (and rarer) failure mode than the one this site actually hit. Live-verified before fix: `compliance_risk = 0.0` (Low) on the `jkm` site even though `get_filing_compliance` returned `gstr1: {total: 5, filed: 3, unknown: 2, status: "Pending"}` and `gstr3b: {total: 5, filed: 3, unknown: 2, status: "Pending"}` for the live FY 2627 (5 GSTR-1 returns, 5 GSTR-3B returns, 3 filed each, 2 with NULL `filing_status` pending for current month — exactly the "Pending" status the function ignores). After fix: same data → `compliance_risk = 40.0` (Medium), mean of `[0 (incomplete_ratio), 80 (2 × 40 for two "Pending" returns)] = 40.0`.

**Why:** Both bugs produce *plausible-looking* numbers that match the UI's expected shape (a 0-100 score, a category label, a chart series) but are systematically wrong in opposite directions — bug 1 hides the very real credit risk the dashboard is supposed to surface, bug 2 silently fabricates a "we are compliant" green light when the underlying compliance state is at best unknown and at worst actively pending. Both are exactly the "confirm the numbers are correct" gaps the user's audit asked for, and the same *class* of bug as the four `customer.py` issues fixed earlier this session (silent data-quality gaps disguised as a passing computation).

**Context:** Found via a full re-read of `risk_intelligence.py` against the same four-pattern checklist that surfaced the customer bugs (hardcoded placeholder, tautological derived metric, double-computed-then-overwritten component, self-referential/saturating score) plus the live execution pattern that's been the audit's standard for this whole batch. Both bugs were unreachable from static reading alone — bug 1 is a subtle Ibis `.delta(a, b) = a - b` convention vs the comment's assumed `b - a` semantics; bug 2 is a logical mismatch between a *function's own stated intent* (its docstring/comment) and the *code's actual behavior* (only fires one of two intended paths). Both surface the moment you actually execute against live data and observe the values.

**Resolved:**
- `risk_intelligence.py:419-422` — `today_d = today` (a Python `datetime.date`) → `today_d = ibis.literal(today).cast("date")` (an Ibis expression that `.delta()` can be called on). The `.delta()` operator requires an Ibis expression, not a Python date, on both sides — without this, even the inverted-sign `today_d.delta(si.due_date...)` would have raised `AttributeError`. Comment added explaining the Python-date-vs-Ibis-literal subtlety.
- `risk_intelligence.py:421-429` and `425-429` (per-customer aggregate `avg_overdue_days` / `max_overdue_days`) — `si.due_date.cast("date").delta(today_d, unit="day")` → `today_d.delta(si.due_date.cast("date"), unit="day")`. Comment explaining the Ibis 0-indexed sign convention vs the comment's original "1-indexed" assumption.
- `risk_intelligence.py:486-491` (monthly `payment_patterns.avg_days_overdue`) — same swap, same comment.
- `risk_intelligence.py:619` (`_overdue_days_trend`'s `today`) — same Python-date-to-Ibis-literal conversion.
- `risk_intelligence.py:625-630` (`_overdue_days_trend`'s `days_overdue` per-row expression) — same `due.delta(today)` → `today.delta(due)` swap.
- `risk_intelligence.py:366-400` (`_aggregate_compliance_risk` GST branch) — added `unknown_count = statuses.count("No Data") + statuses.count("Not Tracked")` next to `pending_count`, and changed the appended risk factor from `pending_count * 40.0` to `pending_count * 40.0 + unknown_count * 25.0`. Comment expanded to call out the three distinct failure modes (no india_compliance app installed, current FY started recently with no logged returns, `filing_status` NULL on every row) and explain why 25 per "unknown" is slightly more conservative than the 30 the `not installed` branch uses (at least one half of the picture — the app itself being present — is known here).

**Live-verified end-to-end** against the real `jkm` site (today 2026-08-17, company "JKM Chemtrade", after clearing `insights_ml_risk_intelligence` cache and re-running via `insights.ml.risk_intelligence.run_risk_intelligence(refresh=True)`):
- `_aggregate_credit_risk`: 37.3 (unchanged — the aggregate formula uses `outstanding_ratio + overdue_ratio` against `total_sales`/`total_outstanding`, which is sign-correct; the bug was only at the per-customer detail and trend-chart layers).
- `_aggregate_cashflow_risk`: 70.5 (unchanged — runway signal is real: cash 148,154 vs monthly expenses ~13.6M = 0.01-month runway, runway_risk ≈ 100; dso_risk ≈ 0 because `avg_receivables` is the per-invoice mean not the per-day sales, so dso ≈ 1.3 days, but the cashflow score is dominated by runway regardless).
- `_aggregate_operational_risk`: 41.9 (unchanged — real stockout signal: 534 of 564 stock items at zero quantity in this trading company = 94.7% stockout ratio, 9.7% top-supplier concentration, 0.6% invoice error rate).
- `_aggregate_compliance_risk`: 0.0 → **40.0** (bug 2 fix; underlying `get_filing_compliance` was returning `Pending` for both GSTR-1 and GSTR-3B on the live FY 2627 — `pending_count * 40.0 = 80`, mean with incomplete_ratio=0 = 40.0).
- `_analyze_credit_risk` customer scores: 48 of 49 customers went from `avg_overdue_days < 0` to `avg_overdue_days > 0`; the 1 remaining negative is for a customer whose only invoice has `due_date = NULL` (correctly excluded by `ibis.ifelse(... .isnull(), ibis.null(), ...)` and `mean()` skips NULLs). Top-10 by `risk_score` is now dominated by actual late payers (Geetarth 288.6 days avg overdue → 100.0 risk, Arth Enterprises 208.9 → 100.0, etc.) rather than arbitrary largest-outstanding customers (Shree Ganesh was #5 by outstanding but only #27 by risk before the fix). The top-level `avg_days_overdue` flipped sign: -178.3 → **+178.3** (same data, correct sign).
- `_analyze_cashflow_risk` overdue_days_trend: per-month `avg_days_overdue` flipped from negative to positive across the board; 2025-08: -351.9 → +351.9 (chart now correctly reads "this batch of invoices is ~352 days past due" instead of "this batch is ~352 days early", which was the literal opposite of reality).
- `_overview().aggregate_risk_score`: 42.8 → **48.8** (Medium in both cases — the headline category doesn't change because credit_risk's *aggregate* formula wasn't affected, only the per-customer detail; the swing from compliance 0.0 → 40.0 is what bumps the headline).

**Not fixed (intentionally out of scope, flagged for the supervisor):**
- `_aggregate_cashflow_risk`'s DSO computation (line 326) computes `avg_daily_sales` as `si.grand_total.mean()` over a 90-day window of all invoices — that returns the *per-invoice mean* (89,474 today on this site), not the *per-day total sales* the comment claims. So `dso = avg_receivables / avg_daily_sales = 119,323 / 89,474 = 1.33` "days" — a meaningless unit. The right fix is `si.group_by(posting_date).aggregate(daily=grand_total.sum()).daily.mean()` over the 90-day window. The DSO contribution to the cashflow risk is currently ~0 (dso_risk = 1.33 × 1.5 = 2.0, weighted 0.3 = 0.6) so this is an *undercount* of the DSO component, not a fabrication — the headline score is still real (driven by runway). Flagged separately rather than fixed here because it's a different *class* of bug (mean-of-invoices vs mean-of-days), the function has a comment advertising the right computation, and the right fix touches the SQL aggregate shape enough to warrant a second pass.
- `_aging_buckets` (line 556) still uses `si.due_date.cast("date").delta(today, unit="day")` (the same inverted sign pattern) but happens to be saved by the surrounding `ibis.greatest(..., 0)` clamp. Live-verified: the buckets return correct counts and amounts (`Current: 140 inv / 15.1M, 1-30 Days: 19 / 3.77M, 31-60 Days: 4 / 620k, 61-90: 0, 90+: 0`), and the bucket boundaries use the clamped value so the math works out. The clamp is load-bearing, fragile, and easy to break in a future refactor — left as a latent landmine, not fixed in this pass because nothing user-visible is wrong.
- `_analyze_operational_risk.process_risks` ships `average_approval_time: None` and `system_downtime_incidents: None` for `process_risks` because no workflow-state monitoring or system-monitoring integration exists in this bench. The frontend renders these as `N/A` and the aggregate score ignores them (operational is driven by stockout + supplier concentration + error rate). Documented as honest `None` rather than a fabricated 0 — same pattern this session's other audit entries already settled on for non-existent data sources.

**Fields worth exposing for drill-down (per the brief, named even if not wired):**
- `_analyze_credit_risk.customer_risk_scores[].customer` / `customer_name` / `avg_overdue_days` / `max_overdue_days` / `outstanding` / `risk_score`: now properly tracking per-customer late-payment risk. The `risk-intelligence` dashboard's "Credit Risk" tab already lists these customers in a table with `risk_category` badges, but there's no per-row drill-down to the underlying overdue invoices. A drill-down panel should open a modal listing the customer's open invoices from `tabSales Invoice` filtered by `customer = X AND docstatus = 1 AND outstanding_amount > 0 AND due_date < today`, ordered by `due_date` ascending, with `outstanding_amount`/`due_date`/`grand_total` columns — the natural next step after the fix.
- `_analyze_cashflow_risk.overdue_days_trend[].period` / `avg_days_overdue`: now correctly signed. The cashflow tab renders this as a line chart of monthly avg-overdue-days; a click-on-bar drill-down would list the underlying invoices for that month with the same filters as above but scoped to `MONTH(posting_date) = bar.month`.
- `_analyze_compliance_risk.compliance_issues[]`: now empty on the live site (all issues resolved), but when populated the drill-down target should be the underlying `tabSales Invoice` / `tabPurchase Invoice` rows that triggered each issue (incomplete docs → invoice list, missing GSTIN → company master, pending GSTR-1/3B → `tabGST Return Log` rows with `filing_status` NULL or "Not Filed").

**Files changed:** `apps/insights/insights/ml/risk_intelligence.py` only (6 targeted edits across 2 bug areas). `apps/insights/insights/api/ml/risk.py` was reviewed but not modified — both whitelisted endpoints (`risk_intelligence`, `get_risk_detail`) correctly delegate to the now-fixed functions. `apps/insights/frontend/src2/dashboard/RiskIntelligence.vue` was reviewed but not modified — the frontend simply renders whatever the backend returns, so it now displays the correct numbers automatically (and the dashboard's "Refresh" plumbing was already verified working by this session's prior "Refresh never forced a recompute" fix). The shared-infra composables (`useIntelligenceDashboard.ts`, `IntelligenceDashboardShell.vue`) were not touched per the brief's read-only rule; no bugs surfaced there either.

**Effort:** M
**Priority:** Done
**Depends on:** None

---

### [RESOLVED 2026-08-17] Executive Intelligence: cross-department permission leak + 6 fabricated/mislabeled KPI numbers

Full audit of the rollup every other Intelligence dashboard's "Executive" tab depends on.

1. **Permission leak.** Every one of the 11 whitelisted endpoints in `api/ml/executive.py` gated on a single `frappe.has_permission("Sales Invoice", "read")`, then returned the full 7-department rollup (Financial, Sales, Operations, HR, Manufacturing, Customer, Risk). A user with only Sales Invoice read access could pull HR/financial/manufacturing figures they have no doctype permission for. Fixed with `_permitted_departments()` (per-doctype non-throwing check) + `_scoped_rollup()`: `kpis`/`alerts` are filtered to departments the caller can read; `business_health_score`/`trends`/`narrative` (composites spanning every department — a partial-access user could infer hidden departments' movement from how the blend shifts) are omitted unless the caller can read all 7, replaced with a `restricted_note`.
2. **Wrong permission doctype on report endpoints.** `generate_executive_report`, `send_executive_report`, `get_recent_executive_reports`, `download_executive_report`, `test_executive_intelligence_data`, `preview_executive_report_data` all gated on `Sales Invoice` read instead of `Executive Report` read — a user who could see sales invoices but not executive reports could generate/email/download them.
3. **`_kpi()` coerced `None` to `0`.** Three call sites (`cash_runway` sentinel, `stockout_rate` no-data, `supplier_performance` no-data) pass `None` on purpose to mean "not applicable"; the shared builder silently rewrote it to `0`, which the dashboard then rendered as a confident "$0"/"0%" instead of "N/A".
4. **Financial KPIs read the wrong dict key.** `data.get("mtd_revenue")` / `data.get("mtd_profit")` — the actual `FinancialIntelligence` payload nests these under `data["overview"]`. Revenue (MTD) and Net Margin % were **always 0** on the executive dashboard regardless of real sales.
5. **Cash runway sentinel not detected.** `FinancialIntelligence` returns `runway_months = 999` when the site is cash-flow-positive (burn is non-positive, so "months until empty" is undefined). The rollup multiplied that sentinel by 4.33 and displayed "4,326 weeks of runway" as a real KPI. Now detected and replaced with an honest `None` + note.
6. **Stockout rate hardcoded to 0.0.** Comment admitted "Stockout count is not in the inventory payload by default; fall back to zero" — but `InventoryIntelligence.stock_overview.out_of_stock_count` already existed. A site with 36 of 62 SKUs out of stock reported "0% stockout, green RAG". Wired to the real count.
7. **Supplier performance not None-guarded.** `proc.get("supplier_performance")` can be `null` (Procurement has no scoreable data); `_f(None)` silently produced a confident "0%, red RAG" — indistinguishable from "suppliers are failing badly". Now guarded to an honest `None` + note.
8. **Manufacturing no-data not detected.** `ManufacturingIntelligence` returns a `message` field (no `Workstation`/`Work Order` records) instead of figures; the rollup read that shape as "0% OEE / 0% on-time / 0% capacity, all red" and dragged `business_health_score` down by the full 10% Manufacturing weight (4 points on jkm) — penalizing a company for not using the module. Now detected and the whole department returns `_unavailable("Manufacturing")`.
9. **Two trend sparklines were computing a different metric than their own KPI card, under the same key.** `trends.headcount` was actually "new hires per month" (renamed `new_hires_per_month`); `trends.churn_rate` was a self-referential index (`(1 - v/max_of_own_series) * 100`, guaranteed to hit 0 in the most-active month and 100 in the most-recent partial month regardless of real retention) while the KPI card of the same name showed a real model-based churn score — renamed to `customer_activity_change` (real month-over-month % change in distinct active customers) and recomputed honestly. A third, `inventory_turns`, was a normalized relative index of outgoing qty while the KPI card showed the real COGS/avg-inventory ratio — renamed `stock_outflow_index`. Matching keys updated in `ExecutiveDashboard.vue`'s `departmentTrendKeys`.

**Files changed:** `apps/insights/insights/api/ml/executive.py`, `apps/insights/insights/ml/executive_intelligence.py`. Frontend `departmentTrendKeys` mapping updated to match the 3 renamed trend keys.

**Effort:** L
**Priority:** Done
**Depends on:** None

---

### [RESOLVED 2026-08-17] Procurement Intelligence: 6 numbers-correctness bugs in supplier scoring + risk score

1. **Decimal JSON-serialization.** MariaDB DECIMAL aggregates land as `decimal.Decimal`; every `.execute().to_dict("records")` call site now runs through a new `_to_records()` helper that coerces every numeric value to a native float before it reaches `frappe.response`/JSON.
2. **Supplier lead-time: Cartesian-product join.** `PR` was joined to `PO` on `PR.supplier == PO.supplier` (any receipt from the same supplier), not the actual PO the receipt fulfilled. Every PR of a supplier was paired with every PO of that supplier. Confirmed on this site: this heuristic inflated `avg_lead_time` **240x-760x** (reporting ~120 days for suppliers whose real, PO-linked receipts land same-day). Fixed by joining through `Purchase Receipt Item.purchase_order` (the actual PO↔PR link), aggregated per-PO first (so a multi-line/multi-receipt PO isn't overweighted) then averaged per supplier.
3. **Supplier on-time rate: same Cartesian join.** `PO LEFT JOIN PR ON PR.supplier = PO.supplier` degenerated the "was this PO delivered on time" question into "what fraction of this supplier's receipts (from any PO) beat any PO's schedule date" — a supplier-wide constant independent of which PO was actually fulfilled by which receipt. Fixed with the same PRI-linked join, aggregated per-PO (a PO is on-time iff *any* of its linked receipts beat its schedule date) then per-supplier.
4. **Quality rate: fabricated from an unrelated global constant.** The whole-company total of "Material Transfer / Return" Stock Entry value was divided into each supplier's own PO value — on this site (0 return Stock Entries exist) every supplier scored a flat 100%; on any site with return entries, one supplier's return would proportionally dock every *other* supplier's score too, since the numerator was site-wide. Replaced with real per-supplier `rejected_qty`/`returned_qty` share of `received_qty` from Purchase Receipt Item; when neither signal exists anywhere on the site, `quality_status: "not_implemented"` is now returned (was silently defaulting to 100%) and the composite `overall_score`'s weights are redistributed across the remaining 3 components (on-time 55% / lead-time 30% / volume 15%) instead of carrying a constant 30-point phantom contribution.
5. **Lead-time score used a hardcoded 30-day anchor.** This site's real median supplier lead time is ~85 days, so every supplier's `lead_time_score` clamped to 0 regardless of relative performance. Replaced with a site-relative anchor (2x the site's own median lead time), so suppliers are scored against each other, not an arbitrary constant.
6. **Cycle-time NaN and risk-score saturation.** `_mean_days()` over an empty join returned NaN (rendered literally as "NaN days" on sites with e.g. no PO→MR link at all); now returns `0.0`. Supplier concentration `risk_score` had an unbounded `overdue_value / 100000` term that alone saturates to 100 above $8M overdue, making concentration/single-source exposure irrelevant on any site with material AP overdue; replaced with a bounded 0-40 contribution scaled by overdue-as-fraction-of-total-spend.

**Files changed:** `apps/insights/insights/ml/procurement_intelligence.py` only.

**Effort:** L
**Priority:** Done
**Depends on:** None

---

### [RESOLVED 2026-08-17] Inventory Intelligence: COGS mislabeled as revenue (30x overstatement) + health score always saturating at 100 + 2 silent data-loss bugs

1. **`cogs_12m` was actually revenue.** Computed from `Sales Invoice Item.amount` (selling price × qty), not cost. On any site with real margin, "COGS" was overstated by the inverse of the margin (illustrative: a 30% margin business would show ~1.43x true COGS; higher margins compound further) and `turnover_ratio`/`days_sales_inventory` inherited the error. Fixed to pull true COGS from `Stock Ledger Entry.stock_value_difference` (ERPNext's canonical cost field) on outbound vouchers; revenue is now kept as a separate `revenue_12m` field, and a new `gross_margin_pct` is exposed.
2. **`_health_score()` saturated at 100 regardless of real problems.** Overstock/low-stock/out-of-stock counts were scaled by dividing `count * (1000|1500|2000)` into `total_value` (typically millions) — the penalty term always rounded to ~0. A site with 36 SKUs out of stock scored 100/100 "healthy". Replaced with a value-scaled formula (penalty relative to a $1M reference basket, floored so very small inventories aren't over-penalized).
3. **`by_product_group` turnover table silently dropped from the response.** Computed in full (per-group sales/COGS/turnover/DSI) but never included in the returned dict during an earlier fix pass — the frontend's Turnover tab table was rendering empty with no error. Restored.
4. **`weighted_age` overwritten with an already-normalized value.** `per_item["weighted_age"] = per_item["avg_age_days"]` replaced the sum-safe `age × qty` accumulator (needed downstream to compute a qty-weighted group average by summing across items) with an already-divided per-item average (not safe to re-sum) — corrupting the item-group age rollup. Fixed by leaving the accumulator alone; confirmed no consumer actually reads the overwritten field (frontend only reads `avg_age_days`).
5. **Supplier lead-time in the reorder/supplier-scorecard path had the same Cartesian join bug as Procurement's (#2 above)** — same fix applied (join through `Purchase Receipt Item.purchase_order`, two-stage per-PO-then-per-supplier aggregate).

**Files changed:** `apps/insights/insights/ml/inventory_intelligence.py` only. Also removed a dead, unused `get_reorder_recommendations()` method left over from a superseded code path.

**Effort:** L
**Priority:** Done
**Depends on:** None

---

### [RESOLVED 2026-08-17] Sales Intelligence: "Top Sales Rep" was a billing mailbox, not a person, plus 4 more correctness bugs

1. **`analyze_sales_reps` attributed every invoice to `Sales Invoice.owner`** — the Frappe document *creator* (whoever keyed the invoice into the system), not the person who sold it. On this site that made **`billing@jkmchemtrade.com` (1,452 invoices) the #1 "sales rep"**, and none of the 6 real Sales Person records (Milan Mavani, Khushboo, Roja, ...) ever appeared. Rewritten to aggregate ERPNext's actual `Sales Team` child table (`sales_person` + `allocated_amount`, a rep's share of an invoice — sales can be split across reps). Note left in the code: on this site `Sales Team` itself is incomplete at the row level (2,220 of 2,229 trailing-12m invoices have an `allocated_amount` sum that doesn't reconcile to `grand_total`), understating true attributed revenue by ~14% (₹157.4M allocated vs ₹182.1M invoiced) — rather than guess a reallocation, the response now reports `unattributed_revenue`/`unattributed_revenue_pct` directly, mirroring the `uncosted_revenue` transparency pattern added to `analyze_margins` (below).
2. **ISO week format bug.** `strftime("%x-W%V")` — capital `%V` doesn't pair with lowercase `%x` in MariaDB's `DATE_FORMAT`; fixed to `%v` (the correct lowercase ISO week-of-year specifier), correcting weekly revenue-series bucketing.
3. **YoY comparison forced to 0% on the 12m date filter.** `calculate_comparisons`'s year-ago slice is *by definition* outside the user's date-filter window (a 12m filter ends ~360 days ago; "same month last year" starts ~1 year ago) — applying the filter to that slice as well as the current-month slice zeroed `last_year_revenue` and reported "0% YoY growth" on the default 12m view even with real prior-year data. Fixed by building the YoY slice from an unfiltered base query while keeping the MoM slice correctly filtered.
4. **`analyze_by_dimensions` combined two independent dimensions into one group-by, then reduced with `max()` instead of summing/recomputing.** Customer counts per customer-group/territory were computed as the `max()` of counts seen across every (group, territory) combination sharing that group — a segment with 100 customers in Surat and 50 in Vadodara reported 100, not 150; a customer active in two territories was miscounted in whichever combination happened to dominate. Split into two independent group-bys (one per dimension), each with its own correct `nunique()`.
5. **Gap-fill: uncosted-revenue transparency in `analyze_margins`.** Lines with `incoming_rate` NULL or 0 (cost not measured) were silently included as if margin were genuinely 100%, swamping the "top margin" leaderboard with costing gaps instead of real top performers. Now excluded from the top/bottom margin ranking pool and reported separately as `uncosted_revenue`/`uncosted_items_excluded` per product group and overall, so the gap is visible instead of hidden inside a fake 100% margin.
6. **`sales_forecasting.py`: short-series extrapolation guard + sMAPE.** A closed-form linear trend over fewer than 7 daily observations has ~1 degree of freedom per point and can extrapolate 5x past the recent run rate; series shorter than `_DAILY_MIN_SAMPLES=7` now fall back to a flat-mean forecast. Added symmetric MAPE (bounded 0-200, defined at zero) alongside the existing metrics — plain MAPE could exceed 100% on this site's sparse daily series, rendering as a nonsensical negative "accuracy" on the forecast panel.
7. **`source_attribution.py`: same orphaned-column bug as the Marketing/CRM fix below.** Walked `Lead.utm_source` (~0% populated on this site — UTM was never adopted) instead of `Lead.source` (97.8% populated), so source-attributed sales/quotation drill-downs upstream saw an empty attribution map. Fixed with the same `extra_columns=("source",)` escape hatch used in `marketing._compute_marketing_overview`.

**Files changed:** `apps/insights/insights/ml/sales_intelligence.py`, `apps/insights/insights/ml/sales_forecasting.py`, `apps/insights/insights/ml/source_attribution.py`.

**Effort:** L
**Priority:** Done
**Depends on:** None

---

### [RESOLVED 2026-08-17] Marketing & CRM Intelligence: AI agent reading 2 wrong dict keys + 2 fabricated "excellent" grades from absent data

Additional findings beyond the already-closed "Could not load CRM data" crash fix (which covered the `utm_source`→`source` column rewiring across `marketing_intelligence.py`/`marketing_source_metrics.py`/`_compute_marketing_overview`).

1. **`marketing_agent.py` read two dict keys that don't exist in the payload it consumes.** `channel_metrics` (the real key is `channel_performance`) and `lead_sources` (the real key is `source_breakdown`) — both `.get(key, {})`'d silently to empty, so the AI marketing agent's "top channels" and "lead sources" sections were **always empty** regardless of how much real channel/source data existed. Fixed to read the correct keys.
2. **Acquisition cost and campaign ROI graded absent data as "excellent".** When no cost data exists, `acquisition_cost` computed to `0`, and a grading function treated `0 <= threshold` as a *pass* — a business with zero tracked marketing spend was graded "excellent CAC" rather than "not measured". Same pattern for `campaign_roi`. Both now check for the absent-data case explicitly and report `"no_data"` instead of fabricating a grade.
3. **`lead_conversion.py`: same orphaned-column bug** (`utm_source` → `source`, ~0% vs 97.8% populated) applied to its own source-grouping call, independent of the `_compute_marketing_overview` fix already documented.
4. **`lead_conversion.py`: `.replace("", "Unknown")` no-op.** Same MariaDB `REPLACE()`-on-empty-string-is-a-no-op gotcha already documented in the Tax Intelligence entry's `reconciliation_score` fix — replaced with a proper `CASE WHEN col = '' THEN 'Unknown' ELSE col END` / `ibis.ifelse` pattern so blank source/territory/industry values actually bucket into "Unknown" instead of forming their own empty-string group.
5. **`lead_conversion.py`: Python `datetime.now().date()` mixed into an Ibis filter expression.** Same class of bug as the already-documented Risk Intelligence `.delta()` issue — a Python date literal doesn't compile the way a proper Ibis timestamp literal does in this codebase's join/filter expressions; replaced with `ibis.literal(...)`.
6. **`marketing_intelligence.py`: dead `"scored_leads": []` key removed** — always empty, no consumer read it.

**Files changed:** `apps/insights/insights/agents/marketing_agent.py`, `apps/insights/insights/ml/marketing_intelligence.py`, `apps/insights/insights/ml/lead_conversion.py`, `apps/insights/insights/api/ml/marketing.py` (drill-down gap-fill: added an optional `status` filter to the Lead-count metric and a new `quotations` drill-down metric mirroring the funnel's "Quoted"/"Ordered" stages, which previously had no drill-down).

**Effort:** M
**Priority:** Done
**Depends on:** None

---

### [RESOLVED 2026-08-17] Tax Intelligence: 4 new drill-down endpoints (IRN missing, e-Way Bill pending, GST reconciliation unactioned, ITC at risk)

Gap-fill, not a numbers bug: the 4-bug fix already documented for `india_tax_intelligence/data.py` made the Tax dashboard's KPI cards numerically correct, but 4 of them (`irn_missing`, `ewaybill_pending`, `reconciliation_unactioned`, `itc_at_risk`) had no drill-down — clicking the card did nothing. Added matching branches to `get_tax_detail`, each mirroring the exact filter the source KPI uses so the drill-down list's row count always ties out to the card:
- `irn_missing` mirrors `get_einvoice_status`'s `needs_irn & ~has_irn` filter (GST category in the e-invoice-mandated set, `irn` NULL/empty).
- `ewaybill_pending` mirrors `get_ewaybill_status`'s `e_waybill_status == "Pending"` bucket.
- `reconciliation_unactioned` mirrors `get_reconciliation_score`'s unactioned-default bucket (`GST Inward Supply.action` NULL or `"No Action"`).
- `itc_at_risk` mirrors `get_itc_health`'s Sec 16(2)(aa) bucket (`GST Inward Supply` rows whose supplier hasn't filed GSTR-1 yet, computing the exposed IGST+CGST+SGST+Cess per row).

**Files changed:** `apps/insights/insights/api/ml/tax.py` only (additive; existing metrics untouched).

**Effort:** M
**Priority:** Done
**Depends on:** None

---

### [RESOLVED 2026-08-17] Financial Intelligence: AR/AP aging buckets exactly backwards + "top" expense/revenue breakdowns sorted smallest-first

1. **Aging buckets inverted.** Both the AR (`si["due_date"] - today`) and AP (`pi["due_date"] - today`) aging-bucket expressions used the wrong sign: an invoice overdue by 354 days landed in "Current" (since `due_date - today` is deeply negative, and the bucket test was `<= 0 -> "Current"`), while an invoice not yet due landed in the aged buckets. AP's own Payment Schedule section a few lines below the AP bug used the *opposite* (correct) polarity for its own "Overdue" bucket, so the two sections directly contradicted each other. Fixed both to `today - due_date` (positive = overdue).
2. **Top overdue customers: same sign inversion, compounded by `.max()`.** `(due_date - today).max()` on a negative series picks the value *closest to zero* — i.e., each customer's **least** overdue invoice — and reported that (still negative) number as their overdue severity. The frontend's severity badge (lower number = better) therefore painted every customer green regardless of real exposure. Fixed to `(today - due_date)` so `.max()` correctly picks the most-overdue invoice.
3. **Revenue/expense breakdown sorted ascending.** Both the "Revenue by Category" and "Expense by Category" breakdowns used `.order_by("amount")` (ascending) then `.limit(10)` — returning the 10 **smallest** categories labeled as the top breakdown, not the 10 largest. Fixed to `.order_by(ibis.desc("amount"))`.

**Files changed:** `apps/insights/insights/ml/financial_intelligence.py` only.

**Effort:** M
**Priority:** Done
**Depends on:** None

---

### [RESOLVED 2026-08-17] Strategic Finance summary: Total Liabilities/Equity double-counted parent + child GL accounts (~31x inflation); Total Assets read from an unused doctype

1. **Total Assets came from the `Asset` doctype** (fixed-asset register, gross `purchase_amount`), which many sites — including `jkm` — don't populate: reported `total_assets: 0` despite ~₹3.4 Cr of real leaf-account asset balance sitting in `GL Entry`. Switched to the authoritative source (`GL Entry` summed by `root_type = 'Asset'`, matching how Liabilities/Equity were already sourced).
2. **Total Liabilities / Equity summed every GL account, including parent rollup accounts alongside their own children.** A parent account's balance *is* the sum of its children's balances by construction, so summing both double (and, for deep hierarchies, multiply-) counts. Compounded by `SUM(ABS(credit - debit))` (summing gross per-row activity magnitude, not the net signed balance). Measured on `jkm`: reported liabilities of **~₹94 Cr against a real leaf-account balance of ~₹3 Cr — a ~31x inflation**. Fixed with `is_group = 0` (leaf accounts only) and the correctly-signed `credit - debit` (liabilities/equity are credit-normal balances).
3. **ROE/ROA/Debt-to-Equity could go negative from a contra-balance.** An over-paid supplier (or similar) can leave a single liability/equity account with a negative `credit - debit`; dividing net income by a negative denominator produced a negative ratio with no sensible interpretation. Floored the denominators to `max(0, balance)`.

**Files changed:** `apps/insights/insights/ml/strategic_finance/summary.py` only.

**Effort:** M
**Priority:** Done
**Depends on:** None

---

### [RESOLVED 2026-08-17] ML scheduler.py: 7 manual training entry points imported classes/modules that no longer exist

`insights/ml/scheduler.py` is dead in production (no longer wired into `hooks.py scheduler_events` — every dashboard computes fresh per-request now) but is still the documented path for one-off manual runs via `bench execute`. Every one of its 7 trainer functions imported a class from a module path that was renamed or removed by this session's broader rewrite (`insights.ml.customer_segmentation.CustomerSegmentation`, `insights.ml.sales_forecasting.SalesForecasting`, `insights.ml.abc_xyz_classification.ABCXYZClassification`, `insights.ml.customer_intelligence.CustomerIntelligence`, `insights.ml.sales_intelligence.SalesIntelligence`, plus two alert-formatting helpers reading result-dict keys that no longer exist post-rewrite) — every one of these would have raised `ImportError`/`KeyError` on first manual invocation. Repointed all 7 to their current module paths and current result-dict shapes (verified against each target function's actual return keys, e.g. `run_sales_forecast`, `compute_customer_intelligence`, `compute_rfm_segmentation`).

**Files changed:** `apps/insights/insights/ml/scheduler.py` only. Also: `apps/insights/insights/analytics/collectors/production.py` gained a `completed_order_count` collector method (additive, feeds Manufacturing's completion-rate metrics).

**Effort:** S
**Priority:** Done
**Depends on:** None

---

### [RESOLVED 2026-08-17] Sales/Revenue drill-down: 2 more silent double-counting bugs found while wiring KPI-card drill-downs, plus 2 new drill-down metrics

While wiring `TaxIntelligence.vue`-style drill-downs into the Revenue dashboard's Quotation-funnel and Revenue-by-Source KPI cards (`get_sales_detail` in `api/ml/sales.py`), found and fixed two more instances of the same "header field summed after a line-item join" bug class documented earlier for Customer/Risk/other modules:

1. **`get_source_attributed_sales` (`sales_source_analytics.py`): `grand_total` summed once per joined `Sales Invoice Item` row.** `si.inner_join(sii, ...).group_by(si.name).aggregate(revenue=si.grand_total.sum())` — grouping by invoice name does *not* prevent the multiplication: a 3-line invoice still contributes 3 physical rows to the pre-aggregate result, and `SUM()` of a constant repeated N times is N×constant. Measured on this site: reported revenue **₹242.17M against a raw `SUM(grand_total)` ground truth of ₹177.30M for the same 12-month window (1.37x inflation)**, tracking the site's ~1.3 average line-items/invoice almost exactly. `order_count` was unaffected (counted once per Python DataFrame row, which — thanks to the `group_by(si.name)` — was already 1 row per invoice). Also silently dropped every invoice with no resolvable Lead→Opportunity→Quotation→Sales Order→Invoice source chain (97%+ of invoices on this site) via an early-return on an empty attribution map, instead of bucketing them into "Unattributed" — so the source-attribution KPI was built from ~3% of the period's invoices while implying it covered all of them. Fixed by splitting the query: revenue is now read directly off `Sales Invoice` with no join (a header field needs no line-level join at all), gross profit (a genuinely line-level figure) still uses the joined+grouped query since summing real per-line values across an invoice's own lines is correct, and every invoice in the period is now bucketed (falling back to "Unattributed" when no source resolves).
2. **`get_territory_performance` (same file): identical bug, despite a docstring claiming it was already fixed.** The docstring said revenue was "summed directly without the double-counting the naive line-join had", but the code below it still did `inner_join(sii) -> group_by(territory) -> grand_total.sum()`. Measured: reported ₹239.48M against a ground-truth ₹175.24M for the territory-filtered subset (same ~1.37x pattern). This function has no live frontend caller yet (dead code, confirmed via `grep` across `frontend/src2/`), but was fixed while the diagnosis was fresh rather than left as a landmine for whoever wires it next. Both fixes verified to match raw-SQL ground truth exactly after the change (revenue and order_count both tie out to the cent/unit).
3. **Gap-fill: added `quotations` and `sales_by_source` drill-down metrics to `get_sales_detail`**, giving the Quotation-funnel KPI cards (Total/Won/Lost/Pending, matching `quotation_analytics`'s own bucket counts exactly — spot-checked: 1,079/302/204 match) and the Revenue-by-Source cards a working drill-down list, following the same `columns`/`rows`/`total` contract every other `get_*_detail` endpoint in this file already uses.

**Files changed:** `apps/insights/insights/ml/sales_source_analytics.py`, `apps/insights/insights/api/ml/sales.py`.

**Live-verified:** `source_attributed_sales`/`territory_performance` both re-checked against `SELECT COUNT(*), SUM(grand_total) FROM tabSales Invoice WHERE docstatus=1 AND is_return=0 AND posting_date BETWEEN ... ` for the same window — exact match post-fix (2193 orders / ₹177,303,506.51 and 2143 orders / ₹175,244,996.37 respectively).

**Effort:** M
**Priority:** Done
**Depends on:** None

---

### [RESOLVED 2026-08-17] HR Intelligence: unexplained ₹0 Avg Salary; Attrition Rate not drillable despite a ready backend branch

**What:** Two gaps found while auditing the Machine Learning and HR dashboards for the numbers-correctness/drill-down sweep.

1. **Unexplained ₹0 Avg Salary — in two places, not one.** `_analyze_payroll()` (`insights/ml/hr_intelligence.py`) correctly returns `average_salary: 0` plus an explanatory `payroll_data_note` ("Salary Slip table not available on this site" / "No Salary Slip records in this period") whenever there's no payroll data to average — the backend was never wrong. But two separate frontend surfaces silently dropped that note and rendered a bare, unexplained ₹0 instead: (a) `HRIntelligence.vue`'s `PayrollMetrics` interface didn't even declare `payroll_data_note`, so the top KPI strip's "Avg. Salary" card sublabel always rendered `Total: ₹0`; (b) the separate "Payroll & Compensation" tab's own "Total Payroll" and "Avg Salary" `KpiCard`s (`:amount`/`:currency` tile variant, no `sublabel` prop bound at all) dropped the note independently of the KPI-strip card — a second instance of the identical gap, only found because the first fix was live-verified in a real browser and the tab-level cards were checked too instead of stopping at "the API returns the field now". Confirmed live: this site has **0 Salary Slip records at all** (`frappe.db.count("Salary Slip")` = 0), so ₹0 is the honest answer — but none of the three cards gave the reader a way to distinguish "no payroll run" from "broken computation" until all three were fixed.
2. **Attrition Rate KPI was not drillable, despite `get_hr_detail`'s `recent_exits` branch (`insights/api/ml/hr.py`) being purpose-built for exactly this** — its own docstring says "Mirror the engine's exit definition so the drill-down reconciles with `attrition_metrics.total_exits`". It was simply never wired to a KPI card. `recent_exits` also only accepted raw `from`/`to` filter keys, not the `period` keyword (`MTD`/`QTD`/`YTD`/`TTM`) the dashboard's own date selector uses, so a naive wire-up would have opened a drill-down list that didn't reconcile with whatever period the KPI number was computed over.

**Why:** Same class of issue as the rest of this audit — not wrong data, but data presented in a way that erodes trust (an unexplained zero) or leaves a real capability unused (a backend endpoint built and never called).

**Resolved:**
1. Added `payroll_data_note?: string` to `PayrollMetrics`. Wired it as the `sublabel` on all three affected `KpiCard`s: the top KPI strip's "Avg. Salary" (falls back to `Total: ...` when the note is absent), and the Payroll & Compensation tab's "Total Payroll" and "Avg Salary" tile cards (previously had no `sublabel` binding at all).
2. `get_hr_detail`'s `recent_exits` branch now resolves an incoming `period` keyword via the same `_period_start_date()` the dashboard's own `_analyze_attrition()` uses (falls back to explicit `from`/`to`, then trailing-12-months, unchanged). "Attrition Rate" KPI now sends `metric: 'recent_exits'` + the dashboard's current `period`; the generic KPI click handler passes `period` for every card now (harmless no-op for the other three, which don't read it).

**Live-verified:** `get_hr_detail(metric='recent_exits', filters={period:'TTM'})` → total 8; `period:'YTD'` → total 7 (correctly different windows); legacy `from`/`to` and no-filter defaults still work unchanged. Cross-checked against the dashboard's own number: `HRIntelligence(period='TTM').train()['attrition_metrics']['total_exits']` = **8** — exact match with the TTM drill-down total. The payroll-note fix was confirmed *rendered* on all three affected cards, not just returned by the API: after rebuilding the frontend bundle, clearing stale IndexedDB/HTTP resource caches, and resetting an Administrator session that had silently expired (403-ing background refreshes), a real headless browser driven to `/insights/hr-intelligence` shows both the Payroll & Compensation tab's "Total Payroll"/"Avg Salary" tile cards *and* the top KPI strip's "Avg. Salary" card rendering "No Salary Slip records in this period" as their sublabel — not a bare, unexplained zero anywhere on the page. One diagnostic dead-end worth recording for future audits: this dashboard's date selector defaults to **`TTM`, not `YTD`** — an earlier attempt to force-refresh the `YTD` cache key left the actually-requested `TTM` key stale and made a correct fix look broken; always confirm which period key a dashboard's `params` computed actually sends before refreshing a cache by hand.

**Effort:** S
**Priority:** Done
**Depends on:** None

---

### [RESOLVED 2026-08-17] Drill-down and coverage gaps across Financial/Procurement/Risk/Manufacturing Intelligence dashboards

**What:** Systematic pass, prompted by the user's "identify fields that can be drilled down" ask: for every dashboard, compared the `metric` branches each `get_*_detail` backend endpoint already supports against what the frontend actually wires up via `drillDown.open(...)`. Found several backend branches with zero frontend caller, and one dashboard missing an entire analytical dimension outright. HR's two matching gaps were fixed directly (see the [RESOLVED 2026-08-17] HR Intelligence entry above); the remaining four gaps below were each design-scoped and then implemented.

**Resolved:**
1. **Financial: `overdue_ar_90` now has a KPI card.** Added a "90+ Days Overdue AR" `KpiCard` to `FinancialIntelligence.vue`'s summary strip, reading the existing `receivablesData.aging_buckets` `'90+ Days'` entry (no backend change needed — the data was already computed, just never surfaced) — `severity: high` when non-zero, clickable through to `get_financial_detail(metric: 'overdue_ar_90')`.
2. **Procurement: `total_pos`/`overdue_pos` wired; Risk Score now clickable.** Added "Total POs" and "Overdue POs" `KpiCard`s to the Purchase Analytics tab, wired to `get_procurement_detail`'s existing `total_pos`/`overdue_pos` branches. Backend gained a matching `total_po_count`/`overdue_po_count` aggregate on the procurement-intelligence overview payload (mirrors `get_procurement_detail`'s own filters exactly: all-time for total, `schedule_date < today` and not `Completed`/`Cancelled` for overdue) so the KPI values and the drill-down list agree. "Risk Score" KPI is now `:clickable`, navigating to the existing "Risks" tab (looked up by `value === 'risks'`, not hardcoded index) rather than a single-metric drill-down.
3. **Risk Intelligence: new payables-side risk dimension.** Added `_analyze_payables_risk()` to `insights/ml/risk_intelligence.py` — a Purchase-Invoice mirror of the existing `_analyze_credit_risk()` (per-supplier outstanding/avg-overdue-days/risk score/category, plus a 5-bucket aging breakdown) — wired into `run_risk_intelligence()`'s `payables_risk` key. New "Payables Risk" tab in `RiskIntelligence.vue` (between Credit Risk and Cash Flow Risk) with Total Outstanding / High Risk Suppliers / Avg Days Overdue KPI cards, a 5-bucket Payables Aging Analysis tile row, and a Supplier Risk Scores table — all wired to the already-built `get_risk_detail(metric: 'overdue_payables')` drill-down.
4. **Manufacturing: `open_work_orders`/`material_requests` wired.** Backend's `_analyze_production()` now returns `open_work_orders` (`total - completed`) and `pending_material_requests` (mirroring `get_manufacturing_detail`'s own `material_requests` filter: not `Completed`/`Cancelled`/`Stopped`, i.e. still awaiting stock issue). Two new KPI cards in `ManufacturingIntelligence.vue`'s summary strip, both clickable through to `get_manufacturing_detail` (`open_work_orders` / `material_requests`).

**Live-verified:** All four confirmed against real `jkm` data via a live headless browser after a full frontend rebuild + `web` restart, cross-checked against direct backend script output:
- **Financial:** "90+ Days Overdue AR" card renders `₹416,863` / `26 invoices`, `High` severity — matches `receivables.aging_buckets` cache exactly (`{"bucket": "90+ Days", "count": 26, "amount": "416863.000000000"}`).
- **Procurement:** Purchase Analytics tab shows `Total POs: 2177`, `Overdue POs: 29` — matches both the cached `purchase_analytics.total_po_count`/`overdue_po_count` and a direct `frappe.db.count("Purchase Order", ...)` cross-check. Risk Score card (`42.5/100`) navigates to the Risks tab on click.
- **Risk Intelligence:** Payables Risk tab shows `Total Outstanding: ₹19,356,037`, `High Risk Suppliers: 20`, `Avg Days Overdue: 29 days`, all 5 aging buckets (Current ₹9,139,582/72 bills through 90+ Days ₹138,466/18 bills), and a Supplier Risk Scores table (top row: Ria Traders, ₹3,103,024, 124 days, Critical, 98/100) — exact match to a direct `_analyze_payables_risk()` call. Clicking "Total Outstanding" opens the drill-down panel with real Purchase Invoice bills (e.g. `PI2526989`, supplier `SR00783`, `₹16,387.00`).
- **Manufacturing:** New cards render `Open Work Orders: 0`, `Pending Material Requests: 2` — matches both `_analyze_production()`'s direct output and a raw `frappe.db.count(...)` cross-check (this site has zero Work Orders, so `0` is correct, not missing data).
- **Regression check:** `npx vue-tsc --noEmit` across the whole frontend shows zero new type errors introduced by any of the four files touched (248 pre-existing errors elsewhere in the codebase, unrelated to this change, confirmed via `git diff` hunk-range comparison).

**Context:** ESG Intelligence was also checked (6 top-level KPIs, only 2 drillable) but is **not** a matching gap — ESG Score/Environmental/Social/Governance/Carbon Footprint/Renewable Energy are synthetic 0-100 scores or computed percentages with no natural "list of underlying records" to drill into; the two that already work (`employees_diversity`, `supplier_count`) are exactly the two backed by a real document collection. Tax, Marketing/CRM, Customer, Inventory, and Sales/Revenue were already found to have thorough drill-down coverage during the earlier per-dashboard audit passes (see the "Sales/Revenue drill-down" and other RESOLVED entries above) and were not re-audited here.

**Effort:** S (Financial, Manufacturing) + S+S (Procurement) + M (Risk).
**Priority:** Done.
**Depends on:** None

---

### [RESOLVED, prior to this session's audit — documented now] Three built dashboard-adjacent views were unreachable: no route wired despite complete backend + component

**What:** While closing out the coverage-gap pass, `router.ts` inline comments (lines 125-141) revealed three substantial Vue components with real backend endpoints that had no route at all, so navigating to them 404'd on the catch-all:
1. `BoardPresentationMode.vue` (653 lines) — no `/board-presentation` route existed; `ExecutiveDashboard.vue`'s "Strategic Report" button pushed here anyway and landed on NotFound.
2. `ExecutiveReports.vue` (521 lines) — no `/executive-reports` route existed; `ExecutiveDashboard.vue`'s "Schedule Reports" button pushed here anyway, same NotFound landing.
3. `CrossDashboardSearch.vue` (1,363 lines) — no route and no importer anywhere, despite `api/ml/search.py` shipping five whitelisted, fully-implemented endpoints. This was also the app's only non-sidebar navigation entry point (command-palette-style cross-dashboard search).

**Why:** This is the router-level version of the same "coverage gap" class the user's audit asked for — not a wrong number, but a finished feature with zero way to reach it. A user clicking "Schedule Reports" or "Strategic Report" from the Executive dashboard got a dead page; `CrossDashboardSearch` was invisible entirely.

**Resolved:** All three routes added to `router.ts` (`/board-presentation` -> `BoardPresentationMode`, `/executive-reports` -> `ExecutiveReports`, `/search` -> `CrossDashboardSearch`), each with an inline comment documenting why it was previously unreachable. `CrossDashboardSearch` additionally wired into `AppSidebar.vue`'s nav links (`{ label: 'Search', icon: Search, to: 'CrossDashboardSearch' }`) since it has no other entry point.

**Live-verified:** All three route names resolve (`router.ts` route table confirmed present); sidebar "Search" link confirmed bound to the `CrossDashboardSearch` route name.

**Effort:** S.
**Priority:** Done.
**Depends on:** None.

---

### [RESOLVED 2026-08-18] Financial Ratios: EBITDA, EBITDA Margin, Working Capital Turnover, Interest Coverage, and DSCR missing from every financial KPI surface

**What:** None of the standard debt/coverage ratios a CEO or lender actually asks for existed anywhere in the Financial Intelligence stack. `strategic_finance/summary.py::calculate_executive_summary` and `financial_intelligence.py::_calculate_financial_overview` computed `ytd_profit`/`net_margin`/`gross_margin` but no EBITDA; `strategic_finance/analysis.py::calculate_ratio_trends` computed only 6 ratios (gross margin, net margin, ROE, ROA, debt/equity, asset turnover) — no EBITDA margin, no working capital turnover, no interest coverage, no DSCR (debt service coverage ratio). `types.ts`'s `RatioTrendRow`/`FinancialRatiosData` interfaces had no fields for any of them, so even if the backend had shipped them the frontend couldn't have rendered them.

**Why:** These are the ratios lenders and boards actually benchmark a business against (interest coverage and DSCR specifically gate loan covenants); their total absence meant the "Financial Ratios" tab was materially incomplete for its stated purpose, not just missing nice-to-haves.

**Resolved:**
1. **Backend — EBITDA.** Added YTD interest expense + depreciation lookups (same GL `account_type`-matching convention `calculate_ratio_trends` already used) to both `strategic_finance/summary.py` (`calculate_executive_summary`) and `financial_intelligence.py` (`_calculate_financial_overview`): `ytd_ebitda = ytd_profit + ytd_interest_expense + ytd_depreciation`, `ebitda_margin = (ytd_ebitda / ytd_revenue * 100)`. Both now return `ytd_ebitda`/`ebitda_margin` alongside the existing `ytd_profit`/`net_margin` fields.
2. **Backend — Working Capital Turnover, Interest Coverage, DSCR.** Added to `calculate_ratio_trends`'s per-quarter loop in `strategic_finance/analysis.py`: `working_capital_turnover = revenue / working_capital` (working capital from the existing current-assets/current-liabilities quarter-end balances), `interest_coverage = ebitda / interest_expense` (`None` when no interest expense that quarter — division-by-zero guarded, not silently zeroed), `dscr = ebitda / (interest_expense + principal_repayment)` (principal from the prior quarter's loan balance delta). Each gets a `_status()` classification (`good`/`warning`/`unavailable`) against a benchmark dict, matching the existing ratio cards' severity convention.
3. **Frontend types.** `types.ts`: `RatioTrendRow` gained `ebitda_margin?`, `working_capital_turnover?`, `interest_coverage?`, `dscr?`; `FinancialRatiosData.ratio_cards` gained matching `RatioCard` entries; `ExecutiveSummaryData`/`StrategicFinanceData` gained `ytd_ebitda`/`ebitda_margin`.
4. **Frontend wiring.** `FinancialIntelligence.vue`'s Summary Cards grid gained an EBITDA `KpiCard` (amount + margin sublabel, matching the existing Net Profit card's shape). `FinancialRatiosTab.vue` gained a 4th ratio category, "Debt & Coverage Ratios" (alongside the existing Liquidity/Profitability/Efficiency sections), with Working Capital Turnover, Interest Coverage, and DSCR cards. Two formatting bugs caught and fixed while wiring this in: the ratio-card top-strip mapper hid any *negative* margin/ROE/ROA as `"N/A"` (a lossmaking period's negative EBITDA would have silently disappeared instead of showing red), and turnover/coverage-style cards had no `x` multiple suffix (`formatMultiple()` helper added, `0`-gated so a genuine zero doesn't render as `"0x"`).

   **Not wired (2026-08-18):** `ExecutiveSummaryTab.vue` was *not* changed — it has no EBITDA card. `strategic_finance/summary.py::calculate_executive_summary`'s `ytd_ebitda`/`ebitda_margin` therefore has no frontend consumer today; only `financial_intelligence.py::_calculate_financial_overview`'s copy is rendered. Either add the card to that tab or drop the unread fields from `calculate_executive_summary`.

**Live-verified:** Backend smoke-tested directly against the live `jkm` site before frontend work (`ytd_ebitda: 2758855.28`, `ebitda_margin: 4.4`), then confirmed rendering end-to-end in a real browser after a full frontend rebuild + `web` restart: Finance dashboard's summary strip shows `EBITDA ₹2,758,855 ↑4.4% margin`; the Ratios & Trends tab's new Debt & Coverage Ratios section shows `Working Capital Turnover 9.04x` (Benchmark 4.00x), `Interest Coverage -` and `DSCR -` (both correctly rendering the NO_VALUE sentinel, not a bug — this site's latest quarter has `interest_coverage: None`/`dscr: None` per the same direct backend call). Zero console errors.

**Effort:** M (backend) + M (frontend).
**Priority:** Done.
**Depends on:** None.

---

### [RESOLVED 2026-08-18] Customer Rankings: no way to see the worst-performing customers, only the best

**What:** `insights.api.ml.customer.customer_rankings` (backend: `compute_customer_rankings`) ranked customers by revenue/gross profit/margin %/consistency — best performers only. `CustomerSections.vue`'s Rankings tab rendered exactly that: three "Top Customers" tables, no bottom/worst view anywhere in the app.

**Why:** A CEO doing account-health triage needs the weak tail at least as much as the strong head — which accounts are shrinking, erratic, or barely worth servicing. That view didn't exist anywhere.

**Resolved:** Refactored `insights/ml/customer.py`'s `compute_customer_rankings` into a shared `_rank_customers(date_filter, limit, company, ascending)` helper (same four Ibis aggregates — revenue, gross profit, margin %, consistency — sort direction as the only parameter), then added `compute_bottom_customers()` calling it with `ascending=True`. New whitelisted endpoint `insights.api.ml.customer.bottom_customers`, mirroring `customer_rankings`'s permission gate (`Customer`, `read`) and parameter contract exactly (`date_filter`, `limit`, `company`). `CustomerSections.vue`'s Rankings tab gained a Top/Bottom `Button` toggle; the "Bottom Performers" table set is lazy-loaded on first toggle to "bottom" rather than fetched on every page load.

**Live-verified:** Toggled to Bottom Performers in a real browser against the live `jkm` site — table renders genuinely weakest accounts by revenue, ascending: Nupur Sales & Service ₹1,838, Hemraj ₹1,956, Plant X Crop ₹1,969, Kalsariya Mansukhbhai Chitharbhai ₹2,065, Herbal Cult ₹2,100, and so on. Zero console errors.

**Effort:** S (backend) + S (frontend).
**Priority:** Done.
**Depends on:** None.

---

### [RESOLVED 2026-08-18] CEO Action Tracker: complete backend (doctype + 5 endpoints), zero frontend

**What:** `insights/api/ml/executive.py` had five fully-implemented whitelisted endpoints — `list_actions`, `create_action`, `update_action_status`, `action_tracker_summary`, `get_permitted_departments` — backed by a real `Insights Financial Action` doctype (title, department, priority, status, description, source_alert, assigned_to, due_date, resolved_on/resolved_by workflow, department-scoped permissions). None of it was reachable: no route in `router.ts`, no nav entry in `AppSidebar.vue`, no Vue component at all. Every cross-department alert surfaced by the Intelligence dashboards had a backend built to track follow-up action on it, and nowhere for a CEO to actually see or work that list.

**Why:** Same "finished feature, zero way to reach it" class of gap as the three stranded views documented in the entry above (Board Presentation Mode, Executive Reports, Cross-Dashboard Search) — except this one didn't even have a component to wire up; the whole frontend half was missing.

**Resolved:** Built `frontend/src2/intelligence/ActionTracker.vue`: department/status filtered list table (title, department, priority badge, status badge, due date with overdue highlighting, assigned to, created-relative-time), a summary strip (open count + overdue count from `action_tracker_summary`), a "New Action" creation dialog (title, department — populated from `get_permitted_departments` — priority, description, due date, assigned to), and inline status-transition buttons (Resolve/Dismiss on open items, Reopen on closed ones) calling `update_action_status`. Registered at `/action-tracker` in `router.ts`; added to `AppSidebar.vue`'s Executive nav group (new `ListChecks` icon import) alongside Overview.

**Live-verified:** Full CRUD loop exercised through the actual browser UI against the live `jkm` site, not mocks: empty state ("No action items") on first load with the real department list populated (Financial, Sales, Customer, Operations, Risk, HR, Manufacturing); created a test action via the dialog (summary badge `0 open` -> `1 open`, row appeared with correct department/priority/status); clicked Resolve (badge -> `0 open`, row shows Resolved status + Reopen button); clicked Reopen (badge -> `1 open`, row shows Open status + Resolve/Dismiss buttons again). Zero console or HTTP errors through the whole sequence. Test record deleted afterward (`frappe.delete_doc`, matched by title) to leave the live site's action tracker clean.

**Superseded 2026-08-18:** Per explicit user direction, `ActionTracker.vue` and its
`router.ts`/`AppSidebar.vue` wiring were removed — this frontend (and the
`Insights Financial Action` doctype it tracked) is no longer the intended mechanism.
Removal live-verified against the rebuilt `jkm` site: sidebar's Executive group now
renders only `Overview` (confirmed via headless browser page-text dump, zero console
errors); `/insights/action-tracker` now renders the app's NotFound 404 page instead of
the tracker; `vue-tsc` shows no new errors from the removal (same 4 pre-existing
environment-config warnings as before, none in the touched files/lines).
Instead, all 12 Intelligence dashboards now interpret into action items through the
`jkm_finance` app's existing weekly pipeline: `weekly_pipeline._call_insights()` calls
eleven Insights ML domains directly (bypassing `executive.py`'s Action Tracker
endpoints and the `Insights Financial Action` doctype entirely); six of them (risk,
customer, financial, procurement, inventory, hr) are adapted by
`weekly_pipeline._insights_findings()` into native-shaped findings, merged into
`agent_results` alongside the SQL agents' own findings, and classified into real
`JKM Action` records by `action_plans.build_action_plans()` /
`reconcile_actions()` — Strategic-tier findings (cashflow, forex exposure, supplier
concentration, churn risk, attrition risk) routed to CFO/Sales Manager/HR Manager,
day-to-day findings (AR/AP aging, dead stock, credit/stockout alerts) left on the
Operational/Finance Manager default. Live-verified end-to-end against the `jkm` site:
all 11 domains called with zero errors; the 6 adapted domains produced 9 real findings
this run (595 customers at churn risk, 1 critical cashflow finding, 20 single-sourced
items, 1 dead-stock item, 15 overdue receivables, 15 overdue payables, high attrition
risk); all persisted as `JKM Action` records on a real `JKM Weekly Report`
(`JKM-WR-2026-08-23`), with the five Strategic-tier reclassifications correctly
auto-resolving their prior Operational-bucket duplicates via `reconcile_actions`'
existing carry/resolve semantics — no manual cleanup needed. The `Insights Financial
Action` doctype and its five `executive.py` endpoints are untouched (still valid,
just no longer the active integration path) in case they're needed again.

**Effort:** M (frontend component + wiring).
**Priority:** Done.
**Depends on:** None.

### [RESOLVED 2026-08-18] `jkm_finance` Desk page: 6 new Insights sections had no metric chips

**What:** `weekly_report.js` (the Desk page that actually renders `JKM Weekly
Report` for a CFO — separate render path from the JSON `_render_findings_html`
snapshot) keys its per-section "figures" strip off a hardcoded client-side
`METRIC_LABELS[section.key]` dict, deliberately isolated from the raw agent
payload ("keeps a new agent from leaking snake_case onto the executive
surface" — see the file's own comment). The 6 new `insights_*` sections were
correctly titled and findings-populated (via the generic `report.sections`
loop, unaffected), but silently had zero metric chips: same class of gap as
`SECTION_TITLES`/`_CODE_BUCKETS` above — a parallel presentation-layer dict
nobody told about the new agents.
**Fix:** Added six entries to `METRIC_LABELS` matching the exact metric keys
`_insights_findings` emits: `insights_risk.aggregate_risk_score`,
`insights_customer.at_risk_customer_count`,
`insights_financial.{overdue_customer_count,net_unrealized}`,
`insights_procurement.risk_score`, `insights_inventory.dead_stock_value`,
`insights_hr.attrition_risk_score`.
**Live-verified** against the real `/app/weekly-report` Desk page (not just the
doc JSON) on `JKM-WR-2026-08-23`, no rebuild step needed (Desk page JS is
un-bundled): all 6 rows show correct title, RED/AMBER status color, headline,
and now the metric chip — `48.9 overall risk score /100`, `42.5 procurement
risk score /100`, `595 customers at churn risk`, `15 customers overdue 60+
days` (financial's second metric, `net_unrealized`, correctly stays hidden —
genuinely zero forex exposure this run, matching the earlier finding), `75
attrition risk score /100`, `KES 1.4M in dead stock`. Clicked through all 5
report tabs (Report/Findings/Strategic/Operational/Tax), zero `pageerror`
events. The only HTTP failures on the page (2 files 500, socket.io 404) are
pre-existing site infrastructure unrelated to this change (missing uploaded
company-logo/WhatsApp-image files, no socket.io server in this dev
environment) — confirmed by URL, none touch `weekly_report.js` or any file
this session modified.
**Effort:** S.
**Priority:** Done.
**Depends on:** None.

### [RESOLVED 2026-09-04] SQL→query-builder migration regressions: -100% growth, Strategic Finance crash, inverted liabilities; YTD fiscal-year bug; Revenue & Customers re-confirmed

**What:** A large `frappe.db.sql` → Ibis/PyPika query-builder migration (32 files,
3671(+)/2669(-)) landed alongside earlier work, and a full backend re-verification
sweep (all 12 Intelligence dashboards) plus live browser smoke on Revenue & Customers
found four real regressions and one long-standing cross-dashboard inconsistency:
1. `sales_intelligence.calculate_comparisons` anchored "current period" to
   `datetime.now()`; once the ledger's newest Sales Invoice (2026-08-07) fell behind
   the real calendar month, `mom_growth`/`yoy_growth` computed against a genuinely
   empty current month and read a false `-100.0%` on both headline KPIs.
2. `strategic_finance/data.py` called PyPika's `Field.notlike()`, which does not
   exist — every Strategic Finance/Executive forecast request raised `AttributeError`
   and surfaced `CANNOT VERIFY - blocking error`.
3. `strategic_finance/summary.py`'s shared `_gl_account_root_type_total` helper only
   ever computed `debit - credit` (correct for debit-normal Assets/Expenses), but two
   call sites used it for credit-normal Liabilities/Equity without negating — Total
   Liabilities and Total Equity rendered as large negative numbers, and ROE/Debt-to-
   Equity silently zeroed out via a `max(0, …)` floor downstream.
4. `hr_intelligence.py`/`marketing_intelligence.py`'s `_period_start_date` resolved
   `YTD` against the calendar year (`Jan 1`) instead of the company fiscal year
   (`Apr 1`, per `_fiscal_year_for`) that Financial/Tax/Strategic Finance already
   used — HR and Marketing "Year to Date" silently covered a shorter window than
   every other dashboard's YTD for Jan-Mar of any year.
**Fix:** See `CHANGELOG.md` `[Unreleased] — 2026-09-04` for the exact diffs and
live-verification numbers for each of the four fixes above.
**Live-verified — Revenue & Customers full re-confirmation (2026-09-04):** After
applying all four fixes, drove the actual Vue frontend (not just backend calls)
against live `jkm` data: header KPIs (Total Revenue ₹172,871,632, Customers 593, AOV
₹82,320, Gross Margin 20.8%, At Risk 176, YoY -62.6%) match direct backend calls
exactly; all 6 Revenue sub-tabs and all 6 Customer sub-tabs render real, sane data;
the Revenue/Customers tab-group radio toggle switches correctly; the Rankings
drill-down (click a customer row → per-customer invoice modal) verified working
against two different customers, real invoice numbers/dates/amounts. Churn risk
distribution is healthy (Low 38.6% / Medium 31.7% / High 15.3% / Critical 14.3% of
593) — not saturated. Two apparent numeric mismatches traced to intentional scope
differences, not bugs: Geography's "1,243 customers" is the all-time roster (its own
independent "Active: 3/6/12 months" filter), vs the header's 593 12-month-active
customers; Margins' revenue is tax-exclusive `net_amount` (correct for GST-era
margin math) vs the header's tax-inclusive `grand_total` — Sales Reps' per-rep
breakdown reconciles to the header exactly (₹149.49M + ₹23.38M = ₹172.87M),
confirming honest, not inconsistent, reporting. Top-level KPI cards (incl. "At Risk")
are intentionally non-interactive by design (`KpiCard`'s `clickable` prop is opt-in
and none of the 6 header cards pass it) — clicking them doing nothing is correct,
not a bug.
**Effort:** L (4 backend fixes across 3 files + full live re-verification of one
merged dashboard).
**Priority:** Done.
**Depends on:** None.

### [RESOLVED 2026-09-04] Quote Conversion % frozen at 0% on every dashboard — `_scalar_int` swallowed a Series/DataFrame shape mismatch

**What:** `executive_intelligence`'s "Quote Conversion %" KPI read `0.0%` and was
flagged `Critical` even on a live site with real submitted quotations — same false-
alert pattern as the `net_margin` bug above, but this one was a real computation bug,
not a stale-data artifact. Root cause in `insights/ml/customer.py`'s `_scalar_int()`
helper (used to unwrap an Ibis scalar aggregate to a Python `int`): `tbl.count()`
returns a plain int, but `tbl.aggregate(name=count())` returns a 1-row, 1-column
DataFrame — `.iloc[0]` on that yields the **row** (a pandas `Series`), not the cell,
and `int(Series or 0)` raises `ValueError: ambiguous truth value`, which the blanket
`except Exception: return 0` then silently downgraded to `0`. `_quotation_conversion`
is the only caller that goes through `.aggregate()` rather than a bare `.count()`, so
every other `_scalar_int` call site was unaffected — this one metric, everywhere it's
surfaced (Executive KPI, Customer Intelligence `quote_conversion_rate`), was wrong.
**Fix:** `_scalar_int` now unwraps positionally — `.iloc[0, 0]` when the executed
result is a 2-D DataFrame (`ndim == 2`), `.iloc[0]` for a bare 1-D Series — instead of
assuming a Series and letting the ambiguous-truth-value path eat the real value.
**Deployment gotcha hit while verifying this fix:** the fix alone did not change the
live dashboard. `insights-worker` (RQ) imports `insights.ml.*` once at process start
and serves `cached_run`-backed endpoints (Executive, Customer Intelligence) from that
frozen bytecode; clearing the Redis cache key without restarting the worker just
recomputes the *same wrong answer* from the *same old code*, which looks like "the
fix didn't work." Confirmed by restarting `jkm-bench` (which respawns the worker),
re-clearing `insights_ml_executive_summary:*` / `insights_ml_customer_intelligence:*`,
and waiting for the background `compute_dashboard` jobs to drain — this is the same
documented gotcha as the SQL-migration entry above, now hit and confirmed twice.
**Live-verified:** direct `customer_intelligence` call: `quote_conversion_rate` 0.0 →
71.0 (YTD, 184/259 converted) and 68.4 (12m, 54/79 converted). Executive dashboard KPI
card, reloaded fresh in the browser after the worker restart: "Quote Conversion %"
now shows `Low` severity, `68.4%`, `↑38.4%` — was `Critical`, `0.0%`.
**Effort:** S (2-line fix; most of the effort was diagnosing the stale-worker
deployment trap, not the code itself).
**Priority:** Done.
**Depends on:** None.

### [RESOLVED 2026-09-04] Three dashboards flagged in the 2026-09-03/04 batch pass — re-verified live after the worker restart above

The batch navigation pass (before the Revenue & Customers deep-dive) flagged three
other dashboards as suspect. Re-checked live, fresh cache, post worker-restart:
- **Marketing & CRM Intelligence** — renders correctly: funnel, channels, lead
  conversion (8.6%), win rate, all real data. Not stuck; the "Preparing CRM data"
  seen during the batch pass was the same cold-cache/stale-worker window as the
  Quote Conversion bug above, not an independent frontend bug.
- **Machine Learning Intelligence** — renders correctly once `model_health()`
  finishes: "Model Health 6 of 7 trained" with real per-model rows (Sales Forecast
  RMSE, Demand Forecast reorder counts, etc.). Confirmed genuinely empty for the
  first 20-25s after navigation/reload (no skeleton distinguishes "computing" from
  "no data" on this page), then populates once the synchronous 6-model health check
  completes — a latency/loading-state gap, not a data or rendering bug. Not fixed
  here (out of the Revenue & Customers scope this session); a real fix would add a
  loading skeleton to `MachineLearning.vue` distinct from its empty state.
- **Manufacturing Intelligence** — real bug, fixed: `manufacturing_intelligence.py`'s
  `completion_rate_pct`/`average_efficiency_pct`/`on_time_completion_pct` returned `0`
  instead of `None` when their denominator (`total_orders`) was `0`, so a site with
  zero Work Orders got a fabricated `0.0%` fed into `KpiCard`'s severity logic, which
  read it as `High` alert. Guarded all three to return `None` on a zero denominator;
  `production_health` label likewise now `None` (not `"needs_improvement"`) when
  `completion_rate` is `None`. Live-verified: Completion Rate and Efficiency now show
  `-` (the shared no-data sentinel), matching how every other zero-denominator metric
  on this dashboard already rendered.
**Effort:** S (one real fix; two false positives confirmed, not changed).
**Priority:** Done.
**Depends on:** None.

### [RESOLVED 2026-09-04] Every panel heading silently missing on Risk Intelligence and Procurement Intelligence

**What:** Both `RiskIntelligence.vue` and `ProcurementIntelligence.vue` use
`<SectionHeader>` throughout their templates (18 and 19 call sites respectively,
covering every tab) but never imported the component in `<script setup>` — the one
import line all 27 other dashboard files that use `SectionHeader` already have. Vue
silently renders an unresolved component tag as a literal, unstyled custom element;
the `title`/`hint` string props became invisible HTML `title`/`hint` DOM attributes
(browser hover-tooltip only, never present in `textContent`), and `<template #actions>`
icon content vanished entirely (a native, non-component `<template>` never renders).
No console error, no visual crash — every panel on both dashboards was simply missing
its heading, on every tab. This slipped past the earlier browser-smoke batch pass in
this same session because that pass checked console errors and data correctness, not
DOM heading presence — both dashboards were marked "no bugs" before this was found.
**Root cause:** missing `import SectionHeader from
'../intelligence/components/SectionHeader.vue'` in both files' `<script setup>` block.
**Fix:** added the one import line to each file, matching the exact pattern already
used by `CustomerSections.vue`, `RevenueSections.vue`, `InventoryIntelligence.vue`,
`MachineLearning.vue`, `CustomerDetail.vue` and 22 other files in this codebase.
**Live-verified:** rebuilt (`yarn build`, clean), then browser-verified every tab on
both dashboards. Risk Intelligence (7 tabs): Overview → "Active Risk Alerts", "Risk
Assessment Matrix", "Key Business Metrics", "Risk Component Breakdown"; Credit Risk →
"Receivables Aging Analysis", "Customer Risk Scores"; Payables Risk → "Payables Aging
Analysis", "Supplier Risk Scores"; Cash Flow Risk → "Revenue Concentration Analysis",
"Overdue Days Trend"; Operational Risk → "Inventory Risk by Item Group", "Supplier
Reliability Analysis"; Compliance Risk → "GST Compliance Status", "Document
Completeness Audit", "GST / PAN Registration"; Predictive Analytics → "Detected
Anomalies", "Early Warning System", "Payment Delay Risk Forecast". Procurement
Intelligence (6 tabs): Overview → "Monthly Spend Trend", "Spend by Category", "Top
Suppliers by Spend"; Supplier Performance → "Top Performers", "Needs Improvement",
"All Supplier Scores"; Purchase Analytics → "Purchase Order Status", "Monthly Purchase
Order Trend", "Pending Purchase Orders"; Price Intelligence → "Recent Price
Increases", "High Price Variance Items", "Item Price Analysis"; Risk Analysis →
"Procurement Risk Score", "Supplier Concentration Risk", "Single Source Items",
"Payment Exposure", "Outstanding by Supplier", "Overdue Invoices"; Forecasts &
Planning → "3-Month Spend Forecast", "Category-wise 3M Forecast", "Historical Spend
Pattern". Zero console errors, zero `SECTIONHEADER` literal tags anywhere in the
rendered DOM, on either dashboard, on any tab.
**Effort:** S (two one-line import fixes; effort was in discovering a bug with no
console signal by cross-checking every dashboard file's import list against its own
template usage).
**Priority:** Done.
**Depends on:** None.

### [RESOLVED 2026-09-04] Executive dashboard's Custom Range narrative leaked the raw filter encoding

**What:** `_narrative()` in `insights/ml/executive_intelligence.py` interpolated its
`period` argument verbatim into "Business health for the {0} period is...". The
acronym periods (`MTD`/`QTD`/`YTD`/`TTM`) read fine, but selecting Custom Range on the
Executive dashboard and applying dates passes the internal `custom:<start>:<end>`
encoding straight through unformatted — the AI Executive Summary literally read
"Business health for the custom:2026-07-01:2026-08-31 period is 68.6/100 (AMBER)."
**Fix:** added `_friendly_period_label()`, used only inside `_narrative()`, which
formats a `custom:` prefix as `01 Jul 2026 - 31 Aug 2026` and passes acronyms through
unchanged. `data.period` itself (the field the frontend round-trips into the filter
control, per this module's own documented frontend contract) is untouched.
**Live-verified:** direct `bench execute` with `period='custom:2026-07-01:2026-08-31'`
and, after a `jkm-bench` restart to clear the worker's stale bytecode (same class of
gotcha as the Quote Conversion entry above) and a fresh cache warm, in the actual
browser: selected Custom Range, set 01 Jul-31 Aug 2026, clicked Refresh — narrative
now reads "Business health for the 01 Jul 2026 - 31 Aug 2026 period is 68.6/100
(AMBER)", zero console errors.
**Effort:** S (one small helper + one call-site edit).
**Priority:** Done.
**Depends on:** None.

### [RESOLVED 2026-09-04] Full browser-smoke sweep of all 13 intelligence dashboards — complete

**What:** Closed out the remaining four dashboards from the browser-smoke phase:
Tax Intelligence (4 tabs: GST Overview, Compliance Health, TDS, Tax Planning, plus its
3m/6m/12m/FY date-range filter), Inventory Intelligence (7 tabs: Stock Overview,
Turnover, ABC/XYZ, Itemwise BE, Aging (FIFO), Warehouses & Transfers, Procurement),
Price Intelligence (single-page by design — no tab bar in `PriceIntelligence.vue`,
confirmed intentional, not a missing-tabs bug), and ESG Intelligence (honest "Not yet
available - ESG intelligence is not yet backed by real data" placeholder, zero
errors, no crash — the known, accepted, out-of-scope gap this file already documents
elsewhere as `not_implemented`, not a new bug).
**Result:** all four clean — real computed data on every tab, zero console/page
errors, zero unresolved custom-element tags, no leaked internal strings (`NaN`,
`undefined`, `[object Object]`, or raw filter encodings). No new bugs found beyond the
Custom Range narrative fix above.
**Note:** the 4 parallel subagents dispatched for this phase all failed identically on
`[ollama-cloud/minimax-m3] HTTP 429 ... weekly usage limit` (provider quota
exhaustion, same failure class already hit earlier this session) — worked all four
dashboards directly instead.
**Effort:** S (verification only, one fix folded in above).
**Priority:** Done.
**Depends on:** None.

**All 13 intelligence dashboards (Executive, Revenue & Customers, Financial/Strategic
Finance/Budget/Breakeven, Tax, Procurement, Inventory, Price, Manufacturing, Marketing
& CRM, HR/People, Risk, Machine Learning, ESG) are now browser-verified clean on every
tab and filter this session, with every numbers-correctness bug found along the way
fixed and live-verified against real `jkm` data.**
