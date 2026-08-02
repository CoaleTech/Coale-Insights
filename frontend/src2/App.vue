<template>
	<div class="flex h-screen w-screen overflow-hidden bg-canvas text-base antialiased">
		<!--
			Desktop: the sidebar is a static column. Below 1024px it would leave
			under 560px of content, which is where the KPI grid and tab strips were
			measured breaking, so it becomes an overlay instead.
		-->
		<div
			v-if="!hideSidebar"
			class="hidden h-full border-r border-outline-gray-1 bg-surface-white lg:block"
		>
			<AppSidebar />
		</div>

		<!--
			Mobile and tablet-portrait: the same sidebar in a slide-over.

			Built on headlessui's Dialog rather than a hand-rolled overlay so the
			focus trap, Escape handling, scroll lock and focus restore are the
			battle-tested implementations. frappe-ui 0.1.142 ships no drawer or
			sheet primitive, only a centred Dialog, and its own Dialog.vue imports
			these same components, so they are proven to bundle in this build.
		-->
		<TransitionRoot :show="drawerOpen" as="template" @after-leave="onDrawerClosed">
			<HDialog class="relative z-50 lg:hidden" @close="dismissDrawer">
				<TransitionChild
					as="template"
					enter="duration-200 ease-out motion-reduce:duration-0"
					enter-from="opacity-0"
					enter-to="opacity-100"
					leave="duration-150 ease-in motion-reduce:duration-0"
					leave-from="opacity-100"
					leave-to="opacity-0"
				>
					<!-- bg-black-overlay-200 is what frappe-ui's own Dialog uses for its
					     scrim. Reaching for an ink-family colour here instead compiled
					     to nothing: the preset scopes bg-* to the surface family, so
					     crossing roles emits zero CSS and the backdrop goes invisible. -->
					<div class="fixed inset-0 bg-black-overlay-200" aria-hidden="true" />
				</TransitionChild>

				<TransitionChild
					as="template"
					enter="duration-200 ease-out motion-reduce:duration-0"
					enter-from="-translate-x-full"
					enter-to="translate-x-0"
					leave="duration-150 ease-in motion-reduce:duration-0"
					leave-from="translate-x-0"
					leave-to="-translate-x-full"
				>
					<DialogPanel
						class="fixed inset-y-0 left-0 flex border-r border-outline-gray-1 bg-surface-white"
					>
						<DialogTitle class="sr-only">Navigation</DialogTitle>
						<AppSidebar in-drawer />
					</DialogPanel>
				</TransitionChild>
			</HDialog>
		</TransitionRoot>

		<div class="flex h-full flex-1 flex-col overflow-auto">
			<!--
				Sticky, because the dashboard's own header scrolls away and navigation
				has to stay reachable. Deliberately carries no page title: every
				dashboard header already states it, and repeating it here would spend
				scarce vertical space restating something on screen.
			-->
			<div
				v-if="!hideSidebar"
				class="sticky top-0 z-30 flex h-12 shrink-0 items-center gap-1 border-b border-outline-gray-1 bg-surface-white px-2 lg:hidden"
			>
				<button
					ref="drawerTrigger"
					type="button"
					class="flex h-11 w-11 items-center justify-center rounded-lg text-ink-gray-7 transition-colors duration-150 motion-reduce:duration-0 hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
					aria-label="Open navigation"
					@click="drawerOpen = true"
				>
					<svg
						class="h-5 w-5"
						viewBox="0 0 20 20"
						fill="none"
						stroke="currentColor"
						stroke-width="1.5"
						stroke-linecap="round"
						aria-hidden="true"
					>
						<path d="M3 6h14M3 10h14M3 14h14" />
					</svg>
				</button>
				<span class="text-sm font-medium text-ink-gray-8">Insights</span>
			</div>

			<RouterView v-slot="{ Component }">
				<Suspense>
					<KeepAlive :include="cachedViews">
						<component :is="Component" />
					</KeepAlive>
				</Suspense>
			</RouterView>
		</div>

		<template>
			<component v-for="dialog in dialogs" :is="dialog" :key="dialog.id" />
		</template>

		<Toaster
			position="bottom-right"
			:expand="true"
			:close-button="true"
			:toast-options="{ duration: 4000 }"
		/>
	</div>
</template>

<script setup lang="ts">
import {
	DialogPanel,
	DialogTitle,
	Dialog as HDialog,
	TransitionChild,
	TransitionRoot,
} from '@headlessui/vue'
import { computed, ref, watch, watchEffect } from 'vue'
import { useRoute } from 'vue-router'
import { Toaster } from 'vue-sonner'
import AppSidebar from './components/AppSidebar.vue'
import { useBreakpoint } from './composables/useBreakpoint'
import { dialogs } from './helpers/confirm_dialog'
import { attachRealtimeListener, waitUntil } from './helpers/index.ts'
import { DASHBOARD_ROUTE_NAMES, EXTRA_CACHED_VIEWS } from './helpers/dashboards'
import { createToast } from './helpers/toasts.ts'
import session from './session'
import telemetry from './telemetry.ts'
import router from '@/router.ts'

// Derived, not hand-listed: a dashboard omitted here silently loses its tab and
// filter state on every navigation, and this list had already drifted from the
// sidebar once.
const cachedViews = [...DASHBOARD_ROUTE_NAMES, ...EXTRA_CACHED_VIEWS]

const route = useRoute()
const hideSidebar = ref(false)
watchEffect(() => {
	// Show sidebar by default, hide only when explicitly set in route meta
	hideSidebar.value = Boolean(route.meta.isGuestView || route.meta.hideSidebar)
})

const drawerOpen = ref(false)
const drawerTrigger = ref<HTMLButtonElement | null>(null)

/**
 * Dismiss by Escape or backdrop, returning focus to the control that opened it.
 *
 * headlessui is supposed to restore focus itself, but measured here it did not:
 * after Escape the active element was `<body>`, dropping a keyboard user at the
 * top of the document to tab back through everything. WCAG 2.4.3 Focus Order.
 *
 * Getting this to stick took three attempts, each losing a race:
 *   - `nextTick`: worked for a backdrop click, lost on Escape.
 *   - `after-leave`: still lost on Escape, because headlessui's focus-trap
 *     cleanup runs when the panel unmounts, which is after that hook.
 *   - two animation frames past `after-leave`: lands after the unmount, so it
 *     is the last write to focus and holds for both dismissal paths.
 */
const restoreFocusOnClose = ref(false)

function dismissDrawer() {
	restoreFocusOnClose.value = true
	drawerOpen.value = false
}

function onDrawerClosed() {
	if (!restoreFocusOnClose.value) return
	restoreFocusOnClose.value = false
	requestAnimationFrame(() => requestAnimationFrame(() => drawerTrigger.value?.focus()))
}

// Navigating is the point of the drawer, so acting on it dismisses it. No focus
// restore here: the user chose a destination, and pulling focus back to the
// hamburger would fight the new page for it.
watch(() => route.fullPath, () => (drawerOpen.value = false))

// The panel is hidden by `lg:hidden` at desktop widths, but headlessui's focus
// trap does not care about CSS visibility: leaving it open across the breakpoint
// would trap the keyboard inside an invisible panel. Close on the way up.
const { isBelowDesktop } = useBreakpoint()
watch(isBelowDesktop, (below) => {
	if (!below) drawerOpen.value = false
})

const isGuestView = computed(() => route.meta.isGuestView || !session.isLoggedIn)
waitUntil(() => session.isLoggedIn).then(() => {
	telemetry.init()
})

attachRealtimeListener('insights_notification', (data: any) => {
	if (data.user == session.user.email) {
		createToast({
			title: data.title || data.message,
			message: data.title ? data.message : '',
			variant: data.type,
			duration: data.duration ? data.duration * 1000 : 4000,
		})
	}
})
</script>
