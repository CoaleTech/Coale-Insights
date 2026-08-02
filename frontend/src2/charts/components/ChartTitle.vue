<script setup>
const props = defineProps({
	title: { type: String, required: false },
})
</script>

<template>
	<div class="px-4 py-2 font-medium leading-6 text-ink-gray-8">
		{{ title }}
	</div>
</template>
