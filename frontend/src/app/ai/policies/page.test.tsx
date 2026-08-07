import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { StrictMode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AIPoliciesPage from './page'
import { getAPPolicies, updateAPPolicy } from '@/lib/ap-policies'
import type { APPolicy, APPolicyListResponse } from '@/types/ap-policies'

vi.mock('@/lib/ap-policies', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/ap-policies')>()
  return { ...actual, getAPPolicies: vi.fn(), updateAPPolicy: vi.fn() }
})

const snapshot: APPolicyListResponse = {
  total: 4,
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
    {
      key: 'payment_due_date',
      name: 'Payment due date',
      description: 'Blocks payments scheduled after the allowed due date.',
      options: null,
      value: '2026-08-31',
      unit: null,
      value_type: 'date',
      severity: 'block',
      active: true,
      version: 1,
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
    vi.stubGlobal(
      'ResizeObserver',
      class ResizeObserver {
        observe() {}
        unobserve() {}
        disconnect() {}
      }
    )
    vi.mocked(getAPPolicies).mockResolvedValue(snapshot)
    vi.mocked(updateAPPolicy).mockResolvedValue(snapshot.items[0])
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
    expect(within(summary).getByText('4')).toBeInTheDocument()
    expect(within(summary).getByText('3')).toBeInTheDocument()
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
    expect(screen.getAllByRole('article')).toHaveLength(4)
  })

  it('opens the appropriate type-specific editor for each live policy', async () => {
    render(<AIPoliciesPage />)

    await screen.findByRole('article', { name: 'Duplicate invoice ceiling policy' })

    fireEvent.click(screen.getByRole('button', { name: 'Edit Duplicate invoice ceiling' }))
    expect(screen.getByLabelText('Policy value')).toHaveAttribute('type', 'number')
    expect(screen.getByLabelText('Policy value')).toHaveAttribute('step', 'any')
    const numberDialog = screen.getByRole('dialog')
    expect(within(numberDialog).getByText('Policy details')).toBeInTheDocument()
    expect(within(numberDialog).getByText('duplicate_invoice_ceiling')).toBeInTheDocument()
    expect(
      within(numberDialog).getByText('Blocks invoices that exceed the duplicate-risk ceiling.')
    ).toBeInTheDocument()
    expect(within(numberDialog).getByText('number')).toBeInTheDocument()
    expect(within(numberDialog).getByText('5000 MYR')).toBeInTheDocument()
    expect(within(numberDialog).getByText('block')).toBeInTheDocument()
    expect(within(numberDialog).getByText('Active')).toBeInTheDocument()
    expect(within(numberDialog).getByText('7')).toBeInTheDocument()
    expect(within(numberDialog).getByText('finance.controller@example.com')).toBeInTheDocument()
    expect(
      within(numberDialog).getByText(formatPolicyTimestamp('2026-08-07T10:30:00Z'))
    ).toHaveAttribute('dateTime', '2026-08-07T10:30:00Z')
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))

    fireEvent.click(screen.getByRole('button', { name: 'Edit Unverified vendor route' }))
    const enumEditor = screen.getByLabelText('Policy value')
    expect(enumEditor.tagName).toBe('SELECT')
    expect(within(enumEditor).getAllByRole('option').map((option) => option.textContent)).toEqual([
      'manager',
      'director',
    ])
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))

    fireEvent.click(screen.getByRole('button', { name: 'Edit Weekend payment review' }))
    expect(screen.getByRole('switch', { name: 'Policy value' })).toBeChecked()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))

    fireEvent.click(screen.getByRole('button', { name: 'Edit Payment due date' }))
    expect(screen.getByLabelText('Policy value')).toHaveAttribute('type', 'date')
  })

  it('sends number decimals and an optional note in the PATCH payload', async () => {
    render(<AIPoliciesPage />)

    await screen.findByRole('article', { name: 'Duplicate invoice ceiling policy' })
    fireEvent.click(screen.getByRole('button', { name: 'Edit Duplicate invoice ceiling' }))
    fireEvent.change(screen.getByLabelText('Policy value'), { target: { value: '5000.25' } })
    fireEvent.change(screen.getByLabelText(/Change note/), { target: { value: '  temporary threshold  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save policy' }))

    await waitFor(() =>
      expect(updateAPPolicy).toHaveBeenCalledWith(
        'duplicate_invoice_ceiling',
        5000.25,
        'temporary threshold'
      )
    )
  })

  it('blocks invalid number values locally with a targeted message', async () => {
    render(<AIPoliciesPage />)

    await screen.findByRole('article', { name: 'Duplicate invoice ceiling policy' })
    fireEvent.click(screen.getByRole('button', { name: 'Edit Duplicate invoice ceiling' }))
    fireEvent.change(screen.getByLabelText('Policy value'), { target: { value: 'not-a-number' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save policy' }))

    expect(await screen.findByText('Policy value must be a number')).toBeInTheDocument()
    expect(updateAPPolicy).not.toHaveBeenCalled()
  })

  it('blocks invalid date values locally with a targeted message', async () => {
    render(<AIPoliciesPage />)

    await screen.findByRole('article', { name: 'Payment due date policy' })
    fireEvent.click(screen.getByRole('button', { name: 'Edit Payment due date' }))
    fireEvent.change(screen.getByLabelText('Policy value'), { target: { value: '2026-02-29' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save policy' }))

    expect(
      await screen.findByText('Policy date must be a valid YYYY-MM-DD date')
    ).toBeInTheDocument()
    expect(updateAPPolicy).not.toHaveBeenCalled()
  })

  it.each<[string, APPolicy['options']]>([
    ['null', null],
    ['non-string values', [1]],
    ['an empty list', []],
  ])('fails closed when enum option metadata contains %s', async (_label, options) => {
    vi.mocked(getAPPolicies).mockResolvedValue({
      ...snapshot,
      items: [{ ...snapshot.items[1], options }],
    })
    render(<AIPoliciesPage />)

    await screen.findByRole('article', { name: 'Unverified vendor route policy' })
    fireEvent.click(screen.getByRole('button', { name: 'Edit Unverified vendor route' }))
    expect(screen.queryByLabelText('Policy value')).not.toBeInTheDocument()
    expect(screen.getByText('Available enum options are unavailable.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save policy' }))

    expect(
      await screen.findByText('Policy value must match an available option')
    ).toBeInTheDocument()
    expect(updateAPPolicy).not.toHaveBeenCalled()
  })

  it('sends boolean values from the policy switch', async () => {
    render(<AIPoliciesPage />)

    await screen.findByRole('article', { name: 'Weekend payment review policy' })
    fireEvent.click(screen.getByRole('button', { name: 'Edit Weekend payment review' }))
    fireEvent.click(screen.getByRole('switch', { name: 'Policy value' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save policy' }))

    await waitFor(() =>
      expect(updateAPPolicy).toHaveBeenCalledWith(
        'weekend_payment_review',
        false,
        ''
      )
    )
  })

  it('disables duplicate save submission while the PATCH is pending', async () => {
    const update = deferred<typeof snapshot.items[0]>()
    vi.mocked(updateAPPolicy).mockReturnValue(update.promise)
    render(<AIPoliciesPage />)

    await screen.findByRole('article', { name: 'Duplicate invoice ceiling policy' })
    fireEvent.click(screen.getByRole('button', { name: 'Edit Duplicate invoice ceiling' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save policy' }))

    expect(screen.getByRole('button', { name: 'Saving policy' })).toBeDisabled()
    expect(updateAPPolicy).toHaveBeenCalledTimes(1)

    await act(async () => {
      update.resolve(snapshot.items[0])
      await update.promise
    })
  })

  it('keeps the editor open and reports server PATCH failures', async () => {
    vi.mocked(updateAPPolicy).mockRejectedValue(new Error('Version conflict'))
    render(<AIPoliciesPage />)

    await screen.findByRole('article', { name: 'Duplicate invoice ceiling policy' })
    fireEvent.click(screen.getByRole('button', { name: 'Edit Duplicate invoice ceiling' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save policy' }))

    expect(await screen.findByText('Version conflict')).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('clears a prior success status when a new edit fails to save', async () => {
    render(<AIPoliciesPage />)

    await screen.findByRole('article', { name: 'Duplicate invoice ceiling policy' })
    fireEvent.click(screen.getByRole('button', { name: 'Edit Duplicate invoice ceiling' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save policy' }))
    expect(await screen.findByText('Policy updated successfully')).toBeInTheDocument()

    vi.mocked(updateAPPolicy).mockRejectedValueOnce(new Error('Version conflict'))
    fireEvent.click(screen.getByRole('button', { name: 'Edit Weekend payment review' }))

    expect(screen.queryByText('Policy updated successfully')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save policy' }))
    expect(await screen.findByText('Version conflict')).toBeInTheDocument()
    expect(screen.queryByText('Policy updated successfully')).not.toBeInTheDocument()
  })

  it('refetches and displays the authoritative server snapshot after saving', async () => {
    const duplicatePolicy = snapshot.items[0] as Extract<APPolicy, { value_type: 'number' }>
    const authoritativeSnapshot: APPolicyListResponse = {
      ...snapshot,
      snapshot_label: 'Authoritative policy snapshot',
      items: [{ ...duplicatePolicy, value: 7250 }, ...snapshot.items.slice(1)],
    }
    vi.mocked(getAPPolicies)
      .mockResolvedValueOnce(snapshot)
      .mockResolvedValueOnce(authoritativeSnapshot)
    vi.mocked(updateAPPolicy).mockResolvedValue({ ...duplicatePolicy, value: 9999 })
    render(<AIPoliciesPage />)

    await screen.findByRole('article', { name: 'Duplicate invoice ceiling policy' })
    fireEvent.click(screen.getByRole('button', { name: 'Edit Duplicate invoice ceiling' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save policy' }))

    await waitFor(() => expect(getAPPolicies).toHaveBeenCalledTimes(2))
    expect(await screen.findByText('7250 MYR')).toBeInTheDocument()
    expect(screen.queryByText('9999 MYR')).not.toBeInTheDocument()
    expect(screen.getByText('Policy updated successfully')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('closes after PATCH success before starting the authoritative refetch', async () => {
    const duplicatePolicy = snapshot.items[0] as Extract<APPolicy, { value_type: 'number' }>
    const update = deferred<APPolicy>()
    const authoritativeFetch = deferred<APPolicyListResponse>()
    const authoritativeSnapshot: APPolicyListResponse = {
      ...snapshot,
      items: [{ ...duplicatePolicy, value: 7250 }, ...snapshot.items.slice(1)],
    }
    vi.mocked(getAPPolicies)
      .mockResolvedValueOnce(snapshot)
      .mockReturnValueOnce(authoritativeFetch.promise)
    vi.mocked(updateAPPolicy).mockReturnValue(update.promise)
    render(<AIPoliciesPage />)

    await screen.findByRole('article', { name: 'Duplicate invoice ceiling policy' })
    fireEvent.click(screen.getByRole('button', { name: 'Edit Duplicate invoice ceiling' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save policy' }))

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(getAPPolicies).toHaveBeenCalledTimes(1)

    await act(async () => {
      update.resolve(duplicatePolicy)
      await update.promise
    })

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(getAPPolicies).toHaveBeenCalledTimes(2)

    await act(async () => {
      authoritativeFetch.resolve(authoritativeSnapshot)
      await authoritativeFetch.promise
    })

    expect(await screen.findByText('7250 MYR')).toBeInTheDocument()
    expect(screen.getByText('Policy updated successfully')).toBeInTheDocument()
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
