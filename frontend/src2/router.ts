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
		path: '/customer-intelligence',
		name: 'CustomerIntelligence',
		component: () => import('./dashboard/CustomerIntelligence.vue'),
	},
	{
		// Legacy route — redirect to merged Customer Intelligence page
		path: '/customer-360',
		redirect: '/customer-intelligence',
	},
	{
		path: '/customer/:customerId',
		name: 'CustomerDetail',
		component: () => import('./dashboard/CustomerDetail.vue'),
		props: true,
	},
	{
		path: '/sales-intelligence',
		name: 'SalesIntelligence',
		component: () => import('./dashboard/SalesIntelligence.vue'),
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
		path: '/tax-intelligence',
		name: 'TaxIntelligence',
		component: () => import('./intelligence/TaxIntelligence.vue'),
	},
	{
		path: '/strategic-finance-intelligence',
		name: 'StrategicFinanceIntelligence',
		component: () => import('./intelligence/StrategicFinanceIntelligence.vue'),
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
		path: '/hotel-intelligence',
		name: 'HotelIntelligence',
		component: () => import('./intelligence/HotelIntelligence.vue'),
	},
	{
		path: '/esg-intelligence',
		name: 'ESGIntelligence',
		component: () => import('./intelligence/ESGIntelligence.vue'),
	},
	{
		path: '/budget-variance-intelligence',
		name: 'BudgetVarianceIntelligence',
		redirect: '/strategic-finance-intelligence',
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
