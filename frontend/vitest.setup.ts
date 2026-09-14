/**
 * jsdom 29 ships no Web Storage, so `window.localStorage` is `undefined` and
 * any spec that clears or asserts persistence dies in its own `beforeEach`.
 *
 * Silencing that by guarding the spec would be worse than the failure: the
 * code under test already guards the access itself
 * (`useTheme.ts:32` / `:68` check `typeof localStorage === 'undefined'`), so
 * with no Storage present the composable takes its degraded branch and never
 * writes anything. The persistence specs would then pass while proving
 * nothing. Install a real in-memory Storage instead, so "an explicit choice
 * survives a reload" is actually exercised.
 *
 * Defined as a plain own property rather than through `vi.stubGlobal`,
 * because the specs call `vi.unstubAllGlobals()` in `beforeEach` and that
 * would strip a stub away again before the first assertion.
 */
type StorageHost = { localStorage?: Storage }

/** Map, not a Record: this needs runtime insertion and deletion, `.size`,
 *  `.clear()` and key iteration, which is exactly what Storage exposes. */
function memoryStorage(): Storage {
	const data = new Map<string, string>()
	const storage = {
		get length() {
			return data.size
		},
		clear: () => data.clear(),
		getItem: (key: string): string | null => data.get(key) ?? null,
		key: (index: number): string | null => Array.from(data.keys())[index] ?? null,
		removeItem: (key: string) => void data.delete(key),
		setItem: (key: string, value: string) => void data.set(key, String(value)),
	}
	// Storage also carries a string index signature, for `storage.foo` access
	// that nothing here uses and an object literal cannot express.
	return storage as unknown as Storage
}

const hosts: StorageHost[] = [globalThis]
if (typeof window !== 'undefined' && window !== globalThis) hosts.push(window)

for (const host of hosts) {
	if (!host.localStorage) {
		Object.defineProperty(host, 'localStorage', {
			value: memoryStorage(),
			configurable: true,
			writable: true,
		})
	}
}
