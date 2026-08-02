<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
	title: string
	types: {
		icon: any
		label: string
		description: string
		tag?: string
		onClick?: () => void
	}[]
}>()

const show = defineModel()
</script>
<template>
	<Dialog v-model="show">
		<template #body>
			<div class="bg-surface-white px-4 py-5 text-base sm:p-6">
				<h3 class="text-lg font-medium leading-6 text-ink-gray-9">
					{{ props.title }}
				</h3>
				<div class="mt-4 grid grid-cols-1 gap-6">
					<div
						v-for="(type, index) in props.types"
						:key="index"
						class="group flex cursor-pointer items-center space-x-4"
						@click="type.onClick?.()"
					>
						<div
						class="rounded border p-4 text-ink-gray-4 shadow-sm transition-all group-hover:scale-105 motion-reduce:transition-none"
						>
							<component :is="type.icon" />
						</div>
						<div>
							<div class="flex items-center space-x-2">
								<p
								class="text-lg font-medium leading-6 text-ink-gray-9 transition-colors group-hover:text-accent motion-reduce:transition-none"
								>
									{{ type.label }}
								</p>
								<Badge v-if="type.tag" theme="green">
									{{ type.tag }}
								</Badge>
							</div>
							<p class="text-sm leading-5 text-ink-gray-6">
								{{ type.description }}
							</p>
						</div>
					</div>
				</div>
			</div>
		</template>
	</Dialog>
</template>
