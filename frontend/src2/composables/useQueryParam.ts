import { computed, getCurrentInstance, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

/**
 * A string ref mirrored to `?<key>=` on the current route, so a dashboard's
 * selected tab and date range survive reload, a shared link, and Back/Forward.
 *
 * - The default is omitted from the URL, so the plain page URL stays clean.
 * - Dashboards are kept alive off-screen, so the ref only writes while its own
 *   route is the active one (otherwise it would stamp its params onto whichever
 *   page the user navigated to).
 * - Outside a component (unit tests) it is a plain ref.
 */
export function useQueryParam(key: string, fallback: string) {
	if (!getCurrentInstance()) return ref(fallback)

	const route = useRoute()
	const router = useRouter()
	const owner = route.name
	const fromUrl = () => {
		const v = route.query[key]
		return typeof v === 'string' && v ? v : fallback
	}

	const state = ref(fromUrl())

	watch(state, (v) => {
		if (route.name !== owner || v === fromUrl()) return
		const query = { ...route.query }
		if (v === fallback) delete query[key]
		else query[key] = v
		router.push({ query })
	})
	watch(
		() => route.query[key],
		() => {
			if (route.name === owner) state.value = fromUrl()
		},
	)

	return state
}

/** A tab index backed by `?<key>=<id>`: `ids[index]` is what the URL carries. */
export function useQueryIndex(key: string, ids: readonly string[]) {
	const param = useQueryParam(key, ids[0])
	return computed({
		get: () => Math.max(0, ids.indexOf(param.value)),
		set: (i: number) => {
			param.value = ids[i] ?? ids[0]
		},
	})
}
