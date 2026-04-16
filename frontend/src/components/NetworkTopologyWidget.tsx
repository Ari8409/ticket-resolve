import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X, ChevronRight, ExternalLink, ZoomIn, ZoomOut, RotateCcw } from 'lucide-react'
import { apiClient } from '../api/client'

// ─── Types ────────────────────────────────────────────────────────────────────

interface NetworkNode {
  node_id: string
  network_type: string
  node_class: string
  parent_node: string | null
  x_pos: number
  y_pos: number
  ticket_count: number
  pending_count: number
  open_count: number
  resolved_count: number
  last_ticket_at: string | null
}

interface NetworkEdge {
  edge_id: number
  source_node: string
  target_node: string
  edge_type: string
}

interface GraphData {
  nodes: NetworkNode[]
  edges: NetworkEdge[]
  summary: {
    total_nodes: number
    nodes_with_pending: number
    nodes_with_issues: number
    total_edges: number
  }
}

interface NodeTicket {
  ticket_id: string
  alarm_name: string | null
  fault_type: string
  severity: string
  status: string
  created_at: string
  network_type: string | null
}

type FilterType = 'All' | '3G' | '4G' | '5G'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function nodeColor(n: NetworkNode): string {
  if (n.pending_count > 0) return '#E60028'
  if (n.open_count > 0)    return '#F59E0B'
  if (n.ticket_count > 0)  return '#22C55E'
  return '#475569'
}

function healthLabel(n: NetworkNode): string {
  if (n.pending_count > 0) return 'Pending Review'
  if (n.open_count > 0)    return 'In Progress'
  if (n.ticket_count > 0)  return 'Healthy'
  return 'No Tickets'
}

function healthBg(n: NetworkNode): string {
  if (n.pending_count > 0) return 'bg-red-900/40 text-red-400 border border-red-700/50'
  if (n.open_count > 0)    return 'bg-amber-900/40 text-amber-400 border border-amber-700/50'
  if (n.ticket_count > 0)  return 'bg-green-900/40 text-green-400 border border-green-700/50'
  return 'bg-slate-700/40 text-slate-400 border border-slate-600/50'
}

function severityColor(s: string): string {
  switch (s?.toLowerCase()) {
    case 'critical': return 'text-red-400'
    case 'major':    return 'text-orange-400'
    case 'medium':
    case 'minor':    return 'text-yellow-400'
    default:         return 'text-slate-400'
  }
}

function statusColor(s: string): string {
  switch (s?.toLowerCase()) {
    case 'resolved': return 'text-green-400'
    case 'pending_review': return 'text-red-400'
    case 'in_progress': return 'text-amber-400'
    default: return 'text-slate-400'
  }
}

function nodeRadius(n: NetworkNode, maxCount: number): number {
  if (n.node_class === 'RNC') return 9
  const base = 4
  const extra = maxCount > 0 ? 6 * (n.ticket_count / maxCount) : 0
  return Math.round(base + extra)
}

function fmtTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  const diff = Math.floor((Date.now() - d.getTime()) / 1000)
  if (diff < 60)   return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

// ─── Detail Panel ─────────────────────────────────────────────────────────────

interface DetailPanelProps {
  node: NetworkNode
  children: NetworkNode[]          // NodeBs if this is an RNC
  onClose: () => void
  onDrillIn: (node: NetworkNode) => void
  isDrilled: boolean
}

function DetailPanel({ node, children, onClose, onDrillIn, isDrilled }: DetailPanelProps) {
  const { data: ticketData, isLoading } = useQuery({
    queryKey: ['node-tickets', node.node_id],
    queryFn: async () => {
      const { data } = await apiClient.get<{ tickets: NodeTicket[] }>(
        `/network/node/${encodeURIComponent(node.node_id)}/tickets?limit=5`
      )
      return data
    },
    staleTime: 2 * 60_000,
  })

  const tickets = ticketData?.tickets ?? []
  const isRNC = node.node_class === 'RNC'

  return (
    <div className="w-72 flex-shrink-0 bg-slate-900 border-l border-slate-700 rounded-r-lg flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-start justify-between p-4 border-b border-slate-700/60">
        <div className="min-w-0 flex-1">
          <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">
            {node.network_type} · {node.node_class}
          </p>
          <p className="font-mono text-sm text-white font-semibold truncate" title={node.node_id}>
            {node.node_id}
          </p>
        </div>
        <button onClick={onClose} className="ml-2 text-slate-500 hover:text-slate-300 transition-colors flex-shrink-0">
          <X size={15} />
        </button>
      </div>

      {/* Health badge */}
      <div className="px-4 pt-3 pb-2">
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${healthBg(node)}`}>
          <span className="w-1.5 h-1.5 rounded-full inline-block" style={{ background: nodeColor(node) }} />
          {healthLabel(node)}
        </span>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-2 px-4 pb-3">
        {[
          { label: 'Total', value: node.ticket_count, cls: 'text-white' },
          { label: 'Pending', value: node.pending_count, cls: node.pending_count > 0 ? 'text-red-400' : 'text-slate-400' },
          { label: 'Open', value: node.open_count, cls: node.open_count > 0 ? 'text-amber-400' : 'text-slate-400' },
          { label: 'Resolved', value: node.resolved_count, cls: 'text-green-400' },
        ].map(({ label, value, cls }) => (
          <div key={label} className="bg-slate-800 rounded-lg px-3 py-2">
            <p className={`text-sm font-semibold ${cls}`}>{value}</p>
            <p className="text-xs text-slate-500">{label}</p>
          </div>
        ))}
      </div>

      {/* Last ticket */}
      {node.last_ticket_at && (
        <p className="px-4 text-xs text-slate-500 pb-2">
          Last ticket: <span className="text-slate-400">{fmtTime(node.last_ticket_at)}</span>
        </p>
      )}

      {/* RNC: drill-in + children */}
      {isRNC && children.length > 0 && (
        <div className="px-4 pb-3">
          <button
            onClick={() => onDrillIn(node)}
            className={`w-full flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-medium transition-colors ${
              isDrilled
                ? 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                : 'bg-red-900/30 text-red-400 border border-red-700/40 hover:bg-red-900/50'
            }`}
          >
            {isDrilled ? 'Exit drill-down' : (
              <>
                <ChevronRight size={13} />
                Drill into cluster ({children.length} NodeBs)
              </>
            )}
          </button>

          {/* Children health summary */}
          <div className="mt-2 space-y-1 max-h-32 overflow-y-auto scrollbar-thin">
            {children.slice(0, 8).map(ch => (
              <div key={ch.node_id} className="flex items-center justify-between text-xs px-1">
                <span className="font-mono text-slate-400 truncate max-w-[140px]" title={ch.node_id}>
                  {ch.node_id}
                </span>
                <span className="ml-2 flex-shrink-0" style={{ color: nodeColor(ch) }}>
                  {ch.ticket_count}t{ch.pending_count > 0 ? ` (${ch.pending_count}p)` : ''}
                </span>
              </div>
            ))}
            {children.length > 8 && (
              <p className="text-xs text-slate-600 px-1">+{children.length - 8} more NodeBs</p>
            )}
          </div>
        </div>
      )}

      {/* Divider */}
      <div className="border-t border-slate-700/60 mx-4" />

      {/* Recent tickets */}
      <div className="flex-1 overflow-y-auto p-4">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
          Recent Tickets
        </p>
        {isLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-12 bg-slate-800 rounded animate-pulse" />
            ))}
          </div>
        ) : tickets.length === 0 ? (
          <p className="text-xs text-slate-600">No tickets found for this node.</p>
        ) : (
          <div className="space-y-2">
            {tickets.map(t => (
              <div key={t.ticket_id} className="bg-slate-800 rounded-lg p-2.5 space-y-0.5">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-slate-300">{t.ticket_id}</span>
                  <span className={`text-xs ${severityColor(t.severity)}`}>{t.severity}</span>
                </div>
                <p className="text-xs text-slate-500 truncate">{t.alarm_name ?? t.fault_type}</p>
                <div className="flex items-center justify-between">
                  <span className={`text-xs ${statusColor(t.status)}`}>
                    {t.status.replace('_', ' ')}
                  </span>
                  <span className="text-xs text-slate-600">{fmtTime(t.created_at)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Tooltip ─────────────────────────────────────────────────────────────────

interface TooltipState { node: NetworkNode; x: number; y: number }

function Tooltip({ tip }: { tip: TooltipState }) {
  const { node, x, y } = tip
  return (
    <div
      style={{ left: x + 14, top: y - 8 }}
      className="absolute z-50 pointer-events-none bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-xs shadow-xl min-w-[160px]"
    >
      <p className="font-mono font-semibold text-white truncate max-w-[200px]">{node.node_id}</p>
      <p className="text-slate-400 mb-1">{node.network_type} · {node.node_class}</p>
      {node.pending_count > 0 && <p className="text-red-400">{node.pending_count} pending</p>}
      {node.open_count > 0    && <p className="text-amber-400">{node.open_count} open</p>}
      {node.ticket_count > 0  && <p className="text-slate-300">{node.ticket_count} total · Click for details</p>}
      {node.ticket_count === 0 && <p className="text-slate-500">No tickets</p>}
    </div>
  )
}

// ─── Main Widget ──────────────────────────────────────────────────────────────

export function NetworkTopologyWidget() {
  const [filter, setFilter] = useState<FilterType>('All')
  const [selectedNode, setSelectedNode] = useState<NetworkNode | null>(null)
  const [drilledRNC, setDrilledRNC] = useState<string | null>(null)   // node_id of drilled-in RNC
  const [tooltip, setTooltip] = useState<TooltipState | null>(null)

  // Pan + zoom
  const [viewBox, setViewBox] = useState({ x: 0, y: 0, w: 1200, h: 700 })
  const dragging = useRef(false)
  const lastPos  = useRef({ x: 0, y: 0 })
  const svgRef   = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const SVG_W = 1200
  const SVG_H = 700
  const PAD   = 30

  // ── Data fetch ────────────────────────────────────────────────────────────
  const { data, isLoading, isError } = useQuery<GraphData>({
    queryKey: ['network-graph'],
    queryFn: async () => {
      const { data } = await apiClient.get<GraphData>('/network/graph')
      return data
    },
    staleTime: 5 * 60_000,
  })

  const allNodes = data?.nodes ?? []
  const allEdges = data?.edges ?? []

  // ── Adjacency map (for highlighting) ─────────────────────────────────────
  const adjacency: Record<string, Set<string>> = {}
  for (const e of allEdges) {
    ;(adjacency[e.source_node] ??= new Set()).add(e.target_node)
    ;(adjacency[e.target_node] ??= new Set()).add(e.source_node)
  }

  // ── Children lookup ───────────────────────────────────────────────────────
  const childrenOf: Record<string, NetworkNode[]> = {}
  for (const n of allNodes) {
    if (n.parent_node) {
      ;(childrenOf[n.parent_node] ??= []).push(n)
    }
  }

  // ── Filtering + drill-down ────────────────────────────────────────────────
  let visibleNodes: NetworkNode[] = allNodes
  if (drilledRNC) {
    // Show only the drilled RNC + its NodeBs
    visibleNodes = allNodes.filter(
      n => n.node_id === drilledRNC || n.parent_node === drilledRNC
    )
  } else if (filter !== 'All') {
    visibleNodes = allNodes.filter(n => n.network_type === filter)
  }

  const visibleIds   = new Set(visibleNodes.map(n => n.node_id))
  const visibleEdges = allEdges.filter(
    e => visibleIds.has(e.source_node) && visibleIds.has(e.target_node)
  )

  // ── Node highlighting ─────────────────────────────────────────────────────
  const highlightedIds: Set<string> | null = selectedNode
    ? new Set([
        selectedNode.node_id,
        ...(adjacency[selectedNode.node_id] ?? []),
      ])
    : null

  const maxCount = Math.max(...visibleNodes.map(n => n.ticket_count), 1)

  // ── Coordinate mapping ────────────────────────────────────────────────────
  function toSvgX(nx: number) { return PAD + nx * (SVG_W - 2 * PAD) }
  function toSvgY(ny: number) { return PAD + ny * (SVG_H - 2 * PAD) }

  const nodeIndex: Record<string, NetworkNode> = {}
  for (const n of visibleNodes) nodeIndex[n.node_id] = n

  // ── Auto-fit viewBox when drilling in ────────────────────────────────────
  function fitToNodes(nodes: NetworkNode[]) {
    if (nodes.length === 0) return
    const xs = nodes.map(n => toSvgX(n.x_pos))
    const ys = nodes.map(n => toSvgY(n.y_pos))
    const minX = Math.min(...xs) - 40
    const maxX = Math.max(...xs) + 40
    const minY = Math.min(...ys) - 40
    const maxY = Math.max(...ys) + 40
    setViewBox({ x: minX, y: minY, w: maxX - minX, h: maxY - minY })
  }

  function resetView() {
    setViewBox({ x: 0, y: 0, w: SVG_W, h: SVG_H })
  }

  function zoomBy(factor: number) {
    setViewBox(v => {
      const cx = v.x + v.w / 2
      const cy = v.y + v.h / 2
      const newW = Math.min(Math.max(v.w * factor, 200), SVG_W * 3)
      const newH = Math.min(Math.max(v.h * factor, 120), SVG_H * 3)
      return { x: cx - newW / 2, y: cy - newH / 2, w: newW, h: newH }
    })
  }

  // ── Drill-in / drill-out ──────────────────────────────────────────────────
  function handleDrillIn(node: NetworkNode) {
    if (drilledRNC === node.node_id) {
      // Exit drill-down
      setDrilledRNC(null)
      resetView()
    } else {
      setDrilledRNC(node.node_id)
      const clusterNodes = allNodes.filter(
        n => n.node_id === node.node_id || n.parent_node === node.node_id
      )
      fitToNodes(clusterNodes)
    }
  }

  // ── Node click ────────────────────────────────────────────────────────────
  function handleNodeClick(e: React.MouseEvent, n: NetworkNode) {
    e.stopPropagation()
    setTooltip(null)
    if (selectedNode?.node_id === n.node_id) {
      setSelectedNode(null)
    } else {
      setSelectedNode(n)
    }
  }

  // ── Pan ───────────────────────────────────────────────────────────────────
  function onMouseDown(e: React.MouseEvent<SVGSVGElement>) {
    dragging.current = true
    lastPos.current = { x: e.clientX, y: e.clientY }
  }
  function onMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    if (!dragging.current) return
    const dx = e.clientX - lastPos.current.x
    const dy = e.clientY - lastPos.current.y
    lastPos.current = { x: e.clientX, y: e.clientY }
    setViewBox(v => ({
      ...v,
      x: v.x - dx * (v.w / SVG_W),
      y: v.y - dy * (v.h / SVG_H),
    }))
  }
  function onMouseUp() { dragging.current = false }

  function onWheel(e: React.WheelEvent<SVGSVGElement>) {
    e.preventDefault()
    const factor = e.deltaY > 0 ? 1.12 : 0.89
    setViewBox(v => {
      const cx = v.x + v.w / 2
      const cy = v.y + v.h / 2
      const newW = Math.min(Math.max(v.w * factor, 200), SVG_W * 3)
      const newH = Math.min(Math.max(v.h * factor, 120), SVG_H * 3)
      return { x: cx - newW / 2, y: cy - newH / 2, w: newW, h: newH }
    })
  }

  // ── Tooltip tracking ──────────────────────────────────────────────────────
  function nodeMouseEnter(e: React.MouseEvent, n: NetworkNode) {
    if (!containerRef.current) return
    const rect = containerRef.current.getBoundingClientRect()
    setTooltip({ node: n, x: e.clientX - rect.left, y: e.clientY - rect.top })
  }
  function nodeMouseMove(e: React.MouseEvent) {
    if (!containerRef.current || !tooltip) return
    const rect = containerRef.current.getBoundingClientRect()
    setTooltip(t => t ? { ...t, x: e.clientX - rect.left, y: e.clientY - rect.top } : null)
  }
  function nodeMouseLeave() { setTooltip(null) }

  // ── Render ────────────────────────────────────────────────────────────────
  const filterBtns: FilterType[] = ['All', '3G', '4G', '5G']

  if (isLoading) {
    return (
      <div className="w-full h-64 flex items-center justify-center">
        <div className="text-slate-400 text-sm animate-pulse">Loading network topology…</div>
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="w-full h-32 flex items-center justify-center text-slate-500 text-sm">
        Network topology unavailable. Run{' '}
        <code className="mx-1 text-xs bg-slate-700 px-1 rounded">POST /api/v1/network/refresh</code>{' '}
        to build it.
      </div>
    )
  }

  return (
    <div ref={containerRef} className="relative select-none">
      {/* Controls row */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          {/* Breadcrumb */}
          {drilledRNC ? (
            <div className="flex items-center gap-1.5 text-xs">
              <button
                onClick={() => { setDrilledRNC(null); resetView(); setSelectedNode(null) }}
                className="text-slate-400 hover:text-white transition-colors underline underline-offset-2"
              >
                All Networks
              </button>
              <ChevronRight size={12} className="text-slate-600" />
              <span className="font-mono text-white">{drilledRNC}</span>
              <span className="text-slate-500">
                ({(childrenOf[drilledRNC]?.length ?? 0) + 1} nodes)
              </span>
            </div>
          ) : (
            <div className="flex gap-1.5">
              {filterBtns.map(f => (
                <button
                  key={f}
                  onClick={() => { setFilter(f); setSelectedNode(null) }}
                  className={`px-3 py-1 text-xs rounded-md font-medium transition-colors ${
                    filter === f
                      ? 'text-white'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                  style={filter === f ? { backgroundColor: '#E60028' } : undefined}
                >
                  {f}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex gap-3 items-center text-xs">
          <span className="text-slate-400">
            <span className="text-white font-semibold">{data.summary.total_nodes}</span> nodes ·{' '}
            <span className="text-red-400 font-semibold">{data.summary.nodes_with_pending}</span> pending
          </span>
          {/* Zoom controls */}
          <div className="flex gap-1 items-center" role="group" aria-label="Zoom controls">
            <button
              onClick={() => zoomBy(0.625)}
              disabled={viewBox.w <= 210}
              aria-label="Zoom in"
              className="flex items-center justify-center w-7 h-7 rounded-lg border border-slate-600 bg-slate-800 hover:bg-slate-700 hover:border-slate-500 text-slate-400 hover:text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1 focus-visible:ring-offset-slate-900"
            >
              <ZoomIn size={13} />
            </button>
            <button
              onClick={() => { resetView(); setSelectedNode(null); setDrilledRNC(null) }}
              aria-label="Reset zoom and pan"
              className="flex items-center justify-center w-7 h-7 rounded-lg border border-slate-600 bg-slate-800 hover:bg-slate-700 hover:border-slate-500 text-slate-400 hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1 focus-visible:ring-offset-slate-900"
            >
              <RotateCcw size={13} />
            </button>
            <button
              onClick={() => zoomBy(1.6)}
              disabled={viewBox.w >= SVG_W * 2.8}
              aria-label="Zoom out"
              className="flex items-center justify-center w-7 h-7 rounded-lg border border-slate-600 bg-slate-800 hover:bg-slate-700 hover:border-slate-500 text-slate-400 hover:text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1 focus-visible:ring-offset-slate-900"
            >
              <ZoomOut size={13} />
            </button>
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="flex gap-4 mb-3 text-xs text-slate-400">
        {[
          { color: '#E60028', label: 'Pending review' },
          { color: '#F59E0B', label: 'Open / active' },
          { color: '#22C55E', label: 'All resolved' },
          { color: '#475569', label: 'No tickets' },
        ].map(({ color, label }) => (
          <span key={label} className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full inline-block flex-shrink-0" style={{ background: color }} />
            {label}
          </span>
        ))}
        {selectedNode && (
          <span className="text-slate-500 ml-auto">Click node to deselect · click RNC for cluster details</span>
        )}
      </div>

      {/* Main area: SVG + optional detail panel */}
      <div className={`flex rounded-lg border border-slate-700 overflow-hidden bg-slate-900/60 ${selectedNode ? '' : ''}`}>
        {/* SVG Canvas */}
        <div className="flex-1 min-w-0">
          <svg
            ref={svgRef}
            width="100%"
            viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`}
            role="img"
            aria-label={`Network topology — ${visibleNodes.length} nodes, ${data.summary.nodes_with_pending} pending review`}
            tabIndex={0}
            style={{
              height: selectedNode ? 480 : 500,
              cursor: dragging.current ? 'grabbing' : 'grab',
              display: 'block',
              outline: 'none',
            }}
            onMouseDown={onMouseDown}
            onMouseMove={onMouseMove}
            onMouseUp={onMouseUp}
            onMouseLeave={onMouseUp}
            onWheel={onWheel}
            onClick={() => setSelectedNode(null)}
            onKeyDown={e => {
              const PAN = 60
              if (e.key === 'ArrowRight') setViewBox(v => ({ ...v, x: v.x + PAN }))
              else if (e.key === 'ArrowLeft')  setViewBox(v => ({ ...v, x: v.x - PAN }))
              else if (e.key === 'ArrowDown')  setViewBox(v => ({ ...v, y: v.y + PAN }))
              else if (e.key === 'ArrowUp')    setViewBox(v => ({ ...v, y: v.y - PAN }))
              else if (e.key === '+' || e.key === '=') zoomBy(0.625)
              else if (e.key === '-') zoomBy(1.6)
              else if (e.key === '0') resetView()
              else return
              e.preventDefault()
            }}
            onFocus={e => { (e.currentTarget as SVGSVGElement).style.outline = '2px solid #3b82f6' }}
            onBlur={e => { (e.currentTarget as SVGSVGElement).style.outline = 'none' }}
          >
            {/* Edges */}
            <g>
              {visibleEdges.map(e => {
                const s = nodeIndex[e.source_node]
                const t = nodeIndex[e.target_node]
                if (!s || !t) return null
                const isHighlighted =
                  !highlightedIds ||
                  (highlightedIds.has(e.source_node) && highlightedIds.has(e.target_node))
                return (
                  <line
                    key={e.edge_id}
                    x1={toSvgX(s.x_pos)} y1={toSvgY(s.y_pos)}
                    x2={toSvgX(t.x_pos)} y2={toSvgY(t.y_pos)}
                    stroke="#94a3b8"
                    strokeWidth={isHighlighted ? 1.2 : 0.6}
                    opacity={isHighlighted ? 0.4 : 0.08}
                  />
                )
              })}
            </g>

            {/* Nodes */}
            {visibleNodes.map(n => {
              const cx = toSvgX(n.x_pos)
              const cy = toSvgY(n.y_pos)
              const r  = nodeRadius(n, maxCount)
              const color = nodeColor(n)
              const isRnc = n.node_class === 'RNC'
              const isSelected = selectedNode?.node_id === n.node_id
              const dimmed = highlightedIds !== null && !highlightedIds.has(n.node_id)

              return (
                <g
                  key={n.node_id}
                  onClick={ev => handleNodeClick(ev, n)}
                  onMouseEnter={ev => !isSelected && nodeMouseEnter(ev, n)}
                  onMouseMove={nodeMouseMove}
                  onMouseLeave={nodeMouseLeave}
                  style={{ cursor: 'pointer' }}
                  opacity={dimmed ? 0.15 : 1}
                >
                  {/* Selection ring */}
                  {isSelected && (
                    <circle cx={cx} cy={cy} r={r + 5} fill="none" stroke="#ffffff" strokeWidth={1.5} opacity={0.6} />
                  )}
                  {/* Glow ring for pending nodes */}
                  {!isSelected && n.pending_count > 0 && (
                    <circle cx={cx} cy={cy} r={r + 3} fill="none" stroke="#E60028" strokeWidth={1.2} opacity={0.35} />
                  )}
                  <circle
                    cx={cx} cy={cy} r={isSelected ? r + 1 : r}
                    fill={color}
                    stroke={isSelected ? '#ffffff' : isRnc ? '#e2e8f0' : color}
                    strokeWidth={isSelected ? 2 : isRnc ? 1.5 : 0.5}
                    opacity={0.9}
                  />
                  {/* RNC label */}
                  {isRnc && (
                    <text
                      x={cx} y={cy + r + 10}
                      textAnchor="middle"
                      fontSize={7}
                      fill={isSelected ? '#ffffff' : '#94a3b8'}
                      style={{ pointerEvents: 'none', userSelect: 'none' }}
                    >
                      {n.node_id}
                    </text>
                  )}
                </g>
              )
            })}

            {/* Zone labels (only in full view) */}
            {!drilledRNC && filter === 'All' && (
              <>
                <text x={toSvgX(0.16)} y={toSvgY(0.01)} textAnchor="middle" fontSize={11} fill="#475569" fontWeight="600">3G</text>
                <text x={toSvgX(0.50)} y={toSvgY(0.01)} textAnchor="middle" fontSize={11} fill="#475569" fontWeight="600">4G</text>
                <text x={toSvgX(0.84)} y={toSvgY(0.01)} textAnchor="middle" fontSize={11} fill="#475569" fontWeight="600">5G</text>
              </>
            )}
          </svg>
        </div>

        {/* Detail panel */}
        {selectedNode && (
          <DetailPanel
            node={selectedNode}
            children={childrenOf[selectedNode.node_id] ?? []}
            onClose={() => setSelectedNode(null)}
            onDrillIn={handleDrillIn}
            isDrilled={drilledRNC === selectedNode.node_id}
          />
        )}
      </div>

      <p className="text-xs text-slate-600 mt-2">
        Scroll or use +/− buttons to zoom · drag to pan · click node for details · keyboard: Arrow keys pan, +/− zoom, 0 resets
      </p>

      {/* Tooltip (only when no node is selected) */}
      {tooltip && !selectedNode && <Tooltip tip={tooltip} />}
    </div>
  )
}
