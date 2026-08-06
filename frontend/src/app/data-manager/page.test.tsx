import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { StrictMode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DataManagerPage from './page'
import { getDataManager, refreshDataManager } from '@/lib/ap-data-manager'
import type { DataManagerResponse } from '@/types/ap-data-manager'

vi.mock('@/lib/ap-data-manager', () => ({
  getDataManager: vi.fn(),
  refreshDataManager: vi.fn(),
}))

vi.mock('framer-motion', async (importOriginal) => {
  const actual = await importOriginal<typeof import('framer-motion')>()
  return { ...actual, useReducedMotion: vi.fn(() => true) }
})

const snapshot: DataManagerResponse = {
  integrations: [
    {
      key: 'outlook',
      name: 'Microsoft Outlook',
      category: 'channel',
      purpose: 'Receives invoice submissions from the AP mailbox.',
      status: 'unknown',
      measurement_method: 'recorded_run_activity',
      last_checked_at: null,
      latency_ms: null,
      records_seen: 0,
      last_activity_at: null,
      detail: { message: 'No Outlook-triggered runs have been recorded' },
      last_error: null,
    },
    {
      key: 'supabase',
      name: 'Supabase',
      category: 'data',
      purpose: 'Stores invoice and policy records.',
      status: 'healthy',
      measurement_method: 'read_only_endpoint_probe',
      last_checked_at: '2026-08-05T01:00:00Z',
      latency_ms: 83,
      records_seen: 450,
      last_activity_at: '2026-08-05T01:00:00Z',
      detail: { message: 'Read-only query succeeded', http_status: 206 },
      last_error: null,
    },
    {
      key: 'slack',
      name: 'Slack',
      category: 'channel',
      purpose: 'Delivers AP exception notifications.',
      status: 'down',
      measurement_method: 'recorded_delivery_activity',
      last_checked_at: '2026-08-05T01:00:00Z',
      latency_ms: null,
      records_seen: 2,
      last_activity_at: '2026-08-05T00:45:00Z',
      detail: { message: 'Latest delivery failed' },
      last_error: 'connector_failure',
    },
    {
      key: 'supervity',
      name: 'Supervity',
      category: 'orchestration',
      purpose: 'Coordinates AP workflow execution.',
      status: 'healthy',
      measurement_method: 'read_only_endpoint_probe',
      last_checked_at: '2026-08-05T01:00:00Z',
      latency_ms: 41,
      records_seen: 0,
      last_activity_at: '2026-08-05T01:00:00Z',
      detail: { message: 'Read-only run listing succeeded' },
      last_error: null,
    },
  ],
  counts: { healthy: 2, degraded: 0, down: 1, unknown: 1 },
  freshness_hours: 24,
  partial_failure: true,
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

describe('Data Manager page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getDataManager).mockResolvedValue(snapshot)
    vi.mocked(refreshDataManager).mockResolvedValue(snapshot)
  })

  it('shows an initial loading state while persisted health is requested', () => {
    vi.mocked(getDataManager).mockReturnValue(new Promise(() => undefined))

    render(<DataManagerPage />)

    const loading = screen.getByRole('status')
    expect(loading).toHaveTextContent('Loading integration health…')
    expect(loading.querySelector('svg')).toHaveClass('motion-safe:animate-spin')
  })

  it('renders the four integrations and API-provided status counts', async () => {
    render(<DataManagerPage />)

    expect(await screen.findByText('Microsoft Outlook')).toBeInTheDocument()
    expect(screen.getByText('Supabase')).toBeInTheDocument()
    expect(screen.getByText('Slack')).toBeInTheDocument()
    expect(screen.getByText('Supervity')).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { level: 2, name: 'Integration health' })
    ).toBeInTheDocument()
    expect(
      screen.getByRole('article', { name: 'Supabase integration' })
    ).not.toHaveStyle({ opacity: 0 })

    const summary = screen.getByRole('region', {
      name: 'Integration status summary',
    })
    expect(within(summary).getByText('2')).toBeInTheDocument()
    expect(within(summary).getByText('0')).toBeInTheDocument()
    expect(
      within(summary).getByText('1', { selector: '[data-status="down"] *' })
    ).toBeInTheDocument()
    expect(
      within(summary).getByText('1', { selector: '[data-status="unknown"] *' })
    ).toBeInTheDocument()
  })

  it('shows honest unknown activity, safe detail entries, and only available latency', async () => {
    render(<DataManagerPage />)

    const outlook = await screen.findByRole('article', {
      name: 'Microsoft Outlook integration',
    })
    const supabase = screen.getByRole('article', {
      name: 'Supabase integration',
    })

    expect(
      within(outlook).getByText('Awaiting real Outlook activity')
    ).toBeInTheDocument()
    expect(within(outlook).getAllByText('Never')).toHaveLength(2)
    expect(within(outlook).queryByText(/ms$/)).not.toBeInTheDocument()
    expect(within(supabase).getByText('83 ms')).toBeInTheDocument()
    expect(within(supabase).getByText('Measurement method')).toBeInTheDocument()
    expect(
      within(supabase).getByText('Read only endpoint probe')
    ).toBeInTheDocument()
    expect(
      within(supabase).getByText('Read-only query succeeded')
    ).toBeInTheDocument()
    expect(within(supabase).getByText('206')).toBeInTheDocument()
  })

  it('distinguishes an unconfigured probe from passive activity that has not happened yet', async () => {
    vi.mocked(getDataManager).mockResolvedValue({
      ...snapshot,
      integrations: snapshot.integrations.map((integration) => {
        if (integration.key === 'supabase') {
          return {
            ...integration,
            status: 'unknown' as const,
            latency_ms: null,
            last_activity_at: null,
            detail: { message: 'Health probe is not configured' },
          }
        }
        if (integration.key === 'slack') {
          return {
            ...integration,
            status: 'unknown' as const,
            last_activity_at: null,
            detail: { message: 'No delivery evidence has been recorded' },
            last_error: null,
          }
        }
        return integration
      }),
      counts: { healthy: 1, degraded: 0, down: 0, unknown: 3 },
    })

    render(<DataManagerPage />)

    const outlook = await screen.findByRole('article', {
      name: 'Microsoft Outlook integration',
    })
    const supabase = screen.getByRole('article', {
      name: 'Supabase integration',
    })
    const slack = screen.getByRole('article', { name: 'Slack integration' })

    expect(within(supabase).getByText('Not configured')).toBeInTheDocument()
    expect(
      within(outlook).getByText('Awaiting real Outlook activity')
    ).toBeInTheDocument()
    expect(
      within(slack).getByText('Awaiting real Slack activity')
    ).toBeInTheDocument()
  })

  it('shows a directed empty state when no integration registry rows exist', async () => {
    vi.mocked(getDataManager).mockResolvedValue({
      ...snapshot,
      integrations: [],
      counts: { healthy: 0, degraded: 0, down: 0, unknown: 0 },
    })

    render(<DataManagerPage />)

    expect(
      await screen.findByText('No integrations are registered')
    ).toBeInTheDocument()
    expect(
      screen.getByText(/seed the integration registry/i)
    ).toBeInTheDocument()
  })

  it('shows an initial request error and retries persisted-state loading', async () => {
    vi.mocked(getDataManager)
      .mockRejectedValueOnce(new Error('Registry unavailable'))
      .mockResolvedValueOnce(snapshot)

    render(<DataManagerPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Registry unavailable'
    )
    fireEvent.click(
      screen.getByRole('button', { name: 'Retry loading health' })
    )

    expect(await screen.findByText('Microsoft Outlook')).toBeInTheDocument()
    expect(getDataManager).toHaveBeenCalledTimes(2)
  })

  it('ignores an older Strict Mode GET success after the newer snapshot wins', async () => {
    const older = deferred<DataManagerResponse>()
    const newer = deferred<DataManagerResponse>()
    const newerSnapshot = {
      ...snapshot,
      integrations: snapshot.integrations.map((integration) =>
        integration.key === 'supabase'
          ? { ...integration, records_seen: 999 }
          : integration
      ),
    }
    vi.mocked(getDataManager)
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise)

    render(
      <StrictMode>
        <DataManagerPage />
      </StrictMode>
    )
    await waitFor(() => expect(getDataManager).toHaveBeenCalledTimes(2))

    await act(async () => {
      newer.resolve(newerSnapshot)
      await newer.promise
    })
    const supabase = await screen.findByRole('article', {
      name: 'Supabase integration',
    })
    expect(within(supabase).getByText('999')).toBeInTheDocument()

    await act(async () => {
      older.resolve({
        ...snapshot,
        integrations: [],
        counts: { healthy: 0, degraded: 0, down: 0, unknown: 0 },
      })
      await older.promise
    })
    expect(within(supabase).getByText('999')).toBeInTheDocument()
    expect(
      screen.queryByText('No integrations are registered')
    ).not.toBeInTheDocument()
  })

  it('ignores an older Strict Mode GET error after the newer snapshot wins', async () => {
    const older = deferred<DataManagerResponse>()
    const newer = deferred<DataManagerResponse>()
    vi.mocked(getDataManager)
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise)

    render(
      <StrictMode>
        <DataManagerPage />
      </StrictMode>
    )
    await waitFor(() => expect(getDataManager).toHaveBeenCalledTimes(2))

    await act(async () => {
      newer.resolve(snapshot)
      await newer.promise
    })
    expect(await screen.findByText('Microsoft Outlook')).toBeInTheDocument()

    await act(async () => {
      older.reject(new Error('Stale registry failure'))
      await older.promise.catch(() => undefined)
    })
    expect(screen.queryByText('Stale registry failure')).not.toBeInTheDocument()
    expect(screen.getByText('Microsoft Outlook')).toBeInTheDocument()
  })

  it('disables refresh and marks it busy while a refresh is pending', async () => {
    const pending = deferred<DataManagerResponse>()
    vi.mocked(refreshDataManager).mockReturnValue(pending.promise)

    render(<DataManagerPage />)
    const refresh = await screen.findByRole('button', {
      name: 'Refresh health',
    })
    fireEvent.click(refresh)

    expect(refresh).toBeDisabled()
    expect(refresh).toHaveAttribute('aria-busy', 'true')

    pending.resolve(snapshot)
    await waitFor(() => expect(refresh).not.toBeDisabled())
  })

  it('uses source-neutral wording for partial failure in the persisted snapshot', async () => {
    render(<DataManagerPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Latest health snapshot includes one or more integrations that are down.'
    )
  })

  it('announces a successful refresh result politely', async () => {
    render(<DataManagerPage />)
    const refresh = await screen.findByRole('button', {
      name: 'Refresh health',
    })
    const announcement = screen.getByRole('status')
    expect(announcement).toHaveAttribute('aria-live', 'polite')
    expect(announcement).toBeEmptyDOMElement()

    fireEvent.click(refresh)

    await waitFor(() =>
      expect(announcement).toHaveTextContent(
        'Integration health refreshed: 2 healthy, 0 degraded, 1 down, 1 unknown.'
      )
    )
  })

  it('treats the refresh response as the authoritative snapshot', async () => {
    const refreshed: DataManagerResponse = {
      ...snapshot,
      integrations: snapshot.integrations.map((integration) =>
        integration.key === 'outlook'
          ? {
              ...integration,
              status: 'healthy' as const,
              records_seen: 7,
              last_activity_at: '2026-08-05T01:30:00Z',
            }
          : integration
      ),
      counts: { healthy: 3, degraded: 0, down: 1, unknown: 0 },
    }
    vi.mocked(refreshDataManager).mockResolvedValue(refreshed)

    render(<DataManagerPage />)
    const outlook = await screen.findByRole('article', {
      name: 'Microsoft Outlook integration',
    })
    expect(within(outlook).getByText('Unknown')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Refresh health' }))

    await waitFor(() =>
      expect(within(outlook).getByText('Healthy')).toBeInTheDocument()
    )
    expect(within(outlook).getByText('7')).toBeInTheDocument()
    expect(
      within(outlook).queryByText('Awaiting real Outlook activity')
    ).not.toBeInTheDocument()
  })

  it('keeps the last successful snapshot visible when refresh fails and offers retry', async () => {
    vi.mocked(refreshDataManager)
      .mockRejectedValueOnce(new Error('Probe timed out'))
      .mockResolvedValueOnce(snapshot)

    render(<DataManagerPage />)
    expect(await screen.findByText('Microsoft Outlook')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Refresh health' }))

    expect(await screen.findByText('Probe timed out')).toBeInTheDocument()
    expect(screen.getByText('Microsoft Outlook')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry refresh' }))

    await waitFor(() => expect(refreshDataManager).toHaveBeenCalledTimes(2))
    expect(screen.queryByText('Probe timed out')).not.toBeInTheDocument()
  })
})
