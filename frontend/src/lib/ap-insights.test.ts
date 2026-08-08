import { describe, expect, it } from 'vitest'

import {
  actionHref,
  evidenceEntries,
  formatMetric,
  sortInsights,
} from '@/lib/ap-insights'
import type { APInsight } from '@/types/ap-insights'

function insight(overrides: Partial<APInsight> = {}): APInsight {
  return {
    id: 1,
    key: 'touchless-rate',
    title: 'Touchless rate 40%',
    severity: 'info',
    body: 'body',
    metric_value: null,
    metric_unit: null,
    evidence: null,
    action_label: null,
    action_type: null,
    action_payload: null,
    computed_at: null,
    dismissed: false,
    ...overrides,
  }
}

describe('sortInsights', () => {
  it('orders critical before warning before info', () => {
    const sorted = sortInsights([
      insight({ id: 1, key: 'c', severity: 'info' }),
      insight({ id: 2, key: 'a', severity: 'critical' }),
      insight({ id: 3, key: 'b', severity: 'warning' }),
    ])

    expect(sorted.map((i) => i.severity)).toEqual(['critical', 'warning', 'info'])
  })

  it('breaks ties by key so the order is stable between renders', () => {
    const sorted = sortInsights([
      insight({ id: 1, key: 'zebra', severity: 'warning' }),
      insight({ id: 2, key: 'alpha', severity: 'warning' }),
    ])

    expect(sorted.map((i) => i.key)).toEqual(['alpha', 'zebra'])
  })

  it('does not mutate the array it was given', () => {
    const items = [
      insight({ id: 1, key: 'c', severity: 'info' }),
      insight({ id: 2, key: 'a', severity: 'critical' }),
    ]
    const original = [...items]

    sortInsights(items)

    expect(items).toEqual(original)
  })
})

describe('formatMetric', () => {
  it('joins the value and its unit', () => {
    expect(formatMetric({ metric_value: 40.2, metric_unit: '%' })).toBe('40.2 %')
  })

  it('groups thousands so large figures stay readable', () => {
    expect(formatMetric({ metric_value: 943523.28, metric_unit: 'MYR' })).toBe(
      `${(943523.28).toLocaleString(undefined, { maximumFractionDigits: 2 })} MYR`
    )
  })

  it('returns the bare number when the backend supplied no unit', () => {
    expect(formatMetric({ metric_value: 12, metric_unit: null })).toBe('12')
  })

  it('shows nothing rather than a placeholder when there is no metric', () => {
    expect(formatMetric({ metric_value: null, metric_unit: '%' })).toBeNull()
  })

  it('rejects a non-finite value instead of rendering Infinity', () => {
    expect(formatMetric({ metric_value: Number.POSITIVE_INFINITY, metric_unit: '%' })).toBeNull()
    expect(formatMetric({ metric_value: Number.NaN, metric_unit: '%' })).toBeNull()
  })
})

describe('actionHref', () => {
  it('sends policy actions to the Policies console', () => {
    expect(actionHref({ action_type: 'create_policy' })).toBe('/ai/policies')
  })

  it('sends queue actions to the Workbench', () => {
    expect(actionHref({ action_type: 'open_workbench' })).toBe('/workbench')
  })

  it('has no destination for actions that are not navigable', () => {
    expect(actionHref({ action_type: 'investigate' })).toBeNull()
    expect(actionHref({ action_type: 'rerun' })).toBeNull()
    expect(actionHref({ action_type: null })).toBeNull()
  })
})

describe('evidenceEntries', () => {
  it('returns nothing when an insight carries no evidence', () => {
    expect(evidenceEntries(null)).toEqual([])
  })

  it('passes scalars through unchanged', () => {
    expect(evidenceEntries({ processed: 11, pay_ready: 4, healthy: true })).toEqual([
      { label: 'processed', value: '11' },
      { label: 'pay_ready', value: '4' },
      { label: 'healthy', value: 'true' },
    ])
  })

  it('renders nested structures as readable JSON', () => {
    const [entry] = evidenceEntries({ protected_by_currency: { MYR: 1000, SGD: 500 } })

    expect(entry.label).toBe('protected_by_currency')
    expect(JSON.parse(entry.value)).toEqual({ MYR: 1000, SGD: 500 })
  })
})
