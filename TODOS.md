# TODOS

## ML Intelligence Layer (plan-eng-review, 2026-08-04)

### Implement real breakeven_engine.predict()

**What:** `breakeven_engine.py::BreakevenEngine.predict()` returns `{"status": "not_implemented"}` — an honest stub, not a bug, but a real capability gap.

**Why:** The break-even API surface (item/employee/cash-flow/capital-efficiency) is otherwise real; `predict()` is the one method left unimplemented.

**Context:** Surfaced during plan-eng-review's fabricated-data triage (D3.3). Unlike the ESG/predictive-analytics modules, this one already does the right thing (explicit not_implemented instead of a plausible-looking fake number) — just needs the actual implementation.

**Effort:** M
**Priority:** P3
**Depends on:** None

### Decide fate of budget variance placeholder methods

**What:** `budget_variance_intelligence.py` has 4 methods (`get_forecast_data`-adjacent helpers) returning empty lists/zeroed dicts (forecast accuracy, allocation efficiency, performance metrics) instead of computing them.

**Why:** These degrade gracefully to "no data" (0/empty) rather than a plausible-looking fake number, so the immediate risk is lower than the ESG/predictive cases — but the API surface still advertises fields it can't fill.

**Context:** Surfaced during plan-eng-review's fabricated-data triage (D3.4). Accepted as lower-risk and deferred rather than fixed inline. Someone needs to decide whether to implement, honest-stub (like breakeven_engine), or remove these fields from the response shape.

**Effort:** M
**Priority:** P3
**Depends on:** None

### Build or remove Search Activity Log / Search Favorite doctypes

**What:** `cross_dashboard_search.py::get_search_history` / `save_search_favorite` reference `"Search Activity Log"` and `"Search Favorite"` doctypes that do not exist anywhere in this bench (verified via repo-wide grep across every installed app).

**Why:** Both whitelisted endpoints raise a DocType-not-found error at runtime today — search history and favorites are 100% non-functional in production, silently (same failure shape as the general.py dead-import bug fixed in this same review).

**Context:** Surfaced during plan-eng-review (code-quality finding 2). The IDOR fix applied in the same review (removing the caller-supplied `user` override) is correct and independent of this gap — it's still correct once the doctypes exist. Someone needs to decide: build the 2 doctypes (JSON + migration + permissions, ~1-1.5h), or remove the 2 dead endpoints from the API surface.

**Effort:** M
**Priority:** P2
**Depends on:** None

### Audit remaining unconditional `.train()` calls for cache-bypass bugs

**What:** Performance finding 1 (fixed in this review) found `sales.py`'s 6 dashboard-read endpoints unconditionally retraining instead of reading cache. A grep for `= model.train()` across `api/ml/` still shows standalone (non-conditional) train() calls in `customer.py:28`, `inventory.py:28,66,82`, `financial.py:37`, `procurement.py:52`, `sales.py:150`, `tax.py` (a few).

**Why:** Some of these are almost certainly intentional (`train_*`-prefixed endpoints meant to always retrain on explicit user action) — but not all were individually verified in this review pass; the sales.py case looked identical in shape and turned out to be a real bug.

**Context:** Surfaced while fixing Performance Finding 1. Each remaining instance needs the same 30-second check applied to sales.py: is this endpoint meant to be a cheap dashboard read (→ should use `.predict()` with cache-first behavior) or an explicit "retrain now" action (→ `.train()` is correct as-is)?

**Effort:** S
**Priority:** P2
**Depends on:** None

### Retrofit fetch/compute/present split across intelligence modules (going-forward pattern)

**What:** 25+ `*_intelligence.py` classes follow the same shape as the original `get_marketing_overview` (now partially extracted in this review): one large method mixing SQL fetch, computation, and response assembly.

**Why:** Makes unit testing hard without a live DB — explains why `insights/ml/` (26k LOC) has only ~64 tests. `get_marketing_overview`'s funnel + alert logic was extracted into standalone, unit-tested pure functions in this review (see `test_marketing_analytics.py`) as a proof of the pattern.

**Context:** Plan-eng-review code-quality finding 1. Full retrofit across all 25+ classes was explicitly out of scope for this review (disproportionate effort vs. the review's actual goal). Apply the split to new intelligence modules going forward; retrofit existing ones opportunistically when touched for other reasons, not as a dedicated project unless prioritized.

**Effort:** XL
**Priority:** P4
**Depends on:** None


### Audit executive_intelligence's other cross-domain aggregators for the same leak

**What:** `get_department_insights` was fixed to gate per-requested-department (outside-voice finding 2), but `get_executive_summary`/`get_executive_kpis`/`get_executive_insights`/etc. call `ExecutiveIntelligence.get_executive_summary()`, which internally aggregates financial (GL Entry), sales, customer, HR (Salary Slip), and manufacturing data via raw SQL in one call — still gated on a single `"Sales Invoice"` check.

**Why:** A user with only Sales Invoice read can still pull the executive summary's HR/finance/manufacturing rollup numbers (just not the department drill-down, which is now correctly gated). Lower severity than the drill-down case since it's aggregate/rollup data rather than raw records, but the same class of gap.

**Context:** Outside-voice (independent second-pass review) finding 2. Fixing this properly means either checking permission on all constituent doctypes before returning the summary, or redesigning `get_executive_summary` to omit sections the caller can't see — real design work, not a one-line fix like the department-insights case.

**Effort:** M
**Priority:** P1
**Depends on:** None

### Fix trainMLModels button: honest stub silently reports false success

**What:** `Dashboard.vue`'s `trainMLModels()` button (line ~396, `frontend/src2`) calls `insights.api.ml.get_dashboard_data`, then unconditionally shows "ML Models Updated — Predictions are now available" on any non-throwing response. Before this review's fix, `get_dashboard_data` threw (dead import → error envelope → thrown exception → accurate "Training Error" toast). After the fix (`general.py`'s honest `not_implemented` stub), the call now returns HTTP 200 `{"status": "success", "data": {"status": "not_implemented", ...}}`, which the frontend's `apiCall`/`readInsightsEnvelope` treats as success — the button now falsely claims success.

**Why:** This is a real user-facing regression introduced by making the backend honest (the frontend was, bizarrely, relying on the backend's brokenness to show an accurate error). Also worth asking whether `trainMLModels()` is even wired to the right endpoint — `get_dashboard_data` doesn't train anything; `run_all_models` is the actual training trigger.

**Context:** Outside-voice finding 6. Two possible fixes: (a) frontend checks `response.data.status === "not_implemented"` and shows an accurate message, or (b) rewire the button to call `run_all_models` (the endpoint that actually trains), which is what its label implies it should do. Needs a frontend change either way — out of scope for this backend-focused review pass.

**Effort:** S
**Priority:** P1
**Depends on:** None

### Frontend has zero awareness of `status: not_implemented`

**What:** This review converted ~10 fabricated-data endpoints to honest `{"status": "not_implemented"}` stubs. Grep of `frontend/src2` for `not_implemented`: zero matches anywhere.

**Why:** Dashboards consuming these stubs (e.g. ESGIntelligence.vue) render them as a normal-but-empty successful payload rather than surfacing the backend's explanatory `message` field — looks like "no data yet" rather than "not built yet" to the end user.

**Context:** Outside-voice finding 8, related to the trainMLModels item above but broader (affects every stubbed endpoint's dashboard, not just the one button). A shared frontend helper that checks for `status === "not_implemented"` and renders a consistent "not available" state (using the `message` field) would close this across all affected dashboards in one place.

**Effort:** S
**Priority:** P2
**Depends on:** None

### FinancialIntelligence.vue doesn't surface permission errors distinctly

**What:** `FinancialIntelligence.vue:538-555` calls `insights.api.ml.breakeven.breakeven_summary` via a raw `createResource` with a generic `onError` ("An error occurred while loading break-even data") — no `isPermissionError`/`exc_type` check, unlike pages built on `useIntelligenceDashboard`.

**Why:** A user newly blocked by this review's added `has_permission` gates gets a vague failure message instead of an actionable "you don't have access to X" message.

**Context:** Outside-voice finding 9. Likely affects other raw-`createResource` callers beyond this one page — worth a quick audit of which frontend pages use `useIntelligenceDashboard` (permission-error-aware) vs. raw `createResource` (not) now that more endpoints can return 403s than before this review.

**Effort:** S
**Priority:** P2
**Depends on:** None

### Minor: run_all_models permission gate doesn't cover everything it triggers

**What:** `general.py`'s `run_all_models` gates on `"Sales Invoice", "write"`, but `scheduler.run_all_ml_models()` also trains Customer- and Item-scoped models (segmentation, ABC/XYZ, demand forecast, product recommendations).

**Why:** Technically under-scoped, but currently unreachable except by direct API call — not wired to any frontend button and not on the actual cron schedule (`hooks.py` uses `run_daily_intelligence`, a different function).

**Context:** Outside-voice finding 10. Low urgency given no live caller; worth fixing if this endpoint is ever wired up.

**Effort:** S
**Priority:** P3
**Depends on:** None

### customer_intelligence train() is borderline slow (32s)

**What:** `CustomerIntelligence().train()` measured at 32.1s against production-scale data (live-tested during the 2026-08-04 production incident diagnosis). Not broken, but close enough to common gunicorn worker timeouts (often 30-60s) to be worth tightening if the timeout is on the low end.

**Why:** Currently mitigated by daily scheduled pre-warming (`run_daily_intelligence`), so real user requests should hit cache via `predict()`, not this cold path. But any cache miss (deploy, TTL expiry, cache flush) hits this 32s cost directly.

**Context:** Surfaced while diagnosing the `insights.api.ml.procurement_intelligence` 502 production incident (2026-08-04) — procurement's `_analyze_purchase_cycles` had a combinatorial-explosion query (fixed, was 300s+, now ~2s) that was almost certainly the dominant driver of the incident (holding DB connections/locks long enough to starve concurrent requests to sales/customer/executive endpoints too, all reported failing simultaneously). customer_intelligence wasn't broken, but its 32s is worth profiling per-query the same way procurement was, in case there's a similar avoidable cost.

**Effort:** S (profiling) / M (fix if found)
**Priority:** P2
**Depends on:** None