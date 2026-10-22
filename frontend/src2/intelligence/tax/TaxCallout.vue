<script setup lang="ts">
// Highlighted note with an optional headline figure.
defineProps<{ big?: string; title?: string }>()
</script>

<template>
	<aside class="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-outline-gray-2 border-l-4 border-l-warn-fill bg-card px-4 py-3">
		<span v-if="big" class="tnum text-xl font-semibold text-warn">{{ big }}</span>
		<p class="min-w-0 flex-1 text-sm text-ink-gray-7">
			<strong v-if="title" class="mr-1 font-semibold text-ink-gray-9">{{ title }}</strong>
			<slot />
		</p>
	</aside>
</template>
