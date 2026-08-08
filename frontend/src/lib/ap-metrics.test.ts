import { describe, expect, it } from 'vitest'

import {
  barPercent,
  formatDuration,
  formatMoney,
  humaniseCode,
  primaryCurrencyTotal,
  verdictLabel,
} from '@/lib/ap-metrics'

describe('primaryCurrencyTotal', () => {
  it('returns nothing when no money has been recorded', () => {
    expect(primaryCurrencyTotal({})).toBeNull()
  })

  it('picks the largest bucket rather than adding currencies together', () => {
    const result = primaryCurrencyTotal({ MYR: 1000, SGD: 5000, USD: 200 })

    expect(result).toEqual({ amount: 5000, currency: 'SGD', otherCurrencies: 2 })
  })

  it('reports no other currencies when only one is present', () => {
    expect(primaryCurrencyTotal({ MYR: 42 })).toEqual({
      amount: 42,
      currency: 'MYR',
      otherCurrencies: 0,
    })
  })

  it('ignores non-finite amounts', () => {
    expect(primaryCurrencyTotal({ MYR: Number.NaN })).toBeNull()
  })
})

describe('formatMoney', () => {
  it('abbreviates millions', () => {
    expect(formatMoney(40_070_000, 'MYR')).toBe('MYR 40.07M')
  })

  it('abbreviates thousands', () => {
    expect(formatMoney(943_523.28, 'MYR')).toBe('MYR 943.5K')
  })

  it('shows small amounts in full', () => {
    expect(formatMoney(942.5, 'SGD')).toBe('SGD 942.5')
  })
})

describe('formatDuration', () => {
  it('shows sub-second runs in milliseconds', () => {
    expect(formatDuration(850)).toBe('850 ms')
  })

  it('shows seconds with one decimal', () => {
    expect(formatDuration(4500)).toBe('4.5s')
  })

  it('shows minutes and seconds for long runs', () => {
    expect(formatDuration(125_000)).toBe('2m 5s')
  })

  it('renders a dash when there is no duration', () => {
    expect(formatDuration(null)).toBe('—')
  })
})

describe('humaniseCode', () => {
  it('turns a reason code into a sentence', () => {
    expect(humaniseCode('PO_LINE_NO_MATCH')).toBe('Po line no match')
    expect(humaniseCode('BEC_SUSPECTED')).toBe('Bec suspected')
  })
})

describe('verdictLabel', () => {
  it('maps every known verdict', () => {
    expect(verdictLabel('PAY_READY')).toBe('Pay ready')
    expect(verdictLabel('PAYMENT_HOLD')).toBe('Payment hold')
    expect(verdictLabel('HUMAN_REVIEW')).toBe('Human review')
    expect(verdictLabel('DATA_ERROR')).toBe('Data error')
  })

  it('falls back gracefully on an unknown verdict', () => {
    expect(verdictLabel('SOMETHING_NEW')).toBe('Something new')
  })
})

describe('barPercent', () => {
  it('scales against the largest value in the set', () => {
    expect(barPercent(5, [10, 5, 1])).toBe(50)
    expect(barPercent(10, [10, 5, 1])).toBe(100)
  })

  it('returns zero rather than dividing by zero', () => {
    expect(barPercent(0, [])).toBe(0)
    expect(barPercent(0, [0, 0])).toBe(0)
  })
})
