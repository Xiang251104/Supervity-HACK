export type APPolicyValueType = 'number' | 'enum' | 'boolean' | 'date'
export type APPolicyValue = string | number | boolean
export type APPolicySeverity = 'block' | 'escalate' | 'advise'

export interface APPolicy {
  key: string
  name: string
  description: string
  value_type: APPolicyValueType
  value: APPolicyValue
  options: APPolicyValue[] | null
  unit: string | null
  severity: APPolicySeverity
  active: boolean
  version: number
  updated_at: string | null
  updated_by: string | null
}

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

export interface APPolicyValidationTarget {
  value_type: APPolicyValueType
  options: readonly APPolicyValue[] | null
}

export type APPolicyValueValidationResult =
  | { valid: true; value: APPolicyValue }
  | { valid: false; error: string }
