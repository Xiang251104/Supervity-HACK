export type IntegrationStatus = 'healthy' | 'degraded' | 'down' | 'unknown'

export interface IntegrationHealth {
  key: string
  name: string
  category: string
  purpose: string
  status: IntegrationStatus
  measurement_method: string | null
  last_checked_at: string | null
  latency_ms: number | null
  records_seen: number
  last_activity_at: string | null
  detail: Record<string, string | number | boolean | null> | null
  last_error: string | null
}

export interface StatusCounts {
  healthy: number
  degraded: number
  down: number
  unknown: number
}

export interface DataManagerResponse {
  integrations: IntegrationHealth[]
  counts: StatusCounts
  freshness_hours: number
  partial_failure: boolean
}
