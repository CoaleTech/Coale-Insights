import { createRouter, createWebHistory, RouteLocation } from 'vue-router'
import session from './session.ts'

const routes = [
	{
		path: '/login',
		name: 'Login',
		component: () => import('./auth/Login.vue'),
		meta: { isGuestView: true, hideSidebar: true },
	},
	{
		path: '/',
		name: 'Home',
		redirect: '/dashboards',
		component: () => import('./home/Home.vue'),
	},
	{
		path: '/dashboards',
		name: 'DashboardList',
		component: () => import('./dashboard/DashboardList.vue'),
	},
	{
		path: '/ai-insights',
		name: 'AIInsights',
		component: () => import('./ai/AIInsights.vue'),
	},
	{
		path: '/executive-dashboard',
		name: 'ExecutiveDashboard',
		component: () => import('./intelligence/ExecutiveDashboard.vue'),
	},
	{
		path: '/revenue-customers-intelligence',
		name: 'RevenueCustomerIntelligence',
		component: () => import('./dashboard/RevenueCustomerIntelligence.vue'),
	},
	{
		// Legacy route: Sales Intelligence and Customer Intelligence were merged
		// into one Revenue & Customers dashboard.
		path: '/customer-intelligence',
		redirect: '/revenue-customers-intelligence',
	},
	{
		// Legacy route: redirects to the merged Revenue & Customers page.
		path: '/customer-360',
		redirect: '/revenue-customers-intelligence',
	},
	{
		path: '/customer/:customerId',
		name: 'CustomerDetail',
		component: () => import('./dashboard/CustomerDetail.vue'),
		props: true,
	},
	{
		// Legacy route: Sales Intelligence and Customer Intelligence were merged
		// into one Revenue & Customers dashboard.
		path: '/sales-intelligence',
		redirect: '/revenue-customers-intelligence',
	},
	{
		path: '/inventory-intelligence',
		name: 'InventoryIntelligence',
		component: () => import('./dashboard/InventoryIntelligence.vue'),
	},
	{
		path: '/procurement-intelligence',
		name: 'ProcurementIntelligence',
		component: () => import('./dashboard/ProcurementIntelligence.vue'),
	},
	{
		path: '/price-intelligence',
		name: 'PriceIntelligence',
		component: () => import('./dashboard/PriceIntelligence.vue'),
	},
	{
		path: '/financial-intelligence',
		name: 'FinancialIntelligence',
		component: () => import('./dashboard/FinancialIntelligence.vue'),
	},
	{
		path: '/risk-intelligence',
		name: 'RiskIntelligence',
		component: () => import('./dashboard/RiskIntelligence.vue'),
	},
	{
		path: '/machine-learning',
		name: 'MachineLearning',
		component: () => import('./dashboard/MachineLearning.vue'),
	},
	{
		path: '/tax-intelligence',
		name: 'TaxIntelligence',
		component: () => import('./intelligence/TaxIntelligence.vue'),
	},
	{
		path: '/strategic-finance-intelligence',
		name: 'StrategicFinanceIntelligence',
		redirect: '/financial-intelligence',
	},
	{
		path: '/manufacturing-intelligence',
		name: 'ManufacturingIntelligence',
		component: () => import('./intelligence/ManufacturingIntelligence.vue'),
	},
	{
		path: '/marketing-crm-intelligence',
		name: 'MarketingCRMIntelligence',
		component: () => import('./intelligence/MarketingCRMIntelligence.vue'),
	},
	{
		path: '/hr-intelligence',
		name: 'HRIntelligence',
		component: () => import('./intelligence/HRIntelligence.vue'),
	},
	{
		path: '/esg-intelligence',
		name: 'ESGIntelligence',
		component: () => import('./intelligence/ESGIntelligence.vue'),
	},
	{
		path: '/budget-variance-intelligence',
		name: 'BudgetVarianceIntelligence',
		redirect: '/financial-intelligence',
	},
	{
		path: '/board-presentation',
		name: 'BoardPresentationMode',
		component: () => import('./intelligence/BoardPresentationMode.vue'),
	},
	{
		// `ExecutiveDashboard.vue:492,504` already pushed here from two buttons
		// ("Strategic Report" and "Schedule Reports"), but no route existed, so
		// both landed on the catch-all NotFound. The component was built and
		// stranded.
		path: '/executive-reports',
		name: 'ExecutiveReports',
		component: () => import('./intelligence/ExecutiveReports.vue'),
	},
	{
		// Was unreachable: no route, no importer, while its five backend endpoints
		// (`api/ml/search.py`) were implemented and whitelisted the whole time.
		// Also the app's only alternative to sidebar navigation, which Dan Brown's
		// "multiple classification" principle asks for.
		path: '/search',
		name: 'CrossDashboardSearch',
		component: () => import('./intelligence/CrossDashboardSearch.vue'),
	},
	{
		props: true,
		name: 'Dashboard',
		path: '/dashboards/:name',
		component: () => import('./dashboard/Dashboard.vue'),
	},
	{
		path: '/workbook',
		name: 'WorkbookList',
		component: () => import('./workbook/WorkbookList.vue'),
	},
	{
		props: true,
		name: 'Workbook',
		path: '/workbook/:workbook_name',
		component: () => import('./workbook/Workbook.vue'),
		meta: { hideSidebar: true },
		children: [
			{
				props: true,
				path: 'query/:query_name',
				name: 'WorkbookQuery',
				component: () => import('./workbook/WorkbookQuery.vue'),
			},
			{
				props: true,
				path: 'chart/:chart_name',
				name: 'WorkbookChart',
				component: () => import('./workbook/WorkbookChart.vue'),
			},
			{
				props: true,
				path: 'dashboard/:dashboard_name',
				name: 'WorkbookDashboard',
				component: () => import('./workbook/WorkbookDashboard.vue'),
			},
		],
	},
	{
		path: '/data-source',
		name: 'DataSourceList',
		component: () => import('./data_source/DataSourceList.vue'),
	},
	{
		props: true,
		path: '/data-source/:name',
		name: 'DataSourceTableList',
		component: () => import('./data_source/DataSourceTableList.vue'),
	},
	{
		props: true,
		path: '/data-source/:data_source/:table_name',
		name: 'DataSourceTable',
		component: () => import('./data_source/DataSourceTable.vue'),
	},
	{
		path: '/data-store',
		name: 'DataStoreList',
		component: () => import('./data_store/DataStoreList.vue'),
	},
	{
		props: true,
		name: 'SharedChart',
		path: '/shared/chart/:chart_name',
		component: () => import('./charts/SharedChart.vue'),
		meta: {
			hideSidebar: true,
			isGuestView: true,
		},
	},
	{
		props: true,
		name: 'SharedDashboard',
		path: '/shared/dashboard/:dashboard_name',
		component: () => import('./dashboard/SharedDashboard.vue'),
		meta: {
			hideSidebar: true,
			isGuestView: true,
		},
	},
	{
		path: '/:pathMatch(.*)*',
		component: () => import('./auth/NotFound.vue'),
		meta: { hideSidebar: true },
	},
]

let router = createRouter({
	history: createWebHistory('/insights'),
	// @ts-ignore
	routes,
})

router.beforeEach(async (to, _, next) => {
	!session.initialized && (await session.initialize())

	if (to.meta.isGuestView && !session.isLoggedIn && to.name !== 'Login') {
		// if page is allowed for guest, and is not login page, allow
		return next()
	}

	// route to login page if not logged in
	if (!session.isLoggedIn) {
		// if in dev mode, open login page
		if (import.meta.env.DEV) {
			return to.fullPath === '/login' ? next() : next('/login')
		}
		// redirect to frappe login page, for oauth and signup
		window.location.href = '/login'
		return next(false)
	}

	to.path === '/login' ? next('/') : next()
})

const _fetch = window.fetch
window.fetch = async function () {
	// @ts-ignore
	const res = await _fetch(...arguments)
	if (res.status === 403 && (!document.cookie || document.cookie.includes('user_id=Guest'))) {
		session.resetSession()
		router.push('/login')
	}
	return res
}

export default router
