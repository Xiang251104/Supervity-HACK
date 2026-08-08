/** Mirrors app/schemas/ap_runs.py. Keep in sync if that file changes. */

export interface RunRequest {
  invoice_ref: string
  run_id?: string
  workflow_id?: string
  trigger_source?: string
}

export interface DecisionOut {
  id: number
  belnr: string
  lifnr: string | null
  ebeln: string | null
  bukrs: string | null
  currency: string | null
  amount: number | null
  amount_myr: number | null
  verdict: string
  reason_codes: string[]
  money_protected: number
  spend_under_review: number
  policy_version_label: string | null
  confidence: number | null
  human_status: string | null
}

export interface PolicyEvaluationOut {
  policy_key: string
  policy_version: number
  threshold_value: unknown
  observed_value: unknown
  fired: boolean
  outcome: string | null
  explanation: string | null
}

export interface RunEventOut {
  seq: number
  event_type: string
  operator_name: string | null
  summary: string | null
  ts: string | null
}

export interface RunDetail {
  run_id: string
  invoice_ref: string | null
  workflow_run_id: string | null
  status: string
  trigger_source: string
  policy_version_label: string | null
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  error: string | null
  events: RunEventOut[]
  decision: DecisionOut | null
  policy_evaluations: PolicyEvaluationOut[]
  workbench_item_id: number | null
}
