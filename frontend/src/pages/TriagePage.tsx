import React, { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, X, CheckCircle2, UserPlus, History, ArrowRight, BarChart2, Network, Zap, AlertTriangle, Filter } from 'lucide-react'
import { api, TriageSummary, AuditLogEntry } from '../api/client'
import { SeverityBadge } from '../components/shared/Badges'
import { TableRowSkeleton } from '../components/shared/Skeleton'
import { useToast } from '../components/shared/Toast'

interface TriagePageProps {
  autoRefresh: boolean
}

// ─── Reason Chip ───────────────────────────────────────────────────────────────

// Keys must match UnresolvableReason enum values from the API:
//   no_sop_match | no_historical_precedent | low_confidence | unknown_fault_type
const REASON_LABELS: Record<string, string> = {
  no_sop_match:            'No SOP',
  no_historical_precedent: 'No History',
  low_confidence:          'Low Confidence',
  unknown_fault_type:      'Unknown Fault',
}

function ReasonChip({ reason }: { reason: string }) {
  const label = REASON_LABELS[reason] ?? reason.replace(/_/g, ' ')
  const colorMap: Record<string, string> = {
    no_sop_match:            'bg-red-500/10 text-red-400 border-red-500/20',
    no_historical_precedent: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    low_confidence:          'bg-amber-500/10 text-amber-400 border-amber-500/20',
    unknown_fault_type:      'bg-orange-500/10 text-orange-400 border-orange-500/20',
  }
  const style = colorMap[reason] ?? 'bg-slate-500/10 text-slate-400 border-slate-500/20'
  return (
    <span className={`inline-flex px-1.5 py-0.5 rounded text-xs border ${style} whitespace-nowrap`}>
      {label}
    </span>
  )
}

// ─── Confidence Bar ────────────────────────────────────────────────────────────

function ConfidenceBar({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color =
    pct >= 75 ? 'bg-green-500' : pct >= 50 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2 min-w-[80px]">
      <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-slate-400 w-8 text-right">{pct}%</span>
    </div>
  )
}

// ─── Relative Time ─────────────────────────────────────────────────────────────

function relativeTime(isoString: string): string {
  const diff = Date.now() - new Date(isoString).getTime()
  const minutes = Math.floor(diff / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

// ─── Assign Modal ──────────────────────────────────────────────────────────────

interface AssignModalProps {
  ticket: TriageSummary
  onClose: () => void
}

function AssignModal({ ticket, onClose }: AssignModalProps) {
  const [assignTo, setAssignTo] = useState('')
  const [notes, setNotes] = useState('')
  const { showToast } = useToast()
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => api.assignTicket(ticket.ticket_id, { assign_to: assignTo, notes: notes || undefined }),
    onSuccess: () => {
      showToast(`Ticket ${ticket.ticket_id} assigned to ${assignTo}`, 'success')
      queryClient.invalidateQueries({ queryKey: ['pending-review'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
      onClose()
    },
    onError: () => showToast('Failed to assign ticket', 'error'),
  })

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-slate-800 rounded-2xl border border-slate-700 w-full max-w-md p-6 shadow-2xl">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-base font-semibold text-white">Assign Ticket</h2>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">{ticket.ticket_id}</p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">
              Engineer / Group <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={assignTo}
              onChange={(e) => setAssignTo(e.target.value)}
              placeholder="e.g. john.doe or NOC-Team-A"
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Notes (optional)</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder="Any additional context..."
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors resize-none"
            />
          </div>
        </div>

        <div className="flex gap-3 mt-6">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 text-sm text-slate-400 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={!assignTo.trim() || mutation.isPending}
            className="flex-1 px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors font-medium"
          >
            {mutation.isPending ? 'Assigning...' : 'Assign Ticket'}
          </button>
        </div>
      </div>
    </ModalOverlay>
  )
}

// ─── Resolve Modal ─────────────────────────────────────────────────────────────

const RESOLUTION_CODES = [
  'Hardware Replacement',
  'Software Update',
  'Configuration Change',
  'Restart',
  'Physical Inspection',
  'Other',
]

interface ResolveModalProps {
  ticket: TriageSummary
  onClose: () => void
}

function ResolveModal({ ticket, onClose }: ResolveModalProps) {
  const [resolvedBy, setResolvedBy] = useState('NOC Engineer')
  const [stepsRaw, setStepsRaw] = useState('')
  const [sopRef, setSopRef] = useState('')
  const [cause, setCause] = useState('')
  const [resCode, setResCode] = useState('Other')
  const [notes, setNotes] = useState('')
  const { showToast } = useToast()
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () =>
      api.manualResolve(ticket.ticket_id, {
        resolved_by: resolvedBy,
        resolution_steps: stepsRaw
          .split('\n')
          .map((s) => s.trim())
          .filter(Boolean),
        sop_reference: sopRef || undefined,
        primary_cause: cause || undefined,
        resolution_code: resCode,
        notes: notes || undefined,
      }),
    onSuccess: () => {
      showToast(`Ticket ${ticket.ticket_id} resolved successfully`, 'success')
      queryClient.invalidateQueries({ queryKey: ['pending-review'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
      queryClient.invalidateQueries({ queryKey: ['tickets'] })
      onClose()
    },
    onError: () => showToast('Failed to resolve ticket', 'error'),
  })

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-slate-800 rounded-2xl border border-slate-700 w-full max-w-lg p-6 shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-base font-semibold text-white">Manual Resolve</h2>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">{ticket.ticket_id}</p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">
              Resolved By <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={resolvedBy}
              onChange={(e) => setResolvedBy(e.target.value)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">
              Resolution Steps <span className="text-red-400">*</span>
              <span className="text-slate-500 font-normal ml-1">(one per line)</span>
            </label>
            <textarea
              value={stepsRaw}
              onChange={(e) => setStepsRaw(e.target.value)}
              rows={4}
              placeholder="Step 1: Checked logs&#10;Step 2: Restarted service&#10;Step 3: Verified connectivity"
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors resize-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">SOP Reference</label>
              <input
                type="text"
                value={sopRef}
                onChange={(e) => setSopRef(e.target.value)}
                placeholder="e.g. SOP-123"
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Primary Cause</label>
              <input
                type="text"
                value={cause}
                onChange={(e) => setCause(e.target.value)}
                placeholder="e.g. Hardware failure"
                className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Resolution Code</label>
            <select
              value={resCode}
              onChange={(e) => setResCode(e.target.value)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 transition-colors"
            >
              {RESOLUTION_CODES.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder="Additional notes..."
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors resize-none"
            />
          </div>
        </div>

        <div className="flex gap-3 mt-6">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 text-sm text-slate-400 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={!resolvedBy.trim() || !stepsRaw.trim() || mutation.isPending}
            className="flex-1 px-4 py-2 text-sm text-white bg-green-600 hover:bg-green-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors font-medium"
          >
            {mutation.isPending ? 'Resolving...' : 'Mark Resolved'}
          </button>
        </div>
      </div>
    </ModalOverlay>
  )
}

// ─── Audit Timeline ────────────────────────────────────────────────────────────

const EVENT_LABELS: Record<string, string> = {
  status_change: 'Status Change',
  assignment:    'Assignment',
  flag_review:   'Flagged for Review',
  escalation:    'Escalation',
  resolution:    'Resolution',
}

const EVENT_COLORS: Record<string, string> = {
  status_change: 'bg-blue-500',
  assignment:    'bg-violet-500',
  flag_review:   'bg-amber-500',
  escalation:    'bg-red-500',
  resolution:    'bg-green-500',
}

function AuditTimelineModal({ ticketId, onClose }: { ticketId: string; onClose: () => void }) {
  const { data: entries, isLoading } = useQuery({
    queryKey: ['audit-log', ticketId],
    queryFn: () => api.getAuditLog(ticketId),
  })

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-slate-800 rounded-2xl border border-slate-700 w-full max-w-lg p-6 shadow-2xl max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-base font-semibold text-white flex items-center gap-2">
              <History className="w-4 h-4 text-violet-400" />
              Audit Trail
            </h2>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">{ticketId}</p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center py-12 text-slate-500 text-sm">
              Loading audit trail...
            </div>
          ) : !entries || entries.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <History className="w-10 h-10 text-slate-600 mb-3" />
              <p className="text-slate-400 text-sm">No audit entries yet.</p>
              <p className="text-slate-500 text-xs mt-1">
                Audit rows are created when this ticket is triage-flagged, assigned, or resolved.
              </p>
            </div>
          ) : (
            <ol className="relative border-l border-slate-700 ml-3 space-y-5 pb-2">
              {entries.map((entry) => (
                <li key={entry.id} className="ml-5">
                  <span
                    className={`absolute -left-[9px] flex w-4 h-4 rounded-full items-center justify-center ring-2 ring-slate-800 ${
                      EVENT_COLORS[entry.event_type] ?? 'bg-slate-500'
                    }`}
                  />
                  <div className="bg-slate-700/40 border border-slate-700 rounded-lg px-4 py-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-semibold text-white">
                        {EVENT_LABELS[entry.event_type] ?? entry.event_type}
                      </span>
                      <span className="text-xs text-slate-500">
                        {new Date(entry.created_at).toLocaleString()}
                      </span>
                    </div>
                    {entry.from_status && entry.to_status && (
                      <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
                        <span className="font-mono bg-slate-700 px-1.5 py-0.5 rounded">
                          {entry.from_status}
                        </span>
                        <ArrowRight className="w-3 h-3 text-slate-600" />
                        <span className="font-mono bg-slate-700 px-1.5 py-0.5 rounded">
                          {entry.to_status}
                        </span>
                      </div>
                    )}
                    {entry.changed_by && (
                      <p className="text-xs text-slate-500">
                        Actor: <span className="text-slate-400">{entry.changed_by}</span>
                      </p>
                    )}
                    {entry.reason && (
                      <p className="text-xs text-slate-500 mt-0.5 truncate max-w-xs" title={entry.reason}>
                        Reason: {entry.reason.startsWith('[') ? JSON.parse(entry.reason).join(', ') : entry.reason}
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </ModalOverlay>
  )
}

// ─── Triage Analytics Dashboard ───────────────────────────────────────────────

const SEVERITY_ORDER = ['critical', 'major', 'high', 'medium', 'minor', 'low', 'info']
const SEVERITY_COLORS: Record<string, string> = {
  critical: '#ef4444',
  major:    '#f97316',
  high:     '#f97316',
  medium:   '#eab308',
  minor:    '#3b82f6',
  low:      '#6366f1',
  info:     '#64748b',
}
const NETWORK_COLORS: Record<string, string> = {
  '5G': '#22d3ee',
  '4G': '#a78bfa',
  '3G': '#34d399',
}
const FAULT_COLOR = '#818cf8'

function MiniBar({ label, count, total, color, active, onClick }: {
  label: string; count: number; total: number; color: string
  active: boolean; onClick: () => void
}) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0
  return (
    <button
      onClick={onClick}
      className={`w-full text-left group transition-all rounded-lg px-3 py-1.5 ${
        active ? 'bg-slate-700 ring-1 ring-slate-500' : 'hover:bg-slate-700/50'
      }`}
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-slate-300 truncate max-w-[120px]" title={label}>
          {label}
        </span>
        <span className="text-xs font-semibold text-slate-200 ml-2">{count}</span>
      </div>
      <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </button>
  )
}

interface TriageFilters {
  network: string | null
  severity: string | null
  faultType: string | null
}

function TriageAnalytics({
  tickets,
  filters,
  onFilter,
}: {
  tickets: TriageSummary[]
  filters: TriageFilters
  onFilter: (f: Partial<TriageFilters>) => void
}) {
  const total = tickets.length

  // Network breakdown
  const byNetwork = useMemo(() => {
    const map: Record<string, number> = {}
    tickets.forEach(t => {
      const k = t.network_type ?? 'Unknown'
      map[k] = (map[k] ?? 0) + 1
    })
    return Object.entries(map).sort((a, b) => b[1] - a[1])
  }, [tickets])

  // Severity breakdown (ordered)
  const bySeverity = useMemo(() => {
    const map: Record<string, number> = {}
    tickets.forEach(t => { map[t.severity] = (map[t.severity] ?? 0) + 1 })
    return SEVERITY_ORDER
      .filter(s => map[s])
      .map(s => [s, map[s]] as [string, number])
  }, [tickets])

  // Fault type breakdown (top 8)
  const byFault = useMemo(() => {
    const map: Record<string, number> = {}
    tickets.forEach(t => { map[t.fault_type] = (map[t.fault_type] ?? 0) + 1 })
    return Object.entries(map).sort((a, b) => b[1] - a[1]).slice(0, 8)
  }, [tickets])

  const hasActiveFilter = filters.network || filters.severity || filters.faultType

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-slate-700/50">
        <div className="flex items-center gap-2">
          <BarChart2 className="w-4 h-4 text-slate-400" />
          <span className="text-sm font-semibold text-slate-300">Queue Analytics</span>
          <span className="text-xs text-slate-500 ml-1">— {total} tickets</span>
        </div>
        {hasActiveFilter && (
          <button
            onClick={() => onFilter({ network: null, severity: null, faultType: null })}
            className="flex items-center gap-1.5 px-2.5 py-1 text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 hover:bg-amber-500/20 rounded-lg transition-colors"
          >
            <Filter className="w-3 h-3" />
            Clear filters
          </button>
        )}
      </div>

      {/* Three-column breakdown */}
      <div className="grid grid-cols-3 divide-x divide-slate-700/50">
        {/* Network */}
        <div className="px-4 py-3">
          <div className="flex items-center gap-1.5 mb-3">
            <Network className="w-3.5 h-3.5 text-cyan-400" />
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Network</span>
          </div>
          <div className="space-y-1">
            {byNetwork.map(([k, v]) => (
              <MiniBar
                key={k}
                label={k}
                count={v}
                total={total}
                color={NETWORK_COLORS[k] ?? '#64748b'}
                active={filters.network === k}
                onClick={() => onFilter({ network: filters.network === k ? null : k })}
              />
            ))}
          </div>
        </div>

        {/* Severity */}
        <div className="px-4 py-3">
          <div className="flex items-center gap-1.5 mb-3">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Severity</span>
          </div>
          <div className="space-y-1">
            {bySeverity.map(([k, v]) => (
              <MiniBar
                key={k}
                label={k.charAt(0).toUpperCase() + k.slice(1)}
                count={v}
                total={total}
                color={SEVERITY_COLORS[k] ?? '#64748b'}
                active={filters.severity === k}
                onClick={() => onFilter({ severity: filters.severity === k ? null : k })}
              />
            ))}
          </div>
        </div>

        {/* Fault Type */}
        <div className="px-4 py-3">
          <div className="flex items-center gap-1.5 mb-3">
            <Zap className="w-3.5 h-3.5 text-violet-400" />
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Fault Type</span>
          </div>
          <div className="space-y-1">
            {byFault.map(([k, v]) => (
              <MiniBar
                key={k}
                label={k.replace(/_/g, ' ')}
                count={v}
                total={total}
                color={FAULT_COLOR}
                active={filters.faultType === k}
                onClick={() => onFilter({ faultType: filters.faultType === k ? null : k })}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Modal Overlay ─────────────────────────────────────────────────────────────

function ModalOverlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      {children}
    </div>
  )
}

// ─── Main Component ────────────────────────────────────────────────────────────

export default function TriagePage({ autoRefresh }: TriagePageProps) {
  const [assignTarget, setAssignTarget] = useState<TriageSummary | null>(null)
  const [resolveTarget, setResolveTarget] = useState<TriageSummary | null>(null)
  const [auditTarget, setAuditTarget] = useState<string | null>(null)
  const [filters, setFilters] = useState<TriageFilters>({ network: null, severity: null, faultType: null })

  const {
    data: tickets,
    isLoading,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['pending-review'],
    queryFn: () => api.getPendingReview(500),
    refetchInterval: autoRefresh ? 30_000 : false,
  })

  const { showToast } = useToast()

  React.useEffect(() => {
    if (error) showToast('Failed to load triage queue', 'error')
  }, [error, showToast])

  const filteredTickets = useMemo(() => {
    if (!tickets) return []
    return tickets.filter(t => {
      if (filters.network   && (t.network_type ?? 'Unknown') !== filters.network)  return false
      if (filters.severity  && t.severity  !== filters.severity)                    return false
      if (filters.faultType && t.fault_type !== filters.faultType)                  return false
      return true
    })
  }, [tickets, filters])

  const handleFilter = (patch: Partial<TriageFilters>) =>
    setFilters(prev => ({ ...prev, ...patch }))

  const activeFilterCount = [filters.network, filters.severity, filters.faultType].filter(Boolean).length

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-white">Triage Queue</h2>
          {tickets !== undefined && (
            <span
              className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold ${
                tickets.length > 0
                  ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                  : 'bg-green-500/20 text-green-400 border border-green-500/30'
              }`}
            >
              {tickets.length}
            </span>
          )}
          {activeFilterCount > 0 && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/20 text-amber-400 border border-amber-500/30">
              {filteredTickets.length} shown
            </span>
          )}
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-2 px-3 py-1.5 text-xs text-slate-400 bg-slate-800 border border-slate-700 hover:bg-slate-700 rounded-lg transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Analytics Panel */}
      {tickets && tickets.length > 0 && (
        <TriageAnalytics tickets={tickets} filters={filters} onFilter={handleFilter} />
      )}

      {/* Table */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 shadow-lg overflow-hidden">
        {isLoading ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700/50">
                {['Ticket ID', 'Node / Alarm', 'Severity', 'Fault Type', 'Network', 'Reasons', 'Confidence', 'Flagged', 'Assigned', 'Actions'].map(
                  (col) => (
                    <th key={col} className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider">
                      {col}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 5 }).map((_, i) => <TableRowSkeleton key={i} cols={10} />)}
            </tbody>
          </table>
        ) : !tickets || tickets.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 px-6 text-center">
            <CheckCircle2 className="w-14 h-14 text-green-500 mb-4" />
            <h3 className="text-lg font-semibold text-white mb-2">
              No tickets pending review
            </h3>
            <p className="text-sm text-slate-400 max-w-xs">
              The pipeline is fully automated — all tickets have been processed successfully.
            </p>
          </div>
        ) : filteredTickets.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
            <Filter className="w-10 h-10 text-slate-600 mb-3" />
            <h3 className="text-sm font-semibold text-white mb-1">No tickets match the selected filters</h3>
            <button
              onClick={() => setFilters({ network: null, severity: null, faultType: null })}
              className="mt-3 px-4 py-1.5 text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-lg hover:bg-amber-500/20 transition-colors"
            >
              Clear filters
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[900px]">
              <thead>
                <tr className="border-b border-slate-700/50">
                  {['Ticket ID', 'Node / Alarm', 'Severity', 'Fault Type', 'Network', 'Reasons', 'Confidence', 'Flagged', 'Assigned', 'Actions'].map(
                    (col) => (
                      <th key={col} className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider whitespace-nowrap">
                        {col}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody>
                {filteredTickets.map((ticket) => (
                  <tr
                    key={ticket.ticket_id}
                    className="border-b border-slate-700/30 hover:bg-slate-700/20 transition-colors"
                  >
                    {/* Ticket ID */}
                    <td className="px-4 py-3">
                      <span className="font-mono text-blue-400 text-xs">{ticket.ticket_id}</span>
                    </td>

                    {/* Node / Alarm */}
                    <td className="px-4 py-3 max-w-[150px]">
                      <p className="text-slate-300 text-xs font-medium truncate">{ticket.affected_node}</p>
                      {ticket.alarm_name && (
                        <p className="text-slate-500 text-xs truncate">{ticket.alarm_name}</p>
                      )}
                    </td>

                    {/* Severity */}
                    <td className="px-4 py-3">
                      <SeverityBadge severity={ticket.severity} />
                    </td>

                    {/* Fault Type */}
                    <td className="px-4 py-3 text-slate-300 text-xs max-w-[100px] truncate">
                      {ticket.fault_type}
                    </td>

                    {/* Network */}
                    <td className="px-4 py-3 text-slate-400 text-xs whitespace-nowrap">
                      {ticket.network_type ?? '—'}
                    </td>

                    {/* Reasons */}
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1 max-w-[180px]">
                        {ticket.reasons.length > 0 ? (
                          ticket.reasons.map((r) => <ReasonChip key={r} reason={r} />)
                        ) : (
                          <span className="text-slate-500 text-xs">—</span>
                        )}
                      </div>
                    </td>

                    {/* Confidence */}
                    <td className="px-4 py-3">
                      <ConfidenceBar score={ticket.confidence_score} />
                    </td>

                    {/* Flagged At */}
                    <td className="px-4 py-3 text-slate-500 text-xs whitespace-nowrap">
                      {relativeTime(ticket.flagged_at)}
                    </td>

                    {/* Assigned To */}
                    <td className="px-4 py-3 text-xs whitespace-nowrap">
                      {ticket.assigned_to ? (
                        <span className="text-slate-300">{ticket.assigned_to}</span>
                      ) : (
                        <span className="text-slate-500 italic">Unassigned</span>
                      )}
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setAssignTarget(ticket)}
                          className="flex items-center gap-1 px-2.5 py-1 text-xs text-blue-400 bg-blue-500/10 hover:bg-blue-500/20 border border-blue-500/20 rounded-lg transition-colors whitespace-nowrap"
                        >
                          <UserPlus className="w-3 h-3" />
                          Assign
                        </button>
                        <button
                          onClick={() => setResolveTarget(ticket)}
                          className="flex items-center gap-1 px-2.5 py-1 text-xs text-green-400 bg-green-500/10 hover:bg-green-500/20 border border-green-500/20 rounded-lg transition-colors whitespace-nowrap"
                        >
                          <CheckCircle2 className="w-3 h-3" />
                          Resolve
                        </button>
                        <button
                          onClick={() => setAuditTarget(ticket.ticket_id)}
                          className="flex items-center gap-1 px-2.5 py-1 text-xs text-violet-400 bg-violet-500/10 hover:bg-violet-500/20 border border-violet-500/20 rounded-lg transition-colors whitespace-nowrap"
                        >
                          <History className="w-3 h-3" />
                          History
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modals */}
      {assignTarget && (
        <AssignModal ticket={assignTarget} onClose={() => setAssignTarget(null)} />
      )}
      {resolveTarget && (
        <ResolveModal ticket={resolveTarget} onClose={() => setResolveTarget(null)} />
      )}
      {auditTarget && (
        <AuditTimelineModal ticketId={auditTarget} onClose={() => setAuditTarget(null)} />
      )}
    </div>
  )
}
