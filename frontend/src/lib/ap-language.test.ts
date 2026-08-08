import { describe, expect, it } from 'vitest'

import {
  OPERATOR_INFO,
  REASON_INFO,
  STATUS_LABELS,
  humanizeCode,
  normalizeStatus,
  reasonInfo,
  reasonLabel,
} from '@/lib/ap-language'

describe('reasonInfo', () => {
  it('translates every code the agent is known to emit', () => {
    // The 18 codes observed across 53 live runs on 2026-08-08. A new code the
    // agent starts emitting should be added here and to the dictionary.
    const observed = [
      'RECEIPT_VARIANCE', 'LOW_CONFIDENCE', 'PO_CURRENCY_MISMATCH', 'PO_LINE_NO_MATCH',
      'GL_CODING_REQUIRED', 'MISSING_INPUT', 'VENDOR_BLOCKED', 'PO_OUT_OF_VALIDITY',
      'NON_PO_APPROVAL', 'VENDOR_MASTER_DUPLICATE', 'PO_VENDOR_MISMATCH', 'ENTITY_MISMATCH',
      'CREDIT_MEMO', 'NEAR_DUP_SUSPECT', 'DATE_AMBIGUOUS', 'BEC_SUSPECTED',
      'BANK_MISMATCH', 'BANK_ACCOUNT_UNKNOWN',
    ]
    for (const code of observed) {
      expect(REASON_INFO[code], `${code} has no dictionary entry`).toBeDefined()
      expect(REASON_INFO[code].label).not.toMatch(/_/)
    }
  })

  it('gives an unknown code a readable fallback instead of failing', () => {
    const info = reasonInfo('SOME_FUTURE_CODE')
    expect(info.label).toBe('Some future code')
    expect(info.tone).toBe('warning')
  })

  it('labels fraud in words a reviewer would say', () => {
    expect(reasonLabel('BEC_SUSPECTED')).toBe('Possible payment-redirect fraud')
    expect(reasonLabel('DUP_LATER_COPY')).toBe('Duplicate of an invoice already received')
  })
})

describe('humanizeCode', () => {
  it('keeps domain acronyms uppercase', () => {
    expect(humanizeCode('PO_EXPIRED_AGAIN')).toBe('PO expired again')
    expect(humanizeCode('NEW_GL_RULE')).toBe('New GL rule')
    expect(humanizeCode('DOA_ESCALATION')).toBe('DOA escalation')
  })

  it('handles empty and single-word codes', () => {
    expect(humanizeCode('')).toBe('')
    expect(humanizeCode('HOLD')).toBe('Hold')
  })
})

describe('normalizeStatus', () => {
  it('accepts the contract statuses', () => {
    expect(normalizeStatus('PASS')).toBe('PASS')
    expect(normalizeStatus('fail')).toBe('FAIL')
    expect(normalizeStatus(' Review ')).toBe('REVIEW')
    expect(normalizeStatus('NOT_APPLICABLE')).toBe('NOT_APPLICABLE')
    expect(normalizeStatus('ERROR')).toBe('ERROR')
  })

  it('maps the PO Entity Resolver deviation SUCCESS to PASS', () => {
    expect(normalizeStatus('SUCCESS')).toBe('PASS')
  })

  it('treats anything else as no result rather than guessing', () => {
    expect(normalizeStatus(undefined)).toBe('UNKNOWN')
    expect(normalizeStatus(null)).toBe('UNKNOWN')
    expect(normalizeStatus('COMPLETED')).toBe('UNKNOWN')
    expect(normalizeStatus(42)).toBe('UNKNOWN')
  })

  it('every status has a display label', () => {
    for (const status of ['PASS', 'FAIL', 'REVIEW', 'NOT_APPLICABLE', 'ERROR', 'UNKNOWN'] as const) {
      expect(STATUS_LABELS[status]).toBeTruthy()
    }
  })
})

describe('OPERATOR_INFO', () => {
  it('covers all six operators in processing order', () => {
    expect(OPERATOR_INFO.map((o) => o.key)).toEqual([
      'intake_result', 'duplicate_result', 'bank_result',
      'po_entity_result', 'match_result', 'entity_result',
    ])
  })

  it('names checks by what they do, not by workflow internals', () => {
    for (const operator of OPERATOR_INFO) {
      expect(operator.name).not.toMatch(/result|operator/i)
    }
  })
})
