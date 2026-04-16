/**
 * HotNodesWidget — high-volume ticket nodes grouped by network type
 *
 * Three buckets (3G / 4G / 5G), each showing its top-6 nodes ranked by
 * ticket count with a two-segment bar: Resolved vs Pending Resolution.
 *
 * Reuses ['network-graph'] React Query cache → 0 extra HTTP calls.
 */

import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { TrendingUp } from 'lucide-react'
import { apiClient } from '../api/client'

// ── Types ─────────────────────────────────────────────────────────────────────

interface NetworkNode {
  node_id: string
  network_type: string
  node_class: string
  ticket_count: number
  pending_count: number
  open_count: number
  resolved_count: number
}

interface GraphData {
  nodes: NetworkNode[]
  edges: unknown[]
  summary: {
    total_nodes: number
    nodes_with_pending: number
    nodes_with_issues: number
    total_edges: number
  }
}

// ── Bucket config ─────────────────────────────────────────────────────────────

interface BucketConfig {
  type: string
  label: string
  headerBg: string
  headerBorder: string
  badgeCls: string
  accentColor: string   // Tailwind text color for totals
  barAccent: string     // CSS color for the unresolved bar segment
}

const PENDING_COLOR = '#f97316'   // orange-500 — universal "needs attention" signal
const PENDING_TEXT  = 'text-orange-400'

const BUCKETS: BucketConfig[] = [
  {
    type: '3G',
    label: '3G · UMTS / NodeB',
    headerBg: 'bg-blue-900/20',
    headerBorder: 'border-blue-700/40',
    badgeCls: 'bg-blue-900/50 text-blue-300 border border-blue-700/50',
    accentColor: 'text-blue-400',
    barAccent: PENDING_COLOR,
  },
  {
    type: '4G',
    label: '4G · LTE / eNodeB',
    headerBg: 'bg-violet-900/20',
    headerBorder: 'border-violet-700/40',
    badgeCls: 'bg-violet-900/50 text-violet-300 border border-violet-700/50',
    accentColor: 'text-violet-400',
    barAccent: PENDING_COLOR,
  },
  {
    type: '5G',
    label: '5G · NR / gNodeB',
    headerBg: 'bg-emerald-900/20',
    headerBorder: 'border-emerald-700/40',
    badgeCls: 'bg-emerald-900/50 text-emerald-300 border border-emerald-700/50',
    accentColor: 'text-emerald-400',
    barAccent: PENDING_COLOR,
  },
]

const TOP_N = 6   // nodes shown per bucket

// ── Skeleton ──────────────────────────────────────────────────────────────────

function SkeletonBucket(): React.ReactElement {
  return (
    <div className="flex flex-col gap-0 animate-pulse">
      <div className="h-14 bg-slate-700/40 rounded-t-lg mb-0.5" />
      {Array.from({ length: TOP_N }).map((_, i) => (
        <div key={i} className="flex items-center gap-2 px-3 py-2.5 border-b border-slate-700/30 last:border-0">
          <div className="w-4 h-2.5 bg-slate-700 rounded" />
          <div className="flex-1 space-y-1.5">
            <div className="h-2.5 w-3/4 bg-slate-700 rounded" />
            <div className="h-1.5 w-full bg-slate-700 rounded-full" />
          </div>
          <div className="w-5 h-3 bg-slate-700 rounded" />
        </div>
      ))}
    </div>
  )
}

// ── Bucket column ─────────────────────────────────────────────────────────────

interface BucketColProps {
  cfg: BucketConfig
  nodes: NetworkNode[]
}

function BucketCol({ cfg, nodes }: BucketColProps): React.ReactElement {
  const topNodes = [...nodes]
    .sort((a, b) => b.ticket_count - a.ticket_count)
    .slice(0, TOP_N)

  const totalTickets   = nodes.reduce((s, n) => s + n.ticket_count,   0)
  const totalResolved  = nodes.reduce((s, n) => s + n.resolved_count, 0)
  const totalUnresolved = totalTickets - totalResolved
  const resolvedPct    = totalTickets > 0 ? Math.round((totalResolved / totalTickets) * 100) : 0

  return (
    <div className="flex flex-col min-w-0 rounded-lg overflow-hidden border border-slate-700/50">

      {/* Bucket header */}
      <div className={`${cfg.headerBg} border-b ${cfg.headerBorder} px-3 py-2.5`}>
        <div className="flex items-center justify-between mb-1.5">
          <span className={`text-xs font-bold px-2 py-0.5 rounded ${cfg.badgeCls}`}>
            {cfg.type}
          </span>
          <span className="text-[10px] text-slate-500 font-mono">{nodes.length} nodes</span>
        </div>
        <p className="text-[10px] text-slate-500 truncate mb-2">{cfg.label}</p>
        {/* Bucket-level resolved vs unresolved bar */}
        <div className="flex h-1.5 rounded-full overflow-hidden bg-slate-700/60">
          <div
            className="bg-green-500/80 transition-all duration-700"
            style={{ width: `${resolvedPct}%` }}
          />
          <div
            className="transition-all duration-700"
            style={{ width: `${100 - resolvedPct}%`, backgroundColor: cfg.barAccent, opacity: 0.85 }}
          />
        </div>
        <div className="flex items-center justify-between mt-1.5 text-[10px]">
          <span className="text-green-400 font-medium">{totalResolved} resolved</span>
          <span className={`${PENDING_TEXT} font-medium`}>{totalUnresolved} pending</span>
        </div>
      </div>

      {/* Node rows */}
      {topNodes.length === 0 ? (
        <div className="flex-1 flex items-center justify-center py-8 text-slate-600 text-xs">
          No {cfg.type} nodes
        </div>
      ) : (
        <div className="bg-slate-800/60">
          {topNodes.map((node, idx) => {
            const total       = node.ticket_count || 1
            const unresolved  = node.pending_count + node.open_count
            const resolvedPct = (node.resolved_count / total) * 100
            const unresPct    = (unresolved / total) * 100

            return (
              <div
                key={node.node_id}
                className="flex items-center gap-2 px-3 py-2 border-b border-slate-700/30 last:border-0 hover:bg-slate-700/20 transition-colors"
              >
                {/* Rank */}
                <span className="text-slate-600 text-[10px] font-mono w-4 flex-shrink-0 text-right">
                  {idx + 1}
                </span>

                {/* Node info + bar */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 mb-1">
                    <span className="font-mono text-[11px] text-slate-300 truncate leading-none">
                      {node.node_id}
                    </span>
                    <span className="text-[9px] text-slate-600 flex-shrink-0">{node.node_class}</span>
                  </div>
                  {/* Two-segment bar: resolved | pending-resolution */}
                  <div className="flex h-1.5 rounded-full overflow-hidden bg-slate-700/60 gap-px">
                    {resolvedPct > 0 && (
                      <div
                        className="bg-green-500 transition-all duration-500"
                        style={{ width: `${resolvedPct}%` }}
                        title={`Resolved: ${node.resolved_count}`}
                      />
                    )}
                    {unresPct > 0 && (
                      <div
                        className="transition-all duration-500"
                        style={{ width: `${unresPct}%`, backgroundColor: cfg.barAccent }}
                        title={`Pending resolution: ${unresolved}`}
                      />
                    )}
                  </div>
                </div>

                {/* Counts */}
                <div className="flex-shrink-0 text-right">
                  <span className="text-white text-xs font-bold block leading-none">
                    {node.ticket_count}
                  </span>
                  {unresolved > 0 && (
                    <span className={`text-[9px] font-medium ${PENDING_TEXT}`}>
                      {unresolved} open
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function HotNodesWidget(): React.ReactElement {
  const { data, isLoading } = useQuery<GraphData>({
    queryKey: ['network-graph'],
    queryFn: async () => {
      const { data } = await apiClient.get<GraphData>('/network/graph')
      return data
    },
    staleTime: 5 * 60_000,
  })

  const allNodes = data?.nodes ?? []

  // Partition by network type
  const byType = (type: string) => allNodes.filter(n => n.network_type === type)

  // Fleet-level totals
  const fleetTotal    = allNodes.reduce((s, n) => s + n.ticket_count,   0)
  const fleetResolved = allNodes.reduce((s, n) => s + n.resolved_count, 0)
  const fleetPending  = allNodes.reduce((s, n) => s + n.pending_count,  0)

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-5 shadow-lg">

      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2">
            <TrendingUp size={15} className="text-red-400" />
            High-Volume Ticket Nodes
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Top nodes by network type · resolved vs pending resolution
          </p>
        </div>
        {/* Legend */}
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-green-500 inline-block flex-shrink-0" />
            Resolved
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-orange-500 inline-block flex-shrink-0" />
            Pending resolution
          </span>
        </div>
      </div>

      {/* Three bucket columns */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {BUCKETS.map(b => <SkeletonBucket key={b.type} />)}
        </div>
      ) : allNodes.length === 0 ? (
        <div className="py-12 text-center text-slate-500 text-sm">No network data available</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {BUCKETS.map(cfg => (
            <BucketCol key={cfg.type} cfg={cfg} nodes={byType(cfg.type)} />
          ))}
        </div>
      )}

      {/* Fleet footer */}
      {!isLoading && allNodes.length > 0 && (
        <div className="mt-4 pt-3 border-t border-slate-700/40 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-slate-500">
          <span>
            <span className="text-slate-400 font-medium">{data?.summary.total_nodes ?? allNodes.length}</span> total nodes
          </span>
          <span>
            <span className="text-slate-300 font-medium">{fleetTotal.toLocaleString()}</span> total tickets
          </span>
          <span>
            <span className="text-green-400 font-medium">{fleetResolved.toLocaleString()}</span> resolved
          </span>
          <span>
            <span className="text-red-400 font-medium">{fleetPending.toLocaleString()}</span> pending review
          </span>
        </div>
      )}
    </div>
  )
}
