import { apiClient } from './api-client'
import type {
  DataManagerResponse,
  IntegrationStatus,
  StatusCounts,
} from '../types/ap-data-manager'

const integrationStatuses: IntegrationStatus[] = [
  'healthy',
  'degraded',
  'down',
  'unknown',
]

export function summarizeIntegrationStatuses(
  integrations: Array<{ status: unknown }>
): StatusCounts {
  const counts: StatusCounts = {
    healthy: 0,
    degraded: 0,
    down: 0,
    unknown: 0,
  }

  for (const integration of integrations) {
    if (integrationStatuses.includes(integration.status as IntegrationStatus)) {
      counts[integration.status as IntegrationStatus] += 1
    }
  }

  return counts
}

export const getDataManager = () =>
  apiClient.get<DataManagerResponse>('/api/ap/data-manager')

export const refreshDataManager = () =>
  apiClient.post<DataManagerResponse>('/api/ap/data-manager/refresh')
