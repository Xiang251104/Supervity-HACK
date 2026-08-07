import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { StrictMode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AIPoliciesPage from './page'
import { getAPPolicies } from '@/lib/ap-policies'
import type { APPolicyListResponse } from '@/types/ap-policies'

vi.mock('@/lib/ap-policies', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/ap-policies')>()
  return { ...actual, getAPPolicies: vi.fn() }
})

const snapshot: APPolicyListResponse = {
  total: 3,
  snapshot_label: 'AP governance snapshot · 07 Aug 2026',
  items: [
    {
      key: 'duplicate_invoice_ceiling',
      name: 'Duplicate invoice ceiling',
      description: 'Blocks invoices that exceed the duplicate-risk ceiling.',
      options: null,
      value: 5000,
      unit: 'MYR',
      value_type: 'number',
      severity: 'block',
      active: true,
      version: 7,
      updated_by: 'finance.controller@example.com',
      updated_at: '2026-08-07T10:30:00Z',
    },
    {
      key: 'unverified_vendor_route',
      name: 'Unverified vendor route',
      description: 'Escalates unverified vendors to the AP review queue.',
      options: ['manager', 'director'],
      value: 'manager',
      unit: null,
      value_type: 'enum',
      severity: 'escalate',
      active: false,
      version: 3,
      updated_by: 'ap.lead@example.com',
      updated_at: '2026-08-06T09:15:00Z',
    },
    {
      key: 'weekend_payment_review',
      name: 'Weekend payment review',
      description: 'Advises reviewers when a payment is scheduled for a weekend.',
      options: null,
      value: true,
      unit: null,
      value_type: 'boolean',
      severity: 'advise',
      active: true,
      version: 2,
      updated_by: 'policy.bot@example.com',
      updated_at: '2026-08-05T08:00:00Z',
    },
  ],
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function formatPolicyTimestamp(value: string): string {
  return new Intl.DateTimeFormat('en-MY', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

describe('AP Policies page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getAPPolicies).mockResolvedValue(snapshot)
  })

  it('shows a labelled loading state while AP policies are requested', () => {
    vi.mocked(getAPPolicies).mockReturnValue(new Promise(() => undefined))

    render(<AIPoliciesPage />)

    expect(screen.getByRole('status')).toHaveTextContent('Loading AP policies…')
    expect(screen.getByRole('button', { name: 'Refresh policies' })).toBeDisabled()
  })

  it('renders live policy fields and the API-derived summary', async () => {
    render(<AIPoliciesPage />)

    const policy = await screen.findByRole('article', {
      name: 'Duplicate invoice ceiling policy',
    })
    expect(within(policy).getByText('duplicate_invoice_ceiling')).toBeInTheDocument()
    expect(
      within(policy).getByText(
        'Blocks invoices that exceed the duplicate-risk ceiling.'
      )
    ).toBeInTheDocument()
    expect(within(policy).getByText('5000 MYR')).toBeInTheDocument()
    expect(within(policy).getByText('number')).toBeInTheDocument()
    expect(within(policy).getByText('Block')).toBeInTheDocument()
    expect(within(policy).getByText('Active')).toBeInTheDocument()
    expect(within(policy).getByText('7')).toBeInTheDocument()
    expect(
      within(policy).getByText('finance.controller@example.com')
    ).toBeInTheDocument()
    expect(
      within(policy).getByText(formatPolicyTimestamp('2026-08-07T10:30:00Z'))
    ).toHaveAttribute('dateTime', '2026-08-07T10:30:00Z')

    const inactive = screen.getByRole('article', {
      name: 'Unverified vendor route policy',
    })
    expect(within(inactive).getByText('Inactive')).toBeInTheDocument()
    expect(within(inactive).getByText('enum')).toBeInTheDocument()
    expect(within(inactive).getByText('Escalate')).toBeInTheDocument()

    const summary = screen.getByRole('region', { name: 'Policy summary' })
    expect(within(summary).getByText('3')).toBeInTheDocument()
    expect(within(summary).getByText('2')).toBeInTheDocument()
    expect(
      within(summary).getByText('AP governance snapshot · 07 Aug 2026')
    ).toBeInTheDocument()
    expect(within(summary).getByText('Duplicate invoice ceiling')).toBeInTheDocument()
    expect(
      within(summary).getByText(formatPolicyTimestamp('2026-08-07T10:30:00Z'))
    ).toHaveAttribute('dateTime', '2026-08-07T10:30:00Z')
  })

  it('shows a truthful empty state for an empty API response', async () => {
    vi.mocked(getAPPolicies).mockResolvedValue({
      total: 0,
      snapshot_label: 'No policy snapshot is available',
      items: [],
    })

    render(<AIPoliciesPage />)

    expect(await screen.findByText('No AP policies are available')).toBeInTheDocument()
    expect(
      screen.getByText('No policy snapshot is available')
    ).toBeInTheDocument()
    expect(screen.queryByText('No policies match the current filters')).not.toBeInTheDocument()
  })

  it('shows an API error and retries the request on user direction', async () => {
    vi.mocked(getAPPolicies)
      .mockRejectedValueOnce(new Error('Policy service unavailable'))
      .mockResolvedValueOnce(snapshot)

    render(<AIPoliciesPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Policy service unavailable'
    )
    fireEvent.click(
      screen.getByRole('button', { name: 'Retry loading policies' })
    )

    expect(
      await screen.findByRole('article', {
        name: 'Duplicate invoice ceiling policy',
      })
    ).toBeInTheDocument()
    expect(getAPPolicies).toHaveBeenCalledTimes(2)
  })

  it('ignores an older Strict Mode success after the newer snapshot loads', async () => {
    const older = deferred<APPolicyListResponse>()
    const newer = deferred<APPolicyListResponse>()
    const newerSnapshot: APPolicyListResponse = {
      total: 1,
      snapshot_label: 'Current AP governance snapshot',
      items: [snapshot.items[1]],
    }
    vi.mocked(getAPPolicies)
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise)

    render(
      <StrictMode>
        <AIPoliciesPage />
      </StrictMode>
    )
    await waitFor(() => expect(getAPPolicies).toHaveBeenCalledTimes(2))

    await act(async () => {
      newer.resolve(newerSnapshot)
      await newer.promise
    })
    expect(
      await screen.findByRole('article', { name: 'Unverified vendor route policy' })
    ).toBeInTheDocument()

    await act(async () => {
      older.resolve(snapshot)
      await older.promise
    })
    expect(
      screen.queryByRole('article', { name: 'Duplicate invoice ceiling policy' })
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('article', { name: 'Unverified vendor route policy' })
    ).toBeInTheDocument()
  })

  it('ignores an older Strict Mode failure after the newer snapshot loads', async () => {
    const older = deferred<APPolicyListResponse>()
    const newer = deferred<APPolicyListResponse>()
    vi.mocked(getAPPolicies)
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise)

    render(
      <StrictMode>
        <AIPoliciesPage />
      </StrictMode>
    )
    await waitFor(() => expect(getAPPolicies).toHaveBeenCalledTimes(2))

    await act(async () => {
      newer.resolve(snapshot)
      await newer.promise
    })
    expect(
      await screen.findByRole('article', { name: 'Duplicate invoice ceiling policy' })
    ).toBeInTheDocument()

    await act(async () => {
      older.reject(new Error('Stale AP policy failure'))
      await older.promise.catch(() => undefined)
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(
      screen.getByRole('article', { name: 'Duplicate invoice ceiling policy' })
    ).toBeInTheDocument()
  })

  it('filters live policy cards by search and severity controls', async () => {
    render(<AIPoliciesPage />)

    await screen.findByRole('article', {
      name: 'Duplicate invoice ceiling policy',
    })
    const search = screen.getByLabelText('Search AP policies')

    fireEvent.change(search, { target: { value: 'weekend' } })
    expect(
      screen.getByRole('article', { name: 'Weekend payment review policy' })
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('article', { name: 'Duplicate invoice ceiling policy' })
    ).not.toBeInTheDocument()

    fireEvent.change(search, { target: { value: 'does-not-exist' } })
    expect(
      screen.getByText('No policies match the current filters')
    ).toBeInTheDocument()

    fireEvent.change(search, { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Block policies' }))
    expect(
      screen.getByRole('article', { name: 'Duplicate invoice ceiling policy' })
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('article', { name: 'Unverified vendor route policy' })
    ).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Escalate policies' }))
    expect(
      screen.getByRole('article', { name: 'Unverified vendor route policy' })
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Advise policies' }))
    expect(
      screen.getByRole('article', { name: 'Weekend payment review policy' })
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'All policies' }))
    expect(screen.getAllByRole('article')).toHaveLength(3)
  })

  it('does not retain the generic policy-builder experiences', async () => {
    render(<AIPoliciesPage />)

    await screen.findByRole('article', {
      name: 'Duplicate invoice ceiling policy',
    })

    for (const obsoleteLabel of [
      'Create with AI',
      'Structured Builder',
      'Permission Matrix',
      'Expense Approval Policy',
      'Data Access Control',
    ]) {
      expect(screen.queryByText(obsoleteLabel)).not.toBeInTheDocument()
    }
  })
})
