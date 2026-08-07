'use client'

import { FormEvent, ReactNode, useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { formatPolicyValue, validatePolicyValue } from '@/lib/ap-policies'
import type { APEnumPolicy, APPolicy, APPolicyValue } from '@/types/ap-policies'

type PolicyEditDialogProps = {
  policy: APPolicy | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSave: (policy: APPolicy, value: APPolicyValue, note: string) => Promise<void>
  onSaved: () => void
}

function hasStringEnumOptions(policy: APPolicy): policy is APEnumPolicy & { options: string[] } {
  return (
    policy.value_type === 'enum' &&
    Array.isArray(policy.options) &&
    policy.options.length > 0 &&
    policy.options.every((option) => typeof option === 'string')
  )
}

function PolicyMetadataField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className='text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500'>
        {label}
      </dt>
      <dd className='mt-1 break-words text-sm text-slate-800'>{children}</dd>
    </div>
  )
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

export function PolicyEditDialog({
  policy,
  open,
  onOpenChange,
  onSave,
  onSaved,
}: PolicyEditDialogProps) {
  const [rawValue, setRawValue] = useState<APPolicyValue | string>('')
  const [note, setNote] = useState('')
  const [valueError, setValueError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (policy && open) {
      setRawValue(policy.value)
      setNote('')
      setValueError(null)
      setSaveError(null)
      setSaving(false)
    }
  }, [open, policy])

  if (!policy) return null

  const enumOptionsAreValid = hasStringEnumOptions(policy)
  const enumOptions: string[] | null = hasStringEnumOptions(policy)
    ? policy.options
    : null
  const valueErrorId = 'policy-value-error'

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (saving) return

    const result = validatePolicyValue(policy, rawValue)
    if (!result.valid) {
      setValueError(result.error)
      setSaveError(null)
      return
    }

    setValueError(null)
    setSaveError(null)
    setSaving(true)
    try {
      await onSave(policy, result.value, note)
      onOpenChange(false)
      onSaved()
    } catch (caught) {
      setSaveError(caught instanceof Error ? caught.message : 'Policy could not be saved.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!saving) onOpenChange(nextOpen)
      }}
    >
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>Edit {policy.name}</DialogTitle>
          <DialogDescription>
            Update this policy&apos;s current value. Other policy metadata is managed by the policy service.
          </DialogDescription>
        </DialogHeader>

        <form className='space-y-5' noValidate onSubmit={handleSubmit}>
          <section aria-label='Policy details' className='rounded-lg border border-slate-200 bg-slate-50 p-4'>
            <h3 className='text-sm font-semibold text-brand-navy'>Policy details</h3>
            <dl className='mt-3 grid gap-x-4 gap-y-3 sm:grid-cols-2'>
              <PolicyMetadataField label='Key'>{policy.key}</PolicyMetadataField>
              <PolicyMetadataField label='Value type'>{policy.value_type}</PolicyMetadataField>
              <PolicyMetadataField label='Description'>{policy.description}</PolicyMetadataField>
              <PolicyMetadataField label='Current server value'>
                <span className='font-mono'>{formatPolicyValue(policy)}</span>
              </PolicyMetadataField>
              <PolicyMetadataField label='Severity'>{policy.severity}</PolicyMetadataField>
              <PolicyMetadataField label='Status'>{policy.active ? 'Active' : 'Inactive'}</PolicyMetadataField>
              <PolicyMetadataField label='Version'>{policy.version}</PolicyMetadataField>
              <PolicyMetadataField label='Updated by'>{policy.updated_by ?? 'Not recorded'}</PolicyMetadataField>
              <PolicyMetadataField label='Updated at'>
                {policy.updated_at ? (
                  <time dateTime={policy.updated_at}>
                    {formatPolicyTimestamp(policy.updated_at)}
                  </time>
                ) : (
                  'Not recorded'
                )}
              </PolicyMetadataField>
            </dl>
          </section>

          <div className='space-y-2'>
            <Label htmlFor='policy-value'>Policy value</Label>
            {policy.value_type === 'number' ? (
              <Input
                id='policy-value'
                type='number'
                step='any'
                value={String(rawValue)}
                onChange={(event) => setRawValue(event.target.value)}
                aria-describedby={valueError ? valueErrorId : undefined}
                disabled={saving}
              />
            ) : null}
            {policy.value_type === 'enum' && enumOptions ? (
              <select
                id='policy-value'
                value={String(rawValue)}
                onChange={(event) => setRawValue(event.target.value)}
                aria-describedby={valueError ? valueErrorId : undefined}
                disabled={saving}
                className='flex h-10 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-cornflower disabled:cursor-not-allowed disabled:opacity-50'
              >
                {enumOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            ) : null}
            {policy.value_type === 'enum' && !enumOptionsAreValid ? (
              <p className='text-sm text-rose-700' role='alert'>
                Available enum options are unavailable.
              </p>
            ) : null}
            {policy.value_type === 'boolean' ? (
              <Switch
                id='policy-value'
                aria-label='Policy value'
                checked={rawValue === true}
                onCheckedChange={setRawValue}
                disabled={saving}
              />
            ) : null}
            {policy.value_type === 'date' ? (
              <Input
                id='policy-value'
                type='date'
                value={String(rawValue)}
                onChange={(event) => setRawValue(event.target.value)}
                aria-describedby={valueError ? valueErrorId : undefined}
                disabled={saving}
              />
            ) : null}
            {valueError ? (
              <p id={valueErrorId} className='text-sm text-rose-700' role='alert'>
                {valueError}
              </p>
            ) : null}
          </div>

          <div className='space-y-2'>
            <Label htmlFor='policy-note'>Change note <span className='text-slate-500'>(optional)</span></Label>
            <textarea
              id='policy-note'
              value={note}
              onChange={(event) => setNote(event.target.value)}
              disabled={saving}
              className='min-h-20 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-cornflower disabled:cursor-not-allowed disabled:opacity-50'
            />
          </div>

          {saveError ? <p className='text-sm text-rose-700' role='alert'>{saveError}</p> : null}

          <DialogFooter>
            <Button type='button' variant='outline' disabled={saving} onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type='submit' disabled={saving} aria-label={saving ? 'Saving policy' : 'Save policy'}>
              {saving ? 'Saving…' : 'Save policy'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
