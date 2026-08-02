<script setup lang="ts">
import { LayoutPanelTop, Table2, XIcon } from 'lucide-vue-next'
import { inject } from 'vue'
import { useRouter } from 'vue-router'
import ChartIcon from '../charts/components/ChartIcon.vue'
import { workbookKey } from './workbook'

const router = useRouter()
const workbook = inject(workbookKey)
</script>

<template>
	<div v-if="workbook" class="relative flex flex-shrink-0 items-center overflow-x-auto bg-surface-white">
		<div class="flex">
			<button
				v-for="(query, idx) in workbook.doc.queries"
				:key="idx"
			class="flex h-10 items-center border-y-2 border-r border-transparent border-r-outline-gray-1 px-3 text-base transition-all motion-reduce:transition-none"
			:class="workbook.isActiveTab('query', idx) ? 'border-b-outline-gray-5' : ''"
				@click="router.push(`/workbook/${workbook.name}/query/${idx}`)"
			>
			<Table2 class="h-3.5 w-3.5 text-ink-gray-6" stroke-width="1.5" />
				<span class="ml-2">{{ query.title }}</span>
				<XIcon
				class="ml-2 h-3.5 w-3.5 cursor-pointer text-ink-gray-4 transition-all hover:text-ink-gray-8 motion-reduce:transition-none"
					@click.prevent.stop="workbook.removeQuery(query.name)"
				/>
			</button>
			<button
				v-for="(chart, idx) in workbook.doc.charts"
				:key="idx"
			class="flex h-10 items-center border-y-2 border-r border-transparent border-r-outline-gray-1 px-3 text-base transition-all motion-reduce:transition-none"
			:class="workbook.isActiveTab('chart', idx) ? 'border-b-outline-gray-5' : ''"
				@click="router.push(`/workbook/${workbook.name}/chart/${idx}`)"
			>
				<ChartIcon :chart-type="chart.chart_type" />
				<span class="ml-2">{{ chart.title }}</span>
				<XIcon
				class="ml-2 h-3.5 w-3.5 cursor-pointer text-ink-gray-4 transition-all hover:text-ink-gray-8 motion-reduce:transition-none"
					@click.prevent.stop="workbook.removeChart(chart.name)"
				/>
			</button>
			<button
				v-for="(dashboard, idx) in workbook.doc.dashboards"
				:key="idx"
			class="flex h-10 items-center border-y-2 border-r border-transparent border-r-outline-gray-1 px-3 text-base transition-all motion-reduce:transition-none"
			:class="workbook.isActiveTab('dashboard', idx) ? 'border-b-outline-gray-5' : ''"
				@click="router.push(`/workbook/${workbook.name}/dashboard/${idx}`)"
			>
			<LayoutPanelTop class="h-3.5 w-3.5 text-ink-gray-6" stroke-width="1.5" />
				<span class="ml-2">{{ dashboard.title }}</span>
				<XIcon
				class="ml-2 h-3.5 w-3.5 cursor-pointer text-ink-gray-4 transition-all hover:text-ink-gray-8 motion-reduce:transition-none"
					@click.prevent.stop="workbook.removeDashboard(dashboard.name)"
				/>
			</button>
		</div>
		<Dropdown
			class="ml-1.5"
			:options="[
				{ label: 'New Query', onClick: workbook.addQuery },
				{ label: 'New Chart', onClick: workbook.addChart },
				{ label: 'New Dashboard', onClick: workbook.addDashboard },
			]"
		>
			<Button variant="ghost" icon="plus"> </Button>
		</Dropdown>
	</div>
</template>
