<script setup lang="ts">
import SectionHeader from '../components/SectionHeader.vue'

withDefaults(
	defineProps<{
		title: string
		/** What the numbers are, e.g. "Oct 2026". */
		subtitle?: string
		/** Right-aligned unit or count, e.g. "5 of 124". */
		meta?: string
		/** Left accent rule for the one card a tab wants read first. */
		highlight?: boolean
	}>(),
	{ highlight: false },
)
</script>

<template>
	<section
		class="min-w-0 rounded-lg border bg-card p-4"
		:class="highlight ? 'border-warn' : 'border-outline-gray-2'"
	>
		<SectionHeader :title="title">
			<template v-if="meta" #actions>
				<span class="shrink-0 text-sm text-ink-gray-6">{{ meta }}</span>
			</template>
		</SectionHeader>
		<p v-if="subtitle" class="mt-0.5 text-sm text-ink-gray-6">{{ subtitle }}</p>
		<div class="mt-3"><slot /></div>
	</section>
</template>
