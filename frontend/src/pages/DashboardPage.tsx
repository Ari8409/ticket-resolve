import React from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { Ticket, Activity, Users, CheckCircle, Wifi, Wrench, Clock } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api, TelcoTicket, DispatchStats } from '../api/client'
import { SeverityBadge, StatusBadge } from '../components/shared/Badges'
import { StatCardSkeleton, TableRowSkeleton } from '../components/shared/Skeleton'
import { useToast } from '../components/shared/Toast'
import { NetworkTopologyWidget } from '../components/NetworkTopologyWidget'
import { HotNodesWidget } from '../components/HotNodesWidget'
import { TicketLocationMapWidget } from '../components/TicketLocationMapWidget'
import { SLAWidget } from '../components/SLAWidget'

interface DashboardPageProps {
  autoRefresh: boolean
}

// ─── Stat Card ─────────────────────────────────────────────────────────────────

interface StatCardProps {
  title: string
  value: number
  icon: React.ReactNode
  color: string
  pulse?: boolean
  description?: string
}

function StatCard({ title, value, icon, color, pulse, description }: StatCardProps) {
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 hover:border-slate-600 transition-all duration-200 shadow-lg">
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-medium text-slate-400">{title}</p>
        <div className={`flex items-center justify-center w-10 h-10 rounded-lg ${color}`}>
          {icon}
        </div>
      </div>
      <div className="flex items-end gap-2">
        <p className="text-4xl font-bold text-white">{value.toLocaleString()}</p>
        {pulse && value > 0 && (
          <span className="mb-1 flex items-center">
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500" />
            </span>
          </span>
        )}
      </div>
      {description && <p className="text-xs text-slate-500 mt-1">{description}</p>}
    </div>
  )
}

// ─── Colour maps ───────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  open: '#E60028',
  in_progress: '#f59e0b',
  pending_review: '#ef4444',
  resolved: '#22c55e',
  failed: '#6b7280',
  escalated: '#f97316',
  closed: '#475569',
  pending: '#fb923c',
  assigned: '#818cf8',
  cleared: '#14b8a6',
}

// ─── Custom Pie tooltip ────────────────────────────────────────────────────────

const PieTooltip = ({ active, payload }: { active?: boolean; payload?: { name: string; value: number }[] }) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs shadow-xl">
        <p className="text-slate-300 font-medium">{payload[0].name.replace(/_/g, ' ')}</p>
        <p className="text-white font-bold">{payload[0].value}</p>
      </div>
    )
  }
  return null
}

const BarTooltip = ({ active, payload, label }: { active?: boolean; payload?: { value: number }[]; label?: string }) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs shadow-xl">
        <p className="text-slate-300 font-medium">{label}</p>
        <p className="text-white font-bold">{payload[0].value} tickets</p>
      </div>
    )
  }
  return null
}

// ─── Main Component ────────────────────────────────────────────────────────────

export default function DashboardPage({ autoRefresh }: DashboardPageProps) {
  const { showToast } = useToast()
  const navigate = useNavigate()

  const {
    data: stats,
    isLoading: statsLoading,
    error: statsError,
  } = useQuery({
    queryKey: ['stats'],
    queryFn: api.getStats,
    refetchInterval: autoRefresh ? 30_000 : false,
  })

  const {
    data: ticketsData,
    isLoading: ticketsLoading,
    error: ticketsError,
  } = useQuery({
    queryKey: ['tickets', { limit: 20 }],
    queryFn: () => api.getTickets({ limit: 20, offset: 0 }),
    refetchInterval: autoRefresh ? 30_000 : false,
  })

  // Separate query for chart data — fetch more tickets for accurate breakdown
  // Falls back to stats.by_fault_type when available (after backend restart)
  const {
    data: chartTicketsData,
  } = useQuery({
    queryKey: ['tickets-chart'],
    queryFn: () => api.getTickets({ limit: 200, offset: 0 }),
    staleTime: 60_000,
  })

  const {
    data: dispatchStats,
    isLoading: dispatchLoading,
  } = useQuery({
    queryKey: ['dispatch-stats'],
    queryFn: api.getDispatchStats,
    refetchInterval: autoRefresh ? 60_000 : false,
    staleTime: 30_000,
  })

  React.useEffect(() => {
    if (statsError) showToast('Failed to load statistics', 'error')
    if (ticketsError) showToast('Failed to load tickets', 'error')
  }, [statsError, ticketsError, showToast])

  // Build pie chart data
  const pieData = stats
    ? Object.entries(stats.by_status)
        .filter(([, v]) => v > 0)
        .map(([name, value]) => ({ name, value }))
    : []

  // Bar chart: prefer stats.by_fault_type (all tickets), fallback to chart sample
  const barData = (() => {
    const source: Record<string, number> =
      stats?.by_fault_type ??
      (() => {
        const counts: Record<string, number> = {}
        for (const t of (chartTicketsData?.tickets ?? [])) {
          counts[t.fault_type] = (counts[t.fault_type] ?? 0) + 1
        }
        return counts
      })()
    return Object.entries(source)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([name, value]) => ({ name: name.replace(/_/g, ' '), value }))
  })()

  // Top alarms chart: prefer stats.by_alarm (all tickets), fallback to chart sample
  const alarmData = (() => {
    const source: Record<string, number> =
      stats?.by_alarm ??
      (() => {
        const counts: Record<string, number> = {}
        for (const t of (chartTicketsData?.tickets ?? [])) {
          if (t.alarm_name) counts[t.alarm_name] = (counts[t.alarm_name] ?? 0) + 1
        }
        return counts
      })()
    return Object.entries(source)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([name, value]) => ({ name: name.length > 22 ? name.slice(0, 22) + '…' : name, value }))
  })()

  // Sort tickets by created_at desc
  const recentTickets: TelcoTicket[] = ticketsData?.tickets
    ? [...ticketsData.tickets].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )
    : []

  const formatRelativeTime = (isoString: string) => {
    const diff = Date.now() - new Date(isoString).getTime()
    const minutes = Math.floor(diff / 60_000)
    if (minutes < 1) return 'just now'
    if (minutes < 60) return `${minutes}m ago`
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `${hours}h ago`
    return `${Math.floor(hours / 24)}d ago`
  }

  return (
    <div className="space-y-6">
      {/* Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {statsLoading ? (
          Array.from({ length: 4 }).map((_, i) => <StatCardSkeleton key={i} />)
        ) : (
          <>
            <StatCard
              title="Total Tickets"
              value={stats?.total ?? 0}
              icon={<Ticket className="w-5 h-5 text-singtel-light" />}
              color="bg-singtel/10"
              description="All time"
            />
            <StatCard
              title="Open Tickets"
              value={stats?.open ?? 0}
              icon={<Activity className="w-5 h-5 text-amber-400" />}
              color="bg-amber-500/10"
              description="Awaiting action"
            />
            <StatCard
              title="Pending Human Review"
              value={stats?.pending_review ?? 0}
              icon={<Users className="w-5 h-5 text-red-400" />}
              color="bg-red-500/10"
              pulse
              description="Requires attention"
            />
            <StatCard
              title="Resolved"
              value={stats?.resolved ?? 0}
              icon={<CheckCircle className="w-5 h-5 text-green-400" />}
              color="bg-green-500/10"
              description="Completed"
            />
          </>
        )}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {/* Donut Chart */}
        <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 shadow-lg">
          <h3 className="text-sm font-semibold text-slate-300 mb-4">Ticket Distribution by Status</h3>
          {statsLoading ? (
            <div className="h-56 flex items-center justify-center">
              <div className="animate-pulse bg-slate-700/50 rounded-full w-40 h-40" />
            </div>
          ) : pieData.length === 0 ? (
            <div className="h-56 flex items-center justify-center text-slate-500 text-sm">
              No data available
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={90}
                  paddingAngle={2}
                  dataKey="value"
                >
                  {pieData.map((entry, i) => (
                    <Cell
                      key={`cell-${i}`}
                      fill={STATUS_COLORS[entry.name] ?? '#64748b'}
                    />
                  ))}
                </Pie>
                <Tooltip content={<PieTooltip />} />
                <Legend
                  formatter={(value) => (
                    <span className="text-slate-400 text-xs">
                      {String(value).replace(/_/g, ' ')}
                    </span>
                  )}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Bar Chart — Fault Types */}
        <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 shadow-lg">
          <h3 className="text-sm font-semibold text-slate-300 mb-4">Tickets by Fault Type</h3>
          {statsLoading ? (
            <div className="h-56 space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="animate-pulse bg-slate-700/50 rounded h-6" />
              ))}
            </div>
          ) : barData.length === 0 ? (
            <div className="h-56 flex items-center justify-center text-slate-500 text-sm">
              No data available
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={barData} margin={{ top: 4, right: 8, left: -20, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis
                  dataKey="name"
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                  tickLine={false}
                  axisLine={{ stroke: '#334155' }}
                  interval={0}
                  angle={-20}
                  textAnchor="end"
                  height={45}
                />
                <YAxis
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  allowDecimals={false}
                />
                <Tooltip content={<BarTooltip />} cursor={{ fill: 'rgba(148,163,184,0.05)' }} />
                <Bar dataKey="value" fill="#E60028" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Top Alarms Bar Chart — full width */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 shadow-lg">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-300">Top Alarm Types</h3>
          <span className="text-xs text-slate-500">
            {stats?.total ? `across ${stats.total.toLocaleString()} tickets` : ''}
          </span>
        </div>
        {statsLoading ? (
          <div className="h-48 space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="animate-pulse bg-slate-700/50 rounded h-6" />
            ))}
          </div>
        ) : alarmData.length === 0 ? (
          <div className="h-48 flex items-center justify-center text-slate-500 text-sm">No data available</div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={alarmData} layout="vertical" margin={{ top: 2, right: 40, left: 8, bottom: 2 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
              <XAxis
                type="number"
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                allowDecimals={false}
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={160}
              />
              <Tooltip content={<BarTooltip />} cursor={{ fill: 'rgba(148,163,184,0.05)' }} />
              <Bar dataKey="value" fill="#E60028" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Remote vs Field Resolution */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 shadow-lg">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h3 className="text-sm font-semibold text-slate-300">Remote vs Field Resolution</h3>
            <p className="text-xs text-slate-500 mt-0.5">Dispatch mode breakdown across all resolved tickets</p>
          </div>
          {dispatchStats && (
            <span className="text-xs text-slate-500 font-mono">{dispatchStats.total.toLocaleString()} decisions</span>
          )}
        </div>

        {dispatchLoading || !dispatchStats ? (
          <div className="space-y-3">
            <div className="h-16 bg-slate-700/40 rounded-lg animate-pulse" />
            <div className="h-16 bg-slate-700/40 rounded-lg animate-pulse" />
          </div>
        ) : (
          <div className="space-y-5">
            {/* Big split bar */}
            <div>
              <div className="flex justify-between text-xs text-slate-400 mb-1.5">
                <span className="flex items-center gap-1.5">
                  <Wifi size={12} className="text-blue-400" />
                  Remote &mdash; {dispatchStats.remote.toLocaleString()} tickets
                </span>
                <span className="flex items-center gap-1.5">
                  {dispatchStats.on_site.toLocaleString()} tickets &mdash; Field
                  <Wrench size={12} className="text-orange-400" />
                </span>
              </div>
              <div className="flex h-7 rounded-lg overflow-hidden gap-0.5">
                <div
                  className="bg-blue-500 flex items-center justify-center text-xs font-bold text-white transition-all duration-700"
                  style={{ width: `${dispatchStats.remote_pct}%` }}
                >
                  {dispatchStats.remote_pct}%
                </div>
                <div
                  className="bg-orange-500 flex items-center justify-center text-xs font-bold text-white transition-all duration-700"
                  style={{ width: `${dispatchStats.on_site_pct}%` }}
                >
                  {dispatchStats.on_site_pct}%
                </div>
              </div>
              <div className="flex justify-between text-xs text-slate-600 mt-1">
                <span>Avg confidence: <span className="text-slate-400">{(dispatchStats.remote_avg_confidence * 100).toFixed(1)}%</span></span>
                <span>Avg confidence: <span className="text-slate-400">{(dispatchStats.on_site_avg_confidence * 100).toFixed(1)}%</span></span>
              </div>
            </div>

            {/* Stat tiles */}
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-blue-900/20 border border-blue-800/30 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <Wifi size={14} className="text-blue-400" />
                  <span className="text-xs text-slate-400">Remote</span>
                </div>
                <p className="text-xl font-bold text-blue-400">{dispatchStats.remote.toLocaleString()}</p>
                <p className="text-xs text-slate-500 mt-0.5">No site visit needed</p>
              </div>
              <div className="bg-orange-900/20 border border-orange-800/30 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <Wrench size={14} className="text-orange-400" />
                  <span className="text-xs text-slate-400">Field</span>
                </div>
                <p className="text-xl font-bold text-orange-400">{dispatchStats.on_site.toLocaleString()}</p>
                <p className="text-xs text-slate-500 mt-0.5">On-site dispatch</p>
              </div>
              <div className="bg-amber-900/20 border border-amber-800/30 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <Clock size={14} className="text-amber-400" />
                  <span className="text-xs text-slate-400">On Hold</span>
                </div>
                <p className="text-xl font-bold text-amber-400">{dispatchStats.hold.toLocaleString()}</p>
                <p className="text-xs text-slate-500 mt-0.5">Pending review</p>
              </div>
            </div>

            {/* Per-network breakdown */}
            {Object.keys(dispatchStats.by_network).length > 0 && (
              <div>
                <p className="text-xs text-slate-500 font-semibold uppercase tracking-wider mb-2">By Network Type</p>
                <div className="space-y-2">
                  {Object.entries(dispatchStats.by_network)
                    .sort((a, b) => (b[1].remote + b[1].on_site) - (a[1].remote + a[1].on_site))
                    .map(([nt, counts]) => {
                      const tot = counts.remote + counts.on_site
                      const remPct = tot > 0 ? Math.round(counts.remote / tot * 100) : 0
                      return (
                        <div key={nt} className="flex items-center gap-3">
                          <span className="text-xs text-slate-400 w-8 font-mono">{nt}</span>
                          <div className="flex-1 flex h-4 rounded overflow-hidden gap-px">
                            <div className="bg-blue-500/70 transition-all duration-500" style={{ width: `${remPct}%` }} />
                            <div className="bg-orange-500/70 transition-all duration-500" style={{ width: `${100 - remPct}%` }} />
                          </div>
                          <span className="text-xs text-slate-500 w-28 text-right">
                            {counts.remote}R / {counts.on_site}F
                          </span>
                        </div>
                      )
                    })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* High-Volume Ticket Nodes */}
      <HotNodesWidget />

      {/* Network Topology */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 shadow-lg">
        <div className="flex items-center justify-between mb-1">
          <div>
            <h3 className="text-sm font-semibold text-slate-300">Network Topology</h3>
            <p className="text-xs text-slate-500 mt-0.5">766 nodes · color = ticket health · scroll to zoom · drag to pan</p>
          </div>
        </div>
        <NetworkTopologyWidget />
      </div>

      {/* Ticket Location Map */}
      <TicketLocationMapWidget />

      {/* SLA Compliance (R-15) */}
      <SLAWidget />

      {/* Recent Tickets Table */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 shadow-lg overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700/50">
          <h3 className="text-sm font-semibold text-slate-300">Recent Tickets</h3>
          <button
            onClick={() => navigate('/triage')}
            className="text-xs text-singtel-light hover:text-singtel-lighter transition-colors font-medium"
          >
            View All →
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700/50">
                {['Ticket ID', 'Node', 'Fault Type', 'Severity', 'Status', 'Network', 'Created'].map(
                  (col) => (
                    <th
                      key={col}
                      className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider"
                    >
                      {col}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {ticketsLoading ? (
                Array.from({ length: 6 }).map((_, i) => <TableRowSkeleton key={i} cols={7} />)
              ) : recentTickets.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-slate-500">
                    No tickets found
                  </td>
                </tr>
              ) : (
                recentTickets.slice(0, 20).map((ticket) => (
                  <tr
                    key={ticket.ticket_id}
                    className="border-b border-slate-700/30 hover:bg-slate-700/30 transition-colors cursor-pointer"
                    onClick={() => navigate('/triage')}
                  >
                    <td className="px-4 py-3">
                      <span className="font-mono text-singtel-light text-xs hover:text-singtel-lighter">
                        {ticket.ticket_id}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-300 max-w-[140px] truncate">
                      {ticket.affected_node}
                    </td>
                    <td className="px-4 py-3 text-slate-300 max-w-[120px] truncate">
                      {ticket.fault_type}
                    </td>
                    <td className="px-4 py-3">
                      <SeverityBadge severity={ticket.severity} />
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={ticket.status} />
                    </td>
                    <td className="px-4 py-3 text-slate-400 text-xs">
                      {ticket.network_type ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-slate-500 text-xs whitespace-nowrap">
                      {formatRelativeTime(ticket.created_at)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
