'use client'

/**
 * "Process an invoice" — the Command Center's own way to start a real
 * Orchestrator run, for a presenter to click live instead of reading Auto's
 * audit trail or waiting on an external channel.
 *
 * Deliberately not the Outlook plan: no mailbox polling, no OAuth, nothing
 * that touches Supervity Auto's workflow builder. This calls the exact same
 * `POST /api/ap/runs` the batch seeder uses, with `trigger_source:
 * "command_center"` — so the audit trail honestly records how the run
 * started, never mislabelled as Outlook ingestion.
 *
 * The call blocks for the whole run (commonly 60-100s). There is no live
 * progress stream from the backend for this endpoint, so the status line
 * below is a plain, honest sequence ("Starting…" then "Running…") rather
 * than a fake progress bar claiming precision it doesn't have.
 */

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { motion, AnimatePresence } from 'framer-motion'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { CardWatermark } from '@/components/ui/card-watermark'
import { Icons } from '@/components/ui/icons'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { formatMoney, humaniseCode, verdictLabel } from '@/lib/ap-metrics'
import { startRun } from '@/lib/ap-runs'
import { cn } from '@/lib/utils'
import type { RunDetail } from '@/types/ap-runs'

type Phase = 'idle' | 'starting' | 'running' | 'done' | 'error'

const VERDICT_TONE: Record<string, string> = {
  PAY_READY: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  HUMAN_REVIEW: 'bg-amber-100 text-amber-800 border-amber-200',
  PAYMENT_HOLD: 'bg-rose-100 text-rose-800 border-rose-200',
  DATA_ERROR: 'bg-slate-100 text-slate-800 border-slate-200',
}

// Switches from "starting" to "running" copy after a few seconds so the
// presenter isn't staring at "Starting…" for the full ~80-100s the actual
// Orchestrator run takes. This is honest framing, not a progress estimate.
const RUNNING_COPY_DELAY_MS = 3500

export function ProcessInvoiceCard({ onRunCompleted }: { onRunCompleted?: () => void }) {
  const [invoiceRef, setInvoiceRef] = useState('')
  const [runId, setRunId] = useState('')
  const [phase, setPhase] = useState<Phase>('idle')
  const [result, setResult] = useState<RunDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  const reset = () => {
    setPhase('idle')
    setResult(null)
    setError(null)
    setInvoiceRef('')
    setRunId('')
  }

  const run = async () => {
    const trimmedRef = invoiceRef.trim()
    if (!trimmedRef) return

    setPhase('starting')
    setError(null)
    setResult(null)

    timerRef.current = setTimeout(() => setPhase('running'), RUNNING_COPY_DELAY_MS)

    try {
      const detail = await startRun({
        invoice_ref: trimmedRef,
        run_id: runId.trim() || undefined,
      })
      setResult(detail)
      setPhase('done')
      onRunCompleted?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The run could not be completed.')
      setPhase('error')
    } finally {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }

  const isBusy = phase === 'starting' || phase === 'running'

  return (
    <Card className='relative col-span-12 overflow-hidden lg:col-span-6'>
      <CardWatermark opacity={3} scale={1.1} />
      <CardHeader className='relative z-10'>
        <CardTitle className='flex items-center gap-2'>
          <Icons.send className='h-5 w-5 text-brand-cornflower' strokeWidth={1.5} />
          Process an invoice
        </CardTitle>
      </CardHeader>
      <CardContent className='relative z-10'>
        <AnimatePresence mode='wait'>
          {phase === 'idle' || phase === 'error' ? (
            <motion.div
              key='form'
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className='space-y-4'
            >
              <div className='space-y-1.5'>
                <Label htmlFor='invoice-ref'>Invoice reference</Label>
                <Input
                  id='invoice-ref'
                  placeholder='e.g. 5110000152'
                  value={invoiceRef}
                  onChange={(e) => setInvoiceRef(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void run()
                  }}
                />
              </div>
              <div className='space-y-1.5'>
                <Label htmlFor='run-id'>
                  Run ID{' '}
                  <span className='font-normal text-muted-foreground'>
                    (optional — generated automatically if left blank)
                  </span>
                </Label>
                <Input
                  id='run-id'
                  placeholder='auto-generated'
                  value={runId}
                  onChange={(e) => setRunId(e.target.value)}
                />
              </div>

              {error ? (
                <div
                  role='alert'
                  className='rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700'
                >
                  {error}
                </div>
              ) : null}

              <Button
                className='w-full'
                disabled={!invoiceRef.trim()}
                onClick={() => void run()}
              >
                <Icons.zap className='h-4 w-4' strokeWidth={1.5} />
                Run AP Controls
              </Button>
              <p className='text-xs text-muted-foreground'>
                Captures the current policy snapshot, invokes the five Operators through
                Supervity, gates the verdict, and routes an exception into the Workbench —
                exactly like a batch run, for one invoice, started right here.
              </p>
            </motion.div>
          ) : isBusy ? (
            <motion.div
              key='busy'
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className='flex flex-col items-center gap-4 py-8 text-center'
            >
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ repeat: Infinity, duration: 1.1, ease: 'linear' }}
              >
                <Icons.loader className='h-8 w-8 text-brand-cornflower' strokeWidth={1.5} />
              </motion.div>
              <div>
                <p className='font-medium text-foreground'>
                  {phase === 'starting'
                    ? 'Starting controls…'
                    : 'Running five AP Operators…'}
                </p>
                <p className='mt-1 text-xs text-muted-foreground'>
                  Invoice {invoiceRef.trim()} — this usually takes about a minute.
                </p>
              </div>
            </motion.div>
          ) : result ? (
            <motion.div
              key='result'
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className='space-y-4'
            >
              <div className='flex flex-wrap items-center gap-2'>
                <span
                  className={cn(
                    'inline-flex items-center rounded-full border px-3 py-1 text-sm font-semibold',
                    VERDICT_TONE[result.decision?.verdict ?? ''] ??
                      'border-slate-200 bg-slate-100 text-slate-700'
                  )}
                >
                  {result.decision ? verdictLabel(result.decision.verdict) : 'No decision recorded'}
                </span>
                <span className='text-xs text-muted-foreground'>
                  Invoice {result.invoice_ref} · run <span className='font-mono'>{result.run_id}</span>
                </span>
              </div>

              {result.decision?.reason_codes.length ? (
                <div>
                  <p className='text-xs font-semibold uppercase tracking-[0.08em] text-slate-500'>
                    Reason
                  </p>
                  <ul className='mt-1.5 space-y-1'>
                    {result.decision.reason_codes.map((code) => (
                      <li key={code} className='text-sm text-slate-700'>
                        {humaniseCode(code)}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {result.decision && result.decision.money_protected > 0 ? (
                <div className='rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3'>
                  <p className='text-xs font-semibold uppercase tracking-[0.08em] text-emerald-700'>
                    Money protected
                  </p>
                  <p className='mt-1 text-lg font-bold text-emerald-800'>
                    {formatMoney(result.decision.money_protected, result.decision.currency ?? '')}
                  </p>
                </div>
              ) : null}

              {result.workbench_item_id ? (
                <Link
                  href='/workbench'
                  className='inline-flex items-center gap-1 text-sm font-medium text-brand-cornflower hover:underline'
                >
                  This invoice needed a person — open it in the Workbench
                  <Icons.arrowRight className='h-4 w-4' />
                </Link>
              ) : (
                <p className='text-sm text-muted-foreground'>
                  Cleared automatically — no human involved.
                </p>
              )}

              <Button variant='outline' className='w-full' onClick={reset}>
                Run another invoice
              </Button>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </CardContent>
    </Card>
  )
}
