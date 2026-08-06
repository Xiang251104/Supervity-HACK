export type WorkbenchStatusFilter = 'all' | 'open' | 'resolved'
export type WorkbenchPriorityFilter = 'all' | 'critical' | 'high' | 'normal'
export type WorkbenchAction = 'approve' | 'reject' | 'request_info'

export interface WorkbenchFilters {
  status: WorkbenchStatusFilter
  priority: WorkbenchPriorityFilter
}

export interface WorkbenchItemSummary {
  id: number
  run_id: string
  decision_id: number | null
  belnr: string
  title: string
  exception_type: string
  priority: string
  status: string
  assigned_role: string | null
  created_at: string
  verdict: string | null
  currency: string | null
  amount: number | null
  money_protected: number | null
}

export interface WorkbenchDecision {
  id: number
  run_id: string
  belnr: string
  lifnr: string | null
  ebeln: string | null
  vendor_name: string | null
  currency: string | null
  amount: number | null
  verdict: string
  reason_codes: string[]
  evidence: Record<string, unknown> | null
  money_protected: number
  spend_under_review: number
  policy_version_label: string | null
  confidence: number | null
  human_status: string | null
  resolved_by: string | null
  resolved_at: string | null
  resolution_action: string | null
  resolution_note: string | null
}

export interface WorkbenchItemDetail {
  id: number
  run_id: string
  decision_id: number | null
  belnr: string
  title: string
  exception_type: string
  priority: string
  recommendation: string | null
  context: Record<string, unknown> | null
  assigned_role: string | null
  assigned_email: string | null
  status: string
  created_at: string
  resolved_at: string | null
  resolved_by: string | null
  action: string | null
  note: string | null
  decision: WorkbenchDecision | null
}

export interface WorkbenchListResponse {
  items: WorkbenchItemSummary[]
  total: number
}

export interface WorkbenchResolvePayload {
  action: WorkbenchAction
  note: string
}
