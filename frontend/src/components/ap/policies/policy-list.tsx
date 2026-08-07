import type { ReactNode } from 'react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatPolicyValue } from '@/lib/ap-policies'
import { cn } from '@/lib/utils'
import type { APPolicy, APPolicySeverity } from '@/types/ap-policies'

const SEVERITY_PRESENTATION: Record<
  APPolicySeverity,
  { label: string; className: string }
> = {
  block: {
    label: 'Block',
    className: 'border-rose-200 bg-rose-50 text-rose-800',
  },
  escalate: {
    label: 'Escalate',
    className: 'border-amber-200 bg-amber-50 text-amber-800',
  },
  advise: {
    label: 'Advise',
    className: 'border-sky-200 bg-sky-50 text-sky-800',
  },
}

function formatPolicyTimestamp(value: string | null): string {
  if (!value) return 'Not recorded'

  const timestamp = new Date(value)
  if (Number.isNaN(timestamp.getTime())) return 'Not recorded'

  return new Intl.DateTimeFormat('en-MY', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(timestamp)
}

function PolicyField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className='text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500'>
        {label}
      </dt>
      <dd className='mt-1 break-words text-sm font-medium text-slate-900'>{children}</dd>
    </div>
  )
}

function PolicyCard({ policy }: { policy: APPolicy }) {
  const severity = SEVERITY_PRESENTATION[policy.severity]

  return (
    <article aria-label={`${policy.name} policy`}>
      <Card className='h-full overflow-hidden hover:translate-y-0'>
        <CardHeader className='border-b border-slate-200 pb-4'>
          <div className='flex flex-wrap items-start justify-between gap-3'>
            <div>
              <p className='font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-brand-cornflower'>
                {policy.key}
              </p>
              <CardTitle className='mt-2'>{policy.name}</CardTitle>
            </div>
            <div className='flex flex-wrap items-center gap-2'>
              <span
                className={cn(
                  'rounded-full border px-2.5 py-1 text-xs font-semibold',
                  severity.className
                )}
              >
                {severity.label}
              </span>
              <span
                className={cn(
                  'rounded-full border px-2.5 py-1 text-xs font-semibold',
                  policy.active
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                    : 'border-slate-200 bg-slate-100 text-slate-700'
                )}
              >
                {policy.active ? 'Active' : 'Inactive'}
              </span>
            </div>
          </div>
          <CardDescription className='pt-2 leading-6'>
            {policy.description}
          </CardDescription>
        </CardHeader>

        <CardContent className='space-y-5 pt-5'>
          <dl className='grid gap-x-5 gap-y-4 sm:grid-cols-2 lg:grid-cols-3'>
            <PolicyField label='Current value'>
              <span className='font-mono'>{formatPolicyValue(policy)}</span>
            </PolicyField>
            <PolicyField label='Value type'>{policy.value_type}</PolicyField>
            <PolicyField label='Version'>{policy.version}</PolicyField>
          </dl>

          <dl className='grid gap-x-5 gap-y-4 border-t border-slate-200 pt-4 sm:grid-cols-2'>
            <PolicyField label='Updated by'>
              {policy.updated_by ?? 'Not recorded'}
            </PolicyField>
            <PolicyField label='Updated at'>
              {policy.updated_at ? (
                <time dateTime={policy.updated_at}>
                  {formatPolicyTimestamp(policy.updated_at)}
                </time>
              ) : (
                'Not recorded'
              )}
            </PolicyField>
          </dl>
        </CardContent>
      </Card>
    </article>
  )
}

export function PolicyList({ policies }: { policies: APPolicy[] }) {
  return (
    <div className='grid gap-4 xl:grid-cols-2'>
      {policies.map((policy) => (
        <PolicyCard key={policy.key} policy={policy} />
      ))}
    </div>
  )
}
