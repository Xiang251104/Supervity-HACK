'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  Archive,
  Check,
  CircleAlert,
  CircleCheck,
  CircleDollarSign,
  CircleHelp,
  CircleMinus,
  Clock3,
  FileSearch,
  LoaderCircle,
  MessageSquareText,
  RefreshCw,
  ShieldAlert,
  UserRoundCheck,
  X,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  OPERATOR_INFO,
  STATUS_LABELS,
  VERDICT_PLAIN,
  actionLabel,
  normalizeStatus,
  reasonInfo,
  type CheckStatus,
  type ReasonTone,
} from '@/lib/ap-language'
import {
  getWorkbenchItem,
  getWorkbenchItems,
  resolveWorkbenchItem,
  summarizeProtectedExposure,
} from '@/lib/ap-workbench'
import { cn } from '@/lib/utils'
import type {
  WorkbenchAction,
  WorkbenchFilters,
  WorkbenchItemDetail,
  WorkbenchItemSummary,
} from '@/types/ap-workbench'

const DEFAULT_FILTERS: WorkbenchFilters = { status: 'open', priority: 'all' }

const PRIORITY_STYLES: Record<string, string> = {
  critical: 'bg-rose-500',
  high: 'bg-amber-500',
  normal: 'bg-sky-500',
}

const VERDICT_STYLES: Record<string, string> = {
  PAYMENT_HOLD: 'border-rose-200 bg-rose-50 text-rose-800',
  HUMAN_REVIEW: 'border-amber-200 bg-amber-50 text-amber-800',
  DATA_ERROR: 'border-slate-300 bg-slate-100 text-slate-700',
  PAY_READY: 'border-emerald-200 bg-emerald-50 text-emerald-800',
}

const REASON_TONE_STYLES: Record<ReasonTone, string> = {
  danger: 'border-rose-200 bg-rose-50',
  warning: 'border-amber-200 bg-amber-50',
  info: 'border-slate-200 bg-slate-50',
}

function formatMoney(currency: string | null, amount: number | null): string {
  if (amount == null) return 'Amount unavailable'
  return `${currency || '—'} ${new Intl.NumberFormat('en-MY', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount)}`
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('en-MY', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function VerdictBadge({ verdict }: { verdict: string | null }) {
  if (!verdict) return null
  return (
    <span
      className={cn(
        'inline-flex rounded-full border px-2.5 py-1 text-[11px] font-semibold tracking-[0.08em]',
        VERDICT_STYLES[verdict] || VERDICT_STYLES.DATA_ERROR
      )}
    >
      {(VERDICT_PLAIN[verdict] || verdict.replaceAll('_', ' ')).toUpperCase()}
    </span>
  )
}

function QueueItem({
  item,
  selected,
  onSelect,
}: {
  item: WorkbenchItemSummary
  selected: boolean
  onSelect: () => void
}) {
  const exception = reasonInfo(item.exception_type)
  return (
    <button
      type='button'
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        'relative w-full overflow-hidden rounded-2xl border bg-white p-4 text-left shadow-sm transition',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-cornflower focus-visible:ring-offset-2',
        selected
          ? 'border-brand-cornflower/60 shadow-md ring-1 ring-brand-cornflower/20'
          : 'border-slate-200 hover:border-slate-300 hover:shadow-md'
      )}
    >
      <span
        aria-hidden='true'
        className={cn(
          'absolute inset-y-0 left-0 w-1.5',
          PRIORITY_STYLES[item.priority] || PRIORITY_STYLES.normal
        )}
      />
      <div className='ml-1 space-y-2.5'>
        <div className='flex items-start justify-between gap-3'>
          <div>
            <p className='font-mono text-[11px] font-semibold tracking-[0.08em] text-slate-500'>
              {item.belnr}
            </p>
            <h3 className='mt-1 text-sm font-semibold leading-5 text-slate-950'>
              {exception.label}
            </h3>
          </div>
          <span className='rounded-full bg-slate-100 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-600'>
            {item.priority}
          </span>
        </div>
        <div className='flex flex-wrap items-center justify-between gap-2'>
          <VerdictBadge verdict={item.verdict} />
          <span className='font-mono text-xs font-semibold text-slate-800'>
            {formatMoney(item.currency, item.amount)}
          </span>
        </div>
        <div className='flex items-center gap-2 text-xs text-slate-500'>
          <Clock3 className='h-3.5 w-3.5' />
          {formatDate(item.created_at)}
        </div>
      </div>
    </button>
  )
}

/* ------------------------------------------------------------------ */
/* Plain-language building blocks                                      */
/* ------------------------------------------------------------------ */

function ReasonCard({ code }: { code: string }) {
  const info = reasonInfo(code)
  // The raw code is deliberately not shown here — it lives in the full audit
  // record below for anyone who needs to trace it.
  return (
    <div className={cn('rounded-xl border p-4', REASON_TONE_STYLES[info.tone])}>
      <p className='text-sm font-semibold text-slate-900'>{info.label}</p>
      {info.hint ? <p className='mt-1 text-sm leading-6 text-slate-700'>{info.hint}</p> : null}
    </div>
  )
}

const STATUS_ICONS: Record<CheckStatus, { icon: typeof CircleCheck; className: string }> = {
  PASS: { icon: CircleCheck, className: 'text-emerald-600' },
  FAIL: { icon: CircleAlert, className: 'text-rose-600' },
  REVIEW: { icon: CircleHelp, className: 'text-amber-600' },
  ERROR: { icon: CircleAlert, className: 'text-rose-600' },
  NOT_APPLICABLE: { icon: CircleMinus, className: 'text-slate-400' },
  UNKNOWN: { icon: CircleMinus, className: 'text-slate-400' },
}

interface CheckRow {
  key: string
  name: string
  checks: string
  status: CheckStatus
  explanation: string
}

/** The six checks in processing order, from whatever operator results exist. */
function buildCheckRows(detail: WorkbenchItemDetail): CheckRow[] {
  const context = detail.context as Record<string, unknown> | null
  const source =
    (context?.operator_results as Record<string, unknown> | undefined) ??
    (detail.decision?.evidence as Record<string, unknown> | undefined) ??
    {}

  return OPERATOR_INFO.map(({ key, name, checks }) => {
    const raw = source[key]
    const result = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
    return {
      key,
      name,
      checks,
      status: normalizeStatus(result.status),
      explanation: typeof result.explanation === 'string' ? result.explanation : '',
    }
  }).filter((row) => row.status !== 'UNKNOWN' || row.explanation)
}

function ChecksList({ rows }: { rows: CheckRow[] }) {
  if (!rows.length) {
    return <p className='text-sm text-slate-500'>No check results were attached to this decision.</p>
  }
  return (
    <ul className='divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white'>
      {rows.map((row) => {
        const { icon: Icon, className } = STATUS_ICONS[row.status]
        return (
          <li key={row.key} className='flex gap-3 px-4 py-3'>
            <Icon aria-hidden='true' className={cn('mt-0.5 h-5 w-5 shrink-0', className)} />
            <div className='min-w-0'>
              <p className='text-sm font-semibold text-slate-900'>
                {row.name}
                <span className={cn('ml-2 text-xs font-medium', className)}>
                  {STATUS_LABELS[row.status]}
                </span>
              </p>
              <p className='mt-0.5 text-sm leading-6 text-slate-600'>
                {row.explanation || row.checks}
              </p>
            </div>
          </li>
        )
      })}
    </ul>
  )
}

/* ------------------------------------------------------------------ */
/* Audit detail (collapsed by default)                                 */
/* ------------------------------------------------------------------ */

function EvidenceTree({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value === null || value === undefined) {
    return <span className='font-mono text-xs text-slate-400'>null</span>
  }
  if (typeof value !== 'object') {
    return <span className='break-all font-mono text-xs text-slate-800'>{String(value)}</span>
  }
  if (Array.isArray(value)) {
    if (!value.length) return <span className='font-mono text-xs text-slate-400'>[]</span>
    return (
      <div className='space-y-2'>
        {value.map((entry, index) => (
          <div key={index} className='rounded-lg border border-slate-200 bg-slate-50 p-2'>
            <EvidenceTree value={entry} depth={depth + 1} />
          </div>
        ))}
      </div>
    )
  }
  return (
    <dl className={cn('grid gap-2', depth === 0 ? 'sm:grid-cols-2' : 'grid-cols-1')}>
      {Object.entries(value as Record<string, unknown>).map(([key, entry]) => (
        <div key={key} className='rounded-lg border border-slate-200 bg-slate-50/80 p-2.5'>
          <dt className='mb-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-slate-500'>
            {key.replaceAll('_', ' ')}
          </dt>
          <dd>
            <EvidenceTree value={entry} depth={depth + 1} />
          </dd>
        </div>
      ))}
    </dl>
  )
}

function DetailLoading() {
  return (
    <div className='flex min-h-[520px] items-center justify-center rounded-3xl border border-slate-200 bg-white'>
      <div className='text-center text-sm text-slate-500'>
        <LoaderCircle className='mx-auto mb-3 h-6 w-6 animate-spin text-brand-cornflower' />
        Loading decision evidence…
      </div>
    </div>
  )
}

function DetailEmpty() {
  return (
    <div className='flex min-h-[520px] items-center justify-center rounded-3xl border border-dashed border-slate-300 bg-white/70 p-8 text-center'>
      <div>
        <FileSearch className='mx-auto h-10 w-10 text-slate-300' />
        <h2 className='mt-4 text-lg font-semibold text-slate-900'>Select an exception</h2>
        <p className='mt-1 max-w-sm text-sm text-slate-500'>
          Choose a queue item to see why it was flagged and record your decision.
        </p>
      </div>
    </div>
  )
}

function DecisionDetail({
  detail,
  note,
  setNote,
  submittingAction,
  actionError,
  actionSuccess,
  onAction,
}: {
  detail: WorkbenchItemDetail
  note: string
  setNote: (value: string) => void
  submittingAction: WorkbenchAction | null
  actionError: string | null
  actionSuccess: string | null
  onAction: (action: WorkbenchAction) => void
}) {
  const decision = detail.decision
  const isResolved = detail.status === 'resolved'
  const checkRows = useMemo(() => buildCheckRows(detail), [detail])
  const confidence = decision?.confidence

  return (
    <article className='overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm'>
      <header className='border-b border-slate-200 bg-slate-950 px-6 py-6 text-white lg:px-8'>
        <div className='flex flex-wrap items-start justify-between gap-4'>
          <div>
            <p className='font-mono text-xs tracking-[0.14em] text-slate-400'>
              INVOICE {detail.belnr}
            </p>
            <h2 className='mt-2 text-2xl font-semibold tracking-tight'>
              {decision?.vendor_name || detail.title}
            </h2>
            <p className='mt-1 text-sm text-slate-300'>
              {decision?.ebeln ? `Purchase order ${decision.ebeln}` : 'No purchase order'}
              {decision?.lifnr ? ` · Vendor ${decision.lifnr}` : ''}
            </p>
          </div>
          <VerdictBadge verdict={decision?.verdict ?? null} />
        </div>
        <div className='mt-6 grid gap-4 sm:grid-cols-3'>
          <div>
            <p className='text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400'>
              Invoice amount
            </p>
            <p className='mt-1 font-mono text-lg font-semibold'>
              {formatMoney(decision?.currency ?? null, decision?.amount ?? null)}
            </p>
          </div>
          <div>
            <p className='text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400'>
              Held from payment
            </p>
            <p className='mt-1 font-mono text-lg font-semibold text-rose-300'>
              {decision?.money_protected
                ? formatMoney(decision?.currency ?? null, decision.money_protected)
                : '—'}
            </p>
          </div>
          <div>
            <p className='text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400'>
              Read confidence
            </p>
            <p className='mt-1 font-mono text-lg font-semibold'>
              {confidence != null ? `${Math.round(confidence * 100)}%` : 'Not reported'}
            </p>
          </div>
        </div>
      </header>

      <div className='space-y-8 p-6 lg:p-8'>
        <section aria-labelledby='why-flagged'>
          <div className='flex items-center gap-2'>
            <ShieldAlert className='h-5 w-5 text-rose-600' />
            <h3
              id='why-flagged'
              className='text-sm font-semibold uppercase tracking-[0.1em] text-slate-900'
            >
              Why this needs you
            </h3>
          </div>
          <div className='mt-4 space-y-3'>
            {decision?.reason_codes.length ? (
              decision.reason_codes.map((reason) => <ReasonCard key={reason} code={reason} />)
            ) : (
              <p className='text-sm text-slate-500'>No reasons were recorded.</p>
            )}
          </div>
          {detail.recommendation ? (
            <div className='mt-4 rounded-xl border border-indigo-100 bg-indigo-50/70 p-4 text-sm leading-6 text-indigo-950'>
              <span className='font-semibold'>Suggested next step:</span> {detail.recommendation}
            </div>
          ) : null}
        </section>

        <section
          aria-labelledby='reviewer-action'
          className='rounded-2xl border border-slate-200 bg-slate-50 p-5'
        >
          <div className='flex items-center gap-2'>
            <UserRoundCheck className='h-5 w-5 text-brand-cornflower' />
            <h3
              id='reviewer-action'
              className='text-sm font-semibold uppercase tracking-[0.1em] text-slate-900'
            >
              Your decision
            </h3>
          </div>

          {isResolved ? (
            <div className='mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4'>
              <p className='text-sm font-semibold text-emerald-900'>
                {detail.action ? actionLabel(detail.action) : 'Resolved'}
              </p>
              <p className='mt-1 text-sm text-emerald-800'>{detail.note}</p>
              <p className='mt-2 text-xs text-emerald-700'>By {detail.resolved_by || 'reviewer'}</p>
            </div>
          ) : (
            <>
              <label htmlFor='reviewer-note' className='mt-4 block text-sm font-medium text-slate-800'>
                Your note <span className='font-normal text-slate-500'>(required)</span>
              </label>
              <textarea
                id='reviewer-note'
                value={note}
                onChange={(event) => setNote(event.target.value)}
                rows={3}
                placeholder='What did you check, and why this decision?'
                className='mt-2 w-full resize-y rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-brand-cornflower focus:ring-2 focus:ring-brand-cornflower/20'
              />
              {actionError ? (
                <p role='alert' className='mt-2 text-sm font-medium text-rose-700'>
                  {actionError}
                </p>
              ) : null}
              {actionSuccess ? (
                <p role='status' className='mt-2 text-sm font-medium text-emerald-700'>
                  {actionSuccess}
                </p>
              ) : null}
              <div className='mt-4 grid gap-2 sm:grid-cols-3'>
                <Button
                  type='button'
                  onClick={() => onAction('approve')}
                  disabled={Boolean(submittingAction)}
                  className='bg-emerald-700 hover:bg-emerald-800'
                  aria-label='Approve payment'
                >
                  {submittingAction === 'approve' ? (
                    <LoaderCircle className='h-4 w-4 animate-spin' />
                  ) : (
                    <Check className='h-4 w-4' />
                  )}
                  Approve payment
                </Button>
                <Button
                  type='button'
                  onClick={() => onAction('reject')}
                  disabled={Boolean(submittingAction)}
                  className='bg-rose-700 hover:bg-rose-800'
                  aria-label='Reject payment'
                >
                  {submittingAction === 'reject' ? (
                    <LoaderCircle className='h-4 w-4 animate-spin' />
                  ) : (
                    <X className='h-4 w-4' />
                  )}
                  Reject payment
                </Button>
                <Button
                  type='button'
                  variant='outline'
                  onClick={() => onAction('request_info')}
                  disabled={Boolean(submittingAction)}
                  aria-label='Request information'
                >
                  {submittingAction === 'request_info' ? (
                    <LoaderCircle className='h-4 w-4 animate-spin' />
                  ) : (
                    <MessageSquareText className='h-4 w-4' />
                  )}
                  Ask for more info
                </Button>
              </div>
            </>
          )}
        </section>

        <section aria-labelledby='checks-run'>
          <h3
            id='checks-run'
            className='text-sm font-semibold uppercase tracking-[0.1em] text-slate-900'
          >
            What the AI checked
          </h3>
          <div className='mt-4'>
            <ChecksList rows={checkRows} />
          </div>
        </section>

        <details className='group rounded-2xl border border-slate-200'>
          <summary className='flex cursor-pointer items-center gap-2 rounded-2xl px-5 py-4 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 [&::-webkit-details-marker]:hidden'>
            <Archive className='h-4 w-4 text-slate-400' />
            Full audit record
            <span className='ml-auto text-xs font-normal text-slate-400 group-open:hidden'>
              Every field, for auditors
            </span>
          </summary>
          <div className='space-y-6 border-t border-slate-100 p-5'>
            <div>
              <h4 className='text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-500'>
                Assignment
              </h4>
              <dl className='mt-3 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4'>
                {[
                  ['Assigned role', detail.assigned_role || 'Unassigned'],
                  ['Assigned email', detail.assigned_email || '—'],
                  ['Run', detail.run_id],
                  ['Policy snapshot', decision?.policy_version_label || 'Not recorded'],
                ].map(([label, value]) => (
                  <div key={label}>
                    <dt className='text-[10px] font-semibold uppercase tracking-[0.1em] text-slate-500'>
                      {label}
                    </dt>
                    <dd className='mt-1 break-all text-sm font-medium text-slate-900'>{value}</dd>
                  </div>
                ))}
              </dl>
            </div>
            {decision?.evidence ? (
              <div>
                <h4 className='text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-500'>
                  Check evidence
                </h4>
                <div className='mt-3'>
                  <EvidenceTree value={decision.evidence} />
                </div>
              </div>
            ) : null}
            {detail.context ? (
              <div>
                <h4 className='text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-500'>
                  Decision context
                </h4>
                <div className='mt-3'>
                  <EvidenceTree value={detail.context} />
                </div>
              </div>
            ) : null}
          </div>
        </details>
      </div>
    </article>
  )
}

export default function WorkbenchPage() {
  const [filters, setFilters] = useState<WorkbenchFilters>(DEFAULT_FILTERS)
  const [items, setItems] = useState<WorkbenchItemSummary[]>([])
  const [total, setTotal] = useState(0)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<WorkbenchItemDetail | null>(null)
  const [loadingQueue, setLoadingQueue] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [queueError, setQueueError] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionSuccess, setActionSuccess] = useState<string | null>(null)
  const [submittingAction, setSubmittingAction] = useState<WorkbenchAction | null>(null)

  const loadQueue = useCallback(async () => {
    setLoadingQueue(true)
    setQueueError(null)
    try {
      const response = await getWorkbenchItems(filters)
      setItems(response.items)
      setTotal(response.total)
      setSelectedId((current) => {
        if (current && response.items.some((item) => item.id === current)) return current
        return response.items[0]?.id ?? null
      })
    } catch (error) {
      setQueueError(error instanceof Error ? error.message : 'The exception queue could not be loaded.')
      setItems([])
      setTotal(0)
      setSelectedId(null)
    } finally {
      setLoadingQueue(false)
    }
  }, [filters])

  useEffect(() => {
    void loadQueue()
  }, [loadQueue])

  useEffect(() => {
    if (selectedId === null) {
      setDetail(null)
      return
    }
    let active = true
    setLoadingDetail(true)
    setDetailError(null)
    setNote('')
    setActionError(null)
    setActionSuccess(null)
    void getWorkbenchItem(selectedId)
      .then((response) => {
        if (active) setDetail(response)
      })
      .catch((error: unknown) => {
        if (active) {
          setDetail(null)
          setDetailError(error instanceof Error ? error.message : 'Decision detail could not be loaded.')
        }
      })
      .finally(() => {
        if (active) setLoadingDetail(false)
      })
    return () => {
      active = false
    }
  }, [selectedId])

  const protectedExposure = useMemo(() => summarizeProtectedExposure(items), [items])

  async function handleAction(action: WorkbenchAction) {
    if (!detail) return
    if (!note.trim()) {
      setActionError('Add a note before recording your decision.')
      return
    }
    setActionError(null)
    setActionSuccess(null)
    setSubmittingAction(action)
    try {
      const updated = await resolveWorkbenchItem(detail.id, action, note)
      setDetail(updated)
      setNote('')
      setActionSuccess(`${actionLabel(action)}.`)
      await loadQueue()
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Your decision could not be recorded.')
    } finally {
      setSubmittingAction(null)
    }
  }

  return (
    <div className='mx-auto w-full max-w-[1600px] space-y-6'>
      <header className='flex flex-col gap-5 border-b border-slate-200 pb-6 lg:flex-row lg:items-end lg:justify-between'>
        <div>
          <p className='font-mono text-xs font-semibold tracking-[0.18em] text-brand-cornflower'>
            HUMAN CONTROL LAYER
          </p>
          <h1 className='mt-2 text-3xl font-bold tracking-tight text-brand-navy sm:text-4xl'>
            AP exception workbench
          </h1>
          <p className='mt-2 max-w-2xl text-sm leading-6 text-slate-600'>
            Invoices the AI would not clear on its own. Review why, then approve, reject, or ask
            for more information — the AI&apos;s original verdict stays on record either way.
          </p>
        </div>
        <Button type='button' variant='outline' onClick={() => void loadQueue()} disabled={loadingQueue}>
          <RefreshCw className={cn('h-4 w-4', loadingQueue && 'animate-spin')} />
          Refresh queue
        </Button>
      </header>

      <section aria-label='Queue summary' className='grid gap-3 sm:grid-cols-2'>
        <div className='rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm'>
          <div className='flex items-center gap-3'>
            <div className='rounded-xl bg-amber-100 p-2 text-amber-700'>
              <AlertTriangle className='h-5 w-5' />
            </div>
            <div>
              <p className='text-xs font-semibold uppercase tracking-[0.1em] text-slate-500'>
                Waiting for review
              </p>
              <p className='mt-1 text-2xl font-semibold text-slate-950'>{total}</p>
            </div>
          </div>
        </div>
        <div className='rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm'>
          <div className='flex items-center gap-3'>
            <div className='rounded-xl bg-rose-100 p-2 text-rose-700'>
              <CircleDollarSign className='h-5 w-5' />
            </div>
            <div>
              <p className='text-xs font-semibold uppercase tracking-[0.1em] text-slate-500'>
                Money held from payment
              </p>
              <div className='mt-1 flex flex-wrap gap-x-4 gap-y-1 font-mono text-xl font-semibold text-slate-950'>
                {protectedExposure.length > 0 ? (
                  protectedExposure.map(({ currency, amount }) => (
                    <span key={currency}>{formatMoney(currency, amount)}</span>
                  ))
                ) : (
                  <span>—</span>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className='grid gap-6 xl:grid-cols-[380px_minmax(0,1fr)]'>
        <aside className='space-y-4'>
          <div className='grid grid-cols-2 gap-3'>
            <label className='text-xs font-semibold uppercase tracking-[0.1em] text-slate-600'>
              Status
              <select
                value={filters.status}
                onChange={(event) =>
                  setFilters((current) => ({
                    ...current,
                    status: event.target.value as WorkbenchFilters['status'],
                  }))
                }
                className='mt-1.5 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm font-medium normal-case tracking-normal text-slate-900 outline-none focus:border-brand-cornflower focus:ring-2 focus:ring-brand-cornflower/20'
              >
                <option value='open'>Open</option>
                <option value='resolved'>Resolved</option>
                <option value='all'>All</option>
              </select>
            </label>
            <label className='text-xs font-semibold uppercase tracking-[0.1em] text-slate-600'>
              Priority
              <select
                value={filters.priority}
                onChange={(event) =>
                  setFilters((current) => ({
                    ...current,
                    priority: event.target.value as WorkbenchFilters['priority'],
                  }))
                }
                className='mt-1.5 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm font-medium normal-case tracking-normal text-slate-900 outline-none focus:border-brand-cornflower focus:ring-2 focus:ring-brand-cornflower/20'
              >
                <option value='all'>All</option>
                <option value='critical'>Critical</option>
                <option value='high'>High</option>
                <option value='normal'>Normal</option>
              </select>
            </label>
          </div>

          {loadingQueue ? (
            <div className='rounded-2xl border border-slate-200 bg-white p-6 text-center text-sm text-slate-500'>
              <LoaderCircle className='mx-auto mb-2 h-5 w-5 animate-spin text-brand-cornflower' />
              Loading exceptions…
            </div>
          ) : queueError ? (
            <div role='alert' className='rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800'>
              <p className='font-semibold'>Queue unavailable</p>
              <p className='mt-1'>{queueError}</p>
            </div>
          ) : items.length === 0 ? (
            <div className='rounded-2xl border border-dashed border-slate-300 bg-white/70 p-6 text-center'>
              <Check className='mx-auto h-8 w-8 text-emerald-500' />
              <p className='mt-3 text-sm font-semibold text-slate-900'>No exceptions match these filters</p>
              <p className='mt-1 text-xs text-slate-500'>Change the filters or refresh the queue.</p>
            </div>
          ) : (
            <div className='max-h-[780px] space-y-3 overflow-y-auto pr-1 [content-visibility:auto]'>
              {items.map((item) => (
                <QueueItem
                  key={item.id}
                  item={item}
                  selected={selectedId === item.id}
                  onSelect={() => setSelectedId(item.id)}
                />
              ))}
            </div>
          )}
        </aside>

        <section aria-label='Selected exception detail'>
          {loadingDetail ? (
            <DetailLoading />
          ) : detailError ? (
            <div role='alert' className='rounded-3xl border border-rose-200 bg-rose-50 p-6 text-rose-800'>
              <p className='font-semibold'>Decision detail unavailable</p>
              <p className='mt-1 text-sm'>{detailError}</p>
            </div>
          ) : detail ? (
            <DecisionDetail
              detail={detail}
              note={note}
              setNote={setNote}
              submittingAction={submittingAction}
              actionError={actionError}
              actionSuccess={actionSuccess}
              onAction={(action) => void handleAction(action)}
            />
          ) : (
            <DetailEmpty />
          )}
        </section>
      </div>
    </div>
  )
}
