import { apiClient } from '@/lib/api-client'
import { REASON_INFO, humanizeCode, verdictPlain } from '@/lib/ap-language'
import type { APMetrics } from '@/types/ap-metrics'

export const getAPMetrics = (): Promise<APMetrics> =>
  apiClient.get<APMetrics>('/api/ap/metrics')

/**
 * Money is held per currency because totals must never be added across them.
 * The dashboard tile can only show one number, so it shows the largest bucket
 * and reports how many others exist rather than inventing a combined figure.
 */
export function primaryCurrencyTotal(
  totals: Record<string, number>
): { amount: number; currency: string; otherCurrencies: number } | null {
  const entries = Object.entries(totals).filter(([, amount]) => Number.isFinite(amount))
  if (entries.length === 0) return null

  entries.sort((a, b) => b[1] - a[1])
  const [currency, amount] = entries[0]
  return { amount, currency, otherCurrencies: entries.length - 1 }
}

export function formatMoney(amount: number, currency: string): string {
  const rounded = Math.round(amount)
  if (rounded >= 1_000_000) return `${currency} ${(amount / 1_000_000).toFixed(2)}M`
  if (rounded >= 1_000) return `${currency} ${(amount / 1_000).toFixed(1)}K`
  return `${currency} ${amount.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

export function formatDuration(ms: number | null): string {
  if (ms === null || !Number.isFinite(ms)) return '—'
  if (ms < 1000) return `${ms} ms`
  const seconds = ms / 1000
  return seconds < 60 ? `${seconds.toFixed(1)}s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
}

/**
 * Reason codes in reviewer language: PO_LINE_NO_MATCH -> "Amount doesn't match
 * any PO line". Codes without a dictionary entry are humanized with acronyms
 * kept intact rather than mangled ("Bec suspected").
 */
export function humaniseCode(code: string): string {
  return REASON_INFO[code]?.label ?? humanizeCode(code)
}

/** One vocabulary everywhere: the dashboard says what the Workbench says. */
export const verdictLabel = (verdict: string): string => verdictPlain(verdict)

/** Bar width as a percentage of the largest count in the set. */
export function barPercent(count: number, values: number[]): number {
  const max = Math.max(...values, 0)
  return max > 0 ? Math.round((count / max) * 100) : 0
}
