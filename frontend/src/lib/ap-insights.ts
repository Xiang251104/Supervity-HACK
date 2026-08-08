import { apiClient } from '@/lib/api-client'
import type {
  APInsight,
  APInsightListResponse,
  APInsightSeverity,
} from '@/types/ap-insights'

export const getAPInsights = (): Promise<APInsightListResponse> =>
  apiClient.get<APInsightListResponse>('/api/ap/insights')

export const refreshAPInsights = (): Promise<APInsightListResponse> =>
  apiClient.post<APInsightListResponse>('/api/ap/insights/refresh', {})

export const dismissAPInsight = (id: number): Promise<APInsight> =>
  apiClient.post<APInsight>(`/api/ap/insights/${id}/dismiss`, {})

const SEVERITY_RANK: Record<APInsightSeverity, number> = {
  critical: 0,
  warning: 1,
  info: 2,
}

export function sortInsights(items: APInsight[]): APInsight[] {
  return [...items].sort((a, b) => {
    const bySeverity = SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]
    return bySeverity !== 0 ? bySeverity : a.key.localeCompare(b.key)
  })
}

/** A metric is only shown when the backend supplied both parts of it. */
export function formatMetric(insight: Pick<APInsight, 'metric_value' | 'metric_unit'>): string | null {
  const { metric_value: value, metric_unit: unit } = insight
  if (value === null || value === undefined || !Number.isFinite(value)) return null

  const formatted =
    Math.abs(value) >= 1000
      ? value.toLocaleString(undefined, { maximumFractionDigits: 2 })
      : String(value)

  return unit ? `${formatted} ${unit}` : formatted
}

/** Where an insight's action button should take the reviewer. */
export function actionHref(insight: Pick<APInsight, 'action_type'>): string | null {
  switch (insight.action_type) {
    case 'create_policy':
      return '/ai/policies'
    case 'open_workbench':
      return '/workbench'
    case 'investigate':
    case 'rerun':
      return null
    default:
      return null
  }
}

/** Evidence is rendered as key/value rows; nested structures are shown as JSON. */
export function evidenceEntries(
  evidence: Record<string, unknown> | null
): Array<{ label: string; value: string }> {
  if (!evidence) return []
  return Object.entries(evidence).map(([label, value]) => ({
    label,
    value:
      typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean'
        ? String(value)
        : JSON.stringify(value, null, 2),
  }))
}
