import { describe, expect, it } from 'vitest'

import {
  buildResolvePayload,
  buildWorkbenchQuery,
  summarizeProtectedExposure,
} from './ap-workbench'

describe('buildWorkbenchQuery', () => {
  it('includes only active status and priority filters', () => {
    expect(buildWorkbenchQuery({ status: 'open', priority: 'critical' })).toBe(
      '/api/ap/workbench?status=open&priority=critical'
    )
  })

  it('omits all-filter values', () => {
    expect(buildWorkbenchQuery({ status: 'all', priority: 'all' })).toBe(
      '/api/ap/workbench'
    )
  })
})

describe('buildResolvePayload', () => {
  it('trims the mandatory reviewer note without changing the action', () => {
    expect(buildResolvePayload('request_info', '  Ask the vendor for proof.  ')).toEqual({
      action: 'request_info',
      note: 'Ask the vendor for proof.',
    })
  })

  it('rejects a blank reviewer note', () => {
    expect(() => buildResolvePayload('approve', '   ')).toThrow(
      'Reviewer note is required'
    )
  })
})

describe('summarizeProtectedExposure', () => {
  it('keeps protected exposure separated by currency', () => {
    expect(
      summarizeProtectedExposure([
        { currency: 'MYR', money_protected: 100 },
        { currency: 'USD', money_protected: 20 },
        { currency: 'MYR', money_protected: 50 },
      ])
    ).toEqual([
      { currency: 'MYR', amount: 150 },
      { currency: 'USD', amount: 20 },
    ])
  })
})
