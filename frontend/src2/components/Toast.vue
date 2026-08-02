<template>
	<div class="m-2 flex transition duration-200 ease-out motion-reduce:transition-none">
		<div :class="['w-[22rem] rounded bg-surface-white p-3 shadow-md', variantClasses]">
			<div class="flex items-start">
				<div v-if="icon || variantIcon" class="mr-2 pt-1">
					<FeatherIcon
						:name="icon || variantIcon"
						:class="['h-4 w-4 rounded-full', variantIconClasses, iconClasses]"
					/>
				</div>
				<div>
					<slot>
					<p class="text-p-base font-medium text-ink-gray-9">
							{{ title }}
						</p>
						<p v-if="message" class="text-p-sm text-ink-gray-6">
							<span v-if="containsHTML" v-html="message"></span>
							<span v-else>{{ message }}</span>
						</p>
					</slot>
				</div>
				<div class="ml-auto pl-2">
					<slot name="actions">
						<!-- <button class="grid h-5 w-5 place-items-center rounded hover:bg-gray-100">
							<FeatherIcon name="x" class="h-4 w-4 text-gray-700" />
						</button> -->
					</slot>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ToastVariant } from '../helpers/toasts'

const props = defineProps<{
	title: string
	message?: string
	variant: ToastVariant
	icon?: string
	iconClasses?: string
}>()

const containsHTML = computed(() => props.message?.includes('<'))

const variantClasses = computed(() => {
	if (props.variant === 'success') {
		return 'bg-surface-green-1'
	}
	if (props.variant === 'info') {
		return 'bg-surface-blue-1'
	}
	if (props.variant === 'warning') {
		return 'bg-surface-amber-1'
	}
	if (props.variant === 'error') {
		return 'bg-surface-red-1'
	}
})

const variantIcon = computed(() => {
	if (props.variant === 'success') {
		return 'check'
	}
	if (props.variant === 'info') {
		return 'info'
	}
	if (props.variant === 'warning') {
		return 'alert-circle'
	}
	if (props.variant === 'error') {
		return 'x'
	}
})

const variantIconClasses = computed(() => {
	if (props.variant === 'success') {
		return 'text-ink-white bg-pos-fill p-0.5'
	}
	if (props.variant === 'info') {
		return 'text-ink-white bg-info-fill'
	}
	if (props.variant === 'warning') {
		return 'text-ink-white bg-warn-fill'
	}
	if (props.variant === 'error') {
		return 'text-ink-white bg-neg-fill p-0.5'
	}
})
</script>
