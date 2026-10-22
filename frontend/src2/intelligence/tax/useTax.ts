import { inject, type InjectionKey, type Ref } from 'vue'
import { formatCount, formatDate, formatDateShort, formatMoney, formatPercent, NO_VALUE } from '../../utils/format'
import type { Drill, Num } from './taxTypes'

export interface TaxCtx {
	currency: Ref<string | null>
	openDrill: (title: string, drill: Drill) => void
}
export const TAX_CTX: InjectionKey<TaxCtx> = Symbol('tax-ctx')

// Date-only ISO strings parse as UTC midnight, which shows the previous day west
// of UTC. Pin them to local midnight so the printed date is the payload's date.
const local = (v: string | null | undefined) => (v && v.length === 10 ? `${v}T00:00:00` : v)

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** `2026-11` -> `Nov`; `2026-W42` -> `W42`; anything else is passed through. */
export function periodLabel(key: string): string {
	const m = /^\d{4}-(\d{2})$/.exec(key)
	if (m) return MONTHS[Number(m[1]) - 1] ?? key
	const w = /^\d{4}-(W\d+)$/.exec(key)
	return w ? w[1] : key
}

export function useTax() {
	const ctx = inject(TAX_CTX)
	if (!ctx) throw new Error('useTax must be used inside TaxIntelligence')
	return {
		/** Exact money for tables: `KES 148,000`. */
		money: (v: Num | undefined) => formatMoney(v ?? null, ctx.currency.value),
		/** Compact money for bars and callouts: `KES 7.8M`. */
		moneyC: (v: Num | undefined) => formatMoney(v ?? null, ctx.currency.value, { compact: true }),
		count: (v: Num | undefined) => formatCount(v ?? null),
		pct: (v: Num | undefined, d = 1) => formatPercent(v ?? null, d),
		date: (v: string | null | undefined) => formatDate(local(v)),
		dateShort: (v: string | null | undefined) => formatDateShort(local(v)),
		text: (v: unknown) => (v === null || v === undefined || v === '' ? NO_VALUE : String(v)),
		/** Y-axis title for money charts, labelled by the payload's currency. */
		amountTitle: () => (ctx.currency.value ? `Amount (${ctx.currency.value})` : 'Amount'),
		openDrill: ctx.openDrill,
	}
}
