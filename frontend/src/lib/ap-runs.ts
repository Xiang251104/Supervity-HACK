import { apiClient } from './api-client'
import type { RunDetail, RunRequest } from '../types/ap-runs'

/**
 * Start one Orchestrator run from the Command Center itself.
 *
 * `trigger_source` is always "command_center" here — never claim this is
 * Outlook ingestion or any other channel. The audit trail should honestly
 * record how the run actually started.
 *
 * This call blocks for the whole run (commonly 60-100s: Auto's five
 * Operators, then the policy gate). There is no live progress stream from
 * the backend for this endpoint, so the caller shows a plain sequence of
 * status messages rather than real percentages.
 */
export const startRun = (payload: RunRequest): Promise<RunDetail> =>
  apiClient.post<RunDetail>('/api/ap/runs', {
    ...payload,
    trigger_source: 'command_center',
  })
