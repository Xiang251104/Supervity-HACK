export type APPolicyValueType = 'number' | 'enum' | 'boolean' | 'date'
export type APPolicySeverity = 'block' | 'escalate' | 'advise'

export interface APPolicyBase {
  key: string
  name: string
  description: string
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
  options: null
}

export interface APEnumPolicy extends APPolicyBase {
  value_type: 'enum'
  value: string
  options: string[]
}

export interface APBooleanPolicy extends APPolicyBase {
  value_type: 'boolean'
  value: boolean
  options: null
}

export interface APDatePolicy extends APPolicyBase {
  value_type: 'date'
  value: string
  options: null
}

export type APPolicy =
  | APNumberPolicy
  | APEnumPolicy
  | APBooleanPolicy
  | APDatePolicy

export type APPolicyValue = APPolicy['value']

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

export type APPolicyValidationTarget = Pick<APPolicy, 'value_type' | 'options'>

export type APPolicyValueValidationResult =
  | { valid: true; value: APPolicyValue }
  | { valid: false; error: string }
