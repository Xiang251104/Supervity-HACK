import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import WorkbenchPage from './page'
import {
  getWorkbenchItem,
  getWorkbenchItems,
  resolveWorkbenchItem,
} from '@/lib/ap-workbench'

vi.mock('@/lib/ap-workbench', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/ap-workbench')>()
  return {
    ...actual,
    getWorkbenchItem: vi.fn(),
    getWorkbenchItems: vi.fn(),
    resolveWorkbenchItem: vi.fn(),
  }
})

const summary = {
  id: 7,
  run_id: 'run-7',
  decision_id: 19,
  belnr: '5110000017',
  title: 'Vendor mismatch requires review',
  exception_type: 'PO_VENDOR_MISMATCH',
  priority: 'critical',
  status: 'open',
  action: null,
  assigned_role: 'AP Manager',
  created_at: '2026-08-04T10:00:00Z',
  verdict: 'PAYMENT_HOLD',
  currency: 'MYR',
  amount: 805966.59,
  money_protected: 805966.59,
}

const detail = {
  ...summary,
  recommendation: 'Confirm the supplier identity before releasing payment.',
  context: {
    invoice_vendor: '4110006',
    po_vendor: '4110030',
    policies_evaluated: [
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
        explanation: 'Extraction confidence must be at least 0.7 to auto-clear.',
      },
    ],
  },
  assigned_email: null,
  resolved_at: null,
  resolved_by: null,
  action: null,
  note: null,
  decision: {
    id: 19,
    run_id: 'run-7',
    belnr: '5110000017',
    lifnr: '4110006',
    ebeln: '46200003',
    vendor_name: 'Demo Vendor',
    currency: 'MYR',
    amount: 805966.59,
    verdict: 'PAYMENT_HOLD',
    reason_codes: ['PO_VENDOR_MISMATCH'],
    evidence: { po_gr: { invoice_vendor: '4110006', po_vendor: '4110030' } },
    money_protected: 805966.59,
    spend_under_review: 0,
    policy_version_label: 'Standard v1.0',
    confidence: 0.99,
    human_status: 'PENDING_REVIEW',
    resolved_by: null,
    resolved_at: null,
    resolution_action: null,
    resolution_note: null,
  },
}

describe('AP Workbench page', () => {
  beforeEach(() => {
    vi.mocked(getWorkbenchItems).mockResolvedValue({ items: [summary], total: 1 })
    vi.mocked(getWorkbenchItem).mockResolvedValue(detail)
    vi.mocked(resolveWorkbenchItem).mockResolvedValue({
      ...detail,
      status: 'resolved',
      action: 'approve',
      note: 'Verified with procurement.',
      decision: { ...detail.decision, human_status: 'APPROVED' },
    })
  })

  it('shows the exception in plain language, never as a raw code', async () => {
    render(<WorkbenchPage />)

    expect(await screen.findByText('AP exception workbench')).toBeInTheDocument()
    // The reviewer sees words, not codes — in the queue card and the reason card.
    expect(
      (await screen.findAllByText('Purchase order belongs to a different vendor')).length
    ).toBeGreaterThan(0)
    expect((await screen.findAllByText('MYR 805,966.59')).length).toBeGreaterThan(0)
    // No raw code anywhere a reviewer reads.
    expect(screen.queryByText('PO_VENDOR_MISMATCH')).not.toBeInTheDocument()
    // Full evidence survives inside the collapsed audit record.
    expect(screen.getAllByText('4110030').length).toBeGreaterThan(0)
  })

  it('shows which rules were applied, including the ones that did nothing', async () => {
    // The gate's record used to reach the API and stop there; the reviewer saw only
    // a version label. Losing this section again would make the audit trail
    // invisible without failing anything else.
    render(<WorkbenchPage />)

    expect(await screen.findByText('Which rules were applied')).toBeInTheDocument()
    const section = screen.getByRole('region', { name: 'Which rules were applied' })
    expect(within(section).getByText(/2 rules were applied/)).toBeInTheDocument()
    expect(within(section).getByText('Minimum reading confidence')).toBeInTheDocument()
    expect(within(section).getByText('Price tolerance')).toBeInTheDocument()
    // Scoped to the section on purpose: the collapsed "Full audit record" below is a
    // deliberate raw dump for auditors and does still carry the database key.
    expect(within(section).queryByText('MIN-CONFIDENCE')).not.toBeInTheDocument()
  })

  it('requires a note and submits the selected human action', async () => {
    render(<WorkbenchPage />)
    const approveButton = await screen.findByRole('button', { name: 'Approve payment' })

    fireEvent.click(approveButton)
    expect(screen.getByText('Add a note before recording your decision.')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/your note/i), {
      target: { value: 'Verified with procurement.' },
    })
    fireEvent.click(approveButton)

    await waitFor(() => {
      expect(resolveWorkbenchItem).toHaveBeenCalledWith(
        7,
        'approve',
        'Verified with procurement.'
      )
    })
  })

  it('shows a parked item as waiting on information, still open for a decision', async () => {
    const parked = {
      ...detail,
      status: 'open',
      action: 'request_info',
      note: 'Please send the delivery note.',
      resolved_by: 'ku@example.com',
    }
    vi.mocked(getWorkbenchItems).mockResolvedValue({
      items: [{ ...summary, action: 'request_info' }],
      total: 1,
    })
    vi.mocked(getWorkbenchItem).mockResolvedValue(parked)

    render(<WorkbenchPage />)

    expect((await screen.findAllByText('Waiting on information')).length).toBeGreaterThan(0)
    expect(await screen.findByText(/Please send the delivery note/)).toBeInTheDocument()
    // Parked is not decided: the reviewer can still approve or reject.
    expect(screen.getByRole('button', { name: 'Approve payment' })).toBeInTheDocument()
  })

  it('does not claim the question was sent when no Slack channel is configured', async () => {
    vi.mocked(resolveWorkbenchItem).mockResolvedValue({
      ...detail,
      status: 'open',
      action: 'request_info',
      note: 'Need the delivery note.',
      notification_outcome: 'not_configured',
      notification_detail: 'SLACK_WEBHOOK_URL is not set, so no message was sent.',
    })

    render(<WorkbenchPage />)
    const askButton = await screen.findByRole('button', { name: 'Request information' })
    fireEvent.change(screen.getByLabelText(/your note/i), {
      target: { value: 'Need the delivery note.' },
    })
    fireEvent.click(askButton)

    expect(await screen.findByText(/nobody was notified/i)).toBeInTheDocument()
  })
})
