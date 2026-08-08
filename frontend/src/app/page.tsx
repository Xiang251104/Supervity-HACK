'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { CardWatermark } from '@/components/ui/card-watermark'
import { Icons } from '@/components/ui/icons'
import { ProcessInvoiceCard } from '@/components/dashboard/ProcessInvoiceCard'
import {
  barPercent,
  formatDuration,
  formatMoney,
  getAPMetrics,
  humaniseCode,
  primaryCurrencyTotal,
  verdictLabel,
} from '@/lib/ap-metrics'
import { cn } from '@/lib/utils'
import type { APMetrics } from '@/types/ap-metrics'

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.08, delayChildren: 0.1 },
  },
}

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] },
  },
}

const VERDICT_COLOUR: Record<string, string> = {
  PAY_READY: 'bg-emerald-500',
  HUMAN_REVIEW: 'bg-amber-500',
  PAYMENT_HOLD: 'bg-rose-500',
  DATA_ERROR: 'bg-slate-500',
}

interface StatCardProps {
  title: string
  value: string
  caption?: string
  icon: React.ElementType
  colorClass: string
  delay?: number
}

function StatCard({ title, value, caption, icon: Icon, colorClass, delay = 0 }: StatCardProps) {
  return (
    <motion.div
      variants={itemVariants}
      initial='hidden'
      animate='visible'
      transition={{ delay }}
      whileHover={{ y: -4 }}
    >
      <Card className='group relative h-full cursor-default overflow-hidden'>
        <CardWatermark opacity={3} scale={0.9} />
        <CardContent className='relative z-10 p-5'>
          <div className='flex items-start justify-between gap-3'>
            <div className='min-w-0 space-y-2'>
              <p className='text-micro uppercase text-brand-muted transition-colors duration-200 group-hover:text-brand-cornflower'>
                {title}
              </p>
              <p className='font-display text-[2rem] font-bold leading-none tracking-tight text-brand-navy'>
                {value}
              </p>
              {caption ? (
                <p className='text-xs font-medium text-muted-foreground'>{caption}</p>
              ) : null}
            </div>
            <motion.div
              className={cn('shrink-0 rounded-xl p-2.5 text-white shadow-lg', colorClass)}
              whileHover={{ scale: 1.15, rotate: 5 }}
              transition={{ type: 'spring', stiffness: 400, damping: 17 }}
            >
              <Icon className='h-5 w-5' strokeWidth={1.5} />
            </motion.div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  )
}

function HeroSection({ metrics }: { metrics: APMetrics | null }) {
  return (
    <motion.div
      className='col-span-12 py-2'
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.25, 0.46, 0.45, 0.94] }}
    >
      <h1 className='text-display-3 font-bold tracking-tight text-brand-navy lg:text-display-2'>
        AP Control Tower
      </h1>
      <p className='mt-4 text-lg font-light text-muted-foreground'>
        {metrics && metrics.invoices_processed > 0
          ? `${metrics.invoices_processed} invoices processed across ${metrics.total_runs} agent runs.`
          : 'No invoices processed yet. Run the Orchestrator to populate this view.'}
      </p>
    </motion.div>
  )
}

function VerdictBreakdown({ metrics }: { metrics: APMetrics }) {
  const entries = Object.entries(metrics.verdict_breakdown).filter(([, count]) => count > 0)
  const total = entries.reduce((sum, [, count]) => sum + count, 0)

  return (
    <Card className='relative h-full overflow-hidden'>
      <CardWatermark opacity={3} scale={1.1} />
      <CardHeader className='relative z-10'>
        <CardTitle className='flex items-center gap-2'>
          <Icons.layers className='h-5 w-5 text-brand-cornflower' strokeWidth={1.5} />
          Outcomes
        </CardTitle>
      </CardHeader>
      <CardContent className='relative z-10'>
        {total === 0 ? (
          <p className='text-sm text-muted-foreground'>Nothing decided yet.</p>
        ) : (
          <>
            <div className='flex h-3 w-full overflow-hidden rounded-full bg-muted'>
              {entries.map(([verdict, count]) => (
                <div
                  key={verdict}
                  className={VERDICT_COLOUR[verdict] ?? 'bg-slate-400'}
                  style={{ width: `${(count / total) * 100}%` }}
                  title={`${verdictLabel(verdict)}: ${count}`}
                />
              ))}
            </div>
            <ul className='mt-4 space-y-2'>
              {entries.map(([verdict, count]) => (
                <li key={verdict} className='flex items-center justify-between text-sm'>
                  <span className='flex items-center gap-2 text-muted-foreground'>
                    <span
                      className={cn(
                        'h-2.5 w-2.5 rounded-full',
                        VERDICT_COLOUR[verdict] ?? 'bg-slate-400'
                      )}
                    />
                    {verdictLabel(verdict)}
                  </span>
                  <span className='font-medium text-foreground'>{count}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  )
}

function ExceptionsByType({ metrics }: { metrics: APMetrics }) {
  const top = metrics.exceptions_by_type.slice(0, 6)
  const counts = top.map((e) => e.count)

  return (
    <Card className='relative h-full overflow-hidden'>
      <CardWatermark opacity={3} scale={1.1} />
      <CardHeader className='relative z-10'>
        <CardTitle className='flex items-center gap-2'>
          <Icons.alertTriangle className='h-5 w-5 text-brand-cornflower' strokeWidth={1.5} />
          Exceptions by type
        </CardTitle>
      </CardHeader>
      <CardContent className='relative z-10'>
        {top.length === 0 ? (
          <p className='text-sm text-muted-foreground'>No exceptions raised.</p>
        ) : (
          <ul className='space-y-3'>
            {top.map((exception) => (
              <li key={exception.code}>
                <div className='flex items-center justify-between text-sm'>
                  <span className='truncate text-muted-foreground' title={exception.code}>
                    {humaniseCode(exception.code)}
                  </span>
                  <span className='ml-3 font-medium text-foreground'>{exception.count}</span>
                </div>
                <div className='mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted'>
                  <div
                    className='h-full rounded-full bg-brand-cornflower'
                    style={{ width: `${barPercent(exception.count, counts)}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function ExceptionAging({ metrics }: { metrics: APMetrics }) {
  const counts = metrics.exception_aging.map((b) => b.count)
  const total = counts.reduce((sum, c) => sum + c, 0)

  return (
    <Card className='relative h-full overflow-hidden'>
      <CardWatermark opacity={3} scale={1.1} />
      <CardHeader className='relative z-10'>
        <CardTitle className='flex items-center gap-2'>
          <Icons.clock className='h-5 w-5 text-brand-cornflower' strokeWidth={1.5} />
          Waiting on a human
        </CardTitle>
      </CardHeader>
      <CardContent className='relative z-10'>
        {total === 0 ? (
          <p className='text-sm text-muted-foreground'>The queue is clear.</p>
        ) : (
          <>
            <ul className='space-y-3'>
              {metrics.exception_aging.map((bucket) => (
                <li key={bucket.bucket}>
                  <div className='flex items-center justify-between text-sm'>
                    <span className='text-muted-foreground'>{bucket.bucket}</span>
                    <span className='font-medium text-foreground'>{bucket.count}</span>
                  </div>
                  <div className='mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted'>
                    <div
                      className='h-full rounded-full bg-amber-500'
                      style={{ width: `${barPercent(bucket.count, counts)}%` }}
                    />
                  </div>
                </li>
              ))}
            </ul>
            <Link
              href='/workbench'
              className='mt-4 inline-flex items-center gap-1 text-sm font-medium text-brand-cornflower hover:underline'
            >
              Open the Workbench
              <Icons.arrowRight className='h-4 w-4' />
            </Link>
          </>
        )}
      </CardContent>
    </Card>
  )
}

function RecentRuns({ metrics }: { metrics: APMetrics }) {
  return (
    <Card className='relative col-span-12 overflow-hidden'>
      <CardWatermark opacity={3} scale={1.1} />
      <CardHeader className='relative z-10'>
        <CardTitle className='flex items-center gap-2'>
          <Icons.activity className='h-5 w-5 text-brand-cornflower' strokeWidth={1.5} />
          Recent agent runs
        </CardTitle>
      </CardHeader>
      <CardContent className='relative z-10'>
        {metrics.recent_runs.length === 0 ? (
          <p className='text-sm text-muted-foreground'>
            No runs recorded. Start one to see the Orchestrator&apos;s activity here.
          </p>
        ) : (
          <div className='overflow-x-auto'>
            <table className='w-full min-w-[36rem] text-sm'>
              <thead>
                <tr className='border-b border-border/50 text-left text-xs uppercase text-muted-foreground'>
                  <th className='pb-2 pr-4 font-medium'>Run</th>
                  <th className='pb-2 pr-4 font-medium'>Invoice</th>
                  <th className='pb-2 pr-4 font-medium'>Status</th>
                  <th className='pb-2 pr-4 font-medium'>Duration</th>
                  <th className='pb-2 font-medium'>Policy version</th>
                </tr>
              </thead>
              <tbody>
                {metrics.recent_runs.map((run) => (
                  <tr key={run.run_id} className='border-b border-border/30 last:border-0'>
                    <td className='py-2 pr-4 font-mono text-xs text-muted-foreground'>
                      {run.run_id}
                    </td>
                    <td className='py-2 pr-4 text-foreground'>{run.invoice_ref ?? '—'}</td>
                    <td className='py-2 pr-4'>
                      <span
                        className={cn(
                          'rounded-full px-2 py-0.5 text-xs font-medium',
                          run.status === 'completed'
                            ? 'bg-emerald-100 text-emerald-700'
                            : run.status === 'failed'
                              ? 'bg-rose-100 text-rose-700'
                              : 'bg-slate-100 text-slate-700'
                        )}
                      >
                        {run.status}
                      </span>
                    </td>
                    <td className='py-2 pr-4 text-muted-foreground'>
                      {formatDuration(run.duration_ms)}
                    </td>
                    <td className='py-2 font-mono text-xs text-muted-foreground'>
                      {run.policy_version_label ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default function HomePage() {
  const [metrics, setMetrics] = useState<APMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setMetrics(await getAPMetrics())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load dashboard metrics')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const protectedTotal = metrics ? primaryCurrencyTotal(metrics.money_protected) : null
  const reviewTotal = metrics ? primaryCurrencyTotal(metrics.spend_under_review) : null

  return (
    <motion.div
      className='space-y-6'
      variants={containerVariants}
      initial='hidden'
      animate='visible'
    >
      <HeroSection metrics={metrics} />

      <motion.div className='grid grid-cols-12 gap-6' variants={itemVariants}>
        <ProcessInvoiceCard onRunCompleted={() => void load()} />
      </motion.div>

      {error ? (
        <div
          role='alert'
          className='rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700'
        >
          {error}
        </div>
      ) : null}

      {loading ? (
        <p className='text-sm text-muted-foreground'>Loading live figures…</p>
      ) : metrics ? (
        <>
          <div className='grid grid-cols-2 gap-4 lg:grid-cols-4'>
            <StatCard
              title='Touchless rate'
              value={`${metrics.touchless_rate}%`}
              caption={`${metrics.pay_ready} of ${metrics.invoices_processed} cleared without a human`}
              icon={Icons.zap}
              colorClass='bg-brand-navy'
              delay={0.1}
            />
            <StatCard
              title='Money protected'
              value={
                protectedTotal
                  ? formatMoney(protectedTotal.amount, protectedTotal.currency)
                  : '—'
              }
              caption={
                protectedTotal && protectedTotal.otherCurrencies > 0
                  ? `plus ${protectedTotal.otherCurrencies} other ${protectedTotal.otherCurrencies === 1 ? 'currency' : 'currencies'}`
                  : 'held before payment'
              }
              icon={Icons.shield}
              colorClass='bg-brand-cornflower'
              delay={0.2}
            />
            <StatCard
              title='Spend under review'
              value={reviewTotal ? formatMoney(reviewTotal.amount, reviewTotal.currency) : '—'}
              caption='awaiting a decision, not protected'
              icon={Icons.clock}
              colorClass='bg-brand-purple'
              delay={0.3}
            />
            <StatCard
              title='Open exceptions'
              value={String(metrics.workbench_open)}
              caption={`${metrics.workbench_resolved} resolved`}
              icon={Icons.inbox}
              colorClass='bg-gradient-to-br from-brand-navy to-brand-purple'
              delay={0.4}
            />
          </div>

          <motion.div className='grid gap-6 lg:grid-cols-3' variants={itemVariants}>
            <VerdictBreakdown metrics={metrics} />
            <ExceptionsByType metrics={metrics} />
            <ExceptionAging metrics={metrics} />
          </motion.div>

          <motion.div className='grid gap-6 lg:grid-cols-12' variants={itemVariants}>
            <RecentRuns metrics={metrics} />
          </motion.div>
        </>
      ) : null}
    </motion.div>
  )
}
