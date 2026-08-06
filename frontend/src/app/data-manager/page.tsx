'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'

import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Icons } from '@/components/ui/icons'
import { getDataManager, refreshDataManager } from '@/lib/ap-data-manager'
import { cn } from '@/lib/utils'
import type {
  DataManagerResponse,
  IntegrationHealth,
  IntegrationStatus,
} from '@/types/ap-data-manager'

const STATUS_PRESENTATION: Record<
  IntegrationStatus,
  {
    label: string
    description: string
    className: string
    dotClassName: string
  }
> = {
  healthy: {
    label: 'Healthy',
    description: 'Operating with current evidence',
    className: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    dotClassName: 'bg-emerald-500',
  },
  degraded: {
    label: 'Degraded',
    description: 'Evidence is older than the freshness window',
    className: 'border-amber-200 bg-amber-50 text-amber-800',
    dotClassName: 'bg-amber-500',
  },
  down: {
    label: 'Down',
    description: 'The latest measurement failed',
    className: 'border-rose-200 bg-rose-50 text-rose-800',
    dotClassName: 'bg-rose-500',
  },
  unknown: {
    label: 'Unknown',
    description: 'No real activity has been recorded yet',
    className: 'border-slate-200 bg-slate-100 text-slate-700',
    dotClassName: 'bg-slate-400',
  },
}

const SUMMARY_ORDER: IntegrationStatus[] = [
  'healthy',
  'degraded',
  'down',
  'unknown',
]

function formatTimestamp(value: string | null): string {
  if (!value) return 'Never'
  return new Intl.DateTimeFormat('en-MY', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function humanizeKey(value: string): string {
  return value.replaceAll('_', ' ')
}

function humanizeMeasurementMethod(value: string): string {
  const label = humanizeKey(value)
  return label.charAt(0).toUpperCase() + label.slice(1)
}

function integrationStatusDescription(integration: IntegrationHealth): string {
  if (integration.status !== 'unknown') {
    return STATUS_PRESENTATION[integration.status].description
  }
  if (integration.detail?.message === 'Health probe is not configured') {
    return 'Not configured'
  }
  if (integration.measurement_method?.startsWith('recorded_')) {
    const connectorName =
      integration.key === 'outlook' ? 'Outlook' : integration.name
    return `Awaiting real ${connectorName} activity`
  }
  return 'Health evidence is not available yet'
}

function StatusBadge({ status }: { status: IntegrationStatus }) {
  const presentation = STATUS_PRESENTATION[status]
  return (
    <span
      className={cn(
        'inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold',
        presentation.className
      )}
    >
      <span
        aria-hidden='true'
        className={cn('h-2 w-2 rounded-full', presentation.dotClassName)}
      />
      {presentation.label}
    </span>
  )
}

function SummaryRail({ data }: { data: DataManagerResponse }) {
  return (
    <section
      aria-label='Integration status summary'
      className='overflow-hidden rounded-2xl border border-slate-800 bg-slate-950 shadow-soft'
    >
      <div className='grid grid-cols-2 divide-x divide-y divide-white/10 sm:grid-cols-4 sm:divide-y-0'>
        {SUMMARY_ORDER.map((status) => (
          <div
            key={status}
            data-status={status}
            className='relative px-5 py-4 text-white'
          >
            <div className='flex items-center justify-between gap-3'>
              <span className='text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400'>
                {STATUS_PRESENTATION[status].label}
              </span>
              <span
                aria-hidden='true'
                className={cn(
                  'h-2 w-2 rounded-full',
                  STATUS_PRESENTATION[status].dotClassName
                )}
              />
            </div>
            <span className='mt-2 block font-mono text-3xl font-semibold tracking-tight'>
              {data.counts[status]}
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}

function IntegrationCard({ integration }: { integration: IntegrationHealth }) {
  const status = STATUS_PRESENTATION[integration.status]
  const detailEntries = Object.entries(integration.detail ?? {})
  const shouldReduceMotion = useReducedMotion()

  return (
    <motion.article
      aria-label={`${integration.name} integration`}
      initial={shouldReduceMotion ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={
        shouldReduceMotion
          ? { duration: 0 }
          : { duration: 0.35, ease: [0.25, 0.46, 0.45, 0.94] }
      }
    >
      <Card className='relative h-full overflow-hidden hover:translate-y-0'>
        <span
          aria-hidden='true'
          className={cn('absolute inset-y-0 left-0 w-1.5', status.dotClassName)}
        />
        <CardHeader className='pb-4 pl-7'>
          <div className='flex items-start justify-between gap-4'>
            <div>
              <p className='font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-brand-muted'>
                {integration.category}
              </p>
              <CardTitle className='mt-2'>{integration.name}</CardTitle>
            </div>
            <StatusBadge status={integration.status} />
          </div>
          <CardDescription className='pt-2 leading-6'>
            {integration.purpose}
          </CardDescription>
          <p className='pt-1 text-xs font-medium text-slate-600'>
            {integrationStatusDescription(integration)}
          </p>
        </CardHeader>

        <CardContent className='space-y-5 pl-7'>
          <dl className='grid grid-cols-2 gap-x-5 gap-y-4 border-y border-slate-200 py-4 text-sm'>
            <div>
              <dt className='text-[10px] font-semibold uppercase tracking-[0.1em] text-slate-500'>
                Last checked
              </dt>
              <dd className='mt-1 text-slate-900'>
                {formatTimestamp(integration.last_checked_at)}
              </dd>
            </div>
            <div>
              <dt className='text-[10px] font-semibold uppercase tracking-[0.1em] text-slate-500'>
                Last activity
              </dt>
              <dd className='mt-1 text-slate-900'>
                {formatTimestamp(integration.last_activity_at)}
              </dd>
            </div>
            <div>
              <dt className='text-[10px] font-semibold uppercase tracking-[0.1em] text-slate-500'>
                Records seen
              </dt>
              <dd className='mt-1 font-mono font-semibold text-slate-900'>
                {integration.records_seen}
              </dd>
            </div>
            <div className='col-span-2'>
              <dt className='text-[10px] font-semibold uppercase tracking-[0.1em] text-slate-500'>
                Measurement method
              </dt>
              <dd className='mt-1 font-mono text-xs font-semibold text-slate-900'>
                {integration.measurement_method
                  ? humanizeMeasurementMethod(integration.measurement_method)
                  : 'Not recorded'}
              </dd>
            </div>
            {integration.latency_ms !== null ? (
              <div>
                <dt className='text-[10px] font-semibold uppercase tracking-[0.1em] text-slate-500'>
                  Latency
                </dt>
                <dd className='mt-1 font-mono font-semibold text-slate-900'>
                  {integration.latency_ms} ms
                </dd>
              </div>
            ) : null}
          </dl>

          {detailEntries.length ? (
            <dl className='grid gap-3 sm:grid-cols-2'>
              {detailEntries.map(([key, value]) => (
                <div
                  key={key}
                  className='rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5'
                >
                  <dt className='text-[10px] font-semibold uppercase tracking-[0.1em] text-slate-500'>
                    {humanizeKey(key)}
                  </dt>
                  <dd className='mt-1 break-words text-sm text-slate-800'>
                    {value === null ? 'Not recorded' : String(value)}
                  </dd>
                </div>
              ))}
            </dl>
          ) : null}

          {integration.last_error ? (
            <p className='rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800'>
              <span className='font-semibold'>Error category:</span>{' '}
              {humanizeKey(integration.last_error)}
            </p>
          ) : null}
        </CardContent>
      </Card>
    </motion.article>
  )
}

function ErrorPanel({
  message,
  onRetry,
}: {
  message: string
  onRetry: () => void
}) {
  return (
    <div
      className='rounded-2xl border border-rose-200 bg-rose-50 p-6'
      role='alert'
    >
      <div className='flex items-start gap-3'>
        <Icons.alertTriangle className='mt-0.5 h-5 w-5 shrink-0 text-rose-700' />
        <div>
          <h2 className='font-semibold text-rose-950'>
            Integration health could not be loaded
          </h2>
          <p className='mt-1 text-sm text-rose-800'>{message}</p>
          <Button
            className='mt-4'
            size='sm'
            variant='outline'
            onClick={onRetry}
            aria-label='Retry loading health'
          >
            <Icons.refresh className='h-4 w-4' />
            Retry
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function DataManagerPage() {
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<DataManagerResponse | null>(null)
  const [refreshAnnouncement, setRefreshAnnouncement] = useState('')
  const loadGeneration = useRef(0)

  const loadPersistedHealth = useCallback(async () => {
    const generation = ++loadGeneration.current
    setLoading(true)
    setError(null)
    try {
      const response = await getDataManager()
      if (generation !== loadGeneration.current) return
      setData(response)
    } catch (caught) {
      if (generation !== loadGeneration.current) return
      setError(
        caught instanceof Error
          ? caught.message
          : 'Persisted integration health is unavailable.'
      )
    } finally {
      if (generation === loadGeneration.current) {
        setLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    void loadPersistedHealth()
    return () => {
      loadGeneration.current += 1
    }
  }, [loadPersistedHealth])

  const refreshHealth = useCallback(async () => {
    setRefreshing(true)
    setError(null)
    setRefreshAnnouncement('')
    try {
      const response = await refreshDataManager()
      setData(response)
      setRefreshAnnouncement(
        `Integration health refreshed: ${response.counts.healthy} healthy, ${response.counts.degraded} degraded, ${response.counts.down} down, ${response.counts.unknown} unknown.`
      )
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'Integration health could not be refreshed.'
      )
    } finally {
      setRefreshing(false)
    }
  }, [])

  if (loading && !data) {
    return (
      <main className='flex min-h-[55vh] items-center justify-center px-4'>
        <div className='text-center text-sm text-brand-muted' role='status'>
          <Icons.loader className='mx-auto mb-3 h-6 w-6 text-brand-cornflower motion-safe:animate-spin' />
          Loading integration health…
        </div>
      </main>
    )
  }

  return (
    <main className='mx-auto w-full max-w-[1440px] space-y-7 px-4 py-6 sm:px-6 lg:px-8 lg:py-8'>
      <header className='flex flex-col justify-between gap-5 border-b border-slate-200 pb-6 sm:flex-row sm:items-end'>
        <div>
          <div className='flex items-center gap-2 text-brand-cornflower'>
            <Icons.network className='h-4 w-4' />
            <p className='font-mono text-[10px] font-semibold uppercase tracking-[0.18em]'>
              Live connector evidence
            </p>
          </div>
          <h1 className='mt-3 font-display text-3xl font-bold tracking-tight text-brand-navy sm:text-4xl'>
            Data Manager
          </h1>
          <p className='mt-2 max-w-2xl text-sm leading-6 text-brand-muted sm:text-base'>
            Inspect persisted health signals and run safe, read-only checks
            across the AP control tower.
          </p>
        </div>
        {data ? (
          <Button
            type='button'
            onClick={() => void refreshHealth()}
            disabled={refreshing}
            aria-busy={refreshing}
            aria-label='Refresh health'
          >
            <Icons.refresh
              className={cn(
                'h-4 w-4',
                refreshing && 'motion-safe:animate-spin'
              )}
            />
            {refreshing ? 'Refreshing…' : 'Refresh health'}
          </Button>
        ) : null}
      </header>

      {error && !data ? (
        <ErrorPanel
          message={error}
          onRetry={() => void loadPersistedHealth()}
        />
      ) : null}

      {data ? (
        <>
          <p className='sr-only' role='status' aria-live='polite'>
            {refreshAnnouncement}
          </p>

          <SummaryRail data={data} />

          {data.partial_failure ? (
            <div
              role='alert'
              className='flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900'
            >
              <Icons.alertTriangle className='mt-0.5 h-5 w-5 shrink-0' />
              <p>
                <span className='font-semibold'>
                  Latest health snapshot includes one or more integrations that
                  are down.
                </span>{' '}
                Review the affected connector evidence below.
              </p>
            </div>
          ) : null}

          {error ? (
            <div
              role='alert'
              className='flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900'
            >
              <div className='flex items-center gap-3'>
                <Icons.alertTriangle className='h-5 w-5 shrink-0' />
                <p>
                  <span className='font-semibold'>Refresh failed.</span> {error}
                </p>
              </div>
              <Button
                type='button'
                size='sm'
                variant='outline'
                onClick={() => void refreshHealth()}
                aria-label='Retry refresh'
              >
                <Icons.refresh className='h-4 w-4' />
                Retry refresh
              </Button>
            </div>
          ) : null}

          <section aria-labelledby='integration-health-heading'>
            <h2 id='integration-health-heading' className='sr-only'>
              Integration health
            </h2>
            {data.integrations.length ? (
              <div className='grid gap-5 lg:grid-cols-2'>
                {data.integrations.map((integration) => (
                  <IntegrationCard
                    key={integration.key}
                    integration={integration}
                  />
                ))}
              </div>
            ) : (
              <Card className='border-dashed'>
                <CardContent className='py-14 text-center'>
                  <Icons.network className='mx-auto h-10 w-10 text-slate-300' />
                  <h3 className='mt-4 text-lg font-semibold text-brand-navy'>
                    No integrations are registered
                  </h3>
                  <p className='mx-auto mt-2 max-w-md text-sm leading-6 text-brand-muted'>
                    Ask an administrator to seed the integration registry before
                    running health checks.
                  </p>
                </CardContent>
              </Card>
            )}
          </section>

          <p className='text-xs text-brand-muted'>
            Activity freshness window: {data.freshness_hours} hours. Refresh
            checks do not send test email or Slack messages.
          </p>
        </>
      ) : null}
    </main>
  )
}
