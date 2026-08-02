import { computed, ref, type ComputedRef, type Ref, type WritableComputedRef } from 'vue'

/**
 * Two-level tab navigation: a group control over a strip scoped to that group.
 *
 * Finance carried fourteen peer tabs in one flat row and Revenue thirteen, while
 * both already declared a `group` on every tab, already routed content by it, and
 * already scoped their two independent fetches' errors to it. Only the strip
 * stayed flat, and the label above it was a read-back of the current selection
 * rather than a control.
 *
 * Shared because the two dashboards had converged on the same shape; keeping one
 * copy means the position-memory behaviour cannot drift between them.
 */

/** Minimum shape a tab must have to be grouped. */
export interface GroupedTab<G extends string = string> {
	id: string
	label: string
	group: G
}

export interface GroupedTabs<G extends string, T extends GroupedTab<G>> {
	/** Selected group. Bind to a `TabButtons` control. */
	activeGroup: Ref<G>
	/** Tabs belonging to the selected group, in declaration order. */
	groupTabs: ComputedRef<T[]>
	/** `{ label }` list for frappe-ui `Tabs`. */
	tabItems: ComputedRef<{ label: string }[]>
	/**
	 * Index within the active group, not the full list. Bind to `Tabs`.
	 *
	 * Group-relative on purpose: a full-list index kept across a group switch
	 * would resolve to a tab from the group the user just left.
	 */
	activeTabIndex: WritableComputedRef<number>
	/** The selected tab, falling back to the group's first rather than nothing. */
	activeTab: ComputedRef<T>
}

export function useGroupedTabs<G extends string, T extends GroupedTab<G>>(
	tabs: T[],
	groups: readonly G[],
): GroupedTabs<G, T> {
	const activeGroup = ref(groups[0]) as Ref<G>
	const groupTabs = computed(() => tabs.filter((t) => t.group === activeGroup.value))
	const tabItems = computed(() => groupTabs.value.map((t) => ({ label: t.label })))

	/**
	 * Position is remembered per group, so returning lands where you left.
	 *
	 * Without this, the extra click a user pays to cross into the other group gets
	 * charged again on every switch back, which is the real cost of a two-level
	 * selector rather than the first click itself.
	 */
	const indexByGroup = ref<Record<string, number>>(Object.fromEntries(groups.map((g) => [g, 0])))
	const activeTabIndex = computed({
		get: () => indexByGroup.value[activeGroup.value] ?? 0,
		set: (i: number) => {
			indexByGroup.value[activeGroup.value] = i
		},
	})

	const activeTab = computed(() => groupTabs.value[activeTabIndex.value] ?? groupTabs.value[0] ?? tabs[0])

	return { activeGroup, groupTabs, tabItems, activeTabIndex, activeTab }
}

/**
 * Build the `TabButtons` list from the group order.
 *
 * Labels default to the group key title-cased, which is correct for every group
 * in use (`actuals`, `planning`, `revenue`, `customers`); pass `labels` when a
 * group key is not what a reader should see.
 */
export function groupButtons<G extends string>(
	groups: readonly G[],
	labels?: Partial<Record<G, string>>,
): { label: string; value: G }[] {
	return groups.map((value) => ({
		label: labels?.[value] ?? value.charAt(0).toUpperCase() + value.slice(1),
		value,
	}))
}
