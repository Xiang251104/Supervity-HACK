import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  PolicyDecisionsPanel,
  formatPolicyValue,
  parsePolicyEvaluations,
} from './policy-decisions-panel'

const evaluations = [
  {
    policy_key: 'PRICE-TOLERANCE',
    policy_version: 1,
    threshold_value: 2,
    observed_value: null,
    fired: false,
    outcome: 'allow',
    explanation: 'Invoice amount had to match a PO line within 2%. Matched.',
  },
  {
    policy_key: 'MIN-CONFIDENCE',
    policy_version: 3,
    threshold_value: 0.7,
    observed_value: 0.62,
    fired: true,
    outcome: 'escalate',
    explanation: 'Extraction confidence must be at least 0.7 to auto-clear. Measured 0.62.',
  },
  {
    policy_key: 'GR-POLICY',
    policy_version: 3,
    threshold_value: 'fo_aware',
    observed_value: null,
    fired: false,
    outcome: 'allow',
    explanation: "Goods-receipt requirement is 'fo_aware'.",
  },
]

describe('parsePolicyEvaluations', () => {
  it('returns nothing for anything that is not an array', () => {
    // `context` is untyped JSON from the database, so every shape has to be survivable.
    for (const input of [null, undefined, {}, 'rows', 42]) {
      expect(parsePolicyEvaluations(input)).toEqual([])
    }
  })

  it('drops entries with no policy key rather than rendering a blank row', () => {
    const rows = parsePolicyEvaluations([
      { policy_key: 'DOA-BAND', fired: true },
      { policy_version: 2 },
      null,
      'nonsense',
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0].policy_key).toBe('DOA-BAND')
  })

  it('defaults a missing fired flag to false instead of assuming it acted', () => {
    const [row] = parsePolicyEvaluations([{ policy_key: 'RETRO-PO' }])
    expect(row.fired).toBe(false)
    expect(row.outcome).toBeNull()
  })
})

describe('formatPolicyValue', () => {
  it('omits values that carry no information', () => {
    for (const input of [null, undefined, '']) {
      expect(formatPolicyValue(input)).toBeNull()
    }
    expect(formatPolicyValue([])).toBeNull()
  })

  it('translates a stored config token into the words the policy page uses', () => {
    expect(formatPolicyValue('fo_aware')).toBe('Framework orders exempt')
  })

  it('humanises reason codes inside an observed list', () => {
    // A raw BANK_MISMATCH here would undo the vocabulary work on every other screen.
    const result = formatPolicyValue(['BANK_MISMATCH'])
    expect(result).not.toContain('BANK_MISMATCH')
    expect(result).toBeTruthy()
  })

  it('keeps plain numbers readable', () => {
    expect(formatPolicyValue(0.62)).toBe('0.62')
    expect(formatPolicyValue(0)).toBe('0')
  })
})

describe('PolicyDecisionsPanel', () => {
  it('lists rules that did nothing, not only the ones that fired', () => {
    // A gate you only see when it fires is indistinguishable from a gate that only
    // runs when it fires. All three must be on screen.
    render(<PolicyDecisionsPanel evaluations={evaluations} />)
    expect(screen.getByText('Price tolerance')).toBeInTheDocument()
    expect(screen.getByText('Minimum reading confidence')).toBeInTheDocument()
    expect(screen.getByText('Goods-receipt requirement')).toBeInTheDocument()
  })

  it('states how many rules ran and how many changed the outcome', () => {
    render(<PolicyDecisionsPanel evaluations={evaluations} />)
    expect(screen.getByText(/3 rules were applied/)).toBeInTheDocument()
    expect(screen.getByText(/1 of them changed the outcome/)).toBeInTheDocument()
  })

  it('says so plainly when nothing was changed', () => {
    render(<PolicyDecisionsPanel evaluations={[evaluations[0]]} />)
    expect(screen.getByText(/1 rule was applied/)).toBeInTheDocument()
    expect(screen.getByText(/None of them changed the outcome/)).toBeInTheDocument()
  })

  it('puts the rule that acted at the top of the list', () => {
    render(<PolicyDecisionsPanel evaluations={evaluations} />)
    const items = screen.getAllByRole('listitem')
    expect(within(items[0]).getByText('Minimum reading confidence')).toBeInTheDocument()
  })

  it('never shows a database policy key', () => {
    render(<PolicyDecisionsPanel evaluations={evaluations} />)
    for (const key of ['MIN-CONFIDENCE', 'PRICE-TOLERANCE', 'GR-POLICY']) {
      expect(screen.queryByText(key)).not.toBeInTheDocument()
    }
  })

  it('shows the setting used and what was found, so a changed threshold is visible', () => {
    // This is the evidence a judge looks for after editing a policy and re-running.
    render(<PolicyDecisionsPanel evaluations={evaluations} />)
    expect(screen.getByText('0.7')).toBeInTheDocument()
    expect(screen.getByText('0.62')).toBeInTheDocument()
    expect(screen.getByText('Framework orders exempt')).toBeInTheDocument()
  })

  it('degrades to a plain statement when no record was attached', () => {
    render(<PolicyDecisionsPanel evaluations={[]} />)
    expect(screen.getByText(/No policy record was attached/)).toBeInTheDocument()
  })
})
