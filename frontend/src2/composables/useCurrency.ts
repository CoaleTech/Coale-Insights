import { computed, inject, unref, type ComputedRef, type Ref } from 'vue'
import { safeCurrency } from '../utils/format'

/**
 * The company currency for the surrounding dashboard, as a plain ISO code.
 *
 * Five components did `inject('currency', 'KES')`, whose default declares the
 * contract to be a string. `FinancialIntelligence.vue` provides
 * `provide('currency', baseCurrency)` -- the ref, not its value. Injection does
 * not unwrap, so every consumer held a `Ref<string>` while its type said
 * `string`, and TypeScript was happy because the inferred type came from the
 * default.
 *
 * Two of them hand-roll `new Intl.NumberFormat({ currency })` for `en-KE`
 * grouping. Handed a ref, Intl stringifies it to "[object Object]" and throws:
 *
 *     RangeError: Invalid currency code : [object Object]
 *
 * which is an unhandled render error -- it takes down the Financial
 * Intelligence cash-flow tab, not just the number it was formatting.
 *
 * Providing the ref is correct: `base_currency` arrives with the API response,
 * so a plain string captured at setup would be stale, and hardcoding "KES" is
 * wrong on any site whose company reports in something else. The contract
 * needed fixing, not the reactivity -- so this unwraps whatever was provided,
 * validates it, and hands back a computed that stays reactive.
 *
 * @param fallback used only when nothing was provided, or the provided value
 *   is not a valid ISO 4217 code.
 */
export function useCurrency(fallback = 'KES'): ComputedRef<string> {
	const provided = inject<Ref<string> | string>('currency', fallback)
	return computed(() => safeCurrency(unref(provided)) ?? fallback)
}
