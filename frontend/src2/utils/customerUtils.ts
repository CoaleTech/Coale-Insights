/**
 * Shared utility functions for customer-related components.
 * Used by CustomerIntelligence, CustomerDetail, and related views.
 *
 * STATUS VOCABULARY: All status colouring is via src2/utils/status.ts.
 * This file exposes ONLY formatters, filter constants, and localStorage helpers.
 *
 * The following colour-returning functions have been removed because they
 * duplicated the status vocabulary or applied identity labels as status colours:
 *   getTierColor, getTierBgColor, getTierIcon  (tier = identity, not status)
 *   getRfmColor                                (RFM segment = identity, not status)
 *   getRiskColor, getHealthColor, getHealthBgColor, getPriorityColor
 *
 * Callers should use severityBadge / severityFill from src2/utils/status.ts,
 * mapping existing string keys through ragSeverity or a direct Severity value.
 * Tier and RFM segment labels are rendered as
 *   <Badge theme="gray" variant="subtle" :label="tier" size="sm" />
 * with no colour coding.
 */

// ─── Currency & Number Formatting ────────────────────────────────────────────
//
// Delegated to `utils/format.ts`, the single money vocabulary. These used to
// default `currency` to 'KES' and format with the `en-KE` locale, which renders
// KES as "Ksh": the headline CLV on Customer Intelligence read
// "Ksh 713,447,224" on a company whose base currency is INR. The default is now
// null, so a caller that forgets to pass one gets an unprefixed number rather
// than a confidently wrong currency.

import { formatCount, formatMoney } from './format'

export function formatCurrency(
  value: number | undefined | null,
  currency: string | null = null,
): string {
  return formatMoney(value, currency)
}

export function formatCurrencyCompact(
  value: number | undefined | null,
  currency: string | null = null,
): string {
  return formatMoney(value, currency, { compact: true })
}

export function formatNumber(value: number | undefined | null, decimals = 0): string {
  return formatCount(value, { decimals })
}

export function formatPercent(value: number | undefined | null): string {
  return `${(value || 0).toFixed(1)}%`
}

export { formatDate } from './format'

// ─── Action Taxonomy ─────────────────────────────────────────────────────────
// The API returns SCREAMING_SNAKE enums. `replace(/_/g, ' ')` was wrong for two
// of the six: RE_ENGAGEMENT read "RE ENGAGEMENT" and PAYMENT_FOLLOW_UP read
// "PAYMENT FOLLOW UP". Both need a hyphen, which no mechanical transform infers,
// so the known values are spelled out.

const ACTION_LABELS: Record<string, string> = {
  CHURN_PREVENTION: 'Churn prevention',
  GROWTH_OPPORTUNITY: 'Growth opportunity',
  NEW_CUSTOMER_NURTURE: 'New customer nurture',
  PAYMENT_FOLLOW_UP: 'Payment follow-up',
  RE_ENGAGEMENT: 'Re-engagement',
  UPSELL_OPPORTUNITY: 'Upsell opportunity',
}

/** Sentence-case label for an action enum. Unknown values degrade to a
 *  readable sentence rather than leaking the raw enum. */
export function actionLabel(action: string | undefined | null): string {
  if (!action) return '-'
  const known = ACTION_LABELS[action]
  if (known) return known
  const words = action.replace(/_/g, ' ').toLowerCase().trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

// ─── Filter Option Constants ─────────────────────────────────────────────────
// Emoji removed. Values are unchanged so existing filter state is preserved.

export const tierFilterOptions = [
  { value: '', label: 'All Tiers' },
  { value: 'Diamond', label: 'Diamond' },
  { value: 'Platinum', label: 'Platinum' },
  { value: 'Gold', label: 'Gold' },
  { value: 'Silver', label: 'Silver' },
  { value: 'Bronze', label: 'Bronze' },
]

export const rfmSegmentFilterOptions = [
  { value: '', label: 'All Segments' },
  { value: 'Champions', label: 'Champions' },
  { value: 'Loyal Customers', label: 'Loyal Customers' },
  { value: 'Potential Loyalists', label: 'Potential Loyalists' },
  { value: 'New Customers', label: 'New Customers' },
  { value: 'Promising', label: 'Promising' },
  { value: 'Need Attention', label: 'Need Attention' },
  { value: 'About to Sleep', label: 'About to Sleep' },
  { value: 'At Risk', label: 'At Risk' },
  { value: "Can't Lose", label: "Can't Lose" },
  { value: 'Hibernating', label: 'Hibernating' },
  { value: 'Lost', label: 'Lost' },
]

export const riskFilterOptions = [
  { value: '', label: 'All Risk Levels' },
  { value: 'Critical', label: 'Critical' },
  { value: 'High', label: 'High' },
  { value: 'Medium', label: 'Medium' },
  { value: 'Low', label: 'Low' },
]

// ─── Recent Customers (localStorage) ─────────────────────────────────────────

const RECENT_KEY = 'insights:recentCustomers'

export function getRecentCustomers(): string[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]')
  } catch {
    return []
  }
}

export function addRecentCustomer(customerId: string): string[] {
  const recent = getRecentCustomers()
  const updated = [customerId, ...recent.filter((id) => id !== customerId)].slice(0, 5)
  localStorage.setItem(RECENT_KEY, JSON.stringify(updated))
  return updated
}
