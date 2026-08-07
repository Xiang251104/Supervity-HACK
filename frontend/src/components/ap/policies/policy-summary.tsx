import type { ReactNode } from 'react'

import { Card, CardContent } from '@/components/ui/card'
import type { APPolicy } from '@/types/ap-policies'

function formatPolicyTimestamp(value: string): string {
  return new Intl.DateTimeFormat('en-MY', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function latestUpdatedPolicy(policies: APPolicy[]): APPolicy | null {
  return policies.reduce<APPolicy | null>((latest, policy) => {
    if (!policy.updated_at || Number.isNaN(new Date(policy.updated_at).getTime())) {
      return latest
    }
    if (!latest || !latest.updated_at) return policy
    return new Date(policy.updated_at).getTime() > new Date(latest.updated_at).getTime()
      ? policy
      : latest
  }, null)
}

function SummaryItem({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className='min-w-0 px-5 py-4'>
      <p className='text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400'>
        {label}
      </p>
      <div className='mt-2 min-h-7 text-sm font-semibold text-white'>{children}</div>
    </div>
  )
}

export function PolicySummary({
  policies,
  total,
  snapshotLabel,
}: {
  policies: APPolicy[]
  total: number
  snapshotLabel: string
}) {
  const activePolicies = policies.filter((policy) => policy.active).length
  const latest = latestUpdatedPolicy(policies)

  return (
    <section aria-label='Policy summary'>
      <Card className='overflow-hidden border-slate-800 bg-slate-950 shadow-soft hover:translate-y-0'>
        <CardContent className='grid divide-y divide-white/10 p-0 sm:grid-cols-2 sm:divide-x sm:divide-y-0 xl:grid-cols-4'>
          <SummaryItem label='Total policies'>
            <span className='font-mono text-3xl tracking-tight'>{total}</span>
          </SummaryItem>
          <SummaryItem label='Active policies'>
            <span className='font-mono text-3xl tracking-tight'>{activePolicies}</span>
          </SummaryItem>
          <SummaryItem label='Snapshot'>{snapshotLabel}</SummaryItem>
          <SummaryItem label='Most recently updated'>
            {latest?.updated_at ? (
              <>
                <span className='block truncate'>{latest.name}</span>
                <time
                  className='mt-1 block text-xs font-medium text-slate-400'
                  dateTime={latest.updated_at}
                >
                  {formatPolicyTimestamp(latest.updated_at)}
                </time>
              </>
            ) : (
              <span className='text-slate-400'>No policy updates are recorded</span>
            )}
          </SummaryItem>
        </CardContent>
      </Card>
    </section>
  )
}
