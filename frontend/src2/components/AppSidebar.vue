<template>
	<div
		class="flex h-full flex-col justify-between transition-all duration-300 ease-in-out motion-reduce:transition-none"
		:class="collapsed ? 'w-12' : 'w-56'"
	>
		<div class="flex flex-col overflow-hidden">
			<UserDropdown class="p-2" :isCollapsed="collapsed" />
			<div class="flex flex-col overflow-y-auto">
				<template v-for="group in navGroups" :key="group.label">
					<div
						v-if="!collapsed"
						class="px-4 pb-1 pt-3 text-xs font-medium uppercase tracking-wide text-ink-gray-5"
					>
						{{ group.label }}
					</div>
					<template v-for="link in group.links" :key="link.to">
						<SidebarLink
							v-if="!link.hidden"
							class="mx-2 my-0.5"
							:icon="link.icon"
							:label="link.label"
							:to="link.to"
							:isCollapsed="collapsed"
						/>
					</template>
				</template>
			</div>
		</div>
		<div>
			<TrialBanner v-if="is_fc_site" :is-sidebar-collapsed="collapsed" />
			<SidebarLink
				:label="theme === 'dark' ? 'Light mode' : 'Dark mode'"
				:icon="theme === 'dark' ? Sun : Moon"
				:isCollapsed="collapsed"
				@click="toggleTheme"
				class="mx-2 my-0.5"
			/>
			<SidebarLink
				label="Settings"
				:icon="SettingsIcon"
				:isCollapsed="collapsed"
				@click="showSettingsDialog = true"
				class="mx-2 my-0.5"
			/>
			<SidebarLink
				v-if="!inDrawer"
				:label="collapsed ? 'Expand' : 'Collapse'"
				:isCollapsed="collapsed"
				@click="isSidebarCollapsed = !isSidebarCollapsed"
				class="m-2"
			>
				<template #icon>
					<span class="grid h-5 w-6 flex-shrink-0 place-items-center">
						<PanelRightOpen
							class="h-4.5 w-4.5 text-ink-gray-7 duration-300 ease-in-out motion-reduce:duration-0"
							:class="{ '[transform:rotateY(180deg)]': collapsed }"
							stroke-width="1.5"
						/>
					</span>
				</template>
			</SidebarLink>
		</div>
	</div>

	<Settings v-model="showSettingsDialog" />
</template>

<script setup lang="ts">
import { useStorage } from '@vueuse/core'
import {
	Book,
	BookOpen,
	Database,
	DatabaseZap,
	LayoutDashboard,
	LayoutGrid,
	Moon,
	PanelRightOpen,
	Search,
	SettingsIcon,
	Sun,
} from 'lucide-vue-next'
import { computed, ref, type Component } from 'vue'
import { useTheme } from '../composables/useTheme'
import { DOMAIN_DASHBOARDS } from '../helpers/dashboards'
import useSettings from '../settings/settings'
import Settings from '../settings/Settings.vue'
import SidebarLink from './SidebarLink.vue'
import UserDropdown from './UserDropdown.vue'
import { TrialBanner } from 'frappe-ui/frappe'

const { theme, toggleTheme } = useTheme()

/**
 * Rendered inside the mobile slide-over rather than as a desktop column.
 *
 * The collapsed rail is a desktop affordance, and the preference is persisted.
 * Without this, a user who collapsed the sidebar on their laptop would open the
 * drawer on their phone and get a 48px sliver of icons.
 */
const props = withDefaults(defineProps<{ inDrawer?: boolean }>(), { inDrawer: false })

const isSidebarCollapsed = useStorage('insights:sidebarCollapsed', false)
/** In the drawer there is no rail: it is always the full panel. */
const collapsed = computed(() => (props.inDrawer ? false : isSidebarCollapsed.value))
const showSettingsDialog = ref(false)

const settings = useSettings()
const is_fc_site = window.is_fc_site

/**
 * Explicit so every group contributes the same shape to the union.
 *
 * Without it the registry-derived Intelligence links (which never set `hidden`)
 * and the Data group's conditional link formed a union where `hidden` existed on
 * only some members, and the template's `!link.hidden` stopped typechecking.
 */
interface NavLink {
	label: string
	icon: Component
	to: string
	hidden?: boolean
}

// Grouped, not a flat list of 20 siblings.
//
// Executive comes first because PRODUCT.md names management as a primary
// audience needing "instant status confidence"; previously they scrolled past
// twelve analyst dashboards to reach their own entry point.
//
// The redundant "Intelligence" suffix is dropped from each label: the group
// heading already carries it, and the old list mixed suffixed
// ("Customer Intelligence") with unsuffixed ("Manufacturing") arbitrarily.
const navGroups = computed<{ label: string; links: NavLink[] }[]>(() => [
	{
		label: 'Executive',
		links: [
			{ label: 'Overview', icon: LayoutDashboard, to: 'ExecutiveDashboard' },
		],
	},
	{
		label: 'Intelligence',
		// Built from `helpers/dashboards`, not hand-listed. This was one of five
		// independent copies of the domain list that were never in sync; the
		// registry is now the only place a domain is declared.
		links: DOMAIN_DASHBOARDS.map((d) => ({ label: d.label, icon: d.icon, to: d.route })),
	},
	{
		label: 'Explore',
		links: [
			{ label: 'Search', icon: Search, to: 'CrossDashboardSearch' },
			{ label: 'Dashboards', icon: LayoutGrid, to: 'DashboardList' },
			{ label: 'Workbooks', icon: Book, to: 'WorkbookList' },
		],
	},
	{
		label: 'Data',
		links: [
			{ label: 'Data Sources', icon: Database, to: 'DataSourceList' },
			{
				label: 'Data Store',
				icon: DatabaseZap,
				to: 'DataStoreList',
				hidden: !settings.doc.enable_data_store,
			},
			{ label: 'Knowledge Base', icon: BookOpen, to: 'KnowledgeBaseList' },
		],
	},
])
</script>
