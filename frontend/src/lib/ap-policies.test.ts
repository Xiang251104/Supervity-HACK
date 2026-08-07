import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiClient } from '@/lib/api-client'

import {
  formatPolicyValue,
  getAPPolicies,
  getAPPolicyHistory,
  updateAPPolicy,
  validatePolicyValue,
} from './ap-policies'

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    patch: vi.fn(),
  },
}))

describe('AP Policies API helpers', () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset()
    vi.mocked(apiClient.patch).mockReset()
  })

  it('gets the authoritative AP policy list', async () => {
    await getAPPolicies()

    expect(apiClient.get).toHaveBeenCalledWith('/api/ap/policies')
  })

  it('patches a policy with a trimmed optional note', async () => {
    await updateAPPolicy('PRICE-TOLERANCE', 3.5, ' August close ')

    expect(apiClient.patch).toHaveBeenCalledWith('/api/ap/policies/PRICE-TOLERANCE', {
      value: 3.5,
      note: 'August close',
    })
  })

  it('gets a policy history from its authoritative endpoint', async () => {
    await getAPPolicyHistory('PRICE-TOLERANCE')

    expect(apiClient.get).toHaveBeenCalledWith(
      '/api/ap/policies/PRICE-TOLERANCE/history'
    )
  })
})

describe('validatePolicyValue', () => {
  it('parses finite decimal number strings into JSON-compatible numbers', () => {
    expect(
      validatePolicyValue({ value_type: 'number', options: null }, ' 3.5 ')
    ).toEqual({ valid: true, value: 3.5 })
  })

  it.each(['', '   ', 'not-a-number', 'Infinity', 'NaN'])(
    'rejects an invalid number string: %j',
    (rawValue) => {
      const result = validatePolicyValue(
        { value_type: 'number', options: null },
        rawValue
      )

      expect(result).toMatchObject({ valid: false })
      if (!result.valid) expect(result.error).toContain('number')
    }
  )

  it('rejects non-finite numeric inputs', () => {
    const result = validatePolicyValue(
      { value_type: 'number', options: null },
      Number.POSITIVE_INFINITY
    )

    expect(result).toMatchObject({ valid: false })
    if (!result.valid) expect(result.error).toContain('finite')
  })

  it('requires an enum input to exactly match a server-supplied option', () => {
    const policy = { value_type: 'enum' as const, options: ['review', 'advisory'] }

    expect(validatePolicyValue(policy, 'review')).toEqual({
      valid: true,
      value: 'review',
    })
    expect(validatePolicyValue(policy, 'Review')).toMatchObject({ valid: false })
    expect(validatePolicyValue(policy, 'review ')).toMatchObject({ valid: false })
  })

  it('accepts only booleans for boolean policies', () => {
    expect(
      validatePolicyValue({ value_type: 'boolean', options: null }, false)
    ).toEqual({ valid: true, value: false })
    expect(
      validatePolicyValue({ value_type: 'boolean', options: null }, 'false')
    ).toMatchObject({ valid: false })
  })

  it('accepts canonical real ISO dates without rolling invalid dates over', () => {
    const policy = { value_type: 'date' as const, options: null }

    expect(validatePolicyValue(policy, '2026-02-28')).toEqual({
      valid: true,
      value: '2026-02-28',
    })
    expect(validatePolicyValue(policy, '2026-02-30')).toMatchObject({ valid: false })
    expect(validatePolicyValue(policy, '2026-2-28')).toMatchObject({ valid: false })
    expect(validatePolicyValue(policy, '2026-02-28T00:00:00Z')).toMatchObject({
      valid: false,
    })
  })

  it('fails closed for unknown policy value types', () => {
    expect(
      validatePolicyValue(
        { value_type: 'unexpected' as never, options: null },
        'anything'
      )
    ).toMatchObject({ valid: false })
  })
})

describe('formatPolicyValue', () => {
  it('uses the API boolean value plainly without inventing a label', () => {
    expect(formatPolicyValue({ value: true, unit: null })).toBe('true')
  })

  it('adds only a non-empty unit as display metadata', () => {
    expect(formatPolicyValue({ value: 3.5, unit: ' % ' })).toBe('3.5 %')
    expect(formatPolicyValue({ value: 3.5, unit: '   ' })).toBe('3.5')
  })

  it('preserves an ISO date exactly without timezone conversion', () => {
    expect(formatPolicyValue({ value: '2026-08-07', unit: null })).toBe('2026-08-07')
  })
})
