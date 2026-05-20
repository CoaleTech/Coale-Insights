/**
 * Shared utility functions for customer-related components.
 * Used by CustomerIntelligence, CustomerDetail, and related views.
 */

// ─── Currency & Number Formatting ────────────────────────────────────────────

export function formatCurrency(value: number | undefined | null, currency: string = 'KES'): string {
  if (value === undefined || value === null) return `${currency} 0`
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

export function formatCurrencyCompact(value: number | undefined | null, currency: string = 'KES'): string {
  if (!value && value !== 0) return `${currency} 0`
  if (value >= 1_000_000) return `${currency} ${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${currency} ${(value / 1_000).toFixed(1)}K`
  return `${currency} ${value.toFixed(0)}`
}

export function formatNumber(value: number | undefined | null, decimals = 0): string {
  return new Intl.NumberFormat('en-KE', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value || 0)
}

export function formatPercent(value: number | undefined | null): string {
  return `${(value || 0).toFixed(1)}%`
}

export function formatDate(dateStr: string | undefined | null): string {
  if (!dateStr) return 'N/A'
  return new Date(dateStr).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

// ─── CLV Tier Helpers ────────────────────────────────────────────────────────

export function getTierColor(tier: string): string {
  const colors: Record<string, string> = {
    Diamond: 'bg-purple-600',
    Platinum: 'bg-blue-400',
    Gold: 'bg-yellow-500',
    Silver: 'bg-gray-400',
    Bronze: 'bg-amber-600',
  }
  return colors[tier] || 'bg-gray-300'
}

export function getTierBgColor(tier: string): string {
  const colors: Record<string, string> = {
    Diamond: 'bg-purple-50 border-purple-200',
    Platinum: 'bg-blue-50 border-blue-200',
    Gold: 'bg-yellow-50 border-yellow-200',
    Silver: 'bg-gray-50 border-gray-200',
    Bronze: 'bg-orange-50 border-orange-200',
  }
  return colors[tier] || 'bg-gray-50 border-gray-200'
}

export function getTierIcon(tier: string): string {
  const icons: Record<string, string> = {
    Diamond: '💎',
    Platinum: '🥇',
    Gold: '🥈',
    Silver: '🥉',
    Bronze: '🏅',
  }
  return icons[tier] || '👤'
}

// ─── Risk & Health Helpers ───────────────────────────────────────────────────

export function getRiskColor(risk: string): string {
  const colors: Record<string, string> = {
    Low: 'text-green-600 bg-green-100',
    Medium: 'text-yellow-600 bg-yellow-100',
    High: 'text-orange-600 bg-orange-100',
    Critical: 'text-red-600 bg-red-100',
  }
  return colors[risk] || 'text-gray-600 bg-gray-100'
}

export function getHealthColor(status: string): string {
  const colors: Record<string, string> = {
    Excellent: 'text-green-600',
    Good: 'text-blue-600',
    Healthy: 'text-blue-600',
    Average: 'text-yellow-600',
    'At Risk': 'text-orange-600',
    Poor: 'text-orange-600',
    Critical: 'text-red-600',
  }
  return colors[status] || 'text-gray-600'
}

export function getHealthBgColor(status: string): string {
  const colors: Record<string, string> = {
    Excellent: 'bg-green-100 text-green-700',
    Good: 'bg-blue-100 text-blue-700',
    Healthy: 'bg-blue-100 text-blue-700',
    Average: 'bg-yellow-100 text-yellow-700',
    'At Risk': 'bg-yellow-100 text-yellow-700',
    Poor: 'bg-orange-100 text-orange-700',
    Critical: 'bg-red-100 text-red-700',
  }
  return colors[status] || 'bg-gray-100 text-gray-700'
}

// ─── RFM Segment Helpers ─────────────────────────────────────────────────────

export function getRfmColor(segment: string): string {
  const colors: Record<string, string> = {
    Champions: 'bg-purple-100 text-purple-800',
    'Loyal Customers': 'bg-blue-100 text-blue-800',
    'Potential Loyalists': 'bg-cyan-100 text-cyan-800',
    'New Customers': 'bg-green-100 text-green-800',
    Promising: 'bg-teal-100 text-teal-800',
    'Need Attention': 'bg-yellow-100 text-yellow-800',
    'About to Sleep': 'bg-orange-100 text-orange-800',
    'At Risk': 'bg-red-100 text-red-800',
    "Can't Lose": 'bg-pink-100 text-pink-800',
    Hibernating: 'bg-gray-100 text-gray-600',
    Lost: 'bg-gray-200 text-gray-500',
  }
  return colors[segment] || 'bg-gray-100 text-gray-600'
}

// ─── Action Priority ─────────────────────────────────────────────────────────

export function getPriorityColor(priority: string): string {
  const colors: Record<string, string> = {
    High: 'bg-red-100 text-red-700 border-red-200',
    Medium: 'bg-yellow-100 text-yellow-700 border-yellow-200',
    Low: 'bg-green-100 text-green-700 border-green-200',
  }
  return colors[priority] || 'bg-gray-100 text-gray-700 border-gray-200'
}

// ─── Filter Option Constants ─────────────────────────────────────────────────

export const tierFilterOptions = [
  { value: '', label: 'All Tiers' },
  { value: 'Diamond', label: '💎 Diamond' },
  { value: 'Platinum', label: '🥇 Platinum' },
  { value: 'Gold', label: '🥈 Gold' },
  { value: 'Silver', label: '🥉 Silver' },
  { value: 'Bronze', label: '🏅 Bronze' },
]

export const rfmSegmentFilterOptions = [
  { value: '', label: 'All Segments' },
  { value: 'Champions', label: '🏆 Champions' },
  { value: 'Loyal Customers', label: '💙 Loyal Customers' },
  { value: 'Potential Loyalists', label: '🌟 Potential Loyalists' },
  { value: 'New Customers', label: '🆕 New Customers' },
  { value: 'Promising', label: '📈 Promising' },
  { value: 'Need Attention', label: '⚠️ Need Attention' },
  { value: 'About to Sleep', label: '😴 About to Sleep' },
  { value: 'At Risk', label: '🔴 At Risk' },
  { value: "Can't Lose", label: "💎 Can't Lose" },
  { value: 'Hibernating', label: '❄️ Hibernating' },
  { value: 'Lost', label: '👻 Lost' },
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
