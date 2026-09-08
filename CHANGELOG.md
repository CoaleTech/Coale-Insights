# Changelog

Notable changes to the intelligence dashboard surface of this fork. Values quoted as
`before → after` were measured against the JKM Chemtrade ledger (INR, Indian fiscal year
Apr–Mar), not estimated.

## [Unreleased] — 2026-09-07

### Changed — Margins tab rebuilt to tell a margin story (and its COGS fixed)

`analyze_margins` still used the pre-fix `qty * SII.incoming_rate` cost formula, so
on this delivery-note-driven ledger nearly every line read cost 0 → fake ~100% margins
that got flagged "uncosted" and held out of the leaderboards, leaving the tab
dominated by costing-gap noise. Migrated it to the shared `dn_cost()` + `line_cogs()`
helpers (one `left_join` on `base` fixes overall, per-group, per-item and trend at
once); the "uncosted" flag now fires only when both SII and the linked DN rate are
zero. Result: overall margin 9.6% (was a distorted 21% inflated by uncosted lines),
0 uncosted items, real per-month trend.

Frontend: the tab computed `margin_trend` but never rendered it. Rebuilt around the
story — a headline KPI band (Overall Margin + 12-month average, Gross Profit on net
sales, This Month with pp delta, Strongest Month), a plain-language narrative
sentence, a **Margin Trend** chart (net-sales bars + margin-% line on a second axis),
a **Where Profit Comes From** table ranking product groups by gross-profit
contribution with share bars, and **Protect / Fix** leaderboards that now carry
revenue alongside margin so a high-margin high-revenue item reads as one to protect
and a high-revenue low-margin item as one to fix. Live-verified on jkm: narrative
reads "9.6% … rose 2.6pp last month to 10.7% … peaked 15.9% Jan 26, bottomed 7.2%
Jun 26", chart + tables render, zero console errors. Same worker-restart caveat as the
COGS fix; primed the cache via `bench execute` (inline compute) for verification.

### Fixed — COGS was zero for delivery-note-driven sales, hiding real 6–11% margins

The prior fix rendered `—` for periods where `cost_of_sales = 0`, treating that as a
valuation gap. Deeper investigation against the JKM ledger showed the zero was a
**backend sourcing bug**, not missing data. Every Sales Invoice on this site is raised
against a Delivery Note, which forces `update_stock = 0` on the invoice
(`sales_invoice.py`: "stock cannot be updated again"). COGS is therefore booked on the
**Delivery Note**, and `Sales Invoice Item.incoming_rate` stays 0 until Repost Item
Valuation back-writes it. All six ML cost sites read `incoming_rate` off the invoice
line, so they saw 0 whenever the invoice ran after a DN — always, here — and depended
on repost timing.

Fix: added `dn_cost()` + `line_cogs()` helpers in `api/ml/ibis_source.py`. `line_cogs`
now coalesces `SII.incoming_rate` (nonzero) → linked Delivery Note Item `incoming_rate`
(joined on `sii.dn_detail`) → 0, so cost is sourced from wherever ERPNext actually
booked it regardless of repost lag. Rewired all six GP sites
(`sales_intelligence.py` revenue-metrics daily/weekly/monthly + sales-rep,
`sales_source_analytics.py` source + territory, `customer.py` list + profitability) to
left-join `dn_cost()` and pass `.dn_rate`. `dn_cost()` projects the DN Item to just
`dn_name` + `dn_rate` to avoid the ~15 shared column names that otherwise collide on
the ibis join.

Verified via `get_sales_intelligence` (the exact dashboard payload): monthly COGS now
real for every month — Mar 6.6%, Apr 7.5%, May 7.6%, Jun 6.1%, Jul 6.9%, Aug 9.4% —
matching the Delivery Note ledger. Source (9 rows) and territory (133 rows) GP nonzero,
`_customer_profitability` returns real margin, zero ibis errors. Operational caveat: the
`:8052` `cached_run` background worker holds the pre-fix module, so the live dashboard
updates only after `bench restart`. The frontend `—` guard is kept as a correct
safeguard for genuinely null cells; with real cost it stays dormant and the tables show
the true 6–11% margins.

### Fixed — Gross Margin % showed a fake 100% for periods with no cost basis

On the Revenue Overview tab the Daily Sales Detail, Weekly Performance and Monthly
Summary tables reported **Gross Margin % = 100%** (and Cost of Sales = 0) for every
recent period. Cause: those invoices carry `incoming_rate = 0` — item valuation has
not been posted for the most recent stock movements (Jul/Aug 2026 on the JKM ledger)
— so `cost_of_sales` is genuinely 0 and `gross_profit = net_amount − 0 = net`,
i.e. a spurious full margin. `grossProfitRows` in `RevenueSections.vue` divided by
`gp + cost` and rendered the result verbatim, and the `money`/`pct`/`num` cell
helpers coerced null to `0`/`0%`, so a missing cost basis was indistinguishable from
a real zero-cost sale. Now a period with `cost_of_sales <= 0` is treated as *not
valued*: Cost of Sales, Gross Margin and Gross Margin % render `—` and are excluded
from the column totals, instead of reporting a false 100%. Verified against the JKM
ledger via a fresh-module compute — Mar–Jun 2026 carry real cost (GM 7.7%–29.9%),
Jul/Aug 2026 have no valuation and now show `—`. Frontend-only; the data itself is
fixed by running Repost Item Valuation so `incoming_rate` populates.

### Fixed — Executive Summary overstated expenses (SUM(ABS) double-counted contra entries)

On the Financial Intelligence dashboard the **Executive Summary** band (strategic
engine) disagreed with the KPI cards + Overview (actuals engine) rendered on the
same screen: `62,260,536.74 → 62,155,486.74` revenue, `670,480.76 → 2,649,626.28`
net income, `1.08% → 4.26%` net margin, `779,709.76 → 2,758,855.28` YTD EBITDA,
`1.25% → 4.44%` EBITDA margin. Root cause: the strategic GL aggregations summed
`ABS(debit − credit)` **per row** (`SUM(ABS(...))`), so every offsetting contra
posting — returns, reversals, adjustments — was added instead of netted. On the JKM
ledger this inflated YTD expenses by ~2.08M (and revenue by ~105K). The actuals
engine already nets first (`ABS(SUM(...))`) and reconciles to the GL P&L exactly.
Changed all strategic P&L root-type aggregations to abs the **aggregate**, not each
row — `_gl_account_root_type_total` and depreciation (`summary.py`),
`_category_total`/`_get_fixed_cost`/`_root_type_sum`/`_cogs_total` and monthly
expense (`cost_ratios.py`), monthly trend + expense breakdown (`data.py`), scenario
baseline + monthly revenue (`scenarios.py`), and quarterly ratio trends
(`analysis.py`). Balance-sheet nets (working capital) and the large-transactions
listing keep per-row abs by design. Verified live on jkm: Executive Summary EBITDA
now matches the Overview KPI to the cent; scenario baseline expenses 59.51M (netted).

### Added — Cost of Sales, Gross Margin and Gross Margin % rows on the Revenue Overview tables

The Monthly Summary, Weekly Performance and Daily Sales Detail tables showed
only Revenue / Orders / Customers. Added three rows to each: **Cost of Sales**
(line-level `sum(qty * incoming_rate)`), **Gross Margin** amount
(`sum(net_amount) - cost`) and **Gross Margin %** (GP / net sales). Backend
`calculate_revenue_metrics` now emits `cost_of_sales`/`gross_profit` per period
for all three series, joining Sales Invoice Item and mirroring the formula used
by the Margins tab and rankings. Margin % is on net (pre-tax) sales, the same
basis as everywhere else in the app — not the tax-inclusive `grand_total` in the
Revenue row. A shared `grossProfitRows()` frontend helper builds the three rows
with per-period totals; the tables now render percent cells via `pct()`.
Live-verified on jkm: Weekly/Monthly rows populate with real values (e.g.
monthly GP ₹2.16M for 2026-08); periods whose lines carry no `incoming_rate`
show as 100% margin, the same costing gap the Margins tab already surfaces.
Zero console errors.

### Changed — Redesigned the Forecasts tab to lead with a plain-language summary

The tab opened with an "ML Forecast Training" panel and a "Sales Forecast (Next
90 Days)" section split into 30-day bucket tiles — jargon and buckets that were
mostly empty for the 30-day model. Replaced the top of the tab with a four-card
summary band (Forecast · Next N Days, Average / Day, Trend, Forecast Reliability)
and a single **Revenue Trend & Projection** line chart: a solid line for the
monthly actuals and a dashed line for the model's projection, built from the
dimensional product-group data already loaded (no extra call). Raw model enums
like `linear_trend` now render as "Linear trend"; the sMAPE error is expressed
as a High/Medium/Low reliability band with a plain caption ("missed by about
68.4% on average … treat projected months as directional"). Dropped the
contradicting severity badge that showed a red "High" beside a "Low" value.
Removed the now-dead `forecastBuckets`/`reliabilitySeverity` computeds.
Live-verified on jkm: summary band and dashed-projection chart render, zero
console errors.

### Fixed — Forecasts tab labelled the current month "Actual" over forecast cells

The dimensional forecast tables (Sales by Product Group / Territory) labelled
each period column Actual/Forecast from a client-side date comparison —
`isPeriodForecast(period)` returned `period > currentYYYY-MM`, i.e. strictly
*after* the current month. But the backend forecasts the current, incomplete
month too (`horizon_months=3` covers Sep/Oct/Nov 26 as of Sep 26), and the
data *cells* shade from the backend `is_forecast` flag. So the Sep 26 column
header read "Actual" while every cell under it was shaded as a forecast.

`buildTransposedDimData` now returns the set of forecast periods straight from
the rows' `is_forecast` flag, and both table headers read from it — the single
source the cells already use. Deleted the dead `isPeriodForecast` date-math
helper. Live-verified on jkm: Sep 25–Aug 26 Actual, Sep–Nov 26 Forecast,
headers and cells agree. Zero console errors.

### Fixed — "Why quotes are lost" showed ~280 count-1 noise slices

`get_quotation_analytics` in `insights/ml/sales_source_analytics.py` built its
lost-reasons breakdown by grouping on `Quotation.order_lost_reason` — a
free-text header field where reps type multi-line memos ("acetic purchase
85\nnot sure about with billing..."). On the JKM ledger 287 lost quotes filled
it and 282 of those values are distinct, so the donut rendered a slice per note,
almost every one `count: 1` — unreadable.

Switched the aggregate to the structured `Quotation Lost Reason Detail` child
table (each row links to a controlled `Quotation Lost Reason` master), counting
each reason once per distinct quotation it appears on. This resolves to a clean
17-reason distribution led by Price (93 in the trailing 12m), Transport (33),
Sample (22), GST (11). Output shape is unchanged (`order_lost_reason` + `count`),
so the frontend was untouched. Live-verified on jkm; zero console errors.

### Changed — Redesigned the Attribution tab

The Attribution tab hid its most useful data. Source attribution rendered only
as a three-bar chart (Revenue/Profit/Orders on a confusing dual axis) with the
actual numbers in a screen-reader-only table; the quotation funnel computed
`conversion_rate` and `pending` but never displayed them; a cramped grid of
"per order" KpiCards duplicated one slice of the data.

Rebuilt it from the same payload — no new backend call:
- **Summary band**: Attributed Revenue (with % of total), Lead Sources, Top
  Source, and Quote Conversion. This surfaces the attribution *gap* directly —
  on the JKM ledger 99.0% of revenue is Unattributed (a sparse lead→invoice
  chain), which the old chart quietly buried.
- **Visible source table**: Source · Revenue · Share · Gross Profit · Margin %
  (severity badge) · Orders · Avg/Order, derived client-side from the existing
  `{revenue, gross_profit, order_count}` rows. Unattributed is de-emphasized.
- **Simplified chart**: dropped the Orders-on-second-axis bar; Revenue and Gross
  Profit now share one currency axis.
- **Fuller quotation funnel**: Total / Won / Pending / Lost / Conversion KPIs
  (Pending and Conversion were previously computed but hidden), lost-reasons
  donut under its own subheading.

Live-verified on jkm: IndiaMart top named source ₹1,307,350 / 6.1% margin;
quotation conversion and pending render. Zero console errors.

### Added — Gross Profit and Margin % columns on the Sales Reps leaderboard

The Sales Rep Leaderboard showed each rep's allocated Revenue but no margin, so
a high-revenue rep carrying thin profit was invisible. Added `Gross Profit`
(amount) and `Margin %` (severity badge) columns after Revenue.

Rep revenue is the `Sales Team.allocated_amount` — a proportional split of each
invoice, not `grand_total` — so gross profit is allocated the same way to
reconcile: each invoice's line-level GP (`net_amount − qty × incoming_rate`, the
same formula as `analyze_margins`) is distributed to its sales persons by their
share of the invoice (`allocated_amount / grand_total`), then summed per rep.
Margin % is that allocated GP over the rep's allocated revenue.

Live-verified on the JKM ledger: Milan Mavani revenue ₹139,294,010 / gross
profit ₹26,649,258 / 19.1%; Khushboo 14.6%; Roja 11.6%; Priyanka 10.7%. Zero
console errors.

### Added — Gross Profit column on the Customers and Geography tabs

Extended the Patterns-tab gross-profit work to two more views. The Customers
list showed Total CLV but no margin, and the Territory Performance table
(Geography tab) showed Revenue but no margin — a high-revenue customer or
territory could be carrying thin profit with no way to see it.

- **Customers tab**: `Gross Profit` column after Total CLV.
- **Geography tab** (Territory Performance): `Gross Profit` column after Revenue.

`compute_customer_intelligence` now merges a per-customer line-level gross-profit
aggregate (`net_amount - qty * incoming_rate`, the same formula as the Rankings
scorecard) into the per-customer frame, so both the customer list and the
territory rollup (a sum over that frame) carry it — one source, no second query.

Live-verified on the JKM ledger: Sujata Nutri-Pharma total CLV ₹30,442,395 /
gross profit ₹2,952,375; Surat territory revenue ₹69,228,233 / gross profit
₹13,053,664. Zero console errors.

### Added — Gross Profit column on the Patterns tab

The Customers → Patterns tab showed Orders, Revenue and Avg Order per day-of-week
and per-month, but no margin, so a high-revenue day could hide thin profit. Added
a **Gross Profit** column (after Revenue) to both the Day of Week and Monthly
tables.

`compute_purchase_patterns` now also aggregates line-level gross profit per
invoice — the same `net_amount - qty * incoming_rate` formula used by the Rankings
scorecard — and buckets it into the day/month rows alongside revenue.

Live-verified on the JKM ledger (top 20% by CLV): Monday revenue ₹34,164,932 /
gross profit ₹5,427,908; January revenue ₹10,786,318 / gross profit ₹1,523,596.
Zero console errors.

### Changed — Actions tab moved last and redesigned to lead with money at stake

`Actions` is now the last tab in the Customers group (was fourth, between
Geography and Cohorts). It is the "what do I do now" tab, so it belongs after
the analytical tabs that justify the action, not in the middle of them.

The tab was a flat list of up to 30 customers, each card a name + three status
badges + a stack of recommendation lines whose only quantities were numbers
baked into the advice text ("Outstanding balance: 31,020"). Nothing was
aggregated, sortable, or filterable, and the reader could not tell a
₹24M-at-risk customer from a ₹3K one without reading every line.

Redesigned to lead with the real ledger figure at stake:

- **Impact summary band** (four KpiCards): total revenue at risk (booked revenue
  of customers flagged for churn or re-engagement), outstanding to collect
  (payment follow-ups), upsell + nurture upside (predicted 12-month forward
  value), and customers flagged with a high-priority count. Each sum dedups by
  customer, so a customer with two recommendations is counted once.
- **Per-customer "At stake"** figure on every card — the largest single ledger
  amount that customer puts at stake — with the list sorted high-priority first,
  then by that amount, so the biggest money surfaces at the top.
- **Per-recommendation money**: each recommendation now shows its own figure and
  what it represents (churn/re-engagement → "Revenue at risk", payment →
  "Outstanding", upsell/nurture → "12-mo forward value").
- **Filters**: action-type and priority selects; the card header is a button
  that drills into the customer's detail page.

Backend `_next_best_actions` now carries the real per-customer figures
(`historical_clv`, `predicted_12m_clv`, `outstanding_amount`, `recency_days`)
on each action item instead of only embedding them in advice strings. All
quantification, filtering and sorting is client-side over that payload.

Live-verified on the JKM ledger (100 flagged customers): revenue at risk
₹56,237,905, outstanding ₹14,875,213, upsell + nurture upside ₹61,635,303;
at-stake column sorts biggest-first (₹23.9M top); action-type filter narrows
upsell → 5, payment → 23 with the correct money labels; card click drills into
`/customer/<id>`. Zero console errors.

### Changed — Rankings tab is now one unified, filterable, sortable scorecard

The Customers → Rankings tab used to be a Top/Bottom toggle over eight separate
mini-tables (top/bottom × revenue, gross profit, margin %, consistency), each a
different set of customers, none of them filterable and none showing more than
one metric per customer. You could not answer "which high-margin customers are
also low-frequency?" without cross-referencing four tables by eye.

Replaced with a single per-customer scorecard: one row per customer carrying
revenue, gross profit, margin %, months-active and consistency score side by
side, plus tier / segment / risk / health joined from the shell payload. New
backend `compute_customer_scorecard` (whitelisted `customer_scorecard`) returns
every customer unlimited and unsorted; the frontend does all filtering and
sorting client-side. Filters: name/ID search, tier / segment / risk selects, and
min-thresholds for revenue, gross profit, margin %, months-active and score.
Every metric column header sorts (click to toggle asc/desc). Row click still
drills into that customer's orders. Table caps the rendered set at 200 rows with
a "showing X of Y" footer.

The old `customer_rankings` / `bottom_customers` endpoints are untouched (still
whitelisted, still valid) — the tab simply no longer consumes them.

`compute_customer_scorecard`'s revenue aggregate groups by `customer` alone
(taking `customer_name` via `.min()`), not by `(customer, customer_name)`. A
customer whose name is spelled differently across invoices would otherwise
produce multiple rows sharing one `customer` id — duplicate Vue `:key`s that
pinned unsortable phantom rows to the top of the list (589 rows / 1 dup →
collapsed to 588 unique).

Live-verified against the JKM ledger (588 customers): search "pharma" → 10,
tier Diamond → 13, min-margin ≥ 20% → 243; margin sort desc → Ganesh/Navchetan
100% top, asc → Kabir −14.4% top; months sort desc → The Drona 12/12 top. Zero
console errors, 200-row render, no phantom rows.

## [Unreleased] — 2026-09-04

### Fixed — Customers tab search and tier/segment/risk filters silently died

The Customers tab on the Revenue & Customer Intelligence dashboard crashed its
entire tab body the instant anything was typed into the search box, which also
made the tier/RFM/risk `Select` filters appear dead (the whole `CustomerSections`
subtree had unmounted). Root cause: `compute_customer_intelligence` in
`insights/ml/customer.py` ran `.fillna(0)` over the per-customer frame, filling
the *string* `territory` column with the integer `0` for the 23 customers with no
territory. The search filter in `CustomerSections.vue` called
`c.territory?.toLowerCase()`; optional chaining only guards `null`/`undefined`, so
`(0).toLowerCase()` threw a `TypeError` inside the `customers` computed, and Vue's
error handler tore the tab down with no console output. Fixed both ends: the
collector now stringifies `territory`/`customer_group`/`customer_name` alongside
the other categoricals (empty string for missing), and the search filter coerces
each field with a `typeof v === 'string'` guard so no payload value can crash it.
Verified live: search narrows (588 → 1 for "pharma" within High risk), tier=13,
RFM=82, risk=88, combinations compose, reset returns 588, zero crashes.

### Fixed — Executive dashboard's Custom Range narrative leaked the raw filter encoding

`_narrative` in `insights/ml/executive_intelligence.py` interpolated the `period`
argument verbatim into the "Business health for the {0} period is..." sentence. For
the acronym periods (`MTD`/`QTD`/`YTD`/`TTM`) that reads fine, but Custom Range passes
the internal `custom:<start>:<end>` encoding straight through — the AI Executive
Summary literally said "Business health for the custom:2026-07-01:2026-08-31 period".
Added `_friendly_period_label()` to format that encoding as `01 Jul 2026 - 31 Aug
2026` for the narrative only; `data.period` itself is untouched since the frontend
round-trips that raw value into the filter control. Verified live via Custom Range
(01 Jul-31 Aug 2026): narrative now reads correctly, zero console errors.

### Fixed — MoM/YoY growth read -100% for the current calendar month once transaction data ran ahead of it

`calculate_comparisons` in `insights/ml/sales_intelligence.py` anchored its "current
period" window to `datetime.now()`. The JKM ledger's newest Sales Invoice is dated
2026-08-07; every day of September before a new invoice posts, `datetime.now()` fell
inside a truly empty month, so `current_revenue = 0` and both `mom_growth` and
`yoy_growth` computed `(0 - prior) / prior * 100 = -100.0%` — a false, saturated crash
signal on the two most-watched KPIs on the merged Revenue & Customers dashboard.
Anchored "today" to `max(today, latest Sales Invoice posting_date)` instead, a no-op
once the ledger catches up. Verified live: `mom_growth -8.6%`, `yoy_growth -62.6%`
(day-aligned Aug 1–7 vs Jul 1–7 vs Aug 1–7 '25) — real numbers, not sentinels.

### Fixed — Strategic Finance crashed instead of loading (`Field` has no `.notlike()`)

`estimate_other_receipts` and `estimate_operating_expenses` in
`insights/ml/strategic_finance/data.py` called PyPika's `Field.notlike()`, which does
not exist (only `.like()` is defined) — every executive/strategic-finance forecast
request raised `AttributeError` and the whole module returned `CANNOT VERIFY -
blocking error`. Replaced with the codebase's existing negation convention used
everywhere else in `strategic_finance/*.py`: `~Field.like(pattern)`.

### Fixed — Total Liabilities and Total Equity were reported as large negative numbers

`_gl_account_root_type_total` in `insights/ml/strategic_finance/summary.py` is shared
by every root-type total in the module. Its non-`apply_abs` branch always computed
`debit - credit`, correct for debit-normal accounts (Asset, Expense) but the sign
convention for credit-normal accounts (Liability, Equity) is `credit - debit` — the
module's own docstrings already said so, but the two call sites never negated the
result. `calculate_balance_sheet`/`calculate_executive_summary` silently flipped a real
₹2.99 Cr liability balance to -₹2.99 Cr, zeroing out ROE and Debt-to-Equity via the
`max(0, …)` floors downstream. Negated both call sites; live-verified `total_assets:
₹4,508,510.89`, `total_liabilities: ₹29,863,482.88` (positive), `roe`/`debt_to_equity`
now compute against the correct signed inputs.

### Fixed — YTD meant "since Jan 1" instead of "since the fiscal year start" (HR, Marketing, Executive)

`_period_start_date` in `insights/ml/hr_intelligence.py` and
`insights/ml/marketing_intelligence.py` resolved the `YTD` keyword against the
calendar year, while Financial/Tax/Strategic Finance already resolved it against the
company's fiscal year (JKM Chemtrade: April–March). For any date after 2026-01-01,
HR and Marketing's "Year to Date" silently covered a different, shorter window than
every other dashboard's YTD — undercounting new hires, exits, leads and revenue for
Jan–Mar. Both now share the same `_fiscal_year_for(company)` resolution Financial
Intelligence already used. Live-verified: HR and Marketing YTD both now resolve to
`2026-04-01` (fiscal year start), matching Financial/Tax/Executive.

### Verified — Revenue & Customers dashboard re-confirmed correct after the above fixes

Full pass over both tab groups on the live `jkm` site: header KPIs (Total Revenue,
Customers, AOV, Gross Margin, At Risk, YoY Growth) cross-checked against direct
backend calls; all 6 Revenue sub-tabs (Overview, Cash vs Credit, Sales Reps, Margins,
Forecasts, Attribution) and all 6 Customer sub-tabs (Overview, Geography, Actions,
Cohorts, Patterns, Rankings); the Revenue/Customers tab-group radio toggle; and the
Rankings drill-down (row click → per-customer invoice detail modal, verified against
two different customers). No regressions from the MoM/YoY fix above, no new bugs.
Two apparent discrepancies traced to intentional design, not bugs: Geography's
"Total 1,243 customers" is the all-time customer roster (its own "Active: 3/6/12
months" filter, independent of the dashboard's date range), not the header's 593
12-month-active customers; Margins' revenue figure is tax-exclusive `net_amount`
(correct for a margin calculation under GST) against the header's tax-inclusive
`grand_total` — Sales Reps' per-rep breakdown reconciles to the header exactly
(₹149.49M + ₹23.38M = ₹172.87M), confirming both are honest, not inconsistent.

### Fixed — Quote Conversion % read a flat 0.0% "Critical" alert everywhere, on a site with real submitted quotations

`_scalar_int()` in `insights/ml/customer.py` unwraps an executed Ibis scalar
aggregate to a Python `int`. `tbl.count().execute()` returns a plain int, but
`tbl.aggregate(name=count()).execute()` returns a 1-row, 1-column DataFrame —
`.iloc[0]` on that yields the row (a pandas `Series`), and `int(Series or 0)` raises
`ValueError: ambiguous truth value`, which the blanket `except Exception: return 0`
silently downgraded to `0`. `_quotation_conversion` is the only `_scalar_int` caller
that goes through `.aggregate()` rather than a bare `.count()`, so this one metric —
surfaced on both the Executive KPI strip and Customer Intelligence's
`quote_conversion_rate` — was wrong everywhere it appeared. Fixed to unwrap
positionally (`.iloc[0, 0]` for a 2-D DataFrame, `.iloc[0]` for a bare 1-D Series).
Live-verified: `quote_conversion_rate` 0.0 → 71.0 (YTD, 184/259) and 68.4 (12m,
54/79); Executive dashboard KPI card `Critical 0.0%` → `Low 68.4% (↑38.4%)`.

### Fixed — Manufacturing showed a fabricated "0.0% High" completion-rate alert with zero Work Orders

`completion_rate_pct`, `average_efficiency_pct` and `on_time_completion_pct` in
`insights/ml/manufacturing_intelligence.py` returned `0` instead of `None` when their
denominator (`total_orders` / planned quantity) was `0` — a site with no Work Orders
got a real-looking `0.0%` fed straight into `KpiCard`'s severity logic, which flagged
it `High`, while every sibling metric on the same page (OEE Score, Availability,
Capacity Utilization) already rendered the correct `-` no-data sentinel for the same
condition. `production_health` guarded the same way: `None`, not `"needs_improvement"`,
when `completion_rate` is `None`. Live-verified: Completion Rate and Efficiency now
show `-`, matching the rest of the page.

### Verified — Marketing & CRM and Machine Learning dashboards render correctly; no fix needed

Both were flagged during an earlier batch pass as apparently broken (Marketing stuck
on "Preparing CRM data", Machine Learning rendering empty). Re-checked live on a fresh
worker with cleared caches: Marketing & CRM renders its full funnel/channel/lead-
conversion breakdown; Machine Learning's `model_health()` synchronously re-trains/
re-evaluates all 6 models on each request and takes ~20-25s cold, with no loading
skeleton distinct from its empty state in that window, then renders correctly
("Model Health 6 of 7 trained" with real per-model rows). Both were transient
cold-cache/stale-worker artifacts of the same deployment gotcha as the fix above, not
independent bugs. The Machine Learning loading-skeleton gap remains open (see TODOS.md).

### Fixed — every panel on Risk Intelligence and Procurement Intelligence was missing its section heading

`RiskIntelligence.vue` (18 call sites, all 7 tabs) and `ProcurementIntelligence.vue`
(19 call sites, all 6 tabs) used `<SectionHeader>` throughout their templates but never
imported the component — the one import line present in all 27 other dashboard files
that use it. Vue's runtime resolves an unregistered component tag as a literal unknown
custom element: the `title`/`hint` props landed as invisible HTML `title`/`hint`
attributes (hover-tooltip only, absent from `textContent`/`innerText`) instead of
rendered text, and content passed via `<template #actions>` (icons) silently vanished
since a native `<template>` element never renders. No console error and no visible
crash, so this was invisible to the console-error/data-correctness smoke-test pass
earlier in this batch — both dashboards were marked "no bugs" on numbers and network
activity alone. Fixed by adding the missing `import SectionHeader from
'../intelligence/components/SectionHeader.vue'` to both files. Live-verified: every
tab on both dashboards now renders its real heading text ("Active Risk Alerts", "Risk
Assessment Matrix", "Key Business Metrics", "Risk Component Breakdown", "Receivables/
Payables Aging Analysis", "Customer/Supplier Risk Scores", "GST Compliance Status",
"Detected Anomalies", "Monthly Spend Trend", "Top Suppliers by Spend", "Procurement
Risk Score", "Supplier Concentration Risk", etc.); no `SECTIONHEADER` tag remains
anywhere in the rendered DOM on either dashboard, on any tab.

## [Unreleased] — 2026-08-25

### Fixed — refresh/action button icons stacked above their label instead of beside it

`Refresh Analysis`, `Refresh Data`, `Export`, `Generate Report` and similar buttons across
the intelligence dashboards rendered their icon on its own line, above the text, on every
viewport width -- not a wrap caused by a narrow container, since a zoomed screenshot of a
fully unconstrained clone of the button (no flex parent, `position:fixed`, 1400px of open
viewport) reproduced it identically. The icon was passed as a child of `<Button>`'s
default slot instead of through the `iconLeft`/`#prefix` named slot frappe-ui's `Button.vue`
expects, so it landed inside the same auto-generated `<span>` as the label text rather than
as a sibling flex item. Tailwind's preflight sets `svg { display: block }`, and a block
element opening a span forces a line break before the text that follows it -- a markup
anti-pattern, not a missing `flex-wrap`/`whitespace-nowrap`, which is why it reproduced at
every width tested (375-1400px) and was never a squeeze/overflow bug at all.

Fixed at all 21 affected instances across seven files by moving each icon into
`<template #prefix>`: `TaxIntelligence.vue` (Refresh Analysis), `ExecutiveReports.vue`
(Refresh, Generate Report), `ExecutiveDashboard.vue` (4 Quick Action cards),
`BoardPresentationMode.vue` (Maximize, Fullscreen, Export, Reset, Generate Presentation),
`CrossDashboardSearch.vue` (Filter, Search History, Help, Download/Export),
`dashboard/InventoryIntelligence.vue` (Refresh Data, Retrain Model) and
`dashboard/RevenueCustomerIntelligence.vue` (Refresh). `frappe-ui`'s `Button.vue` renders
`iconLeft` as a proper sibling flex item, so the fix is byte-identical to the pattern the
codebase already used correctly on every other button. Verified with `yarn build`, `yarn
lint`, and a live DOM sweep across all seven pages at 10 widths (375-1400px) each: zero
overflow, zero icon/text line breaks.

### Changed — every intelligence dashboard hand-rolled its own date-range option list

`TaxIntelligence.vue`, `ExecutiveDashboard.vue`, `HRIntelligence.vue` and
`MarketingCRMIntelligence.vue` each declared their own inline `dateRangeOptions` /
`periodOptions` / `periods` array and rendered it through a raw frappe-ui `<Select>`,
independently of the `IntelligenceDateFilter.vue` component eight sibling dashboards
(Financial, Revenue & Customers, Inventory, ESG, Manufacturing, Procurement, Risk, Price)
already share. Two different vocabularies were duplicated this way: a rolling lookback
window (`3m`/`6m`/`12m`/`fy`, consumed by `insights.api.ml.tax.tax_intelligence` and
`_coerce_period`) and a fiscal-period keyword (`MTD`/`QTD`/`YTD`/`TTM`, matched by string
equality in three independent backend resolvers --
`insights.api.ml.marketing._period_start`, `hr_intelligence._period_start_date`, and
executive's period plumbing). A typo'd or re-cased token in either copy would silently mis-
scope a dashboard's data rather than fail loudly, and the two vocabularies were never
interchangeable to begin with.

Both are now named exports of `frontend/src2/utils/dateRangePresets.ts`
(`DEFAULT_DATE_RANGES` and `FISCAL_PERIOD_RANGES`), guarded by
`dateRangePresets.spec.ts` against a value drifting outside what the backend actually
parses. `IntelligenceDateFilter.vue` takes a configurable `options` prop (defaulting to
`DEFAULT_DATE_RANGES`, unchanged for its eight existing callers) instead of a hardcoded
list, and all four remaining dashboards now render it in place of their local `<Select>`,
passing their own preset -- `TaxIntelligence` keeps its lookback-window options, the other
three pass `FISCAL_PERIOD_RANGES`. No dashboard's default selected period or API param
name changed. Verified with `yarn build`, `yarn lint`, and a live check of all four pages:
correct per-dashboard option labels/values, correct preserved defaults (Tax `fy`, Executive
`YTD`, HR/Marketing `TTM`), and a live interaction test confirming the bound value updates
and a reload fires on selection change.

## [Unreleased] — 2026-08-13

### Fixed — dashboard payloads were computed inside the web request, so a mount 502/503'd

Every intelligence endpoint computed synchronously in the gunicorn worker under a
concurrency lease. One dashboard mount fires ~9 of them at once (financial, sales,
customer, inventory, procurement, risk, tax, marketing, HR), each 20–130s of Ibis/pandas
work on this ledger, so the fan-out failed in both directions: callers past the lease got
an immediate 503 (`ServiceUnavailableError: Server is busy`), and a compute that outran
gunicorn's `-t 120` was SIGKILLed into an empty-bodied 502 with the cache still unwritten
— so the next request repeated it, for every dashboard, forever.
`strategic_finance_intelligence` takes 64–128s here; it could never finish inside a
request at all.

`insights.api.ml.utils.cached_run` now answers requests out of cache only. A miss records
demand, queues one `long`-queue job per (endpoint, params, user) — deduplicated on that
triple, so two people on one dashboard or one person on two date filters don't collide —
and returns `{"status": "warming"}`. The job calls the same whitelisted endpoint
off-request, where `cached_run` computes inline and writes the cache, so there is still
one definition of what a dashboard returns. `refresh` keeps serving the payload it has
while the recompute runs, rather than blanking a dashboard someone is reading. An hourly
scheduler pass (`refresh_dashboard_caches`) recomputes what people actually opened;
entries nobody has touched in 3 days drop out, so background load tracks real usage.
Errors are never cached. The ML concurrency lease is gone from this path — the request no
longer computes, so there is nothing left to cap; `execute_live_query` keeps it.

Measured, cold cache, all 9 endpoints fired concurrently over HTTP: 9×200 `warming` in
0.36s wall, against a 502/503 storm before. Warm read ~50ms for a 19KB payload.
`t(doctype)` in `insights.api.ml.ibis_source` is now memoised per request (the financial
payload alone made 34 such calls over 8 DocTypes), taking that compute 38.2s → 22.3s;
sales is groupby-bound rather than schema-bound and is unchanged at ~34s.

The frontend already understood `warming` through `useIntelligenceDashboard`. The one
holdout was the Finance dashboard's planning feed, a raw `createResource` whose
`onSuccess` treated anything but `status === "success"` as a failure — it would have shown
"Planning data could not be loaded" for the entire first compute. It now decodes the
envelope, polls every 4s, and renders a "Preparing planning data" panel instead of a tab
full of blanks that reads as "the company has no working capital".

Deploying this needs a worker restart (`compute_dashboard` is a new job function; a
running worker holds the old module and fails every job) and `bench migrate` — the hourly
event only appears in Scheduled Job Type after `sync_jobs`.

### Fixed — the background job computed inside a forked work-horse, so dashboards warmed forever

With the change above deployed, every dashboard sat on "This dashboard is being computed in
the background" indefinitely — past five minutes, nothing loading, no error anywhere.

`compute_dashboard` called the endpoint in the RQ work-horse. Unless a bench sets
`FRAPPE_BACKGROUND_WORKERS_NOFORK` (this one does; Frappe Cloud does not) that horse is an
`os.fork()` of a multi-threaded worker — RQ's heartbeat thread, the GC thread, whatever
BLAS pool the worker touched last — and pandas/numpy work in such a child is undefined
behaviour per POSIX. This app already had the scars: `insights.api.ml.ibis_source` documents
the same code segfaulting on Frappe Cloud with "waitpid returned 139 (signal 11)", which is
why these endpoints were made synchronous in the first place. Moving them back into a job
walked into it again. A horse killed by a signal runs no exception handler, so nothing was
written — no payload, no error, no trace — and `deduplicate=True` kept the dead job's id in
the registry, so later polls queued nothing. The frontend polled a key that would never be
filled, which is exactly what "warming forever" looks like.

The job now spawns a fresh interpreter (`python -m insights.api.ml.compute_child`, not a
fork), which computes one payload, leaves it in the cache and exits; the horse only waits
for the exit status. That status is about the payload, not about the child getting through
its code: 0 only if a payload is now cached, 2 if the endpoint answered an error envelope,
3 if it claimed success but left nothing at the key, and negative if a signal killed it —
SIGKILL named as the platform's OOM killer, SIGSEGV as the crash above. Anything non-zero
lands on an attempt marker (`insights_ml_attempt`: ts, job_id, fails, error) and the next
request gets that error instead of another `warming`. Three failures stop re-queueing, and
a marker older than 30 minutes is treated as dead, so a killed worker cannot lock a payload
out of ever being computed again. If nothing is listening on the `long` queue at all, a miss
says so rather than promising a compute nobody will run.

`bench --site SITE execute insights.api.ml.utils.warm_all` computes every payload people
have asked for in-process — for a bench with no worker, or after a Redis flush.

Verified in the configuration that used to crash: `execute_job` in a forked horse off a
multi-threaded parent with a warmed BLAS pool now exits 0 with the payload cached (HR,
28.7s). A 20-check contract script covers miss → `warming` → one queued job → child →
cached hit, plus silent death, the attempt cap, and in-flight dedupe.

### Fixed — a crashing compute reported the signal but threw away the crash

With the change above deployed, a Frappe Cloud dashboard reported
`Dashboard compute was killed by SIGSEGV` — the contract working as designed, and still
not enough to act on. All that reached the log was the tail of the child's dump:

    Binary file "/home/frappe/frappe-bench/env/bin/python", at _start+0x30 [0x653730]
    Extension modules: markupsafe._speedups, ..., numpy._core._multiarray_umath, numpy.linalg._umath

`_child_error` kept the last three lines of the child's stderr, and a fatal-signal dump
ends with the C stack root and a trailer of loaded extensions — so the three lines kept
were exactly the three that name nothing, and the Python frames printed above them were
dropped. The whole of the child's output now goes to the Error Log; the dashboard gets one
line pointing at it. The child is spawned with `-u -X faulthandler` so the frames exist
even where the environment has not armed faulthandler, and it announces each phase
(`insights-child: phase=init|call|cached`) before taking it, so a fault with no Python
frame of its own is still read against the last phase it reached.

What that trailer does say: numpy is fully imported (`_multiarray_umath` and
`linalg._umath`, which is a complete NumPy 2.x import) and no `pandas._libs` are loaded
yet, so the fault lands between the two — in numpy's BLAS initialisation, not in this
app's own code. Ibis materialises every aggregate through pandas (`expr.execute()`, 225
call sites), so each dashboard imports pandas and numpy no matter how much of the compute
now happens inside MariaDB; `insights/ml/hr_intelligence.py` says "no pandas / numpy in
this rewrite" in its docstring while `_scalar`/`_rows` call `.execute()` two lines down.

`bench --site SITE execute insights.api.ml.utils.child_selftest` spawns a child of exactly
that shape — same interpreter, flags, environment and sites path — which walks the imports
a payload needs (numpy, a BLAS matmul, pandas, a frame, ibis, one aggregate against the
site) announcing each step first. A host that faults names the step that does it, which is
the one thing a dashboard's error line cannot.

### Fixed — a payload that landed was reported as a failure if the child died on the way out

`compute_dashboard` read the exit status alone, so a child that wrote its payload and then
faulted during interpreter shutdown — a real hazard with this many native extensions
loaded — blanked a dashboard whose data was sitting in Redis, and burned one of its three
attempts. The cache is now the contract it was always documented to be: if the key holds a
payload when the child exits, that is a success, and the crash is logged as one that
landed anyway.

25 checks cover it: the flag's effect on a real faulting child, frames/trailer/breadcrumbs
surviving into the Error Log, the one-line message, exits 1/2/3 mapping, a landed payload
outranking SIGSEGV, and the selftest end to end. The 20-check background contract and the
HTTP path (cold → `warming` in 1.1s → `success` in 16.5s over 3 polls) still pass.

### Fixed — the crash dump was capped from the wrong end, cutting the frames

The first dump the change above delivered proved the point and then hit the next bug in
the same code. `_child_output` capped the child's output at 6000 characters *from the
tail*, on the reasoning that a fatal dump is the last thing a crashing process writes.
It is — but it prints innermost frame first and *ends* with the loaded-extension trailer,
which is 2KB of it here (67 modules). So the cap kept the trailer and cut the frames,
again, one layer further out. It also cut the child's own `insights-child:` breadcrumbs,
which live at the head, so a non-signal failure lost the endpoint's own error message.

Capped from the middle now, at 16000: three quarters head, one quarter tail, with the
number of cut characters stated. A production-shaped dump (deep stack, C stack trace,
trailer — about 8KB) is kept whole.

What the recovered frames say: the fault is in pandas' datetime C library
(`pandas/_libs/pandas_datetime…so`, called from `pandas/_libs/tslibs/np_datetime…so`),
entered from `ibis/formats/pandas.py` `convert_column` — the per-column type conversion
ibis runs over a cursor result — under `_fetch_from_cursor`. It repeats identically for
procurement, customer and sales, always on the first `.execute()` that returns a date, and
one of those results is `.limit(20)`: twenty rows. Nothing to do with memory, the fork,
or BLAS. `convert_Date`/`convert_Timestamp` call `Series.astype("datetime64[…]")`, which
lands in `np_datetime.astype_overflowsafe` and from there in the `pandas_datetime`
capsule — two extensions compiled together, wired through a `PyCapsule` that carries no
version check.

`child_selftest` now walks that ground too, one announced step at a time: a numpy-only
`datetime64` unit conversion, then date objects → `datetime64`, datetimes → `datetime64`,
timedeltas → `timedelta64`, then `PandasData.convert_table` on a frame of exactly the
shape a query returns (date, timestamp, decimal, int64 with nulls), then a real query
with a date column. The numpy-only step comes first because it discriminates: a host that
faults there has a numpy problem, one that survives it and dies on the next has a pandas
one. It also reports `machine`, both versions, and a build fingerprint of
`pandas/_libs` — extension count, mtime spread, how many pandas distributions claim the
directory — because a valid call into a valid address that faults on its first field read
is what a tree upgraded in place over a live one looks like.

### Fixed — the declared dependency pins could not be installed

`pandas~=2.2.2` cannot be satisfied by a wheel on this app's own Python: 2.3.3 is the only
pandas 2.x with a cp314 build, and 2.2 predates 3.14's C API. Honouring that pin means
compiling pandas 2.2 from source against whatever numpy is on the host — one half of the
`pandas_datetime`/`np_datetime` pair built somewhere the other half was not. Now
`pandas>=2.3.3,<3` (below 3.x because ibis's pandas format layer is not tested against
it), and `ibis-framework>=10.5,<12`, which is what every bench already runs while the pin
said otherwise.

numpy is now declared as well (`>=2.3,<3`) rather than left transitive. ibis declares no
constraint on either pandas or numpy, so before this the native stack under
`ibis.formats.pandas` — the code that just segfaulted — was pinned by nothing at all.

## [Unreleased] — 2026-08-12

### Fixed — ML computes ran with unpinned native thread pools inside gunicorn

Every ML dashboard endpoint kept 502ing (and, once the concurrency lease above
existed, dragging every other endpoint into a 503 with it) even after the lease
capped concurrency at 2. The compute itself was still slow enough to flirt with
gunicorn's `-t 120`, and its actual duration wasn't stable across requests.

`insights.ml.gl_anomaly` carries a comment claiming `n_jobs=1` is used "because
OpenBLAS threads are pinned app-wide" — true only for the RQ worker, which the
Procfile pins with `OPENBLAS_NUM_THREADS=1` etc. The Ibis rewrite made every ML
compute synchronous, so it now runs inside gunicorn instead, which has no such
pinning. gunicorn runs many worker processes (33 on this bench); each one
spawning an unpinned native thread pool (OpenBLAS/OpenMP, via numpy/pandas/
scikit-learn/statsmodels) per compute oversubscribes the host's cores under
concurrent load — this both slows every compute down unpredictably and is a
known OpenBLAS crash surface, indistinguishable from this app's history of
fork-related segfaults even though this path never forks.

`insights.api.ml.utils._compute` — the single choke point every ML endpoint
already routes through for the concurrency lease — now wraps `fn()` in
`threadpoolctl.threadpool_limits(1)`. Verified locally: pinning made both
sales and customer intelligence *faster*, not slower (35.2s → 26.2s, 6.7s →
5.0s, Administrator/full dataset) — these are groupby/rolling-window bound,
not matrix-multiply bound, so multi-threaded BLAS was pure coordination
overhead. `threadpoolctl` added as an explicit dependency (previously only
pulled in transitively via scikit-learn).

### Fixed — a crashed worker could zero the query/dashboard concurrency pool for an hour

`frappe.concurrent_limit` releases its Redis token in a `finally` block. gunicorn's
`-t 120` kills an over-running request with SIGKILL, which skips `finally` entirely, so
the token was never returned and core's `RedisSemaphore.CAPACITY_TTL` (1 hour, hardcoded)
was the only thing that reclaimed it. Two SIGKILLed ML computes zeroed the `limit=2` pool
on production and 503'd every dashboard for the rest of the hour with no load at all —
worse than the 502s the limiter exists to prevent. `execute_live_query` carried the same
decorator (every workbook/chart query) with the same unbounded blast radius.

Replaced both call sites with `insights.concurrency_lease.concurrent_limit_lease`: same
reject-immediately contract, but a leaked slot self-heals within 150s (just past the
gateway timeout) instead of an hour.

### Fixed — a cache keyed only on arguments served one user's rows to another

`cached_run` (below) keyed on the endpoint's arguments alone. But
`insights.api.ml.permissions.permitted()` filters rows out of every read according to
the caller's User Permissions, so two callers passing byte-identical arguments compute
materially different payloads. Whoever missed the cache first had their payload served
to everyone who asked next. Measured on this ledger: a salesperson restricted by
`custom_sales_person` sees 278 Sales Invoices and should total ₹6,763,075 across 210
transactions; through the shared cache they were served the manager's ₹182,105,991
across 2,229 — a **27x overstatement and a confidentiality breach**. It runs both ways:
load order decides, so the manager could equally be served the salesperson's figures
and silently under-report. This is the same class of defect as the row/column
permission fix, one layer up — the row filter is only a boundary if the cache in front
of it keeps the same shape. Cache keys are now scoped per user. Regression test
`test_cache_keeps_the_shape_of_the_row_filter` discovers a discriminating pair of real
users on the bench and asserts neither is served the other's payload; it fails on the
pre-fix key (`AssertionError: 278 == 278`).

### Fixed — cold dashboards 502'd because nothing capped how many ran at once

Every ML dashboard endpoint returned `502 Bad Gateway` on production while returning
correct, fast `403`s to unauthenticated probes — the worker, routing and imports were
all healthy. bench runs gunicorn with `-t 120` behind nginx `proxy_read_timeout 120`,
and a cold compute that overruns that is killed mid-flight: the browser gets an
empty-bodied 502 (which also crashed the frontend's error decoder, since it parses the
body as JSON) *and nothing is written to the cache*, so the next request starts cold and
repeats it forever. The 1h TTL was irrelevant because it was never reached.

What let a single ~46s compute overrun a 120s budget is that nothing bounded how many
ran at once: each pinned a web thread for its full duration, and contention inflated
them all until they crossed the limit together — which is why cheap endpoints died
alongside expensive ones. Upstream Insights already solves exactly this, and this fork
had dropped it: `ibis_utils._execute_live_query` is wrapped in Frappe's
`concurrent_limit(wait_timeout=0)`, whose upstream comment reads *"a blocked request
holds on to a web thread, so waiting here is what starves the pool when a dashboard
executes all of its charts at once. The frontend retries on the 503."* This fork had no
`concurrent_limit` anywhere.

The ML compute path now carries the same cap. `limit` is set to 2 rather than left to
default: the default derives from gunicorn's worker count (16 here), which measures how
many *cheap* requests can be in flight, and these computes are three orders of magnitude
slower. Measured cold as a row-filtered (non-Administrator) user: 46s alone, 65s with two
in flight — two keeps ~55s of headroom under the 120s gateway, three would start spending
it. Cache *hits* are not gated, only misses, and the limiter disengages entirely
off-request, so the scheduler, `bench execute` and the test suite are unaffected.

A rejected caller now gets a real `503 ServiceUnavailableError`, which
`useIntelligenceDashboard` retries with jittered exponential backoff (8 attempts, 1s→8s)
rather than surfacing — the same contract as upstream's `scheduleQueryExecution`. Four of
the ten endpoints wrapped `cached_run` in `except Exception: return error(...)`, which
swallowed the 503 into a `200 {status: "error"}` and would have killed the retry
silently; they now re-raise it alongside `PermissionError`.

Verified over real HTTP as a restricted user, four concurrent cold requests: two returned
`200 success` (69.9s, holding both slots), two returned `503 ServiceUnavailableError`, and
a following request was a 0.02s cache hit. This replaces the background-warming approach
briefly taken here, which reintroduced a queue, a redis lock, a patience window and a
`{"status": "warming"}` polling contract to work around the timeout — a second
implementation of what the 503 contract already provides.

### Fixed — workbook and chart live queries had no concurrency cap either

The same unbounded-concurrency gap existed one layer down. `execute_ibis_query`
(called by `Insights Query v3` / workbooks / charts / table previews) ran
`query.execute()` directly, so a burst of heavy workbook queries could pin every
web thread and 502 the dashboards above them. Standard Insights already wraps
this in `_execute_live_query` with `@concurrent_limit(wait_timeout=0)`; this fork
had dropped that too.

Ported the upstream pattern: live queries now flow through
`_execute_live_query`, which rejects immediately with `503 ServiceUnavailableError`
when the slot is taken, preserving web threads and letting the frontend retry.
Cache hits, warehouse/data-store queries and metadata probes are not gated by this
limit. Includes the same fallback decorator as upstream for older Frappe versions.
Smoke-tested with a trivial Ibis query through `execute_ibis_query`.

### Fixed — every dashboard endpoint is now cached, not just `get_executive_summary`

`get_executive_summary()`'s 502 (fixed 2026-08-10, see below) was one symptom of a
wider gap: only that endpoint had a cache. The other 10 top-level dashboard payloads
(`sales_intelligence`, `customer_intelligence`, `financial_intelligence`,
`tax_intelligence`, `procurement_intelligence`, `risk_intelligence`,
`strategic_finance_intelligence`, `get_hr_overview`, `get_marketing_overview`,
`inventory_intelligence`) recomputed their full Ibis pipeline -- some fanning out to
2-3 nested sub-computations -- on every single request, with no cache at all. Added
`insights.api.ml.utils.cached_run`, a read-through Redis cache (1h TTL, matching the
executive summary contract) that gates on a fresh permission check every call but
skips the compute on a warm hit; errors are never cached, so a transient failure
retries fresh next request instead of serving (or locking in) an error for the full
TTL. All 10 endpoints wrapped, cache keys scoped per (date_filter/period, company)
where the underlying compute actually uses those parameters. Verified with a direct
cache-hit/miss/error-path probe (`cached_run` called twice: second call is a cache
hit, zero re-invocation; error results re-run every time) and the full test suite.

### Changed — the ML layer is pure Ibis now; `BaseMLModel` and the async queue are gone

Every intelligence domain (customer, executive, financial, strategic finance, procurement,
risk, HR, product recommendations, marketing, inventory) is rewritten from a `BaseMLModel`
subclass — `train()` fits a model, `predict()` serves an hourly Redis cache, sklearn/pandas
do the heavy lifting — to a synchronous Ibis expression compiled to one SQL statement per
endpoint. There is no cache, no background job, no fork; every whitelisted endpoint computes
fresh, synchronously, inside the gunicorn web worker that received the request — with one
documented exception, `get_executive_summary()`, see "Fixed" below.

`insights/ml/base.py` is trimmed to `ensure_dependencies()` (the one live caller left,
`model_ops.py`'s `model_health` diagnostic). `esg_intelligence.py` (1,488 lines) and
`tax_intelligence.py` (1,187 lines) are deleted — zero remaining importers.
`strategic_finance/model.py` was the last subclass; it now computes and returns directly,
`predict()` is a `train()` alias.

`executive_intelligence.py` (1,888 → 1,048 lines) no longer re-implements every department
KPI in pandas; it calls the already-rewritten domain modules and pulls KPIs out of their live
payloads, composing `business_health_score` via a weighted RAG-mean with no numpy.
`executive.py`'s 17 whitelisted endpoints are now thin wrappers: permission gate, delegate to
the rollup, return the standard envelope — no lazy-compute helper, no "compute or fall back to
stale cache" branch anywhere.

`MLAnalyticsEngine._get_ml_predictions()` was the last caller still importing the deleted
subclasses (`CustomerSegmentation`, `SalesForecasting`, `PaymentPrediction`,
`ABCXYZClassification`, `ProductRecommendations`) and their removed
`get_cached_results()`/`train()` cache contract. All 5 branches
(customer/sales/financial/procurement/production) are rewired to the live module-level
functions, each behind its own `try`/`except` so one failing domain doesn't blank the panel.

### Fixed — real bugs the rewrite left behind, found by exercising every endpoint against the live jkm DB

Ibis raises structural errors MariaDB never would, so most of these only surfaced under a real
run against the live site, not under `ruff` or `pyright` — the ML domain is dynamically typed
by design (Ibis columns resolve at runtime).

- **`customer.py` — 5 broken Ibis expressions.** `.first()` has no MariaDB compilation rule in
  this Ibis version; 7 call sites picking a representative
  `customer_name`/`customer_group`/`territory` used it and crashed — replaced with `.min()`.
  `_product_affinity` joined `sii.join(si).join(item)` and collided on shared Frappe meta
  columns (`name`, `owner`, `creation`, `docstatus`); fixed by filtering `si` before the join
  and selecting explicit named columns between stages. `_cohort_analysis` and
  `compute_customer_rankings` called `si.mutate(x=...)` then referenced the pre-mutate `si.x`
  (`AttributeError` — `x` only exists on the mutated relation). `_quotation_conversion`
  aggregated `q.count()` from the pre-filter relation inside an aggregate whose parent was the
  filtered one (Ibis `IntegrityError`). Fixed by binding every transformed relation to its own
  variable and chaining off that, never the table it was derived from.
- **`product_recommendations.py` — 4 relation-binding bugs across the two self-join methods**
  (`_pair_table`, `get_recommendations_for_item`). `a.join(b, ... a.name < b.name ...)`
  compared `name` after a prior join that made it ambiguous between `Sales Invoice Item.name`
  and `Sales Invoice.name`; aliased to an explicit `row_id` column instead. Separately,
  `pairs = a.join(b, ...).view()` followed by `pairs.filter((a.item_code == …) | (b.item_code
  == …))` raised `Cannot add <Or> to filter, they belong to another relation` — `.view()` forks
  a new relation identity Ibis no longer considers the same lineage as `a`/`b`. Dropping the
  trailing `.view()` on both self-joins fixes it; `recommend_for_item`, `recommend_for_cart`,
  and `recommend_for_customer` verified end-to-end against real invoice history afterward.
- **`marketing.py`'s `_compute_marketing_overview` — the same relation-binding bug repeated
  across 8 aggregate blocks.** Each block filtered `lead`/`quote`
  (`.filter(lead["docstatus"] < 2)`) inline and then referenced the *original* unfiltered
  `lead`/`quote` table inside the `.group_by()`/`.aggregate()` that followed. `quote_by_source
  _df`'s `won_value` compounded this with a second bug: `quote["base_grand_total"].case()
  .when(...).else_(...).end()` — the wrong API (column-level `.case()` builds a different
  chain than `ibis.cases(...)`, and here compared a boolean expression against the searched
  case's implicit base column). Fixed by binding each filtered relation to its own name
  (`lead_total`, `quote_total`, `lead_trend`) once and referencing only that name downstream,
  and switching to `ibis.cases(...)`. Also removed the dead `_scalar()` helper and a
  `lead_totals_row` block computing a value the code immediately below it overwrote — both
  orphaned by an earlier partial fix. Re-verified `get_marketing_overview`, `source_metrics`,
  `cost_per_lead`, `territory_leads`, and `get_crm_detail` end-to-end.
- **12 files read `System Settings.default_currency`, a field that does not exist on that
  doctype** (confirmed live: `frappe.get_meta("System Settings").get_field("default_currency")`
  is `None`; the call raised `ValidationError`). The correct site-wide fallback is `Global
  Defaults.default_currency` (`INR` on this site, matching `Company.default_currency`) — every
  other currency-resolution site in the codebase already used it. Fixed identically in
  `analytics/ml_engine.py`, `api/ml/executive.py`, `ml/customer.py`,
  `ml/executive_intelligence.py`, `ml/financial_intelligence.py`, `ml/gl_anomaly.py`,
  `ml/hr_intelligence.py`, `ml/india_tax_intelligence/model.py`,
  `ml/procurement_intelligence.py`, `ml/risk_intelligence.py`, `ml/strategic_finance/model.py`,
  and `reports/executive_reports.py`.
- **`inventory.py` — 3 real bugs**: `get_inventory_detail`'s `low_stock_items` branch called
  `frappe.qb.functions.Count` — a bound method, not a namespace (`AttributeError` on every
  call); `inventory_classification` used `ABCXYZClassification` without importing it
  (`NameError` on every call); `get_inventory_recommendations` called a
  `get_reorder_recommendations()` method that does not exist on `ABCXYZClassification` (it only
  has `train()`) — delegated to the same `demand_forecasting.get_reorder_alerts()`
  `general.py`'s own `get_reorder_alerts` endpoint already uses, instead of inventing new
  logic. Plus one PEP 484 violation a full-repo pyright sweep caught:
  `item_breakeven(fiscal_year: str = None)` — implicit-`Optional` default, now
  `Optional[str] = None`.
- **`model_ops.py`'s `retrain()` called `compute_or_cache`**, deleted along with the async-queue
  removal. It now calls the model's `trainer_fn()` directly and returns the fresh result —
  there is no cache left to fill; this recomputes the model the same way the domain dashboard
  that owns it already does, on demand.

- **`procurement_intelligence.py` — `_supplier_performance` and `_purchase_cycles` fetched full
  row-level fan-outs into pandas before aggregating, mis-weighting the results.**
  `_supplier_performance`'s lead-time and on-time-delivery calcs pulled every `PO`×`PR` row into
  a DataFrame and reduced it with a nested `.groupby()`/`.iterrows()` double-loop;
  `_purchase_cycles`'s three cycle-time averages chained `POI → MR → PRI → PR → PII → PI` into
  one join, so a PO with 5 items and 3 partial receipts produced 15+ duplicate rows before any
  averaging happened — both slow (`_purchase_cycles` 22.94s + `_supplier_performance` 8.75s =
  84% of the module's 37.8s) and wrong (multi-item/multi-receipt POs were over-weighted vs.
  single-line POs). Rewrote both as SQL-side `.group_by().aggregate()` calls and three
  independently-scoped two-table joins, matching the `.aggregate()` idiom already used
  everywhere else in this file; module total dropped 37.8s → 11.4s (71%). Also fixed GRN
  completion rate, which could read >100%: it counted distinct *receipt* names instead of
  distinct *PO* names with ≥1 receipt, so a PO split across several partial receipts inflated
  the numerator past the denominator — switched to `nunique(where=...)` scoped to PO names.
  `procurement_intelligence()` end-to-end: 9.85s.

### Fixed — the test suite still exercised the deleted architecture

- **`test_ml_permission_gates.py` — 4 tests mocked classes and methods the rewrite deleted**:
  `HRIntelligence.get_hr_overview` (real call is `.train()`),
  `ExecutiveIntelligence.get_department_deep_dive` (department insight is now sliced out of the
  pure-Ibis `get_executive_summary()` rollup directly), the old `refresh=True` →
  `frappe.enqueue(train_payment_prediction)` async path (payment risk always computes live now
  and ignores `refresh`), and `_get_domain_data`/`SalesIntelligence` (domain search is a single
  capped `frappe.get_all`, zero ML). All 4 rewritten against the real call paths.
- **`test_api_integration.py` — `TestAPIIntegration` rebuilt its company/customer/item fixture
  in every test's `setUp` and tore it down in `tearDown` via `frappe.delete_doc("Company", ...,
  force=True)`**, which cascades through `create_default_cost_center`'s Chart of Accounts /
  Cost Center / Fiscal Year teardown once per test. Moved fixture creation to `setUpClass`
  (built once) and dropped the manual per-test teardown — `FrappeTestCase`'s automatic
  `rollback()` handles isolation between tests instead. `test_api_refactoring.py` (which
  referenced the now-deleted `get_date_filter_sql` helper and the old `parse_date_filter`
  return shape) updated to match.
- **`test_ml_functionality.py` (1,352 → 1,078 lines)** — deleted or rewrote every test
  asserting on `BaseMLModel` internals (`.train()` writing to a Redis cache key, `.predict()`
  reading it back, cache TTLs) that the pure-Ibis rewrite has no equivalent for.

Combined suite (`test_api_integration` + `test_api_refactoring` + `test_ml_functionality`):
**75 tests, 0 failures, 0 errors, 94.6s.**

### Verified

A static sweep of `insights/api/ml/*.py` counts **145 `@frappe.whitelist()` endpoints across
17 files**. `pyright`'s remaining findings on every file touched this session are exclusively
3 known framework-stub gaps already present before this session — `frappe.throw` has no
`NoReturn` annotation (so pyright can't see code after it is unreachable),
`frappe.parse_json`'s return type is a broad union pyright won't narrow through `or {}`, and
`frappe.defaults` isn't exposed as a typed submodule — not new type errors. `ruff check
--select F821,F811,F822,E9,F631,F632,F633,F701,F702,F706,F707` (the error-class rules) passes
clean; remaining findings are pre-existing style warnings (deprecated `Dict`/`List`/`Tuple`
typing, trailing whitespace). A final targeted re-run of the 20 endpoints this entry changes —
`customer_360_detail`; `get_marketing_overview`, `source_metrics`, `cost_per_lead`,
`territory_leads`, `get_crm_detail`; `retrain("sales_forecast")`; `recommend_for_item`,
`recommend_for_cart`, `recommend_for_customer`; `train_financial_intelligence`,
`get_financial_overview`, `get_cash_flow_analysis`, `get_receivables_analysis`,
`get_payables_analysis`, `get_forex_exposure`; `get_purchase_analytics`,
`get_price_intelligence`, `get_procurement_risks`, `get_procurement_forecast` — returns
`status: success` on every one against the live jkm site: **20/20**.

### Fixed — `get_executive_summary()` recomputed all nine domains on every call, ~60s

`ExecutiveDashboard.vue` calls `get_executive_summary()` on load. The endpoint fans out to
`_load_sales`/`_load_customer`/`_load_inventory`/`_load_procurement`/`_load_financial`/
`_load_risk`/`_load_hr`/`_load_manufacturing`/`_load_marketing` — nine full domain Ibis
pipelines — on every single call, with no cache (see the "no cache" note above). Measured
cold on the live jkm DB: the nine loaders sum to ~57s, the full rollup ~62s — well past most
gateway/reverse-proxy timeouts. This is what "the intelligent dashboard is still loading"
actually was.

Two scheduler functions, `run_daily_intelligence` and `warm_dashboard_caches`, already called
`get_executive_summary(period)` for all four periods (`MTD`/`QTD`/`YTD`/`TTM`) with comments
describing a "1h TTL" that had been deleted along with the rest of the cache layer — restored
it: a synchronous read-through Redis cache (`insights_ml_executive_summary:{period}`, 1h TTL),
populated inline on a miss inside the same request. No background job, no fork — the one
narrow exception to the "no cache" rule above, scoped to the one endpoint that fans out to all
nine domains at once, using the same `frappe.cache.get_value`/`set_value` convention already
in `model_ops.py`. A failed compute is never cached, so a transient error retries fresh on the
next request instead of serving (or locking in) an error for an hour.

Verified end-to-end against the live jkm DB: cold 60.6s → warm cache hit 0.003s, byte-identical
payload; a different period (`MTD`) still misses correctly (no cache-key collision). 75/75
tests still pass.

## [Unreleased] — 2026-08-10

### Fixed — the work-horse segfault, and two 502s it was hiding

Frappe Cloud crash records showed every dashboard job dying as
`Work-horse terminated unexpectedly; waitpid returned 139 (signal 11)` at
141–179 MB peak RSS — a native fault during import, not an OOM and not a
timeout. The 2026-08-08b diagnosis blamed Apple Accelerate and concluded the
crash was macOS-only. It is not: the same fault occurs on Linux.

**Cause.** OpenBLAS, MKL and libgomp each allocate a thread pool on first import,
sized from the *host's* CPU count. That pool does not survive `fork()`, and rq
forks a work-horse per job. `insights/__init__.py` now pins all of them to one
thread before numpy can load — the only placement our own import order cannot
race, since numpy reaches the process solely through an `insights.*` module.

This was never a jkm regression. `master` schedules the same ML training
(`hooks.py:168`, `run_daily_intelligence`) into the same forked work-horse, so
those jobs have been dying there too — silently, because no page reads them.
jkm only moved the dashboards onto the path that was already broken.

### Changed — dashboards stay inline, and the queue layer is gone

`async_compute.py` (683 lines) is deleted along with every `frappe.enqueue` on a
dashboard path. `master` and `restaurant` carry neither, and both serve this site
correctly, which is the evidence that inline computation fits inside the gateway
read timeout here. Measured through `frappe.app.application` on a cold cache:

| endpoint | | |
|---|---|---|
| `sales_intelligence` | 3.42s | 54,871 B |
| `procurement_intelligence` | 2.24s | 49,430 B |
| `customer_intelligence` | 2.70s | 1,475,103 B |
| `get_executive_summary` | 0.10s | 4,662 B |
| `get_business_health_score` | 0.03s | 274 B |

The client followed: `apiCall` no longer polls
`insights.api.ml.async_compute.async_status`, and `readInsightsEnvelope` no
longer recognises a `queued` envelope. Left in, they were a loaded gun — any
payload reporting `queued` would have sent the browser to a method that no
longer exists, producing the same non-JSON response the whole fix is about.

### Fixed — a page load no longer fits forecasting models

With the dashboards inline, `sales_intelligence` was the last endpoint that
could run for an unbounded time: `aggregate_forecasts(refresh=True)` fits a
Prophet model and up to 100 Holt-Winters models whenever their caches are cold.
Everything else in that endpoint is SQL and pandas aggregation. It was also the
only endpoint still failing after the queue came out, and the only one that did
this.

The request path now passes `refresh_forecasts=False` — in the endpoint and in
`SalesIntelligence.predict`, so no caller can reach it by another route. Those
two models keep their own scheduled trainers (`train_sales_forecast` daily,
`train_demand_forecast` weekly) and the dashboard's own "ML Forecast Training"
button, which already warns that training "may take several minutes". Until one
of them runs, `aggregate_forecasts` leaves the keys null and the section hides
itself (`RevenueSections.vue:904`).

`aggregate_forecasts` also stopped constructing the forecasting models to read
their caches. `SalesForecasting.__init__` calls `_check_prophet()`, so building
one to reach a method it inherits from `BaseMLModel` imported prophet and
matplotlib — 126 MB and 1.4s — into a web worker that was only ever going to
read a cache key. Both caches are now read through `self`; the models are
constructed only to train.

Measured on a fully cold cache, through `frappe.app.application`:

| | before | after |
|---|---|---|
| `sales_intelligence` | 2.71s, 54,871 B | 2.22s, 39,017 B |
| prophet in web worker | loaded | **not loaded** |
| cmdstanpy / matplotlib / statsmodels | loaded | **not loaded** |

The scheduler path is unchanged: `SalesIntelligence().train()` still defaults to
`refresh_forecasts=True` and still populates both forecasts.

### Fixed — `numpy.float64` in a response body was a bare HTML 500

Reproduced on `get_executive_summary`: orjson raises
`Type is not JSON serializable: numpy.float64` inside
`frappe/utils/response.py:155`, past every `except` in the endpoint. Frappe's
`handle_exception` re-encodes the same payload, fails again, and the request
escapes the WSGI app — gunicorn answers with a bare HTML 500. No Error Log entry,
no traceback, and frappe-ui reports it as "the server returned a gateway error"
because `JSON.parse` fails and it reads `exc_type` off `undefined`.

`sanitize_for_json` now also folds `±Infinity` to 0 — pandas yields infinity, not
NaN, on division by zero, so ratio and growth-rate fields hit this routinely — and
matches JSON-safe types by identity rather than `isinstance`, because
`numpy.float64` is a real `float` subclass and would otherwise pass through
untouched.

### Fixed — 143 MB of pandas in every web worker

`insights.api.response` imported `sanitize_for_json` from `insights.ml.base`,
which imports pandas and numpy at module level. Every API module imports
`response`, so the first call to *any* Insights endpoint pulled the whole ML stack
into that gunicorn worker — measured at 143 MB resident, for a function that needs
neither. It moved to `insights/api/serialization.py`, which has no ML imports and
detects numpy scalars through `sys.modules` (exact: a numpy scalar cannot exist
unless numpy is loaded). `insights.ml.base` re-exports it, so no caller changed.
Web-worker import path: **143 MB → 2 MB**.

### Fixed — a redis wipe blanked the dashboards

`predict(allow_train=False)` now serves the durable on-disk snapshot before
falling back to a `warming` placeholder. Redis is cleared by every deploy and by
`bench clear-cache`, which left perfectly good numbers on disk and an empty page.

### Verified

All five endpoints answer 200 with valid JSON on a cold cache, timings above. Test
suite unchanged against a stashed baseline: 116 run, 6 failures, 79 errors before
and after — all pre-existing, a mandatory `custom_lut_no` custom field on Company
blocking ERPNext test-record creation on this bench.

## [Unreleased] — 2026-08-08e

### Changed — dashboards compute inline again, in the gunicorn web worker

Reverted to the pre-async execution model on request, matching `master` and
`restaurant`. The forked work-horse is the only mechanism those branches avoid and the
only one that segfaults on the production host, so the dashboards no longer use it.

`async_compute.serve()` is gone from every dashboard endpoint; each now computes in the
web worker that received the request:

| endpoint | inline, cold | fields |
|---|---|---|
| `sales_intelligence` | 2.9s | 12 |
| `customer_intelligence` | 3.6s | 14 |
| `procurement_intelligence` | 1.8s | 10 |
| `get_executive_summary` | 1.6s | 8 |
| `get_business_health_score` | 0.0s | 4 (shares the executive model cache) |

Deliberate differences from `master`, which would otherwise be regressions:

- **The cache read is kept.** `master`'s `sales_intelligence` calls `model.train()`
  unconditionally, retraining on every page load. These call `predict(allow_train=True)` —
  cached-or-compute — so only a cold 24h window pays full cost. `refresh=true` still
  forces a retrain.
- **`get_business_health_score` keeps the key fix.** It reads `business_health_score` and
  shares the executive summary rather than rebuilding it; on `master` it returns `{}` on
  every call.
- **Cache warming follows the endpoints.** `warm_dashboard_caches` now trains the three
  models and the executive summary — the model-level cache the endpoints actually read.
  Filling `insights_async:result:*` would repeat the exact bug that warm-up was written to
  fix: populating a key nothing serves. The migrate hook and daily scheduler both point at
  the new function.

`async_compute.py` is retained but no longer on any dashboard path: `async_status`,
`queue_health` and `environment_report` remain callable, and the crash forensics, circuit
breaker and memory telemetry stay available if the queue is ever reinstated.

**Accepted risk, stated plainly.** This reinstates the failure mode originally reported:
a cold compute holds the connection, and anything exceeding the gateway read timeout
returns 502 — which is how "Could not load procurement data … gateway error" arose in the
first place. Measured worst cases on this bench were `strategic_finance_intelligence`
59.6s and `get_business_health_score` 42.6s on a fully cold model cache. Each concurrent
cold dashboard also occupies a gunicorn worker for its duration. Keeping the scheduler and
the migrate-time warm running is what holds that risk down.

The non-forking worker (`FRAPPE_BACKGROUND_WORKERS_NOFORK=1 bench worker-pool`) remains
the alternative that avoids both the fork and the timeout; it was verified working on this
bench but not adopted.

## [Unreleased] — 2026-08-08d

### Explained — why master and restaurant never crash, and jkm does

The decisive clue came from the question "the other branches work, why?". They work
because **they never fork.**

| | where the compute runs |
|---|---|
| `master` / `restaurant` | inline `model.train()` inside the **gunicorn web worker** |
| `jkm` | `async_compute.serve()` → `frappe.enqueue` → **rq forks a work-horse per job** |

Same code, same data, same host: it survives in a web process and takes `SIGSEGV` in a
forked child. That is fork-unsafety, and the ordering is what makes gunicorn immune —
gunicorn forks its workers at startup *before* numpy exists, so each initialises its
native stack cleanly, while rq forks *per job*.

Every earlier symptom now fits: deterministic, ~1–2s in, at ~137 MB (below the real
working set), across every pandas-using compute, independent of user and data volume,
and invisible on any host whose native stack happens to tolerate fork.

### Fixed — run the queue without forking

Frappe already ships a non-forking worker for exactly this, and its own comment on the
forking path reads *"TODO: switch to multiprocessing.Process() after further investigating
of fork -> forkserver"* (`frappe/utils/background_jobs.py`):

```python
if sbool(os.environ.get("FRAPPE_BACKGROUND_WORKERS_NOFORK", False)):
    worker_klass = FrappeWorkerNoFork      # "Execute job in same thread/process, do not fork()"
```

Run the workers as:

```bash
FRAPPE_BACKGROUND_WORKERS_NOFORK=1 bench worker-pool --queue long --num-workers 2
```

Verified on this bench — all three previously-crashing computes succeed, and materially
faster, because the per-job fork and re-initialisation disappear:

| compute | forking worker | non-forking | peak RSS |
|---|---|---|---|
| `sales_intelligence:12m` | 40s | **8s** | 254.7 MB |
| `customer_intelligence:12m` | 58s | **4s** | 357.2 MB |
| `procurement_intelligence` | 84s | **2s** | — |

This keeps the whole async architecture — queue, 24h payload cache, client polling, no
blocked web worker — while removing the one mechanism the working branches never used.

`environment_report` now reports `workers_nofork` as its first-line answer, so a host that
is still forking says so plainly.

**Caveat:** a non-forking worker executes jobs in its own process, so a job that crashes
takes the worker with it rather than one child. The circuit breaker and per-key job
isolation added earlier both still apply; run at least two workers in the pool.

## [Unreleased] — 2026-08-08c

### Ruled out — the crash is not memory exhaustion

The work-horse memory telemetry added in the previous entry answered the question it was
built for. Four consecutive crashes on production:

| compute | attempt | peak RSS at death |
|---|---|---|
| `sales_intelligence:12m` | 1 | **135.0 MB** |
| `customer_intelligence:12m` | 1 | **139.5 MB** |
| `sales_intelligence:12m` | 2 | **135.6 MB** |
| `customer_intelligence:12m` | 2 | **140.0 MB** |

The same computes peak at **371.6 MB** and **262.3 MB** on this bench and succeed. Dying
at ~137 MB — *below* the working set, at a near-identical point every time, roughly 1–2s
in — is a deterministic native fault during data load or first pandas interop, not an
allocation failure. An OOM kill would also arrive as SIGKILL (9), not SIGSEGV (11).

It also shows the env-var pinning from `2026-08-08` did **not** fix it: production is
running that code (the `workhorse_peak_rss_mb` field only exists in it) and still crashes.

### Added — `environment_report`, a one-command diagnostic for the crashing host

Five rounds of this have been inference from a bench that behaves correctly. This runs the
discriminating checks *on the host that actually crashes*:

```
bench --site <site> execute insights.api.ml.async_compute.environment_report
```

It reports platform, Python, numpy/pandas versions, the BLAS backend, and whether the
thread-pinning variables are actually set in that process — then runs the decisive test:
a **subprocess that initialises BLAS, forks, and does real numpy + pandas work in the
child**, exactly as rq does. Out-of-process, so a segfault is reported rather than taking
the caller down.

- child killed by a signal → generic fork-unsafety is reproduced; the verdict names the
  worker-environment fix and the pandas/numpy ABI rebuild.
- child exits 0 → fork is healthy and the fault belongs to a specific computation, so the
  verdict points at running that compute inline, outside a work-horse.

On this bench: `fork_probe: survived`, thread vars all `1`, numpy 2.4.4 / pandas 2.2.3.

Leading hypothesis for production, still unconfirmed: a **numpy/pandas C-ABI mismatch**.
numpy 2.x changed the ABI, and a pandas built against numpy 1.x segfaults on first
interop — deterministic, early, affects every pandas-using compute, and would not
reproduce on a host with a matched pair.

## [Unreleased] — 2026-08-08b

### Corrected — the Accelerate diagnosis below does not apply to production

The previous entry blamed Apple's Accelerate BLAS. New forensics carry
`referrer: https://jkmchem.coale.tech/insights/inventory-intelligence` — production is a
hosted **Linux** host, where Accelerate does not exist. `VECLIB_MAXIMUM_THREADS` is inert
there. Of the four variables that entry added, only `OPENBLAS_NUM_THREADS` is meaningful
on Linux. The change is retained (OpenBLAS has its own fork-safety issues and pinning
threads is harmless), but it was **not** demonstrated to fix anything: this bench never
reproduced the crash, so "it passes now" proved nothing.

Two further facts from the new forensics narrow it:

- `ran_as_user` is now `dhaval@jkmchemtrade.com`, not just `Administrator`. Not
  user-specific, and not a permission-path artefact.
- A **fourth** surface fails: `insights.api.ml.inventory_intelligence`, logged under
  `ML Inventory` with full request context. That row is a *Python exception* with a
  traceback, not a work-horse death — the single most informative artefact available, and
  it has not been shared yet.

### Added — the work-horse now reports its own memory

`web_peak_rss_kb` in the forensics measured **the wrong process**: `RUSAGE_SELF` evaluated
in the gunicorn worker handling the poll, not the work-horse that died. Its 230–375 MB
readings described an unrelated process and should not have been presented as evidence.

`run()` now starts a sampler thread that writes the work-horse's own RSS to redis every
second, and `_record_crash_forensics` reports the last value with a verdict hint. A crash
that dies at 3 GB and one that dies at 200 MB are different bugs; until now the forensics
could not tell them apart.

The sampler resolves its redis key and connection **on the calling thread** — `frappe.local`
is thread-local, so `frappe.cache()` inside the sampler silently found no site and the
thread died on its first tick. Verified live: RSS climbing `151.4 → 223.5 → 223.6 MB` peak
across a real `customer_intelligence` compute.

Peak RSS measured on this bench (3,704 sales invoices) for scale:
`sales 371.6 MB`, `customer 262.3 MB`, `procurement 245.4 MB`.

## [Unreleased] — 2026-08-08

### Fixed — the SIGSEGV was Accelerate in a forked work-horse

All three dashboards (sales, customer, procurement) crashed the rq work-horse with
`waitpid returned 139 (signal 11)`. Confirmed by the forensics recorder deployed in the
previous entry: every crash was `signal 11` (SIGSEGV), `started_at` was set (the job began
executing), `web_peak_rss_kb ~230–260 MB` (not an OOM kill — that would be signal 9), and
the worker process had **Accelerate loaded** (verified via `vmmap`).

The root cause: **Apple's Accelerate BLAS is not fork-safe.** numpy 2.4.4 on macOS links
Accelerate, and rq forks a work-horse for every job. The worker parent process loads
numpy (which initialises Accelerate's BLAS thread pools), then `os.fork()` creates a child
that inherits those initialised thread pools. The first BLAS call in the child corrupts
the shared state and segfaults. This did not reproduce on a direct `python -c` call
(no fork) or with small test matrices (BLAS may not engage), which is why it took so long
to identify.

Fix: pin every BLAS backend to a single thread **before numpy is imported**, so no thread
pools exist for fork to inherit.

- **Procfile**: `VECLIB_MAXIMUM_THREADS=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
  MKL_NUM_THREADS=1` added to the worker line, alongside the existing
  `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES`.
- **`async_compute.py`**: the same env vars are set via `os.environ.setdefault` at module
  import time, before any `import numpy` can run. This covers paths that don't inherit the
  Procfile (supervisor configs, `bench execute`, direct imports).

Verified: worker restarted with the env vars, all three dashboards driven through the real
forked work-horse with cold caches:

```
sales_intelligence:12m     queued -> success (40s)
customer_intelligence:12m  queued -> success (58s)
procurement_intelligence   queued -> success (84s)
```

Zero work-horse deaths. semgrep p/python: 0 findings.

## [Unreleased] — 2026-08-07i

### Fixed — two ML queries referenced columns that do not exist

`ml/esg_intelligence.py` read **`Work Order.qty_completed`** (four queries) and
**`Work Order.qty_to_manufacture`** (one). Neither column exists in ERPNext v16 — the
real names are **`produced_qty`** and **`qty`**. The queries did not error loudly; they
would fail inside a background job and surface as a zero on a dashboard.

### Added — the schema contract is now enforced by a test

The ML layer runs ~250 hand-written aggregate queries instead of `frappe.qb`. That is
defensible — these are multi-join aggregates the ORM cannot express, and rewriting them
would be large and risky for no behavioural gain. What it forfeits is the query builder's
one free guarantee: a column renamed upstream fails at *runtime*, in a worker, as a wrong
number rather than an error.

`insights/tests/test_sql_schema_contract.py` closes that gap without touching a single
query. It extracts every `frappe.db.sql` string under `ml/` and `api/ml/` via AST,
normalises interpolated fragments to position-appropriate stand-ins, and hands each query
to the database's own parser with **`PREPARE`** — which resolves every table and column
but executes nothing. An ERPNext upgrade that moves a column now fails a test naming the
file and line.

- **251 SELECTs validated, 251 pass**, in 0.88s under `bench run-tests`.
- Proven to catch drift, not merely to pass: renaming one column to
  `qty_completed_RENAMED_UPSTREAM` produced
  `FAIL … 1 of 251 ML queries no longer match the schema: ml/esg_intelligence.py:291
  (1054, "Unknown column …")`, then reverted clean.

### Not changed — the `str(date)` deviation was overstated

A previous review claimed "several sites pass `str(date)`, forfeiting `%s` type
coercion". Re-measured: an AST scan finds **0** `str(...)` values passed directly as SQL
parameters, and of 11 date-like `str()` coercions in files that run raw SQL, most are
dict keys or already-string fields. The genuine cases resolve `Fiscal Year.year_start_date`,
which is already a `datetime.date` whose `str()` is `'2026-04-01'` — byte-identical to
what the driver emits for the date object. There is no behavioural difference, so no
change was made.

## [Unreleased] — 2026-08-07h

### Added — a work-horse death now records its own forensics

A process killed by a signal leaves no Python traceback, so the usual
`frappe.log_error(frappe.get_traceback())` captures nothing and the only evidence is one
line in `worker.error.log` — on a machine the developer may have no shell access to. rq
still holds the job's identity and arguments for a short window after the death.

`_diagnose` now harvests that window into an **Error Log** row titled
`insights work-horse died: <key>`, recording the cache key, the exact
`compute_method` and `compute_kwargs`, **the user the job ran as** (jobs inherit
`frappe.session.user`, so a restricted user can take a different code path than an admin
test), queue, timeout, attempt count, enqueue/start timestamps, worker name, live worker
health, and the tail of rq's `exc_info`. Forensics are fully guarded — they can never
mask the failure they describe.

Verified against a job forced into exactly the reported state
(`waitpid returned 139 (signal 11)`): the client still receives
`Computation failed on the server: …` and one Error Log row is written:

```
cache_key: procurement_intelligence
compute_method: insights.api.ml.procurement._compute_procurement_intelligence
compute_kwargs: {'refresh': False}
ran_as_user: Administrator
queue: long   timeout: 1500   attempts: 1
```

### Note — still not reproducible on this bench

Re-checked after the report: **0** real work-horse deaths in this bench's
`worker.error.log`, and all seven dashboard keys currently cache `success` with
`attempts=0`. An earlier claim of "195 crashes" in this file was a bad grep — all 195
lines were `customer_segmentation.py` pandas `FutureWarning`s matching the word
*segmentation*. The 18 genuine work-horse lines in `worker.log` are `scheduled_job`
entries from June with `waitpid returned None`, unrelated to Insights.

## [Unreleased] — 2026-08-07g

### Changed — one crashing dashboard no longer takes the other six down

`warm_dashboard_caches` computed all seven payloads inside a **single** background job,
so one work-horse. A process killed by a signal takes everything in it, which meant a
single crashing computation denied every dashboard its cache *and* stacked all seven
working sets into one process's peak memory. `customer_intelligence` alone builds a
1.55 MB payload from 1,243 × 27-field rows.

- New `warm_one_dashboard_cache(key)` warms exactly one key; `enqueue_dashboard_warm_jobs()`
  fans out one job per key with its own deduplicated id and corpse reaping. The daily
  scheduler and the migrate hook both use the fan-out. `warm_dashboard_caches()` is kept
  as the in-process `bench execute` entry point.
- Blast radius per crash: **7 dashboards → 1**. Peak memory per work-horse drops to a
  single computation. Failures become attributable to a named key.

Verified: 7 distinct job ids queued, **7/7 keys PRESENT** after the fan-out completed.

### Reviewed — the segfault does not reproduce on this bench

Asked to align the ML behind the crash, the honest finding is that nothing here
reproduces it, so no ML computation was changed on speculation:

- **Procurement is not numpy-bound.** `procurement_intelligence.py` makes **zero** `np.*`
  calls and one `groupby`; it is SQL-heavy. The Accelerate/fork theory from the previous
  entry does not fit this dashboard.
- **The data is small.** 5,289 Purchase Invoices / 5,827 item rows / 970 suppliers / 641
  items / 3,704 Sales Invoices / 1,250 customers. Nothing at this scale explains an
  out-of-memory kill.
- **It does not crash.** Five consecutive cold trains driven through the real forked
  work-horse (model cache cleared each round) returned `success` in ~30s, with **0**
  work-horse deaths in rq's failed registry.

The crash is therefore environment- or data-shape-specific to production. The fan-out
above and the circuit breaker below contain it; identifying it needs the 30 lines before
`Work-horse terminated` in that server's `worker.error.log`.

## [Unreleased] — 2026-08-07f

### Added — a crashing computation no longer loops forever

A work-horse killed by a signal (`waitpid returned 139`, SIGSEGV) never reaches `run`'s
`except` or `finally`, so **no error is ever cached**. The client's retry therefore
re-queues the same computation, which kills another work-horse, indefinitely — each
"Try Again" costs a worker process.

- `serve()` now counts enqueues per key (`insights_async:attempts:*`, 15 min window) and
  parks a terminal error after **3** deaths, holding it for `ERROR_TTL` so the page stops
  thrashing the worker pool. `run()` clears the counter on completion — success *or*
  Python-level failure — so only a genuinely process-killing computation reaches the
  ceiling. Under normal operation a key goes `1 → cleared`.
- The message names the real situation: *"crashed the background worker N times (no
  Python error — the process was killed). Check the worker log for a segfault or
  out-of-memory kill."*

Verified: three simulated work-horse deaths trip the breaker on the 4th call, the error
is sticky and re-queues nothing, and a healthy key resolves with `attempts` back to `0`.

### Note — the segfault itself is environmental, not fixed here

`numpy 2.4.4` on this bench links **Accelerate**, which is not fork-safe, and rq runs
every job in a forked work-horse. That is a plausible cause but is *unconfirmed against
production*: a full scan of this bench's 15.6 MB `worker.error.log` finds **0**
work-horse deaths, so the crash does not reproduce here and is likely data-volume or
environment dependent. The standard mitigation is to pin BLAS/OpenMP threads for
background workers, which is bench configuration rather than app code:

```
VECLIB_MAXIMUM_THREADS=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
```

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
