<script setup lang="ts">
// Status chip. Colour is never the only carrier: every tone pairs an icon with
// the label text.
import { AlertCircle, CheckCircle2, Clock, Info, Minus } from 'lucide-vue-next'
import type { Chip } from './taxTypes'

defineProps<{ chip: Chip | null | undefined }>()

const TONES = {
	pos: { icon: CheckCircle2, cls: 'bg-surface-green-2 text-pos' },
	warn: { icon: Clock, cls: 'bg-surface-amber-1 text-warn' },
	neg: { icon: AlertCircle, cls: 'bg-surface-red-1 text-neg' },
	mut: { icon: Minus, cls: 'bg-surface-gray-2 text-ink-gray-7' },
	acc: { icon: Info, cls: 'bg-accent-soft text-accent-strong' },
} as const
</script>

<template>
	<span
		v-if="chip"
		class="inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium"
		:class="(TONES[chip.tone] ?? TONES.mut).cls"
	>
		<component :is="(TONES[chip.tone] ?? TONES.mut).icon" class="h-3 w-3 shrink-0" aria-hidden="true" />
		{{ chip.label }}
	</span>
	<span v-else class="text-ink-gray-6">-</span>
</template>
