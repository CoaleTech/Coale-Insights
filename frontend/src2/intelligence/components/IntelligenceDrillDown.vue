<script setup lang="ts">
import type { DrillDownColumn } from '../composables/useDrillDown'
import { Lock, Inbox } from 'lucide-vue-next'

const props = defineProps<{
  show: boolean
  title: string
  columns: DrillDownColumn[]
  rows: Record<string, unknown>[]
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

function cellValue(row: Record<string, unknown>, col: DrillDownColumn): string {
  const val = row[col.fieldname]
  if (val === null || val === undefined) return '—'
  if (col.fieldtype === 'Currency') {
    return new Intl.NumberFormat(undefined, { style: 'decimal', minimumFractionDigits: 2 }).format(Number(val))
  }
  if (col.fieldtype === 'Date') {
    // Rows carry arbitrary DocType columns, so the value is genuinely unknown
    // here; Date wants a string or number.
    return new Date(String(val)).toLocaleDateString()
  }
  return String(val)
}

/**
 * Build ERPNext form URL for Link fieldtype columns.
 * Multi-word DocType names (e.g. "Sales Invoice") to "sales-invoice".
 */
function erpnextLink(col: DrillDownColumn, row: Record<string, unknown>): string | null {
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
        <div v-if="loading" class="flex flex-1 items-center justify-center gap-3 text-ink-gray-6">
          <LoadingIndicator class="h-5 w-5 text-ink-gray-6" />
          <span class="text-sm">Loading records…</span>
        </div>

        <!-- 2. NO PERMISSION — checked before generic error -->
        <div v-else-if="isPermissionError" class="flex flex-1 items-center justify-center">
          <div class="text-center">
            <Lock class="w-8 h-8 text-ink-gray-5 mx-auto mb-3" />
            <p class="text-sm font-medium text-ink-gray-7">You don't have permission to view these records.</p>
          </div>
        </div>

        <!-- 3. ERROR (non-permission) -->
        <div v-else-if="error" class="flex flex-1 flex-col items-center justify-center gap-4 p-6">
          <div class="w-full rounded border border-outline-gray-2 bg-surface-gray-2 p-3 text-sm text-ink-gray-8">
            {{ error }}
          </div>
          <Button variant="subtle" @click="emit('retry')">Try Again</Button>
        </div>

        <!-- 4. EMPTY -->
        <div v-else-if="rows.length === 0" class="flex flex-1 items-center justify-center">
          <div class="text-center text-ink-gray-6">
            <Inbox class="w-8 h-8 text-ink-gray-5 mx-auto mb-3" />
            <p class="text-sm">No records found for this metric.</p>
          </div>
        </div>

        <!-- 5. SUCCESS -->
        <template v-else>
          <div class="flex-1 overflow-auto">
            <table class="w-full min-w-max border-collapse text-sm">
              <thead class="sticky top-0 bg-surface-gray-1">
                <tr>
                  <th
                    v-for="col in columns"
                    :key="col.fieldname"
                    scope="col"
                    class="border-b px-4 py-2 text-left text-xs font-medium uppercase tracking-wide text-ink-gray-6"
                  >
                    {{ col.label }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, idx) in rows" :key="idx" class="border-b hover:bg-surface-gray-1">
                  <td v-for="col in columns" :key="col.fieldname" class="px-4 py-2 text-ink-gray-7">
                    <a
                      v-if="erpnextLink(col, row)"
                      :href="erpnextLink(col, row)!"
                      target="_blank"
                      class="text-ink-gray-8 underline underline-offset-2"
                    >{{ cellValue(row, col) }}</a>
                    <span v-else>{{ cellValue(row, col) }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="flex flex-shrink-0 items-center justify-between border-t bg-surface-white px-4 py-2 text-sm text-ink-gray-6">
            <Button variant="subtle" size="sm" :disabled="isPrevDisabled()" @click="emit('prev-page')">← Prev</Button>
            <span>Showing {{ rangeStart() }}–{{ rangeEnd() }} of {{ total }} records</span>
            <Button variant="subtle" size="sm" :disabled="isNextDisabled()" @click="emit('next-page')">Next →</Button>
          </div>
        </template>

      </div>
    </template>
  </Dialog>
</template>
