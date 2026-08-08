export interface APExceptionCount {
  code: string
  count: number
}

export interface APAgingBucket {
  bucket: string
  count: number
}

export interface APRecentRun {
  run_id: string
  invoice_ref: string | null
  status: string
  started_at: string | null
  duration_ms: number | null
  policy_version_label: string | null
}

export interface APMetrics {
  invoices_processed: number
  touchless_rate: number
  pay_ready: number
  verdict_breakdown: Record<string, number>

  /** Grouped by currency. Never summed across currencies. */
  money_protected: Record<string, number>
  spend_under_review: Record<string, number>

  exceptions_by_type: APExceptionCount[]
  workbench_open: number
  workbench_resolved: number
  workbench_priority: Record<string, number>
  exception_aging: APAgingBucket[]

  average_confidence: number | null
  total_runs: number
  average_run_ms: number | null
  recent_runs: APRecentRun[]
  last_decision_at: string | null
}
