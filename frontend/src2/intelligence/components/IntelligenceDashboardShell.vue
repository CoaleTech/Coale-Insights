<!--
  The state machine every intelligence dashboard needs, in one place.

  Manufacturing, ESG and HR each carried their own copy: three byte-identical
  permission blocks, three structurally identical error blocks, and a first-load
  skeleton that was character-for-character the same in two of them.

  Consolidating on MarketingCRM's version rather than the majority one, because
  the majority was worse in three ways the user can see:

  - No icon on the permission state, so it read as body copy rather than a stop.
  - No next step. "You do not have permission" without naming the access to ask
    for leaves the reader with nothing to do; MarketingCRM named it.
  - The error icon used `text-ink-gray-5`, a neutral, for a failure. Semantic
    colour belongs on a failure, and greys it out of the reader's attention.

  Error outranks the skeleton here. `loading` is first-load only
  (`useIntelligenceDashboard.ts:110`) so the two are mutually exclusive in
  practice, but ordering the failure first means a future change to that
  definition cannot hide an error behind a spinner.
-->
<template>
	<div v-if="isPermissionError" class="flex flex-1 items-center justify-center p-6">
		<div class="max-w-md rounded-lg border border-outline-gray-1 bg-surface-white p-8 text-center">
			<Lock class="mx-auto mb-3 h-8 w-8 text-ink-gray-5" aria-hidden="true" />
			<p class="font-medium text-ink-gray-8">Access restricted</p>
			<p class="mt-1 text-sm text-ink-gray-6">
				You do not have permission to view {{ subject }}.
			</p>
			<!-- Naming the permission is what turns this from a dead end into a
			     request the reader can actually make. -->
			<p v-if="permissionHint" class="mt-2 text-sm text-ink-gray-6">{{ permissionHint }}</p>
		</div>
	</div>

	<div v-else-if="error" class="flex flex-1 items-center justify-center p-6">
		<div class="max-w-md rounded-lg border border-outline-gray-1 bg-surface-white p-8 text-center">
			<TriangleAlert class="mx-auto mb-3 h-8 w-8 text-neg" aria-hidden="true" />
			<p class="font-medium text-ink-gray-8">Could not load {{ subject }}</p>
			<p class="mt-1 text-sm text-ink-gray-6">{{ error }}</p>
			<Button variant="subtle" class="mt-4" :loading="refreshing" @click="$emit('retry')">
				Try again
			</Button>
		</div>
	</div>

	<div v-else-if="loading" class="flex-1 overflow-auto">
		<!-- Overridable: a dashboard whose first screen is not a KPI strip should
		     describe its own shape rather than flash the wrong one. -->
		<slot name="skeleton">
			<div class="grid grid-cols-2 gap-4 p-6 md:grid-cols-3 lg:grid-cols-6">
				<KpiCard v-for="n in kpiCount" :key="n" label="" value="" loading />
			</div>
			<div class="space-y-3 p-6">
				<SkeletonBlock class="h-8 w-48" />
				<SkeletonBlock class="h-64 w-full rounded-lg" />
			</div>
		</slot>
	</div>

	<!--
		A cold cache answers `{status: "warming"}` while a background job fits the
		models. Distinct from `loading` (first paint, a skeleton) and from the
		empty state (a successful response with no rows): the numbers are coming,
		so say so and offer a manual re-check rather than a spinner with no end or
		a dead "no data" page.
	-->
	<div v-else-if="warming" class="flex flex-1 items-center justify-center p-6">
		<div class="max-w-md rounded-lg border border-outline-gray-1 bg-surface-white p-8 text-center">
			<Loader2 class="mx-auto mb-3 h-8 w-8 text-ink-gray-5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
			<p class="font-medium text-ink-gray-8">Preparing {{ subject }}</p>
			<p class="mt-1 text-sm text-ink-gray-6">
				This dashboard is being computed in the background. It can take a few
				minutes the first time.
			</p>
			<Button variant="subtle" class="mt-4" :loading="refreshing" @click="$emit('retry')">
				Check again
			</Button>
		</div>
	</div>

	<!--
		A `{status: "not_implemented"}` payload is an honest backend admitting a
		capability isn't built yet (see TODOS.md — "Frontend has zero awareness
		of status: not_implemented"). Distinct from `error` (something broke) and
		the empty state below (a real query with no rows): retrying or changing
		filters cannot help either of those read as "try again" or "no data for
		this period", which both mislead here.
	-->
	<div v-else-if="notImplemented" class="flex flex-1 items-center justify-center p-6">
		<div class="max-w-md rounded-lg border border-outline-gray-1 bg-surface-white p-8 text-center">
			<Wrench class="mx-auto mb-3 h-8 w-8 text-ink-gray-5" aria-hidden="true" />
			<p class="font-medium text-ink-gray-8">Not yet available</p>
			<p class="mt-1 text-sm text-ink-gray-6">
				{{ notImplementedMessage || `${subject} is not yet available.` }}
			</p>
		</div>
	</div>

	<!--
		`hasData` requires a payload, not just the absence of an error, so this
		branch cannot render over empty refs during a retry.
	-->
	<div v-else-if="hasData" class="flex-1 overflow-auto">
		<slot />
	</div>

	<div v-else class="flex flex-1 items-center justify-center p-6">
		<slot name="empty">
			<p class="text-sm text-ink-gray-6">No data available for this period.</p>
		</slot>
	</div>
</template>

<script setup lang="ts">
import { Button } from 'frappe-ui'
import { Lock, TriangleAlert, Loader2, Wrench } from 'lucide-vue-next'
import KpiCard from './KpiCard.vue'
import SkeletonBlock from './SkeletonBlock.vue'

withDefaults(
	defineProps<{
		loading?: boolean
		refreshing?: boolean
		error?: string | null
		isPermissionError?: boolean
		hasData?: boolean
		/**
		 * A cold cache answers `{status: "warming"}` while a background job fits
		 * the models. Distinct from `loading` (first paint) and the empty state
		 * (a success with no rows), so it gets its own branch and copy.
		 */
		warming?: boolean
		/**
		 * True when the API returned `{status: "not_implemented"}` one level down
		 * — an honest stub, not a failure. Takes precedence over `hasData`: the
		 * composable also nulls `payload` for this case, so the two never race.
		 */
		notImplemented?: boolean
		/** The backend's explanation shown in place of the generic copy. */
		notImplementedMessage?: string | null
		/**
		 * Lower-case noun phrase completing "permission to view ..." and
		 * "Could not load ...", e.g. `manufacturing data`. One string rather than
		 * two messages, because the three copies this replaces had already drifted
		 * into different phrasings of the same sentence.
		 */
		subject: string
		/** e.g. "Ask an administrator for Work Order read access." */
		permissionHint?: string
		/** Skeleton KPI count. Match the real strip so the page does not resize. */
		kpiCount?: number
	}>(),
	{
		loading: false,
		refreshing: false,
		error: null,
		isPermissionError: false,
		hasData: false,
		warming: false,
		notImplemented: false,
		notImplementedMessage: null,
		permissionHint: '',
		kpiCount: 6,
	},
)

defineEmits<{ retry: [] }>()
</script>
