'use client'

import Link from 'next/link'
import { useCallback, useEffect, useRef, useState } from 'react'

import {
  actionHref,
  dismissAPInsight,
  evidenceEntries,
  formatMetric,
  getAPInsights,
  refreshAPInsights,
  sortInsights,
} from '@/lib/ap-insights'
import type { APInsight, APInsightListResponse, APInsightSeverity } from '@/types/ap-insights'

const SEVERITY_STYLE: Record<APInsightSeverity, { chip: string; bar: string; label: string }> = {
  critical: {
    chip: 'bg-rose-100 text-rose-700 border-rose-200',
    bar: 'bg-rose-500',
    label: 'Critical',
  },
  warning: {
    chip: 'bg-amber-100 text-amber-700 border-amber-200',
    bar: 'bg-amber-500',
    label: 'Warning',
  },
  info: {
    chip: 'bg-sky-100 text-sky-700 border-sky-200',
    bar: 'bg-sky-500',
    label: 'Info',
  },
}

function SummaryTile({ label, value }: { label: string; value: number | string }) {
  return (
    <div className='rounded-xl border border-slate-200 bg-white p-4 shadow-sm'>
      <p className='text-xs font-medium uppercase tracking-wide text-slate-500'>{label}</p>
      <p className='mt-1 text-2xl font-semibold text-slate-900'>{value}</p>
    </div>
  )
}

function InsightCard({
  insight,
  onDismiss,
  dismissing,
}: {
  insight: APInsight
  onDismiss: (id: number) => void
  dismissing: boolean
}) {
  const [showEvidence, setShowEvidence] = useState(false)
  const style = SEVERITY_STYLE[insight.severity] ?? SEVERITY_STYLE.info
  const metric = formatMetric(insight)
  const href = actionHref(insight)
  const entries = evidenceEntries(insight.evidence)

  return (
    <article className='overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm'>
      <div className={`h-1 w-full ${style.bar}`} />
      <div className='p-5'>
        <div className='flex flex-wrap items-start justify-between gap-3'>
          <div className='min-w-0'>
            <span
              className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium ${style.chip}`}
            >
              {style.label}
            </span>
            <h3 className='mt-2 text-base font-semibold text-slate-900'>{insight.title}</h3>
          </div>
          {metric ? (
            <p className='shrink-0 text-2xl font-semibold text-slate-900'>{metric}</p>
          ) : null}
        </div>

        <p className='mt-3 text-sm leading-relaxed text-slate-600'>{insight.body}</p>

        <div className='mt-4 flex flex-wrap items-center gap-2'>
          {insight.action_label ? (
            href ? (
              <Link
                href={href}
                className='rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-slate-700'
              >
                {insight.action_label}
              </Link>
            ) : (
              <span className='rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600'>
                {insight.action_label}
              </span>
            )
          ) : null}

          {entries.length > 0 ? (
            <button
              type='button'
              onClick={() => setShowEvidence((open) => !open)}
              aria-expanded={showEvidence}
              aria-controls={`insight-evidence-${insight.id}`}
              className='rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 transition hover:bg-slate-50'
            >
              {showEvidence ? 'Hide evidence' : `Show evidence (${entries.length})`}
            </button>
          ) : null}

          <button
            type='button'
            onClick={() => onDismiss(insight.id)}
            disabled={dismissing}
            className='rounded-lg px-3 py-1.5 text-sm text-slate-500 transition hover:text-slate-800 disabled:opacity-50'
          >
            {dismissing ? 'Dismissing…' : 'Dismiss'}
          </button>
        </div>

        {showEvidence ? (
          <dl
            id={`insight-evidence-${insight.id}`}
            className='mt-4 space-y-3 rounded-lg bg-slate-50 p-4'
          >
            {entries.map((entry) => (
              <div key={entry.label}>
                <dt className='text-xs font-medium uppercase tracking-wide text-slate-500'>
                  {entry.label}
                </dt>
                <dd className='mt-1 overflow-x-auto'>
                  <pre className='whitespace-pre-wrap break-words text-xs text-slate-700'>
                    {entry.value}
                  </pre>
                </dd>
              </div>
            ))}
          </dl>
        ) : null}
      </div>
    </article>
  )
}

export default function InsightsPage() {
  const [data, setData] = useState<APInsightListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [dismissingId, setDismissingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  // The GET is read-only, so the first visit after a run has nothing stored yet. We
  // compute once, guarded so React Strict Mode's double effect cannot fire two writes.
  const autoComputed = useRef(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      let response = await getAPInsights()
      if (response.items.length === 0 && response.decisions_analysed > 0 && !autoComputed.current) {
        autoComputed.current = true
        response = await refreshAPInsights()
      }
      setData(response)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load insights')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const handleRefresh = async () => {
    setRefreshing(true)
    setError(null)
    try {
      setData(await refreshAPInsights())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not recompute insights')
    } finally {
      setRefreshing(false)
    }
  }

  const handleDismiss = async (id: number) => {
    setDismissingId(id)
    setError(null)
    try {
      await dismissAPInsight(id)
      setData((current) => {
        if (!current) return current
        const removed = current.items.find((i) => i.id === id)
        if (!removed) return current
        // Keep the summary tiles in step with the list, or they claim a severity that
        // has no card under it until the next reload.
        return {
          ...current,
          items: current.items.filter((i) => i.id !== id),
          total: current.total - 1,
          critical: current.critical - (removed.severity === 'critical' ? 1 : 0),
          warning: current.warning - (removed.severity === 'warning' ? 1 : 0),
          info: current.info - (removed.severity === 'info' ? 1 : 0),
        }
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not dismiss the insight')
    } finally {
      setDismissingId(null)
    }
  }

  const items = data ? sortInsights(data.items) : []

  return (
    <main className='mx-auto w-full max-w-5xl px-4 py-8'>
      <header className='flex flex-wrap items-start justify-between gap-4'>
        <div>
          <h1 className='text-2xl font-semibold text-slate-900'>AI Insights</h1>
          <p className='mt-1 text-sm text-slate-600'>
            Patterns and anomalies computed from the invoices the agent has actually processed.
            {data?.computed_at
              ? ` Last computed ${new Date(data.computed_at).toLocaleString()}.`
              : ''}
          </p>
        </div>
        <button
          type='button'
          onClick={handleRefresh}
          disabled={refreshing || loading}
          className='rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:opacity-50'
        >
          {refreshing ? 'Recomputing…' : 'Recompute'}
        </button>
      </header>

      {error ? (
        <div
          role='alert'
          className='mt-6 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700'
        >
          {error}
        </div>
      ) : null}

      {data ? (
        <section className='mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4'>
          <SummaryTile label='Critical' value={data.critical} />
          <SummaryTile label='Warning' value={data.warning} />
          <SummaryTile label='Info' value={data.info} />
          <SummaryTile label='Invoices analysed' value={data.decisions_analysed} />
        </section>
      ) : null}

      <section className='mt-6 space-y-4'>
        {loading ? (
          <p className='text-sm text-slate-500'>Loading insights…</p>
        ) : items.length === 0 ? (
          <div className='rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center'>
            <h2 className='text-base font-semibold text-slate-900'>No insights yet</h2>
            <p className='mx-auto mt-2 max-w-md text-sm text-slate-600'>
              {data && data.decisions_analysed === 0
                ? 'Insights are computed from invoices the agent has processed. Run the Orchestrator on at least one invoice, then recompute.'
                : 'Nothing stood out across the processed invoices. Recompute after the next run.'}
            </p>
          </div>
        ) : (
          items.map((insight) => (
            <InsightCard
              key={insight.id}
              insight={insight}
              onDismiss={handleDismiss}
              dismissing={dismissingId === insight.id}
            />
          ))
        )}
      </section>
    </main>
  )
}
