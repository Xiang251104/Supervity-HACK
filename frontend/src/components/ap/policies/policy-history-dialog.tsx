'use client'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { formatPolicyValue } from '@/lib/ap-policies'
import type { APPolicy, APPolicyValue, APPolicyVersion } from '@/types/ap-policies'

type PolicyHistoryDialogProps = {
  policy: APPolicy | null
  open: boolean
  items: APPolicyVersion[]
  loading: boolean
  error: string | null
  onOpenChange: (open: boolean) => void
  onRetry: () => void
}

function formatPolicyTimestamp(value: string): string {
  const timestamp = new Date(value)
  if (Number.isNaN(timestamp.getTime())) return value

  return new Intl.DateTimeFormat('en-MY', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(timestamp)
}

function formatHistoryValue(policy: APPolicy, value: APPolicyValue | null): string {
  if (value === null) return 'Not recorded'

  return formatPolicyValue({ value, unit: policy.unit })
}

export function PolicyHistoryDialog({
  policy,
  open,
  items,
  loading,
  error,
  onOpenChange,
  onRetry,
}: PolicyHistoryDialogProps) {
  if (!policy) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='max-h-[85vh] overflow-y-auto sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>History for {policy.name}</DialogTitle>
          <DialogDescription>
            Server-recorded changes for <span className='font-mono'>{policy.key}</span>.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className='py-8 text-center text-sm text-brand-muted' role='status'>
            Loading policy historyâ€¦
          </div>
        ) : null}

        {error ? (
          <div role='alert' className='rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900'>
            <p>{error}</p>
            <Button
              type='button'
              className='mt-3'
              size='sm'
              variant='outline'
              onClick={onRetry}
              aria-label='Retry loading policy history'
            >
              Retry
            </Button>
          </div>
        ) : null}

        {!loading && !error && items.length === 0 ? (
          <p className='rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center text-sm text-brand-muted'>
            No policy history is available
          </p>
        ) : null}

        {!loading && !error && items.length > 0 ? (
          <ol className='space-y-3' aria-label={`${policy.name} history entries`}>
            {items.map((item) => (
              <li key={`${item.version}-${item.changed_at}`} className='rounded-xl border border-slate-200 bg-slate-50 p-4'>
                <div className='flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1'>
                  <h3 className='font-semibold text-brand-navy'>Version {item.version}</h3>
                  <time className='text-xs text-brand-muted' dateTime={item.changed_at}>
                    {formatPolicyTimestamp(item.changed_at)}
                  </time>
                </div>
                <dl className='mt-3 grid gap-x-5 gap-y-3 sm:grid-cols-2'>
                  <div>
                    <dt className='text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500'>
                      Previous value
                    </dt>
                    <dd className='mt-1 break-words font-mono text-sm text-slate-900'>
                      {formatHistoryValue(policy, item.previous_value)}
                    </dd>
                  </div>
                  <div>
                    <dt className='text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500'>
                      New value
                    </dt>
                    <dd className='mt-1 break-words font-mono text-sm text-slate-900'>
                      {formatHistoryValue(policy, item.value)}
                    </dd>
                  </div>
                  <div>
                    <dt className='text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500'>
                      Changed by
                    </dt>
                    <dd className='mt-1 break-words text-sm text-slate-900'>
                      {item.changed_by ?? 'Not recorded'}
                    </dd>
                  </div>
                  {item.note ? (
                    <div>
                      <dt className='text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500'>
                        Note
                      </dt>
                      <dd className='mt-1 break-words text-sm text-slate-900'>{item.note}</dd>
                    </div>
                  ) : null}
                </dl>
              </li>
            ))}
          </ol>
        ) : null}

        <DialogFooter>
          <Button type='button' variant='outline' onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
