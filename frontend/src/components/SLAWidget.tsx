import { useQuery } from '@tanstack/react-query'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from 'recharts'
import { ShieldCheck } from 'lucide-react'
import { api, type SLAFaultSummary } from '../api/client'

// ---------------------------------------------------------------------------
// Colour helpers
// ---------------------------------------------------------------------------

function complianceColour(rate: number): string {
  if (rate >= 90) return '#22c55e'   // green
  if (rate >= 70) return '#f59e0b'   // amber
  return '#E60028'                    // red
}

// ---------------------------------------------------------------------------
// Custom tooltip
// ---------------------------------------------------------------------------

interface TooltipPayload {
  payload: SLAFaultSummary
}

function SLATooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg p-3 text-xs shadow-xl">
      <p className="font-semibold text-white mb-1">{d.fault_type.replace(/_/g, ' ')}</p>
      <p className="text-slate-400 mb-2">{d.description}</p>
      <p>
        Target: <span className="text-white font-medium">{d.target_hours}h</span>
      </p>
      <p>
        Avg resolution: <span className="text-white font-medium">{d.avg_resolution_hours.toFixed(1)}h</span>
      </p>
      <p>
        Resolved: <span className="text-white font-medium">{d.total_resolved}</span>
      </p>
      <p>
        Within SLA: <span className="text-green-400 font-medium">{d.within_sla}</span>
      </p>
      <p>
        Breached: <span className="text-red-400 font-medium">{d.breached}</span>
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Widget
// ---------------------------------------------------------------------------

export function SLAWidget() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['sla-summary'],
    queryFn: api.getSLASummary,
    staleTime: 5 * 60_000,
  })

  // ── Loading state ──────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 shadow-lg">
        <div className="flex items-center gap-2 mb-6">
          <div className="animate-pulse h-4 w-4 bg-slate-700 rounded" />
          <div className="animate-pulse h-4 w-48 bg-slate-700 rounded" />
        </div>
        <div className="flex gap-6 mb-6">
          {[1, 2, 3].map((i) => (
            <div key={i} className="animate-pulse flex-1 h-20 bg-slate-700 rounded-lg" />
          ))}
        </div>
        <div className="animate-pulse h-52 bg-slate-700 rounded-lg" />
      </div>
    )
  }

  // ── Error state ────────────────────────────────────────────────────────
  if (error || !data) {
    return (
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 shadow-lg">
        <div className="flex items-center gap-2 mb-2">
          <ShieldCheck size={15} className="text-slate-400" />
          <span className="text-lg font-semibold text-white">SLA Compliance</span>
        </div>
        <p className="text-red-400 text-sm">SLA data unavailable — backend may be offline.</p>
      </div>
    )
  }

  // ── Empty state ────────────────────────────────────────────────────────
  if (data.total_resolved === 0) {
    return (
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 shadow-lg">
        <div className="flex items-center gap-2 mb-2">
          <ShieldCheck size={15} className="text-green-400" />
          <span className="text-lg font-semibold text-white">SLA Compliance</span>
        </div>
        <p className="text-slate-400 text-sm">No resolved tickets found to compute SLA metrics.</p>
      </div>
    )
  }

  const overallColour = complianceColour(data.compliance_rate)

  // Prepare chart data — sort by compliance_rate ascending (worst first)
  const chartData = [...data.by_fault_type]
    .sort((a, b) => a.compliance_rate - b.compliance_rate)
    .map((d) => ({
      ...d,
      label: d.fault_type.replace(/_/g, ' '),
    }))

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 shadow-lg">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <ShieldCheck size={15} style={{ color: overallColour }} />
          <h2 className="text-lg font-semibold text-white">SLA Compliance</h2>
          <span className="text-xs text-slate-400 ml-1">resolved tickets only</span>
        </div>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {/* Compliance rate */}
        <div className="bg-slate-900 rounded-lg p-4 text-center">
          <p
            className="text-3xl font-bold"
            style={{ color: overallColour }}
            aria-label={`Overall SLA compliance rate: ${data.compliance_rate}%`}
          >
            {data.compliance_rate}%
          </p>
          <p className="text-slate-400 text-xs mt-1">Overall compliance</p>
        </div>

        {/* Breached */}
        <div className="bg-slate-900 rounded-lg p-4 text-center">
          <p className="text-3xl font-bold text-red-400" aria-label={`${data.breached} tickets breached SLA`}>
            {data.breached}
          </p>
          <p className="text-slate-400 text-xs mt-1">SLA breaches</p>
        </div>

        {/* Avg resolution */}
        <div className="bg-slate-900 rounded-lg p-4 text-center">
          <p className="text-3xl font-bold text-blue-400" aria-label={`Average resolution time: ${data.avg_resolution_hours} hours`}>
            {data.avg_resolution_hours.toFixed(1)}h
          </p>
          <p className="text-slate-400 text-xs mt-1">Avg resolution time</p>
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs text-slate-400 mb-3">
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-green-500" />
          ≥ 90%
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-amber-400" />
          70–89%
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: '#E60028' }} />
          &lt; 70%
        </span>
      </div>

      {/* Bar chart — compliance rate by fault type */}
      <section aria-label="SLA compliance rate by fault type">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart
            data={chartData}
            layout="vertical"
            margin={{ top: 0, right: 40, left: 10, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
            <XAxis
              type="number"
              domain={[0, 100]}
              tickFormatter={(v) => `${v}%`}
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              type="category"
              dataKey="label"
              width={120}
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip content={<SLATooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
            {/* Target line at 90% */}
            <ReferenceLine x={90} stroke="#22c55e" strokeDasharray="4 4" strokeWidth={1} />
            <Bar dataKey="compliance_rate" radius={[0, 4, 4, 0]} maxBarSize={18}>
              {chartData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={complianceColour(entry.compliance_rate)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </section>

      {/* Footer */}
      <p className="text-slate-500 text-xs mt-3 text-right">
        {data.total_resolved.toLocaleString()} resolved tickets ·{' '}
        {data.by_fault_type.length} fault categories
      </p>
    </div>
  )
}
