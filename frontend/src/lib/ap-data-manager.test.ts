import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiClient } from '@/lib/api-client'

import {
  getDataManager,
  refreshDataManager,
  summarizeIntegrationStatuses,
} from './ap-data-manager'

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

describe('summarizeIntegrationStatuses', () => {
  it('initializes all four statuses and counts recognized values', () => {
    expect(
      summarizeIntegrationStatuses([
        { status: 'healthy' },
        { status: 'unknown' },
        { status: 'healthy' },
        { status: 'down' },
      ])
    ).toEqual({ healthy: 2, degraded: 0, down: 1, unknown: 1 })
  })

  it('ignores unrecognized runtime statuses', () => {
    expect(
      summarizeIntegrationStatuses([
        { status: 'healthy' },
        { status: 'unexpected' },
        { status: null },
      ])
    ).toEqual({ healthy: 1, degraded: 0, down: 0, unknown: 0 })
  })
})

describe('Data Manager API helpers', () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset()
    vi.mocked(apiClient.post).mockReset()
  })

  it('gets the persisted Data Manager snapshot', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      integrations: [],
      counts: { healthy: 0, degraded: 0, down: 0, unknown: 0 },
      freshness_hours: 24,
      partial_failure: false,
    })

    await getDataManager()

    expect(apiClient.get).toHaveBeenCalledWith('/api/ap/data-manager')
  })

  it('posts an explicit Data Manager refresh', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      integrations: [],
      counts: { healthy: 0, degraded: 0, down: 0, unknown: 0 },
      freshness_hours: 24,
      partial_failure: false,
    })

    await refreshDataManager()

    expect(apiClient.post).toHaveBeenCalledWith('/api/ap/data-manager/refresh')
  })
})
