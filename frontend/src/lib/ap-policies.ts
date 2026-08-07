import { apiClient } from '@/lib/api-client'
import type {
  APPolicy,
  APPolicyHistoryResponse,
  APPolicyListResponse,
  APPolicyUpdateRequest,
  APPolicyValidationTarget,
  APPolicyValue,
  APPolicyValueValidationResult,
} from '@/types/ap-policies'

const invalidValue = (error: string): APPolicyValueValidationResult => ({
  valid: false,
  error,
})

export function validatePolicyValue(
  policy: APPolicyValidationTarget,
  rawValue: unknown
): APPolicyValueValidationResult {
  switch (policy.value_type) {
    case 'number': {
      if (typeof rawValue === 'number') {
        return Number.isFinite(rawValue)
          ? { valid: true, value: rawValue }
          : invalidValue('Policy number must be finite')
      }

      if (typeof rawValue !== 'string' || !rawValue.trim()) {
        return invalidValue('Policy value must be a number')
      }

      const value = Number(rawValue)
      return Number.isFinite(value)
        ? { valid: true, value }
        : invalidValue('Policy number must be finite')
    }
    case 'enum':
      return typeof rawValue === 'string' &&
        policy.options?.some((option) => option === rawValue)
        ? { valid: true, value: rawValue }
        : invalidValue('Policy value must match an available option')
    case 'boolean':
      return typeof rawValue === 'boolean'
        ? { valid: true, value: rawValue }
        : invalidValue('Policy value must be a boolean')
    case 'date':
      return isCanonicalDate(rawValue)
        ? { valid: true, value: rawValue }
        : invalidValue('Policy date must be a valid YYYY-MM-DD date')
    default:
      return invalidValue('Unsupported policy value type')
  }
}

export function formatPolicyValue(
  policy: Pick<APPolicy, 'value' | 'unit'>
): string {
  const unit = policy.unit?.trim()
  const value = String(policy.value)

  return unit ? `${value} ${unit}` : value
}

export const getAPPolicies = (): Promise<APPolicyListResponse> =>
  apiClient.get<APPolicyListResponse>('/api/ap/policies')

export function updateAPPolicy(
  key: string,
  value: APPolicyValue,
  note = ''
): Promise<APPolicy> {
  const payload: APPolicyUpdateRequest = { value, note: note.trim() }
  return apiClient.patch<APPolicy>(`/api/ap/policies/${key}`, payload)
}

export const getAPPolicyHistory = (
  key: string
): Promise<APPolicyHistoryResponse> =>
  apiClient.get<APPolicyHistoryResponse>(`/api/ap/policies/${key}/history`)

function isCanonicalDate(rawValue: unknown): rawValue is string {
  if (typeof rawValue !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(rawValue)) {
    return false
  }

  const year = Number(rawValue.slice(0, 4))
  if (year < 1 || year > 9999) return false

  const parsed = new Date(`${rawValue}T00:00:00.000Z`)
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === rawValue
}
