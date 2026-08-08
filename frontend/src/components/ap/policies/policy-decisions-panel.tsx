'use client'

/**
 * The policy gate, shown to the person it acted on.
 *
 * The backend already records one row per policy per run, fired or not, with the
 * threshold it used, what it observed and why it concluded what it did. Until this
 * panel existed that record reached the database and the API and stopped there —
 * the Workbench showed a version label like `v3.3.1.1.2` and nothing else, so the
 * one claim that matters most about this system (rules are applied before anything
 * happens, and every application is recorded) was invisible to the people it was
 * meant to reassure.
 *
 * Two deliberate choices:
 *
 *   * Rules that did nothing are still listed. A gate you only see when it fires
 *     is indistinguishable from a gate that only runs when it fires.
 *   * Policy keys never appear. `MIN-CONFIDENCE` is a database key; the reviewer
 *     reads "Minimum reading confidence", the same words the AI Policies page and
 *     the insights use.
 */

import { ShieldAlert, ShieldCheck } from 'lucide-react'

import { cn } from '@/lib/utils'
import {
  policyInfo,
  policyOutcomeLabel,
  policyValueLabel,
  reasonLabel,
} from '@/lib/ap-language'
import type { APPolicyEvaluation } from '@/types/ap-policies'

/** Narrow untyped `context` JSON to the rows we can actually render. */
export function parsePolicyEvaluations(value: unknown): APPolicyEvaluation[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((entry) => {
    if (!entry || typeof entry !== 'object') return []
    const row = entry as Record<string, unknown>
    if (typeof row.policy_key !== 'string' || !row.policy_key) return []
    return [
      {
        policy_key: row.policy_key,
        policy_version: typeof row.policy_version === 'number' ? row.policy_version : 0,
        threshold_value: row.threshold_value ?? null,
        observed_value: row.observed_value ?? null,
        fired: row.fired === true,
        outcome: typeof row.outcome === 'string' ? row.outcome : null,
        explanation: typeof row.explanation === 'string' ? row.explanation : null,
      },
    ]
  })
}

/**
 * Render a threshold or observation in the reviewer's language.
 *
 * Observed values are the loosest data on the page: a number for a confidence, a
 * list of reason codes for the bank rule, sometimes nothing at all. Codes are
 * humanised here too — a raw `BANK_MISMATCH` leaking through this panel would
 * undo the vocabulary work everywhere else.
 */
export function formatPolicyValue(value: unknown): string | null {
  if (value === null || value === undefined || value === '') return null
  if (Array.isArray(value)) {
    const parts = value
      .filter((entry) => entry !== null && entry !== undefined && entry !== '')
      .map((entry) => (typeof entry === 'string' ? reasonLabel(entry) : String(entry)))
    return parts.length ? parts.join(', ') : null
  }
  if (typeof value === 'object') {
    const parts = Object.entries(value as Record<string, unknown>)
      .filter(([, entry]) => entry !== null && entry !== undefined && entry !== '')
      .map(([key, entry]) => `${reasonLabel(key)}: ${String(entry)}`)
    return parts.length ? parts.join(' · ') : null
  }
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return policyValueLabel(value)
}

export function PolicyDecisionsPanel({
  evaluations,
  className,
}: {
  evaluations: APPolicyEvaluation[]
  className?: string
}) {
  if (!evaluations.length) {
    return (
      <p className='text-sm text-slate-500'>
        No policy record was attached to this decision.
      </p>
    )
  }

  // Rules that acted come first; the rest keep the order the gate ran them in, so
  // the list reads the same way twice for anyone comparing two invoices.
  const ordered = [...evaluations].sort((a, b) => Number(b.fired) - Number(a.fired))
  const actedCount = evaluations.filter((row) => row.fired).length

  return (
    <div className={className}>
      <p className='text-sm leading-6 text-slate-600'>
        {evaluations.length === 1 ? '1 rule was' : `${evaluations.length} rules were`}{' '}
        applied to this invoice before it could be paid, alerted on, or sent to you.{' '}
        {actedCount === 0
          ? 'None of them changed the outcome.'
          : actedCount === 1
            ? '1 of them changed the outcome.'
            : `${actedCount} of them changed the outcome.`}
      </p>

      <ul className='mt-4 divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white'>
        {ordered.map((row) => {
          const info = policyInfo(row.policy_key)
          const threshold = formatPolicyValue(row.threshold_value)
          const observed = formatPolicyValue(row.observed_value)
          const Icon = row.fired ? ShieldAlert : ShieldCheck
          const tone = row.fired ? 'text-amber-600' : 'text-emerald-600'

          return (
            <li key={row.policy_key} className='flex gap-3 px-4 py-3'>
              <Icon aria-hidden='true' className={cn('mt-0.5 h-5 w-5 shrink-0', tone)} />
              <div className='min-w-0 flex-1'>
                <p className='text-sm font-semibold text-slate-900'>
                  {info.name}
                  {row.outcome ? (
                    <span className={cn('ml-2 text-xs font-medium', tone)}>
                      {policyOutcomeLabel(row.outcome)}
                    </span>
                  ) : null}
                </p>

                {row.explanation ? (
                  <p className='mt-0.5 text-sm leading-6 text-slate-600'>{row.explanation}</p>
                ) : info.asks ? (
                  <p className='mt-0.5 text-sm leading-6 text-slate-600'>{info.asks}</p>
                ) : null}

                {threshold || observed ? (
                  <p className='mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500'>
                    {threshold ? (
                      <span>
                        Setting used:{' '}
                        <span className='font-medium text-slate-700'>{threshold}</span>
                      </span>
                    ) : null}
                    {observed ? (
                      <span>
                        Found on this invoice:{' '}
                        <span className='font-medium text-slate-700'>{observed}</span>
                      </span>
                    ) : null}
                  </p>
                ) : null}
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
