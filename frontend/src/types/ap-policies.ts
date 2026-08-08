export type APPolicyValueType = 'number' | 'enum' | 'boolean' | 'date'
export type APPolicyValue = string | number | boolean
export type APPolicySeverity = 'block' | 'escalate' | 'advise'

export interface APPolicyBase {
  key: string
  name: string
  description: string
  options: APPolicyValue[] | null
  unit: string | null
  severity: APPolicySeverity
  active: boolean
  version: number
  updated_at: string | null
  updated_by: string | null
}

export interface APNumberPolicy extends APPolicyBase {
  value_type: 'number'
  value: number
}

export interface APEnumPolicy extends APPolicyBase {
  value_type: 'enum'
  value: string
}

export interface APBooleanPolicy extends APPolicyBase {
  value_type: 'boolean'
  value: boolean
}

export interface APDatePolicy extends APPolicyBase {
  value_type: 'date'
  value: string
}

export type APPolicy =
  | APNumberPolicy
  | APEnumPolicy
  | APBooleanPolicy
  | APDatePolicy

export interface APPolicyListResponse {
  items: APPolicy[]
  total: number
  snapshot_label: string
}

export interface APPolicyUpdateRequest {
  value: APPolicyValue
  note: string
}

export interface APPolicyVersion {
  version: number
  value: APPolicyValue
  previous_value: APPolicyValue | null
  changed_by: string | null
  changed_at: string
  note: string | null
}

export interface APPolicyHistoryResponse {
  policy_key: string
  items: APPolicyVersion[]
  total: number
}

/**
 * One policy, applied to one invoice, on one run.
 *
 * The backend writes a row per policy per run whether or not it fired — that is
 * what makes the gate auditable rather than merely logged. It reaches the
 * Workbench inside the item's untyped `context`, so treat it as unvalidated JSON
 * until it has been through `parsePolicyEvaluations`.
 */
export interface APPolicyEvaluation {
  policy_key: string
  policy_version: number
  threshold_value: unknown
  observed_value: unknown
  fired: boolean
  outcome: string | null
  explanation: string | null
}

export type APPolicyValidationTarget = Pick<APPolicy, 'value_type' | 'options'>

export type APPolicyValueValidationResult =
  | { valid: true; value: APPolicyValue }
  | { valid: false; error: string }
