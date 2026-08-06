import { apiClient } from './api-client'
import type {
  WorkbenchAction,
  WorkbenchFilters,
  WorkbenchItemDetail,
  WorkbenchListResponse,
  WorkbenchResolvePayload,
} from '../types/ap-workbench'

interface ProtectedExposureItem {
  currency: string | null
  money_protected: number | null
}

export interface ProtectedExposureTotal {
  currency: string
  amount: number
}

export function summarizeProtectedExposure(
  items: ProtectedExposureItem[]
): ProtectedExposureTotal[] {
  const totals = new Map<string, number>()
  for (const item of items) {
    if (!item.currency || item.money_protected == null) continue
    totals.set(item.currency, (totals.get(item.currency) || 0) + item.money_protected)
  }
  return Array.from(totals, ([currency, amount]) => ({ currency, amount }))
}

export function buildWorkbenchQuery(filters: WorkbenchFilters): string {
  const params = new URLSearchParams()
  if (filters.status !== 'all') params.set('status', filters.status)
  if (filters.priority !== 'all') params.set('priority', filters.priority)
  const query = params.toString()
  return `/api/ap/workbench${query ? `?${query}` : ''}`
}

export function buildResolvePayload(
  action: WorkbenchAction,
  note: string
): WorkbenchResolvePayload {
  const trimmedNote = note.trim()
  if (!trimmedNote) throw new Error('Reviewer note is required')
  return { action, note: trimmedNote }
}

export function getWorkbenchItems(filters: WorkbenchFilters): Promise<WorkbenchListResponse> {
  return apiClient.get<WorkbenchListResponse>(buildWorkbenchQuery(filters))
}

export function getWorkbenchItem(itemId: number): Promise<WorkbenchItemDetail> {
  return apiClient.get<WorkbenchItemDetail>(`/api/ap/workbench/${itemId}`)
}

export function resolveWorkbenchItem(
  itemId: number,
  action: WorkbenchAction,
  note: string
): Promise<WorkbenchItemDetail> {
  return apiClient.post<WorkbenchItemDetail>(
    `/api/ap/workbench/${itemId}/resolve`,
    buildResolvePayload(action, note)
  )
}
