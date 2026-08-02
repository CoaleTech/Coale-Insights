<script setup lang="ts">
import { Breadcrumbs, call } from 'frappe-ui'
import { apiCall } from '../helpers/api'
import { RefreshCcw, Brain, Loader2, TrendingUp, AlertTriangle, Package, Users, DollarSign, ShoppingCart } from 'lucide-vue-next'
import {computed, provide, ref } from 'vue'
import { useRouter } from 'vue-router'
import { downloadImage, waitUntil, wheneverChanges } from '../helpers'
import useDashboard from './dashboard'
import DashboardItem from './DashboardItem.vue'
import VueGridLayout from './VueGridLayout.vue'
import { useStorage } from '@vueuse/core'
import { createToast } from '../helpers/toasts'

const props = defineProps<{ name: string }>()

const dashboard_name = await call('insights.api.shared.get_dashboard_name', {
	dashboard_name: props.name,
})

const dashboard = useDashboard(dashboard_name)
provide('dashboard', dashboard)
dashboard.refresh()

const router = useRouter()
function openWorkbook() {
	router.push(`/workbook/${dashboard.doc.workbook}`)
}
await waitUntil(() => dashboard.isloaded)
const canOpenWorkbook = ref(dashboard.doc.has_workbook_access)

const dashboardContainer = ref<HTMLElement | null>(null)
async function downloadDashboardImage() {
	if (!dashboardContainer.value) return
	await downloadImage(dashboardContainer.value, `${dashboard.doc.title}.png`)
}

const verticalCompact = useStorage('dashboard_vertical_compact', true)

// AI Refresh functionality
const isAIRefreshing = ref(false)
const aiInsights = ref<string | null>(null)
const mlPredictions = ref<any>(null)
const aiError = ref<string | null>(null)
const showMLPanel = ref(false)
const dashboardCurrency = ref('KES')

// Determine dashboard type from title
function getDashboardType() {
	const title = dashboard.doc.title?.toLowerCase() || ''
	if (title.includes('financial')) return 'financial'
	if (title.includes('sales')) return 'sales'
	if (title.includes('procurement')) return 'procurement'
	if (title.includes('inventory')) return 'inventory'
	if (title.includes('production')) return 'production'
	if (title.includes('customer')) return 'customer'
	return 'financial' // default
}

async function refreshWithAI() {
	if (isAIRefreshing.value) return
	
	isAIRefreshing.value = true
	aiError.value = null
	
	try {
		const dashboardType = getDashboardType()
		const response = await call('insights.analytics.ml_engine.get_dashboard', {
			dashboard_type: dashboardType
		})
		
		if (response?.ai_insights?.insights) {
			aiInsights.value = response.ai_insights.insights
			createToast({
				title: 'AI Insights Generated',
				message: `Insights generated using ${response.ai_insights.model_used || 'AI'}`,
				variant: 'success'
			})
		} else if (response?.ai_insights?.error) {
			aiError.value = response.ai_insights.error
			createToast({
				title: 'AI Error',
				message: response.ai_insights.error,
				variant: 'warning'
			})
		}
		
		// Store ML predictions
		if (response?.ml_predictions?.available) {
			mlPredictions.value = response.ml_predictions
			showMLPanel.value = true
		}
		
		// Set currency from response
		if (response?.base_currency) {
			dashboardCurrency.value = response.base_currency
		}
	} catch (error: any) {
		aiError.value = error.message || 'Failed to generate AI insights'
		createToast({
			title: 'Error',
			message: aiError.value,
			variant: 'error'
		})
	} finally {
		isAIRefreshing.value = false
	}
}

// Train ML models
async function trainMLModels() {
	try {
		const dashboardType = getDashboardType()
		createToast({
			title: 'Training ML Models',
			message: 'This may take a few moments...',
			variant: 'info'
		})
		
		await apiCall('insights.api.ml.get_dashboard_data', {
			dashboard_type: dashboardType
		})

		await refreshWithAI()
		createToast({
			title: 'ML Models Updated',
			message: 'Predictions are now available',
			variant: 'success'
		})
	} catch (error: any) {
		createToast({
			title: 'Training Error',
			message: error.message || 'Failed to train models',
			variant: 'error'
		})
	}
}

// Format numbers for display
function formatNumber(value: number, type: string = 'number'): string {
	if (type === 'currency') {
		return new Intl.NumberFormat('en-KE', { style: 'currency', currency: dashboardCurrency.value, maximumFractionDigits: 0 }).format(value)
	}
	return new Intl.NumberFormat('en-KE').format(value)
}
</script>

<template>
	<header class="flex h-12 items-center justify-between border-b py-2.5 pl-5 pr-2">
		<Breadcrumbs
			:items="[
				{ label: 'Dashboards', route: '/dashboards' },
				{ label: dashboard.doc.title, route: `/dashboards/${dashboard.doc.name}` },
			]"
		/>
		<div class="flex items-center gap-2">
			<Button variant="outline" @click="() => dashboard.refresh(true)" label="Refresh">
				<template #prefix>
					<RefreshCcw class="h-4 w-4 text-ink-gray-6" stroke-width="1.5" />
				</template>
			</Button>
			<Button 
				variant="solid" 
				theme="blue"
				@click="refreshWithAI" 
				:loading="isAIRefreshing"
				label="AI + ML Insights"
			>
				<template #prefix>
					<Brain v-if="!isAIRefreshing" class="h-4 w-4" stroke-width="1.5" />
					<Loader2 v-else class="h-4 w-4 animate-spin motion-reduce:animate-none" stroke-width="1.5" />
				</template>
			</Button>
			<Button 
				v-if="mlPredictions?.available"
				variant="outline"
				@click="showMLPanel = !showMLPanel"
				:label="showMLPanel ? 'Hide ML' : 'Show ML'"
			>
				<template #prefix>
					<TrendingUp class="h-4 w-4 text-ink-violet-1" stroke-width="1.5" />
				</template>
			</Button>
			<Dropdown
				placement="left"
				:button="{ icon: 'more-vertical', variant: 'outline' }"
				:options="[
					{
						label: 'Export as PNG',
						variant: 'outline',
						icon: 'download',
						onClick: downloadDashboardImage,
					},
					 canOpenWorkbook ? {
						label: 'Open Workbook',
						variant: 'outline',
						icon: 'external-link',
						onClick: openWorkbook,
					} : null
					,
				]"
			/>
		</div>
	</header>

	<div class="relative flex h-full w-full overflow-hidden">
		<!-- AI Insights Panel -->
		<div 
			v-if="aiInsights" 
			class="absolute right-0 top-0 z-10 h-full w-96 overflow-y-auto border-l bg-surface-white p-4 shadow-lg"
			:class="{ 'right-96': showMLPanel && mlPredictions?.available }"
		>
			<div class="flex items-center justify-between mb-4">
				<h3 class="text-lg font-semibold flex items-center gap-2">
					<Brain class="h-5 w-5 text-accent" />
					AI Insights
				</h3>
				<Button variant="ghost" size="sm" @click="aiInsights = null">
					<template #icon>
						<span class="text-ink-gray-6">✕</span>
					</template>
				</Button>
			</div>
			<div class="prose prose-sm max-w-none">
				<div class="whitespace-pre-wrap text-ink-gray-6 text-sm leading-relaxed">
					{{ aiInsights }}
				</div>
			</div>
		</div>
		
		<!-- ML Predictions Panel -->
		<div 
			v-if="showMLPanel && mlPredictions?.available" 
			class="absolute right-0 top-0 z-10 h-full w-96 overflow-y-auto border-l bg-gradient-to-b from-surface-violet-1 to-surface-white p-4 shadow-lg"
		>
			<div class="flex items-center justify-between mb-4">
				<h3 class="text-lg font-semibold flex items-center gap-2">
					<TrendingUp class="h-5 w-5 text-ink-violet-1" />
					ML Predictions
				</h3>
				<Button variant="ghost" size="sm" @click="showMLPanel = false">
					<template #icon>
						<span class="text-ink-gray-6">✕</span>
					</template>
				</Button>
			</div>
			
			<!-- Customer Segmentation -->
			<div v-if="mlPredictions.models?.customer_segmentation?.status === 'ready'" class="mb-4 p-3 bg-surface-white rounded-lg border">
				<div class="flex items-center gap-2 mb-2">
				<Users class="h-4 w-4 text-ink-pink-1" />
					<span class="font-medium text-sm">Customer Segments</span>
				</div>
				<div class="text-xs text-ink-gray-6 mb-2">
					{{ mlPredictions.models.customer_segmentation.total_customers }} customers segmented
				</div>
				<div class="space-y-1">
					<div v-for="(data, segment) in mlPredictions.models.customer_segmentation.segments" :key="segment" 
						class="flex justify-between text-xs">
						<span class="text-ink-gray-6">{{ segment }}</span>
						<span class="font-medium">{{ data.count || 0 }}</span>
					</div>
				</div>
			</div>
			
			<!-- Sales Forecast -->
			<div v-if="mlPredictions.models?.sales_forecast?.status === 'ready'" class="mb-4 p-3 bg-surface-white rounded-lg border">
				<div class="flex items-center gap-2 mb-2">
				<TrendingUp class="h-4 w-4 text-ink-blue-2" />
					<span class="font-medium text-sm">Sales Forecast</span>
				</div>
				<div class="text-xs text-ink-gray-6 mb-2">
					Method: {{ mlPredictions.models.sales_forecast.method }}
				</div>
				<div class="space-y-1">
					<div class="flex justify-between text-xs">
						<span class="text-ink-gray-6">30-Day Forecast</span>
						<span class="font-medium text-pos">
							{{ formatNumber(mlPredictions.models.sales_forecast.forecast_summary?.total_forecast || 0, 'currency') }}
						</span>
					</div>
					<div class="flex justify-between text-xs">
						<span class="text-ink-gray-6">Daily Average</span>
						<span class="font-medium">
							{{ formatNumber(mlPredictions.models.sales_forecast.forecast_summary?.avg_daily_forecast || 0, 'currency') }}
						</span>
					</div>
					<div class="flex justify-between text-xs">
						<span class="text-ink-gray-6">Trend</span>
						<span :class="mlPredictions.models.sales_forecast.forecast_summary?.trend === 'up' ? 'text-pos' : 'text-neg'" class="font-medium">
							{{ mlPredictions.models.sales_forecast.forecast_summary?.trend === 'up' ? '↑ Up' : mlPredictions.models.sales_forecast.forecast_summary?.trend === 'down' ? '↓ Down' : '→ Stable' }}
						</span>
					</div>
				</div>
			</div>
			
			<!-- Payment Risk -->
			<div v-if="mlPredictions.models?.payment_prediction?.status === 'ready'" class="mb-4 p-3 bg-surface-white rounded-lg border">
				<div class="flex items-center gap-2 mb-2">
				<DollarSign class="h-4 w-4 text-warn" />
					<span class="font-medium text-sm">Payment Risk</span>
				</div>
				<div class="space-y-1">
					<div class="flex justify-between text-xs">
						<span class="text-ink-gray-6">Outstanding</span>
						<span class="font-medium">
							{{ formatNumber(mlPredictions.models.payment_prediction.summary?.total_outstanding || 0, 'currency') }}
						</span>
					</div>
					<div class="flex justify-between text-xs">
						<span class="text-ink-gray-6">High Risk Invoices</span>
						<span class="font-medium text-neg">
							{{ mlPredictions.models.payment_prediction.summary?.high_risk_count || 0 }}
						</span>
					</div>
					<div class="flex justify-between text-xs">
						<span class="text-ink-gray-6">At Risk Amount</span>
						<span class="font-medium text-neg">
							{{ formatNumber(mlPredictions.models.payment_prediction.summary?.high_risk_amount || 0, 'currency') }}
						</span>
					</div>
				</div>
				<div v-if="mlPredictions.models.payment_prediction.high_risk_invoices?.length" class="mt-2 pt-2 border-t">
					<div class="text-xs font-medium text-ink-gray-6 mb-1">Top Risk Invoices:</div>
					<div v-for="inv in mlPredictions.models.payment_prediction.high_risk_invoices.slice(0, 3)" :key="inv.invoice_id" 
						class="text-xs text-ink-gray-6 flex justify-between">
						<span>{{ inv.customer_name?.substring(0, 20) }}...</span>
						<span class="text-neg">{{ formatNumber(inv.outstanding_amount, 'currency') }}</span>
					</div>
				</div>
			</div>
			
			<!-- ABC/XYZ Classification -->
			<div v-if="mlPredictions.models?.abc_xyz_classification?.status === 'ready'" class="mb-4 p-3 bg-surface-white rounded-lg border">
				<div class="flex items-center gap-2 mb-2">
				<Package class="h-4 w-4 text-highlight" />
					<span class="font-medium text-sm">Inventory Classification</span>
				</div>
				<div class="text-xs text-ink-gray-6 mb-2">
					{{ mlPredictions.models.abc_xyz_classification.total_items }} items classified
				</div>
				<div class="grid grid-cols-3 gap-1">
					<div v-for="(count, cls) in mlPredictions.models.abc_xyz_classification.class_distribution" :key="cls"
						class="text-center p-1 rounded text-xs"
						:class="{
							'bg-neg-fill text-neg': cls.startsWith('A'),
							'bg-warn-fill text-warn': cls.startsWith('B'),
							'bg-pos-fill text-pos': cls.startsWith('C')
						}">
						<div class="font-bold">{{ cls }}</div>
						<div>{{ count }}</div>
					</div>
				</div>
			</div>
			
			<!-- Reorder Alerts -->
			<div v-if="mlPredictions.models?.demand_forecast?.status === 'ready' || mlPredictions.models?.reorder_recommendations?.status === 'ready'" 
				class="mb-4 p-3 bg-surface-white rounded-lg border">
				<div class="flex items-center gap-2 mb-2">
				<AlertTriangle class="h-4 w-4 text-neg" />
					<span class="font-medium text-sm">Reorder Alerts</span>
				</div>
				<div class="text-xs text-ink-gray-6 mb-2">
					{{ (mlPredictions.models.demand_forecast || mlPredictions.models.reorder_recommendations)?.reorder_now_count || 0 }} items need reordering
				</div>
				<div v-if="(mlPredictions.models.demand_forecast || mlPredictions.models.reorder_recommendations)?.reorder_items?.length" class="space-y-1">
					<div v-for="item in (mlPredictions.models.demand_forecast || mlPredictions.models.reorder_recommendations).reorder_items.slice(0, 5)" 
						:key="item.item_code" 
					class="text-xs flex justify-between p-1 bg-surface-red-1 rounded">
						<span class="text-ink-gray-6 truncate max-w-[150px]">{{ item.item_name }}</span>
						<span class="text-neg font-medium">Stock: {{ item.current_stock }}</span>
					</div>
				</div>
			</div>
			
			<!-- Product Recommendations -->
			<div v-if="mlPredictions.models?.product_recommendations?.status === 'ready'" class="mb-4 p-3 bg-surface-white rounded-lg border">
				<div class="flex items-center gap-2 mb-2">
				<ShoppingCart class="h-4 w-4 text-ink-violet-1" />
					<span class="font-medium text-sm">Product Associations</span>
				</div>
				<div class="text-xs text-ink-gray-6 mb-2">
					{{ mlPredictions.models.product_recommendations.total_rules }} association rules found
				</div>
				<div v-if="mlPredictions.models.product_recommendations.frequently_bought_together?.length" class="space-y-1">
					<div class="text-xs font-medium text-ink-gray-6 mb-1">Frequently Bought Together:</div>
					<div v-for="(pair, idx) in mlPredictions.models.product_recommendations.frequently_bought_together.slice(0, 3)" 
						:key="idx" 
					class="text-xs text-ink-gray-6 p-1 bg-surface-violet-1 rounded">
						{{ pair.item1_name?.substring(0, 15) }}... + {{ pair.item2_name?.substring(0, 15) }}...
					</div>
				</div>
			</div>
			
			<!-- Train Models Button -->
			<div class="mt-4 pt-4 border-t">
				<Button variant="outline" class="w-full" @click="trainMLModels">
					<template #prefix>
						<RefreshCcw class="h-4 w-4" />
					</template>
					Retrain ML Models
				</Button>
				<p class="text-xs text-ink-gray-6 mt-2 text-center">
					Models are auto-trained daily/weekly
				</p>
			</div>
		</div>
		
		<div ref="dashboardContainer" class="flex-1 overflow-y-auto p-4" :class="{ 'pr-[400px]': (aiInsights || (showMLPanel && mlPredictions?.available)) }">
			<VueGridLayout
				v-if="dashboard.doc.items.length > 0"
				class="h-fit w-full"
				:cols="20"
				:disabled="true"
				:verticalCompact="verticalCompact"
				:modelValue="dashboard.doc.items.map((item) => item.layout)"
			>
				<template #item="{ index }">
					<DashboardItem :index="index" :item="dashboard.doc.items[index]" />
				</template>
			</VueGridLayout>
		</div>
	</div>
</template>
