# Changelog

Notable changes to the intelligence dashboard surface of this fork. Values quoted as
`before → after` were measured against the JKM Chemtrade ledger (INR, Indian fiscal year
Apr–Mar), not estimated.

## [Unreleased] — 2026-08-07e

### Added — dashboards warm themselves on install and migrate

- `after_install` / `after_migrate` now enqueue
  `insights.ml.scheduler.warm_dashboard_caches` directly — the hook equivalent of
  `bench --site <site> execute insights.ml.scheduler.warm_dashboard_caches`, so no
  operator has to remember it after a deploy. It runs on a worker, so a migration never
  blocks on it.
- **It is queued ahead of the full training pass.** `after_migrate` previously enqueued
  only `run_daily_intelligence`, which trains six models before it warms anything, so
  dashboards stayed cold for the length of that job. The short targeted warm now goes
  first; the full pass still follows on `long`.
- **Both migrate jobs are now reaped before enqueueing.** They use fixed job ids with
  `deduplicate=True`, which meant a job left `STARTED` by an OOM kill or a deploy would
  silence every later migration — `frappe.enqueue` returns without queueing and the
  migration still reports success. `reap_dead_job` was generalised to take a raw job id
  so the migrate hook gets the same protection as the dashboard keys.

Verified with a real `bench --site jkm migrate`: both ids absent beforehand; afterwards
`insights_warm_dashboard_caches` **STARTED** with `insights_warm_intelligence` **QUEUED**
behind it, and on completion (`FINISHED`) all five keys — `sales_intelligence:12m`,
`customer_intelligence:12m`, `executive_summary:YTD`, `executive_summary:MTD`,
`procurement_intelligence` — **PRESENT**.

## [Unreleased] — 2026-08-07d

The reason "still being computed after 300s" survived three rounds of fixes: the code
that was supposed to explain the failure could never run.

### Fixed — the failure diagnosis was dead code

- **`_diagnose` double-namespaced the job id.** It called
  `get_job_status(create_job_id(_job_name(key)))`, but `get_job_status` → `get_job` →
  `Job.fetch(create_job_id(job_id))` already namespaces. The lookup asked redis for
  `jkm||jkm||insights_async_sales_intelligence_12m`, which never exists, so the helper
  **always returned `None`** and every `failed` branch below it was unreachable. Whatever
  went wrong on the server, the client got the generic 5-minute timeout. Measured:
  single-namespaced → `JobStatus.QUEUED`, double-namespaced → `None`.

### Fixed — a dead worker wedged a key permanently

- **`deduplicate=True` refuses to re-queue behind a corpse.** `frappe.enqueue` returns
  *silently* when a job with the same id is `QUEUED` or `STARTED`
  (`background_jobs.py:120-129`). A work-horse killed by OOM, a supervisor restart, or a
  deploy leaves its job `STARTED` in redis forever, so every later request enqueued
  nothing, answered `queued` anyway, and polled out at 300s — permanently, for that key.
- `serve()` now reaps first: it runs rq's own `started_job_registry.cleanup()`, then
  deletes any job still claiming a `worker_name` that is not in `Worker.all()`. It also
  checks whether a job actually exists after enqueueing, and reports an error rather than
  answering `queued` when deduplication silently skipped it.
- `_diagnose` now covers the states it previously fell through: **failed** (with the real
  exception line), **started with a dead worker**, and **queued with zero workers** — each
  clearing the `running` flag so the next poll re-queues instead of waiting out the 15
  minute `STATE_TTL`.

Verified against a job forced into each state: dead-worker wedge → *"The worker computing
this dashboard stopped unexpectedly. Retry to recompute it."* with the flag cleared, and
the next `serve()` re-queues. A genuinely live job is still left alone. Happy path
unchanged: `sales_intelligence` **6.0s**, `procurement_intelligence` **8.0s** end to end.

## [Unreleased] — 2026-08-07c

### Fixed — "Unknown or expired job key."

- **A warm cache could be refused to the client holding its key.** `async_status`
  resolved a key's required permission *only* from a Redis `META` entry written by
  `serve()`, and checked it **before** looking at the result. Any path that filled
  `RESULT` without going through `serve()` — notably `warm_dashboard_caches`, which
  calls `run()` directly — left a valid payload with no META, and the poll was rejected
  with `PermissionError: Unknown or expired job key.` The same happened once META's 24h
  TTL lapsed while the daily warm kept `RESULT` fresh indefinitely. Reproduced with
  `RESULT present / META absent` on all four dashboard keys.
- Which doctype guards a dashboard is a **static property of that dashboard, not cache
  state**, so it now lives in code as `KEY_PERMISSIONS` (keyed on the prefix before the
  first `:`). META remains a fallback for keys an extension registers at runtime, and
  `warm_dashboard_caches` records it as well. An unrecognised key is still refused, so
  the endpoint cannot be used to read arbitrary cache entries — verified both ways.

## [Unreleased] — 2026-08-07b

Follow-up to the entry below, after Revenue & Customers still timed out at 300s and
Procurement returned a gateway error. Both surfaces are now aligned to the same Frappe
background-job contract instead of each improvising.

### Changed — queue selection now follows Frappe's contract

- **`default` was the wrong queue, and the previous entry chose it.**
  `frappe.utils.background_jobs.get_queues_timeout()` budgets `short=300`, `default=300`,
  `long=1500`, and merges custom queues declared in `common_site_config.json` under
  `workers`. Parking a multi-minute dashboard compute on `default` with a 900s timeout
  starves the framework's own default-queue work — emails, notifications, doc events —
  which is the same head-of-line problem as before with a different victim.
- `async_compute` now resolves its queue at runtime: a dedicated **`insights`** queue
  when the operator has declared one, otherwise **`long`**, with the timeout read from
  the queue's own configured budget rather than a hardcoded number. Resolving against
  the live registry means an undeclared queue can never silently swallow jobs.
- To get real isolation from the nightly trainer, declare the queue in
  `common_site_config.json` and re-run `bench setup supervisor`:

  ```json
  { "workers": { "insights": { "timeout": 1500, "background_workers": 2 } } }
  ```

  Without it the fallback is `long`, which is correct but shares a worker with
  `run_daily_intelligence`. `worker_health()` now reports `dedicated: true|false` so
  `queue_health` answers "is this configured?", not just "is it busy?".

### Fixed — Procurement returned a gateway error

- **`procurement_intelligence` was the last heavy dashboard still computing inline.**
  It ran `model.predict()` on the request path, so a cold cache outlived the gateway
  timeout and reached the browser as a 502 — reported as *"The server did not return a
  response (gateway error)"*. It now queues through `async_compute.serve` like every
  other heavy dashboard, keeping its flat `{status, spend_overview, …}` envelope so the
  decoder path is unchanged.
- **The Procurement page could not have consumed a queued answer anyway.** It used
  `createResource`, which has no poll loop, so a `{status: "queued"}` envelope would have
  rendered as data. Switched to `apiCall`, which owns polling and transport-error
  translation for every other dashboard. **`502 → resolves in 10.0s`**.
- `ProcurementIntelligence.predict()` gained the same `allow_train` guard as sales and
  customer, and `procurement_intelligence` joined `DASHBOARD_CACHE_TARGETS` so the daily
  job warms it too.

### Note on the previous entry's verification

The 2026-08-07 reproduction called `warm_dashboard_caches()` directly and never exercised
enqueue → worker → cache. A follow-up test that did appeared to hang for the full 300s,
which looked like the reported bug; it was an artefact of the harness. `frappe.cache()`
memoises reads into `frappe.local.cache`, so a single long-lived process never observes a
worker's write. Real browser polls are separate requests and are unaffected. With the
cache dropped per poll, both surfaces resolve in **10.0s** end to end.

## [Unreleased] — 2026-08-07

Overview and Revenue & Customers took minutes to load, or timed out. Neither page ever
blocked a web worker — both queue and poll — so the wait was entirely background work
that should not have been happening at all. Three independent defects stacked into one
symptom.

### Fixed — dashboard latency

- **`predict()` silently retrained on a cache miss.** `SalesIntelligence.predict` and the
  customer equivalent fell through to `self.train()` whenever `get_cached_results` missed
  its 24h window, so a "prediction" became a full training pass. Measured cold:
  `get_business_health_score` **42.6s**, `strategic_finance_intelligence` **59.6s**,
  `at_risk_customers` **21.5s** — against **0.8s / 0.0s / 0.1s** warm. Training is now
  opt-in via `allow_train`, which only the worker-side `_compute_*` entry points pass;
  request-path callers get a `warming` envelope instead: **60s block → 0.00s**.
- **Interactive computes shared the nightly trainer's queue.**
  `insights.ml.scheduler.run_daily_intelligence` is enqueued on `long` with a 3600s
  timeout, and production runs one worker per queue, so a dashboard request landing
  behind it waited out the entire training pass and blew the frontend's 5-minute poll
  ceiling. `async_compute.QUEUE` is now `default`; `JOB_TIMEOUT` **3600 → 900s**, since
  the client stops polling at 300s and a payload needing longer is a bug, not a slow
  query.
- **The daily warm-up populated a cache nothing reads.** It called
  `ExecutiveIntelligence().get_executive_summary(period)` directly, filling the
  model-level key `executive_summary:<period>` on a **1-hour** TTL. The dashboards read
  `insights_async:result:executive_summary:YTD` on a **24-hour** TTL, written only by
  `async_compute.run`. Two caches, different keys, different lifetimes — the warm step
  missed the served key and expired an hour later regardless. New
  `warm_dashboard_caches()` drives `async_compute.run` over all six keys the pages
  actually read: **6/6 warmed in 9.98s**, each target isolated so one failure cannot deny
  the rest their cache.

### Fixed — data correctness

- **`get_business_health_score` returned `{}` on every call.** It read
  `summary.get("business_health", summary.get("health_score", {}))`; the summary emits
  **`business_health_score`**, so neither name ever matched: **`{}` → `overall_score:
  57.0, overall_rag: "red"`** with the seven department scores. It also rebuilt the whole
  executive summary inline just to pluck that one field, and now shares the cached
  `executive_summary:YTD` payload that Overview already loads.

### Operational note

These changes remove the cold-compute cliff but do not substitute for the scheduler. If
`frappe.utils.scheduler.is_scheduler_inactive` reports `True`, `run_daily_intelligence`
never fires and no cache is ever warmed ahead of a visitor. The queue change also assumes
a `default` worker is running — confirm with
`insights.api.ml.async_compute.worker_health` after deploying.

## [Unreleased] — 2026-08-02

A correctness and consolidation pass over the 11 domain dashboards. The theme running
through most of it: **an absent measurement was being rendered as a confident one.** A
dashboard that reports zero when it means "no data" is worse than one that reports
nothing, because a reader cannot tell the difference and acts anyway.

### Security

- **Stored XSS in AI chat and recommendation rendering.** Markdown was passed to `v-html`
  with a hand-rolled converter that emitted raw HTML by design, so any string persisted
  server-side and echoed into a chat panel executed in every reader's session.
  Sanitisation is now centralised in `utils/markdown.ts` (DOMPurify), verified by
  removing the sanitiser and confirming 8 of 8 payload tests fail without it.

### Fixed — data correctness

- **"YTD" meant two different periods.** The actuals engine used the calendar year
  (`datetime.now().replace(month=1, day=1)`) while the strategic engine used the fiscal
  year. On a 1 April fiscal start these are 7 months and 4 months, so one dashboard
  reported YTD revenue as `₹495,774,606` and another as `₹451,855,824`. Both engines now
  resolve the fiscal year from the `Fiscal Year` doctype: **`495,774,606` → `451,855,824`
  (they now agree)**.
- **DSO and DPO measured invoice age, not the ratio.** `AVG(DATEDIFF(CURDATE(),
  posting_date))` over every unpaid invoice with no period bound reported **724 days DSO**
  and **731 days DPO**. Replaced with `outstanding / credit sales × days` on a
  trailing-twelve-month denominator: **724 → 188** and **731 → 249**. Trailing twelve
  months rather than fiscal YTD because outstanding payables predate the four-month
  fiscal window, which inflated DPO to 581 as an artefact of the window. The former
  figures are retained under honest names (`avg_open_receivable_age_days`).
- **`net_margin` was assigned the gross margin** (`net_margin = gross_margin  #
  Simplified`). Now computed: **88.9% → 95.8%**.
- **A fabricated gross margin.** `gross_profit = ytd_revenue - ytd_cogs if ytd_cogs > 0
  else ytd_revenue * 0.7` invented a 70% margin when COGS could not be found. The
  fallback is removed; the value is absent instead. (For this ledger COGS *is* identified
  — `₹148,171`, 0.03% of revenue — so the 99.97% margin is real, not a fabrication.)
- **Revenue growth off a negligible base.** `1554.3% YoY` came from a prior period worth
  6% of the current one. The ratio is now withheld when the base is under 10% of current,
  and `prior_period_revenue` is exposed so the card can state the base
  (`vs ₹27.3M last year`) rather than hide the change.
- **`avg_dso` in the risk engine** measured average days past due. Renamed to
  `avg_days_overdue` with all consumers updated; the dashboard label is now
  "Avg Days Overdue".
- **A sentinel rendered as a measurement.** `runway_months` returns `999` when net burn is
  zero. The Finance card multiplied it by 30 and displayed **"29970 days runway"** — an
  82-year forecast, to the day, from monthly averages. Now **"no net cash burn"**, in the
  unit the server measures.

### Fixed — the Risk dashboard was blank

- **Every Risk metric rendered `N/A` while the API returned HTTP 200 with data.**
  `helpers/api.ts` handled `{status, data:{…}}` but not the shape this endpoint returns —
  `status` at the top level with the payload as siblings — and returned `null` for it. The
  dashboard now shows Overall Risk `32.6/100`, Credit Risk `70.8/100 High`, Operational
  Risk `42.4/100 High` and **6 active alerts naming ₹9.4 crore of overdue receivables with
  a recommended action each**, none of which was previously reachable.
  The decoder now has a spec covering all four response shapes; it had none.

### Fixed — absent versus zero

- `formatMoney`, `formatCount` and `formatPercent` coerced `null`/`undefined`/non-finite
  input to `0`. They now return `-`; a real `0` still renders `0`. The module had been
  split against itself, since its date formatters already returned a dash.
- **49 `KpiCard` call sites** pre-guarded values with `|| 0`, converting absent to zero
  before the component could distinguish them. Removed. `KpiCard` gained a `unit` prop
  (`' days'`, `'x'`, `'/100'`) because the suffix is what forced the interpolation.
- **27 local formatters** returned `'0'`, `'0%'`, `'0.00'`, `'0 bps'` or `` `${currency} 0` ``
  from their own null branch.
- `hasData` in `useIntelligenceDashboard` required only the absence of an error, so during
  a `retry()` — which clears the error before the refetch resolves — the content branch
  rendered over empty refs. It now requires a payload, and `retry()` marks the resource
  refreshing so the control shows progress.
- `KpiCard` treats a `null` delta as nothing to compare rather than `0.0%`, which had
  asserted flat performance for a figure the server deliberately withheld.
- `KpiCard` gained `error` and `target` props. A failed fetch previously left `loading`
  false and the parent's ref empty, so `|| 0` took over and the card rendered a confident
  `0`. It now reads `Unavailable`, and the severity badge is suppressed when errored or
  loading — a verdict derived from a fallback is still a false verdict.

### Fixed — currency

- **HR hardcoded `KES` in nine places on a company reporting in INR**, and Tax hardcoded
  `INR` with an `en-IN` locale — two different wrong currencies on one site. Both now read
  `base_currency` from the payload. The HR endpoint did not send it and now does, matching
  the other seven modules.
- `yarn lint:currency` rejects a currency code written as a literal. A `withDefaults` prop
  fallback is exempt; formatting with a constant is not.

### Fixed — charts

- **`chartPalette(n)` returned the same colour twice.** `--app-accent` and
  `--app-info-fill` both resolve to `#0070cc` and both sat in the series list, so a
  two-series chart drew one indistinguishable pair. Removing the duplicate repaired four
  existing charts: Marketing CRM (2 series, identical), Revenue Sections and Tax (3 series
  from 2 hues) and the expense pie (6 from 5).
- **Board chart slides shipped a placeholder over real data.** The slide rendered an icon
  and the words "Chart Visualization" while `presentation_service.py` had always sent
  `labels` and `datasets`. Now transposed to a real axis chart, with an explicit empty
  state — an axis chart handed an empty series draws bare gridlines, which reads as flat
  rather than absent. The server's `#3b82f6` / `#ef4444` are discarded as light-mode
  literals outside the palette.
- Raw hex in SVG presentation attributes stayed light-mode fixed under `data-theme="dark"`.
  Fixed, and `yarn lint:svg` now rejects them — these bypass `lint:palette`, which greps
  Tailwind class names rather than attributes.

### Fixed — navigation

- **Two buttons pushed `/executive-reports` with no such route**, so both landed on the
  catch-all NotFound. Route registered.
- **`CrossDashboardSearch` (1,376 lines) had no route and no importer.** Its five backend
  endpoints were implemented and whitelisted; the feature was built and stranded. Routed at
  `/search` with a sidebar entry.
- **AI chat was dead on two dashboards.** `get_agent_for_dashboard` throws for an
  unregistered type, and Revenue & Customers and Customer 360 mounted names with no agent.
  The frontend swallowed it with `console.error`, so chat failed silently. All 10 mounted
  types now resolve, verified per type against the live endpoint.
- **Five drifting dashboard registries** (sidebar, cached views, search, board types, chat
  union) consolidated into `helpers/dashboards.ts`. Four ghost identities purged; five of
  ten domains had been unsearchable and six unpresentable.
- **Three dead API fetches** in `CustomerSections` fired on mount and on every filter
  change for data nothing rendered.

### Changed — presentation

- **Finance (14 tabs) and Revenue & Customers (13 tabs)** now use a two-level control: a
  group selector above a tab strip scoped to that group, giving 7+7 and 6+7. Every tab was
  already declaring a group, content was already routed by it, and the two groups are
  separate fetches with separately scoped errors — only the strip was flat, and the label
  above it merely reported the current selection. Position is remembered per group.
- **Six dashboards' hand-rolled loading/error/permission blocks** replaced by
  `IntelligenceDashboardShell`, consolidating on the best of the six variants: an icon on
  the permission state, a named next step ("Ask an administrator for Work Order read
  access"), and a semantic error colour instead of `text-ink-gray-5`, which greyed a
  failure out of the reader's attention. Failure now outranks the skeleton.
- **Thirteen `formatDate` implementations** consolidated into four canonical shapes. They
  had diverged across three axes at once: locale (`en-KE`, `en-US`, browser default),
  empty sentinel (`-`, `''`, `N/A`, `TBD`, `Never`) and whether time was included.
- `ExecutiveSummaryTab` rendered four explicit cards and then looped the server's `kpis`
  array, which already contained four of them — Cash Position appeared three times with
  three different runway sublabels. The loop now filters by label.
- Health-score thresholds unified on `60/40` where the server's four-band vocabulary was
  verified; call sites using unverified metrics keep explicit literals with a note, since
  moving a green/amber line on no evidence is the same defect in the other direction.

### Added

- `IntelligenceDashboardShell`, `useGroupedTabs`, `presentationChart`, `asNumber`,
  `NO_VALUE`, `chartTheme`, `utils/format`, `utils/status`, `helpers/dashboards`.
- `yarn lint:svg` and `yarn lint:currency`, each verified load-bearing by reintroducing the
  bug it was written for and confirming rejection.
- Test count **73 → 163**, covering the response envelope, the absence contract, chart
  palette distinctness, grouped-tab navigation, route reachability and the shell state
  machine. `vue-tsc` held at its pre-existing baseline of 259 throughout.

### Known gaps

- The **Executive dashboard** and **Risk** build their own cards rather than using
  `KpiCard`, so the fixes above skip them. Executive still shows the runway sentinel as
  `4325.7 weeks`, `0.0% vs target` where no target exists, and a `High` severity badge on a
  *Health* score, which reads as good news but means high concern.
- **People/HR** payload is 56% empty (average salary `₹0` for 17 employees) and
  **Marketing & CRM** reports its own data as 480 days stale. Both render honestly; neither
  is decision-ready.
- **Board Presentations** is a generator form, not a pre-composed deck.
- Density exceeds guidance on several surfaces: 24 metrics above the fold on Finance and
  People, 15 on Executive. Eye-tracking research puts registration of the fifth item in a
  row as weak.
