<!-- frontend/src2/components/TerritoryMap.vue -->
<script setup lang="ts">
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

interface GeoDataPoint {
  name: string
  value: number
}

interface UnmappedEntry {
  territory: string
  value: number
}

const props = defineProps<{
  worldData: GeoDataPoint[]
  indiaData: GeoDataPoint[]
  unmapped?: UnmappedEntry[]
  metric: string
  colorScale?: string
  initialView?: 'world' | 'india'
}>()

const emit = defineEmits<{
  (e: 'region-click', region: string, value: number): void
}>()

const chartRef = ref<HTMLElement | null>(null)
const currentView = ref(props.initialView || 'world')
let eChart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

const COLOR_SCALES: Record<string, [string, string]> = {
  blue: ['#e0f0ff', '#1a56db'],
  green: ['#e8faf0', '#047857'],
  purple: ['#f3e8ff', '#7c3aed'],
  red: ['#fee2e2', '#dc2626'],
  orange: ['#fff7ed', '#ea580c'],
}

function getChartOptions() {
  const isIndia = currentView.value === 'india'
  const data = isIndia ? props.indiaData : props.worldData
  const mapName = isIndia ? 'india' : 'world'
  const [minColor, maxColor] = COLOR_SCALES[props.colorScale || 'blue']

  const values = data.map((d) => d.value).filter((v) => v > 0)
  const maxVal = values.length ? Math.max(...values) : 1

  return {
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        const val = params.value || 0
        return `<b>${params.name}</b><br/>${props.metric}: ${val.toLocaleString()}`
      },
    },
    visualMap: {
      min: 0,
      max: maxVal,
      text: ['High', 'Low'],
      realtime: false,
      calculable: true,
      inRange: { color: [minColor, maxColor] },
      left: 'left',
      bottom: 20,
      textStyle: { fontSize: 11, color: '#6b7280' },
    },
    series: [
      {
        type: 'map',
        map: mapName,
        roam: true,
        data: data,
        emphasis: {
          label: { show: true, fontSize: 12 },
          itemStyle: { areaColor: '#fbbf24' },
        },
        select: {
          label: { show: true },
          itemStyle: { areaColor: '#f59e0b' },
        },
        itemStyle: {
          borderColor: '#d1d5db',
          borderWidth: 0.5,
        },
        label: { show: false },
      },
    ],
  }
}

async function registerMapData(mapName: string) {
  if (mapName === 'india') {
    const mapJson = await import('../assets/maps_json/india.json')
    echarts.registerMap('india', mapJson.default)
  } else {
    const mapJson = await import('../assets/maps_json/world_map.json')
    echarts.registerMap('world', mapJson.default)
  }
}

async function renderChart() {
  if (!eChart || !chartRef.value) return
  const mapName = currentView.value === 'india' ? 'india' : 'world'
  await registerMapData(mapName)
  eChart.setOption(getChartOptions(), true)
}

function handleClick(params: any) {
  if (currentView.value === 'world' && params.name === 'India') {
    currentView.value = 'india'
    return
  }
  emit('region-click', params.name, params.value || 0)
}

function goBack() {
  currentView.value = 'world'
}

onMounted(async () => {
  if (!chartRef.value) return
  eChart = echarts.init(chartRef.value, 'light', { renderer: 'canvas' })
  eChart.on('click', handleClick)
  await renderChart()
  resizeObserver = new ResizeObserver(() => eChart?.resize())
  resizeObserver.observe(chartRef.value)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  eChart?.dispose()
})

watch(currentView, () => renderChart())
watch(() => [props.worldData, props.indiaData], () => renderChart(), { deep: true })
</script>

<template>
  <div class="flex flex-col h-full">
    <div class="flex items-center justify-between px-3 py-2">
      <span class="text-sm font-medium text-gray-700">
        {{ currentView === 'india' ? 'India' : 'World' }} — {{ metric }}
      </span>
      <button
        v-if="currentView === 'india'"
        @click="goBack"
        class="flex items-center gap-1 px-2 py-1 text-xs font-medium text-gray-600 bg-gray-100 rounded hover:bg-gray-200"
      >
        &larr; World View
      </button>
    </div>
    <div ref="chartRef" class="flex-1 min-h-[300px]"></div>
    <div v-if="unmapped && unmapped.length > 0" class="px-3 py-2 border-t">
      <p class="text-xs font-medium text-gray-500 mb-1">Unmapped Territories</p>
      <div class="flex flex-wrap gap-1">
        <span
          v-for="item in unmapped"
          :key="item.territory"
          class="px-2 py-0.5 text-xs bg-gray-100 rounded text-gray-600"
        >
          {{ item.territory }}: {{ item.value.toLocaleString() }}
        </span>
      </div>
    </div>
  </div>
</template>
