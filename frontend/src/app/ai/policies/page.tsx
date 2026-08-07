'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { PolicyList } from '@/components/ap/policies/policy-list'
import { PolicyEditDialog } from '@/components/ap/policies/policy-edit-dialog'
import { PolicyHistoryDialog } from '@/components/ap/policies/policy-history-dialog'
import { PolicySummary } from '@/components/ap/policies/policy-summary'
import { Button } from '@/components/ui/button'
import { Icons } from '@/components/ui/icons'
import { getAPPolicies, getAPPolicyHistory, updateAPPolicy } from '@/lib/ap-policies'
import { cn } from '@/lib/utils'
import type {
  APPolicy,
  APPolicySeverity,
  APPolicyListResponse,
  APPolicyValue,
  APPolicyVersion,
} from '@/types/ap-policies'

type SeverityFilter = 'all' | APPolicySeverity

const SEVERITY_FILTERS: Array<{ value: SeverityFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'block', label: 'Block' },
  { value: 'escalate', label: 'Escalate' },
  { value: 'advise', label: 'Advise' },
]

function PolicyLoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role='alert' className='rounded-2xl border border-rose-200 bg-rose-50 p-6 text-rose-900'>
      <div className='flex items-start gap-3'>
        <Icons.alertTriangle className='mt-0.5 h-5 w-5 shrink-0 text-rose-700' />
        <div>
          <h2 className='font-semibold'>AP policies could not be loaded</h2>
          <p className='mt-1 text-sm text-rose-800'>{message}</p>
          <Button
            type='button'
            className='mt-4'
            size='sm'
            variant='outline'
            onClick={onRetry}
            aria-label='Retry loading policies'
          >
            <Icons.refresh className='h-4 w-4' />
            Retry
          </Button>
        </div>
      </div>
    </div>
  )
}

function EmptyPolicyState({ hasFilters }: { hasFilters: boolean }) {
  return (
    <div className='rounded-2xl border border-dashed border-slate-300 bg-white/70 px-6 py-14 text-center'>
      <Icons.layers className='mx-auto h-9 w-9 text-slate-300' />
      <h3 className='mt-4 text-lg font-semibold text-brand-navy'>
        {hasFilters ? 'No policies match the current filters' : 'No AP policies are available'}
      </h3>
      <p className='mx-auto mt-2 max-w-md text-sm leading-6 text-brand-muted'>
        {hasFilters
          ? 'Adjust the search or severity filter to review another policy.'
          : 'The AP policy service did not return any policies in this snapshot.'}
      </p>
    </div>
  )
}

export default function AIPoliciesPage() {
  const [data, setData] = useState<APPolicyListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all')
  const [editingPolicy, setEditingPolicy] = useState<APPolicy | null>(null)
  const [historyPolicy, setHistoryPolicy] = useState<APPolicy | null>(null)
  const [historyItems, setHistoryItems] = useState<APPolicyVersion[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const loadGeneration = useRef(0)
  const historyGeneration = useRef(0)

  const loadPolicies = useCallback(async (): Promise<boolean> => {
    const generation = ++loadGeneration.current
    setLoading(true)
    setError(null)
    try {
      const response = await getAPPolicies()
      if (generation !== loadGeneration.current) return false
      setData(response)
      return true
    } catch (caught) {
      if (generation !== loadGeneration.current) return false
      setData(null)
      setError(
        caught instanceof Error ? caught.message : 'AP policies are unavailable.'
      )
      return false
    } finally {
      if (generation === loadGeneration.current) {
        setLoading(false)
      }
    }
  }, [])

  const handlePolicySave = useCallback(async (policy: APPolicy, value: APPolicyValue, note: string) => {
    await updateAPPolicy(policy.key, value, note.trim())
  }, [])

  const loadHistory = useCallback(async (policy: APPolicy): Promise<void> => {
    const generation = ++historyGeneration.current
    setHistoryLoading(true)
    setHistoryError(null)
    try {
      const response = await getAPPolicyHistory(policy.key)
      if (generation !== historyGeneration.current) return
      setHistoryItems(response.items)
    } catch (caught) {
      if (generation !== historyGeneration.current) return
      setHistoryItems([])
      setHistoryError(
        caught instanceof Error ? caught.message : 'Policy history is unavailable.'
      )
    } finally {
      if (generation === historyGeneration.current) {
        setHistoryLoading(false)
      }
    }
  }, [])

  const handlePolicySaved = useCallback(async () => {
    const policyToRefresh =
      editingPolicy && historyPolicy?.key === editingPolicy.key ? historyPolicy : null
    if (policyToRefresh) {
      void loadHistory(policyToRefresh)
    }
    const refreshed = await loadPolicies()
    if (refreshed) {
      setSuccessMessage('Policy updated successfully')
    }
  }, [editingPolicy, historyPolicy, loadHistory, loadPolicies])

  const handlePolicyEdit = useCallback((policy: APPolicy) => {
    setSuccessMessage(null)
    setEditingPolicy(policy)
  }, [])

  const handlePolicyHistory = useCallback((policy: APPolicy) => {
    setHistoryPolicy(policy)
    setHistoryItems([])
    setHistoryError(null)
    void loadHistory(policy)
  }, [loadHistory])

  const handleHistoryOpenChange = useCallback((open: boolean) => {
    if (open) return

    historyGeneration.current += 1
    setHistoryPolicy(null)
    setHistoryItems([])
    setHistoryError(null)
    setHistoryLoading(false)
  }, [])

  useEffect(() => {
    void loadPolicies()
    return () => {
      loadGeneration.current += 1
      historyGeneration.current += 1
    }
  }, [loadPolicies])

  const filteredPolicies = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    return (data?.items ?? []).filter((policy) => {
      const matchesSeverity =
        severityFilter === 'all' || policy.severity === severityFilter
      const matchesSearch =
        !query ||
        policy.key.toLowerCase().includes(query) ||
        policy.name.toLowerCase().includes(query) ||
        policy.description.toLowerCase().includes(query)

      return matchesSeverity && matchesSearch
    })
  }, [data, searchQuery, severityFilter])

  const hasFilters = Boolean(searchQuery.trim()) || severityFilter !== 'all'

  return (
    <div className='mx-auto w-full max-w-[1440px] space-y-7 px-4 py-6 sm:px-6 lg:px-8 lg:py-8'>
      <header className='flex flex-col justify-between gap-5 border-b border-slate-200 pb-6 sm:flex-row sm:items-end'>
        <div>
          <div className='flex items-center gap-2 text-brand-cornflower'>
            <Icons.shield className='h-4 w-4' />
            <p className='font-mono text-[10px] font-semibold uppercase tracking-[0.18em]'>
              AP governance controls
            </p>
          </div>
          <h1 className='mt-3 font-display text-3xl font-bold tracking-tight text-brand-navy sm:text-4xl'>
            AP Policies
          </h1>
          <p className='mt-2 max-w-2xl text-sm leading-6 text-brand-muted sm:text-base'>
            Inspect the live controls that block, escalate, or advise invoice-processing decisions.
          </p>
        </div>
        <Button
          type='button'
          variant='outline'
          onClick={() => void loadPolicies()}
          disabled={loading}
          aria-busy={loading}
          aria-label='Refresh policies'
        >
          <Icons.refresh
            className={cn('h-4 w-4', loading && 'motion-safe:animate-spin')}
          />
          {loading ? 'Refreshing…' : 'Refresh'}
        </Button>
      </header>

      {loading && !data ? (
        <div className='flex min-h-[38vh] items-center justify-center' role='status'>
          <div className='text-center text-sm text-brand-muted'>
            <Icons.loader className='mx-auto mb-3 h-6 w-6 text-brand-cornflower motion-safe:animate-spin' />
            Loading AP policies…
          </div>
        </div>
      ) : null}

      {error && !data ? (
        <PolicyLoadError message={error} onRetry={() => void loadPolicies()} />
      ) : null}

      {data ? (
        <>
          {loading ? (
            <p className='sr-only' role='status' aria-live='polite'>
              Refreshing AP policies…
            </p>
          ) : null}

          {successMessage ? (
            <p role='status' aria-live='polite' className='rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800'>
              {successMessage}
            </p>
          ) : null}

          <PolicySummary
            policies={data.items}
            total={data.total}
            snapshotLabel={data.snapshot_label}
          />

          <section aria-labelledby='policy-list-heading' className='space-y-4'>
            <div className='flex flex-col justify-between gap-4 sm:flex-row sm:items-end'>
              <div>
                <h2 id='policy-list-heading' className='text-xl font-semibold text-brand-navy'>
                  Policy controls
                </h2>
                <p className='mt-1 text-sm text-brand-muted'>
                  Filter live controls by severity or search their key, name, and description.
                </p>
              </div>
              <label className='w-full text-sm font-medium text-slate-700 sm:max-w-sm'>
                <span className='sr-only'>Search AP policies</span>
                <div className='relative'>
                  <Icons.search className='pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400' />
                  <input
                    type='search'
                    value={searchQuery}
                    onChange={(event) => setSearchQuery(event.target.value)}
                    placeholder='Search policies'
                    className='w-full rounded-xl border border-slate-300 bg-white py-2.5 pl-10 pr-3 text-sm text-slate-900 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-brand-cornflower focus:ring-2 focus:ring-brand-cornflower/20'
                  />
                </div>
              </label>
            </div>

            <div aria-label='Severity filters' className='flex flex-wrap gap-2'>
              {SEVERITY_FILTERS.map((filter) => (
                <Button
                  key={filter.value}
                  type='button'
                  size='sm'
                  variant={severityFilter === filter.value ? 'default' : 'outline'}
                  onClick={() => setSeverityFilter(filter.value)}
                  aria-pressed={severityFilter === filter.value}
                  aria-label={`${filter.label} policies`}
                >
                  {filter.label}
                </Button>
              ))}
            </div>

            {data.items.length === 0 || filteredPolicies.length === 0 ? (
              <EmptyPolicyState hasFilters={data.items.length > 0 && hasFilters} />
            ) : (
              <PolicyList
                policies={filteredPolicies}
                onEdit={handlePolicyEdit}
                onViewHistory={handlePolicyHistory}
              />
            )}
          </section>
        </>
      ) : null}

      <PolicyEditDialog
        policy={editingPolicy}
        open={editingPolicy !== null}
        onOpenChange={(open) => {
          if (!open) setEditingPolicy(null)
        }}
        onSave={handlePolicySave}
        onSaved={() => void handlePolicySaved()}
      />
      <PolicyHistoryDialog
        policy={historyPolicy}
        open={historyPolicy !== null}
        items={historyItems}
        loading={historyLoading}
        error={historyError}
        onOpenChange={handleHistoryOpenChange}
        onRetry={() => {
          if (historyPolicy) void loadHistory(historyPolicy)
        }}
      />
    </div>
  )
}
