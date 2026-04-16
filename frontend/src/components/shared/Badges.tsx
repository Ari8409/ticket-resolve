import React from 'react'

type Severity = 'info' | 'minor' | 'medium' | 'low' | 'major' | 'high' | 'critical' | string
type Status =
  | 'open'
  | 'assigned'
  | 'in_progress'
  | 'pending_review'
  | 'pending'
  | 'cleared'
  | 'resolved'
  | 'closed'
  | 'escalated'
  | 'failed'
  | string

const severityStyles: Record<string, string> = {
  critical: 'bg-red-500/20 text-red-400 border border-red-500/30',
  high: 'bg-orange-500/20 text-orange-400 border border-orange-500/30',
  major: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  medium: 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30',
  minor: 'bg-blue-500/20 text-blue-400 border border-blue-500/30',
  low: 'bg-slate-500/20 text-slate-400 border border-slate-500/30',
  info: 'bg-slate-500/20 text-slate-400 border border-slate-500/30',
}

const statusStyles: Record<string, string> = {
  open: 'bg-blue-500/20 text-blue-400 border border-blue-500/30',
  assigned: 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30',
  in_progress: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  pending_review: 'bg-red-500/20 text-red-400 border border-red-500/30',
  pending: 'bg-orange-500/20 text-orange-400 border border-orange-500/30',
  cleared: 'bg-teal-500/20 text-teal-400 border border-teal-500/30',
  resolved: 'bg-green-500/20 text-green-400 border border-green-500/30',
  closed: 'bg-slate-500/20 text-slate-400 border border-slate-500/30',
  escalated: 'bg-orange-500/20 text-orange-400 border border-orange-500/30',
  failed: 'bg-red-900/30 text-red-400 border border-red-800/30',
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  const style = severityStyles[severity] ?? severityStyles.low
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${style}`}>
      {severity.charAt(0).toUpperCase() + severity.slice(1)}
    </span>
  )
}

export function StatusBadge({ status }: { status: Status }) {
  const style = statusStyles[status] ?? statusStyles.open
  const label = status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${style}`}>
      {label}
    </span>
  )
}
