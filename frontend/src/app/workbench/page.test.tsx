import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  context: { invoice_vendor: '4110006', po_vendor: '4110030' },
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
})
