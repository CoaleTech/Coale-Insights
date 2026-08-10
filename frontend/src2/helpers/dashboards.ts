import {
	BrainCircuit,
	DollarSign,
	Factory,
	LayoutDashboard,
	Leaf,
	Megaphone,
	Package,
	Receipt,
	ShieldAlert,
	ShoppingCart,
	TrendingUp,
	UserCog,
} from 'lucide-vue-next'
import type { Component } from 'vue'

/**
 * The one description of an intelligence dashboard.
 *
 * Before this module the same list was re-declared in five places that were
 * never in sync: `AppSidebar` nav, `App.vue` cachedViews, CrossDashboardSearch's
 * filter registry, BoardPresentationMode's type options, and
 * DashboardChatButton's prop union. The drift was not theoretical:
 *
 * - Tax, Procurement, Inventory, Marketing and Risk were missing from search,
 *   so five of ten domains could not be filtered for at all.
 * - Six domains were missing from board types, so no board pack could be made
 *   for them.
 * - Ghost ids outlived their dashboards: `budget` and `sales`/`customer`
 *   survived two merges, and `operations` never had a dashboard at all.
 *
 * Adding a dashboard now means adding one row here.
 */
export interface IntelligenceDashboard {
	/**
	 * Stable short id. Doubles as the backend `dashboard_type` for cross-dashboard
	 * search and board-pack generation, so it must not be renamed casually.
	 */
	id: string
	/** Route `name` in `router.ts`. */
	route: string
	/**
	 * Sidebar label. Deliberately without an "Intelligence" suffix; the group
	 * heading already carries it.
	 */
	label: string
	/** Longer name for surfaces that list dashboards outside nav context. */
	searchName: string
	/** Icon for nav and search results. */
	icon: Component
	/**
	 * `dashboardType` to hand `DashboardChatButton`, or `null` where the surface
	 * mounts no chat.
	 *
	 * MUST be a type the server has an agent for: `get_agent_for_dashboard`
	 * (`api/dashboard_chat.py:107`) throws on anything else, and the frontend
	 * swallows that with `console.error`, so a wrong value here is a silently
	 * broken chat rather than a visible failure.
	 */
	chatType: string | null
	/**
	 * Whether cross-dashboard search can filter to this surface.
	 *
	 * Defaults to true. Set false only where the backend has no branch for the
	 * id: `CrossDashboardSearchService._get_domain_data` returns `{}` for an
	 * unknown domain (`ml/cross_dashboard_search.py:510`), so listing such an id
	 * as a filter offers the user a choice that silently finds nothing.
	 */
	searchable?: boolean
}

/**
 * Ordered as the sidebar presents them. Executive first, per PRODUCT.md naming
 * management as a primary audience needing "instant status confidence".
 */
export const INTELLIGENCE_DASHBOARDS: IntelligenceDashboard[] = [
	{
		id: 'executive',
		route: 'ExecutiveDashboard',
		label: 'Overview',
		searchName: 'Executive Intelligence',
		icon: LayoutDashboard,
		// No chat button is mounted on this surface today.
		chatType: null,
	},
	{
		id: 'revenue-customers',
		route: 'RevenueCustomerIntelligence',
		label: 'Revenue & Customers',
		searchName: 'Revenue & Customers Intelligence',
		icon: TrendingUp,
		// 'Sales', not 'Revenue & Customers': the server has no agent under the
		// merged name, so the mounted value threw "No agent available" and the
		// chat was dead on this dashboard. 'Sales' matches the landing tab and the
		// `/sales-intelligence` route this page replaced, and returns real quick
		// actions. A dedicated merged agent would be better; see chatType docs.
		chatType: 'Sales',
	},
	{
		id: 'financial',
		route: 'FinancialIntelligence',
		label: 'Finance',
		searchName: 'Financial Intelligence',
		icon: DollarSign,
		chatType: 'Financial',
	},
	{
		id: 'tax',
		route: 'TaxIntelligence',
		label: 'Tax',
		searchName: 'Tax Intelligence',
		// Receipt, not DollarSign: Tax previously shared Finance's icon, so the
		// two were indistinguishable in the collapsed rail.
		icon: Receipt,
		chatType: 'Tax',
	},
	{
		id: 'procurement',
		route: 'ProcurementIntelligence',
		label: 'Procurement',
		searchName: 'Procurement Intelligence',
		icon: ShoppingCart,
		chatType: 'Procurement',
	},
	{
		id: 'inventory',
		route: 'InventoryIntelligence',
		label: 'Inventory',
		searchName: 'Inventory Intelligence',
		icon: Package,
		chatType: 'Inventory',
	},
	{
		id: 'manufacturing',
		route: 'ManufacturingIntelligence',
		label: 'Manufacturing',
		searchName: 'Manufacturing Intelligence',
		icon: Factory,
		chatType: 'Manufacturing',
	},
	{
		id: 'marketing',
		route: 'MarketingCRMIntelligence',
		label: 'Marketing & CRM',
		searchName: 'Marketing & CRM Intelligence',
		icon: Megaphone,
		// This surface mounts no chat button today, though the server does have a
		// 'Marketing' agent if one is ever added.
		chatType: null,
	},
	{
		id: 'hr',
		route: 'HRIntelligence',
		label: 'People',
		searchName: 'HR Intelligence',
		icon: UserCog,
		chatType: 'HR',
	},
	{
		id: 'esg',
		route: 'ESGIntelligence',
		label: 'Sustainability',
		searchName: 'ESG Intelligence',
		icon: Leaf,
		chatType: 'ESG',
	},
	{
		id: 'risk',
		route: 'RiskIntelligence',
		label: 'Risk',
		searchName: 'Risk Intelligence',
		icon: ShieldAlert,
		chatType: 'Risk',
	},
	{
		id: 'machine_learning',
		route: 'MachineLearning',
		label: 'Machine Learning',
		searchName: 'Machine Learning',
		icon: BrainCircuit,
		// No agent server-side: `get_agent_for_dashboard` throws on anything
		// outside its map (`api/dashboard_chat.py:103`) and the frontend swallows
		// it with console.error, so a value here would be a silently dead button.
		chatType: null,
		// Model metadata, not domain data -- nothing for search to match on.
		searchable: false,
	},
]

/** Everything except the executive roll-up, which is not a domain. */
export const DOMAIN_DASHBOARDS = INTELLIGENCE_DASHBOARDS.filter((d) => d.id !== 'executive')

/**
 * Filter options for cross-dashboard search.
 *
 * Skips rows marked `searchable: false` -- the backend has no branch for them
 * and would return an empty result set for the filter.
 */
export const SEARCH_DASHBOARD_OPTIONS = INTELLIGENCE_DASHBOARDS.filter(
	(d) => d.searchable !== false,
).map((d) => ({
	id: d.id,
	name: d.searchName,
}))

/**
 * Board-pack options.
 *
 * Every dashboard qualifies: `presentation_service.generate_presentation_data`
 * is type-agnostic, using `dashboard_type` only for a colour-scheme lookup with
 * a safe fallback (`presentation_service.py:88`) while the slides are built from
 * data the frontend supplies. The previous six-entry list was therefore an
 * arbitrary restriction, not a backend limit.
 */
export const BOARD_DASHBOARD_OPTIONS = INTELLIGENCE_DASHBOARDS.map((d) => ({
	value: d.id,
	label: d.label,
}))

/** Icon lookup by id, for surfaces that only carry the id. */
export const DASHBOARD_ICONS: Record<string, Component> = Object.fromEntries(
	INTELLIGENCE_DASHBOARDS.map((d) => [d.id, d.icon]),
)

/** Route names to keep alive, so tab state survives navigation. */
export const DASHBOARD_ROUTE_NAMES = INTELLIGENCE_DASHBOARDS.map((d) => d.route)

/**
 * Chat dashboard types actually in use.
 *
 * Derived rather than hand-listed so the prop union cannot drift from what the
 * dashboards mount. `Customer` is included for `CustomerDetail`, which is a
 * per-customer profile rather than one of the domain dashboards above.
 */
export const CHAT_DASHBOARD_TYPES = [
	'Sales',
	'Financial',
	'Tax',
	'Procurement',
	'Inventory',
	'Manufacturing',
	'HR',
	'ESG',
	'Risk',
	'Customer',
] as const

export type ChatDashboardType = (typeof CHAT_DASHBOARD_TYPES)[number]

/** Non-dashboard views that still need their state kept alive. */
export const EXTRA_CACHED_VIEWS = ['BoardPresentationMode'] as const
