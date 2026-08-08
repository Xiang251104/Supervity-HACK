/**
 * Plain language for the AP domain.
 *
 * The agent speaks in reason codes (BEC_SUSPECTED) and operator keys
 * (bank_result). The people using the Workbench are finance reviewers, not
 * engineers, so every code the system can emit gets a label a reviewer would
 * say out loud and a hint that tells them what to actually check. Raw codes
 * stay visible in small print for the audit trail — translated, never hidden.
 */

export type ReasonTone = 'danger' | 'warning' | 'info'

export interface ReasonInfo {
  label: string
  hint: string
  tone: ReasonTone
}

export const REASON_INFO: Record<string, ReasonInfo> = {
  // Fraud and bank signals
  BEC_SUSPECTED: {
    label: 'Possible payment-redirect fraud',
    hint: 'Bank details changed recently and other fraud signals line up. Confirm with the vendor by phone on a known number before anything is paid.',
    tone: 'danger',
  },
  BANK_MISMATCH: {
    label: "Bank account doesn't match vendor records",
    hint: 'The account on this invoice differs from the one on file for this vendor.',
    tone: 'danger',
  },
  BANK_ACCOUNT_UNKNOWN: {
    label: 'Bank account not on file',
    hint: 'The invoice quotes an account we have no record of for this vendor.',
    tone: 'danger',
  },
  BANK_CHANGE_UNVERIFIED: {
    label: 'Recent bank change not yet verified',
    hint: "The vendor's bank details changed inside the freeze window and no one has confirmed the change out-of-band.",
    tone: 'warning',
  },

  // Vendor state
  VENDOR_BLOCKED: {
    label: 'Vendor is blocked for payment',
    hint: 'This supplier is blocked in the vendor master. Payments cannot go out until the block is lifted.',
    tone: 'danger',
  },
  VENDOR_DELETED: {
    label: 'Vendor is flagged for deletion',
    hint: 'The supplier record is marked for deletion and should not receive payments.',
    tone: 'danger',
  },
  VENDOR_MASTER_DUPLICATE: {
    label: 'Vendor has duplicate master records',
    hint: 'The same supplier appears more than once in vendor data, so totals for it can double-count.',
    tone: 'warning',
  },

  // Duplicates
  DUP_LATER_COPY: {
    label: 'Duplicate of an invoice already received',
    hint: 'Paying this would pay the same bill twice.',
    tone: 'danger',
  },
  NEAR_DUP_SUSPECT: {
    label: 'Looks like a copy of another invoice',
    hint: 'Same vendor with a near-identical reference or amount as another invoice, possibly sent through a different channel.',
    tone: 'warning',
  },

  // Purchase order checks
  PO_VENDOR_MISMATCH: {
    label: 'Purchase order belongs to a different vendor',
    hint: 'The PO quoted on the invoice was raised for another supplier.',
    tone: 'danger',
  },
  PO_CURRENCY_MISMATCH: {
    label: 'Currency differs from the purchase order',
    hint: 'The invoice is in a different currency than the PO it references.',
    tone: 'danger',
  },
  PO_LINE_NO_MATCH: {
    label: "Amount doesn't match any PO line",
    hint: 'No line on the purchase order matches this amount within the price tolerance.',
    tone: 'danger',
  },
  PO_LINE_AMBIGUOUS: {
    label: 'Amount matches more than one PO line',
    hint: 'The match is ambiguous, so a person has to pick the right line.',
    tone: 'warning',
  },
  PO_OUT_OF_VALIDITY: {
    label: "Invoice dated outside the PO's validity period",
    hint: 'The invoice date falls before or after the window the purchase order covers.',
    tone: 'warning',
  },
  RETRO_PO: {
    label: 'Purchase order raised after the invoice',
    hint: 'The PO was created retroactively — after the invoice already existed.',
    tone: 'warning',
  },
  ENTITY_MISMATCH: {
    label: 'Billed to the wrong company entity',
    hint: 'The invoice is booked to a different company code than the purchase order.',
    tone: 'danger',
  },

  // Goods receipt
  RECEIPT_VARIANCE: {
    label: "Goods receipt doesn't cover the invoice",
    hint: 'What was received does not fully support what is being billed.',
    tone: 'warning',
  },
  RECEIPT_MISSING: {
    label: 'No goods receipt recorded',
    hint: 'Nothing has been booked as received against this purchase order.',
    tone: 'warning',
  },
  RECEIPT_PARTIAL: {
    label: 'Only part of the goods received',
    hint: 'The received quantity covers only part of the invoiced amount.',
    tone: 'warning',
  },
  GR_EXEMPT_FRAMEWORK: {
    label: 'Framework order — no receipt required',
    hint: 'This PO type is exempt from goods-receipt matching under the current policy.',
    tone: 'info',
  },

  // Data quality and routing
  LOW_CONFIDENCE: {
    label: 'Invoice was hard to read',
    hint: 'Extraction confidence is below the policy floor, so the key numbers deserve a second look.',
    tone: 'warning',
  },
  DATE_AMBIGUOUS: {
    label: 'Invoice date format was ambiguous',
    hint: 'The date could be read more than one way; the safer reading was used.',
    tone: 'info',
  },
  MISSING_INPUT: {
    label: 'Key information is missing from the invoice',
    hint: 'A field the checks depend on was not present, and nothing was invented in its place.',
    tone: 'warning',
  },
  CREDIT_MEMO: {
    label: 'Credit note — money owed back to us',
    hint: 'The amount is negative. Route it as a credit against the vendor, never as a payment.',
    tone: 'warning',
  },
  NON_PO_APPROVAL: {
    label: 'No purchase order — needs an approver',
    hint: 'Spend without a PO always goes through a delegated approver.',
    tone: 'info',
  },
  GL_CODING_REQUIRED: {
    label: 'Needs a ledger account assigned',
    hint: 'A general-ledger account has to be chosen before this can post.',
    tone: 'info',
  },
  DOA_BAND_NOT_FOUND: {
    label: 'No approver band covers this amount',
    hint: 'The delegation-of-authority matrix has no band for this spend, so routing needs a person.',
    tone: 'warning',
  },
  HIGH_VALUE: {
    label: 'High-value invoice',
    hint: 'The amount is above the high-value threshold and gets extra scrutiny.',
    tone: 'info',
  },
}

// Acronyms that must survive humanization of a code we have no entry for.
const ACRONYMS = new Set(['PO', 'GR', 'GL', 'BEC', 'DOA', 'FX', 'GST'])

/** Best-effort label for a code with no dictionary entry. */
export function humanizeCode(code: string): string {
  const words = code
    .split('_')
    .filter(Boolean)
    .map((word) => (ACRONYMS.has(word) ? word : word.toLowerCase()))
  if (!words.length) return code
  const first = words[0]
  words[0] = ACRONYMS.has(first) ? first : first.charAt(0).toUpperCase() + first.slice(1)
  return words.join(' ')
}

export function reasonInfo(code: string): ReasonInfo {
  return (
    REASON_INFO[code] ?? {
      label: humanizeCode(code),
      hint: '',
      tone: 'warning',
    }
  )
}

export const reasonLabel = (code: string): string => reasonInfo(code).label

/**
 * The checks, in processing order, named by what they do for the reviewer
 * rather than by workflow internals.
 */
export interface OperatorInfo {
  key: string
  name: string
  checks: string
}

export const OPERATOR_INFO: OperatorInfo[] = [
  { key: 'intake_result', name: 'Reading the invoice', checks: 'Data capture and quality' },
  { key: 'duplicate_result', name: 'Duplicate check', checks: 'Same bill received twice' },
  { key: 'bank_result', name: 'Bank details check', checks: 'Account changes and fraud signals' },
  { key: 'po_entity_result', name: 'Purchase order lookup', checks: 'PO exists and matches the vendor' },
  { key: 'match_result', name: 'Invoice vs PO and goods', checks: 'Price and delivery support the amount' },
  { key: 'entity_result', name: 'Company entity and approvals', checks: 'Right entity, right approver' },
]

export type CheckStatus = 'PASS' | 'FAIL' | 'REVIEW' | 'NOT_APPLICABLE' | 'ERROR' | 'UNKNOWN'

/** Normalize an operator status; SUCCESS is a known contract deviation meaning PASS. */
export function normalizeStatus(raw: unknown): CheckStatus {
  const value = String(raw ?? '').trim().toUpperCase()
  if (value === 'SUCCESS') return 'PASS'
  if (['PASS', 'FAIL', 'REVIEW', 'NOT_APPLICABLE', 'ERROR'].includes(value)) {
    return value as CheckStatus
  }
  return 'UNKNOWN'
}

export const STATUS_LABELS: Record<CheckStatus, string> = {
  PASS: 'Passed',
  FAIL: 'Failed',
  REVIEW: 'Needs review',
  NOT_APPLICABLE: 'Not applicable',
  ERROR: 'Check errored',
  UNKNOWN: 'No result',
}

/** Verdicts in the reviewer's words — the same words on every page. */
export const VERDICT_PLAIN: Record<string, string> = {
  PAY_READY: 'Cleared to pay',
  HUMAN_REVIEW: 'Needs review',
  PAYMENT_HOLD: 'Payment held',
  DATA_ERROR: "Couldn't process",
}

export const verdictPlain = (verdict: string): string =>
  VERDICT_PLAIN[verdict] ?? humanizeCode(verdict)

/** Workbench actions, named by what actually happened. */
export const ACTION_LABELS: Record<string, string> = {
  approve: 'Payment approved',
  reject: 'Payment rejected',
  request_info: 'More information requested',
}

export const actionLabel = (action: string): string =>
  ACTION_LABELS[action] ?? humanizeCode(action)

/**
 * Policy values a business user picks between, in words rather than config
 * tokens. The stored value never changes — only what the screen shows.
 */
export const POLICY_VALUE_LABELS: Record<string, string> = {
  fo_aware: 'Framework orders exempt',
  strict_require_gr: 'Receipt required for every order',
  advisory: 'Record only',
  review: 'Send to a person',
}

export function policyValueLabel(value: unknown): string {
  if (typeof value === 'string' && POLICY_VALUE_LABELS[value]) {
    return POLICY_VALUE_LABELS[value]
  }
  return String(value)
}

export const VALUE_TYPE_LABELS: Record<string, string> = {
  number: 'Number',
  enum: 'Choice',
  boolean: 'On / off',
  date: 'Date',
}

export const valueTypeLabel = (type: string): string => VALUE_TYPE_LABELS[type] ?? type
