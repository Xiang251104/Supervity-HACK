export type APInsightSeverity = 'critical' | 'warning' | 'info'

export type APInsightActionType =
  | 'create_policy'
  | 'open_workbench'
  | 'rerun'
  | 'investigate'

export interface APInsight {
  id: number
  key: string
  title: string
  severity: APInsightSeverity
  body: string
  metric_value: number | null
  metric_unit: string | null
  evidence: Record<string, unknown> | null
  action_label: string | null
  action_type: APInsightActionType | null
  action_payload: Record<string, unknown> | null
  computed_at: string | null
  dismissed: boolean
}

export interface APInsightListResponse {
  items: APInsight[]
  total: number
  critical: number
  warning: number
  info: number
  decisions_analysed: number
  computed_at: string | null
}
