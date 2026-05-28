<script setup lang="ts">
import type { DrillDownColumn } from '../composables/useDrillDown'

const props = defineProps<{
  show: boolean
  title: string
  columns: DrillDownColumn[]
  rows: Record<string, any>[]
  loading: boolean
  error: string | null
  isPermissionError: boolean
  total: number
  page: number
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  'next-page': []
  'prev-page': []
  'close': []
  'retry': []
}>()

const pageSize = 50

function rangeStart() { return (props.page - 1) * pageSize + 1 }
function rangeEnd() { return Math.min(props.page * pageSize, props.total) }
function isPrevDisabled() { return props.page === 1 }
function isNextDisabled() { return props.page * pageSize >= props.total }

function cellValue(row: Record<string, any>, col: DrillDownColumn): string {
  const val = row[col.fieldname]
  if (val === null || val === undefined) return '—'
  if (col.fieldtype === 'Currency') {
    return new Intl.NumberFormat(undefined, { style: 'decimal', minimumFractionDigits: 2 }).format(Number(val))
  }
  if (col.fieldtype === 'Date') {
    return val ? new Date(val).toLocaleDateString() : '—'
  }
  return String(val)
}

/**
 * Build ERPNext form URL for Link fieldtype columns.
 * Multi-word DocType names (e.g. "Sales Invoice") → "sales-invoice".
 */
function erpnextLink(col: DrillDownColumn, row: Record<string, any>): string | null {
  if (col.fieldtype !== 'Link' || !col.options) return null
  const val = row[col.fieldname]
  if (!val) return null
  const routePart = col.options
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '-')
  return `/app/${routePart}/${encodeURIComponent(String(val))}`
}
</script>

<template>
  <Dialog
    :options="{ title, size: '5xl' }"
    :model-value="show"
    @update:model-value="emit('update:show', $event)"
  >
    <template #body-content>
      <div class="flex h-[32rem] w-full flex-col overflow-hidden">

        <!-- 1. LOADING — checked first -->
        <div v-if="loading" class="flex flex-1 items-center justify-center gap-3 text-gray-500">
          <LoadingIndicator class="h-5 w-5 text-gray-600" />
          <span class="text-sm">Loading records…</span>
        </div>

        <!-- 2. NO PERMISSION — checked before generic error -->
        <div v-else-if="isPermissionError" class="flex flex-1 items-center justify-center">
          <div class="text-center">
            <div class="text-4xl mb-3">🔒</div>
            <p class="text-sm font-medium text-gray-700">You don't have permission to view these records.</p>
          </div>
        </div>

        <!-- 3. ERROR (non-permission) -->
        <div v-else-if="error" class="flex flex-1 flex-col items-center justify-center gap-4 p-6">
          <div class="w-full rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {{ error }}
          </div>
          <Button variant="subtle" @click="emit('retry')">Try Again</Button>
        </div>

        <!-- 4. EMPTY -->
        <div v-else-if="rows.length === 0" class="flex flex-1 items-center justify-center">
          <div class="text-center text-gray-500">
            <div class="text-4xl mb-3">📭</div>
            <p class="text-sm">No records found for this metric.</p>
          </div>
        </div>

        <!-- 5. SUCCESS -->
        <template v-else>
          <div class="flex-1 overflow-auto">
            <table class="w-full min-w-max border-collapse text-sm">
              <thead class="sticky top-0 bg-gray-50">
                <tr>
                  <th
                    v-for="col in columns"
                    :key="col.fieldname"
                    class="border-b px-4 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500"
                  >
                    {{ col.label }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, idx) in rows" :key="idx" class="border-b hover:bg-gray-50">
                  <td v-for="col in columns" :key="col.fieldname" class="px-4 py-2 text-gray-700">
                    <a
                      v-if="erpnextLink(col, row)"
                      :href="erpnextLink(col, row)!"
                      target="_blank"
                      class="text-blue-600 underline-offset-2 hover:underline"
                    >{{ cellValue(row, col) }}</a>
                    <span v-else>{{ cellValue(row, col) }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="flex flex-shrink-0 items-center justify-between border-t bg-white px-4 py-2 text-sm text-gray-600">
            <Button variant="subtle" size="sm" :disabled="isPrevDisabled()" @click="emit('prev-page')">← Prev</Button>
            <span>Showing {{ rangeStart() }}–{{ rangeEnd() }} of {{ total }} records</span>
            <Button variant="subtle" size="sm" :disabled="isNextDisabled()" @click="emit('next-page')">Next →</Button>
          </div>
        </template>

      </div>
    </template>
  </Dialog>
</template>
