<!--
  A dated obligation list: what falls due, when, who owns it, and where it
  stands.

  The date tile is split month-over-day because these rows are read as a
  calendar, not as a table of timestamps: the reader is scanning for "what is
  this week", and a full `3 Feb 2026` string in a narrow column forces that
  comparison to happen word by word.

  An unparseable date renders verbatim rather than as a dash. Everywhere else
  in the shared vocabulary an unparseable value is absent, but a due date is
  the one field where the raw server string is more useful than its absence:
  a row that says `2026-13-01` is a data bug someone can act on, whereas a
  row that says `-` next to a live legal deadline hides one.

  Empty input renders `emptyText`. An empty bordered box is indistinguishable
  from a panel that failed to load.
-->
<template>
  <ul v-if="rows.length" class="divide-y divide-outline-gray-1">
    <li
      v-for="(row, i) in rows"
      :key="`${row.date}-${i}`"
      class="flex min-w-0 items-center gap-3 py-2.5 first:pt-0 last:pb-0"
    >
      <!--
        `role="img"` with the full date as its label: read character by
        character, a two-line "SEP / 17" tile is announced as two unrelated
        fragments.
      -->
      <div
        class="flex h-10 w-10 shrink-0 flex-col items-center justify-center rounded-lg bg-surface-gray-2"
        role="img"
        :aria-label="formatDate(row.date)"
      >
        <span class="text-xs font-semibold uppercase leading-none text-ink-gray-6">
          {{ tile(row.date).month }}
        </span>
        <span class="tnum text-lg font-semibold leading-tight text-ink-gray-9">
          {{ tile(row.date).day }}
        </span>
      </div>

      <div class="min-w-0 flex-1">
        <p class="truncate text-sm font-medium text-ink-gray-8">{{ row.title }}</p>
        <p v-if="row.meta" class="truncate text-xs text-ink-gray-5">{{ row.meta }}</p>
      </div>

      <Badge v-if="row.status" v-bind="severityBadge(row.severity)" class="shrink-0">
        {{ row.status }}
      </Badge>
    </li>
  </ul>
  <p v-else class="text-sm text-ink-gray-5">{{ emptyText }}</p>
</template>

<script setup lang="ts">
defineOptions({ name: 'DateCalendar' })

import { Badge } from 'frappe-ui'
import { formatDate } from '../../utils/format'
import { severityBadge, type Severity } from '../../utils/status'

interface CalendarRow {
  /** ISO `YYYY-MM-DD`. */
  date: string
  title: string
  meta?: string
  /** Chip text. Omitted means no chip, which is different from an empty one. */
  status?: string
  severity?: Severity
}

withDefaults(
  defineProps<{
    rows: CalendarRow[]
    emptyText?: string
  }>(),
  { emptyText: 'Nothing scheduled' },
)

/**
 * Split for the two-line tile. Falls back to the raw string in the day slot
 * so a malformed date stays visible and diagnosable -- see the note at the
 * top of the file for why this one field departs from `NO_VALUE`.
 */
function tile(value: string): { month: string; day: string } {
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return { month: '', day: value ?? '' }
  return {
    month: d.toLocaleDateString('en-KE', { month: 'short' }),
    day: String(d.getDate()),
  }
}
</script>
