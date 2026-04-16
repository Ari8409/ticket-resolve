import React, { useState, useRef, useEffect, useCallback } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Send, Bot, BarChart2, List, HelpCircle, Zap, Activity, Users, CheckCircle, ThumbsUp, ThumbsDown } from 'lucide-react'
import { api, ChatMessage, ChatFeedbackRequest, TelcoTicket, TriageSummary } from '../api/client'
import { SeverityBadge, StatusBadge } from '../components/shared/Badges'
import { useToast } from '../components/shared/Toast'

// ─── Simple Markdown renderer ──────────────────────────────────────────────────

function renderMarkdown(text: string): React.ReactNode[] {
  const lines = text.split('\n')
  const elements: React.ReactNode[] = []
  let i = 0
  let key = 0

  while (i < lines.length) {
    const line = lines[i]

    // Code block
    if (line.startsWith('```')) {
      const codeLines: string[] = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) {
        codeLines.push(lines[i])
        i++
      }
      elements.push(
        <pre key={key++} className="bg-slate-900 rounded-lg p-3 text-xs font-mono text-slate-300 overflow-x-auto my-2 border border-slate-700">
          <code>{codeLines.join('\n')}</code>
        </pre>
      )
      i++
      continue
    }

    // Heading
    if (line.startsWith('### ')) {
      elements.push(<h3 key={key++} className="text-sm font-semibold text-white mt-3 mb-1">{renderInline(line.slice(4))}</h3>)
      i++
      continue
    }
    if (line.startsWith('## ')) {
      elements.push(<h2 key={key++} className="text-base font-semibold text-white mt-3 mb-1">{renderInline(line.slice(3))}</h2>)
      i++
      continue
    }

    // Bullet list
    if (line.startsWith('- ') || line.startsWith('* ')) {
      const items: string[] = []
      while (i < lines.length && (lines[i].startsWith('- ') || lines[i].startsWith('* '))) {
        items.push(lines[i].slice(2))
        i++
      }
      elements.push(
        <ul key={key++} className="list-none space-y-1 my-2">
          {items.map((item, idx) => (
            <li key={idx} className="flex items-start gap-2 text-sm text-slate-300">
              <span className="text-singtel-light mt-0.5">•</span>
              <span>{renderInline(item)}</span>
            </li>
          ))}
        </ul>
      )
      continue
    }

    // Numbered list
    if (/^\d+\.\s/.test(line)) {
      const items: string[] = []
      let num = 1
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s/, ''))
        i++
        num++
      }
      elements.push(
        <ol key={key++} className="space-y-1 my-2">
          {items.map((item, idx) => (
            <li key={idx} className="flex items-start gap-2 text-sm text-slate-300">
              <span className="text-singtel-light font-mono text-xs mt-0.5 w-4">{idx + 1}.</span>
              <span>{renderInline(item)}</span>
            </li>
          ))}
        </ol>
      )
      continue
    }

    // Horizontal rule
    if (line.startsWith('---') || line.startsWith('===')) {
      elements.push(<hr key={key++} className="border-slate-700 my-3" />)
      i++
      continue
    }

    // Empty line
    if (line.trim() === '') {
      elements.push(<div key={key++} className="h-2" />)
      i++
      continue
    }

    // Paragraph
    elements.push(
      <p key={key++} className="text-sm text-slate-300 leading-relaxed">
        {renderInline(line)}
      </p>
    )
    i++
  }

  return elements
}

function renderInline(text: string): React.ReactNode {
  // Bold: **text**
  // Inline code: `code`
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} className="text-white font-semibold">{part.slice(2, -2)}</strong>
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code key={i} className="bg-slate-900 text-singtel-lighter rounded px-1 py-0.5 text-xs font-mono">
          {part.slice(1, -1)}
        </code>
      )
    }
    return part
  })
}

// ─── Data Cards ────────────────────────────────────────────────────────────────

function StatsDataCard({ data }: { data: Record<string, number> }) {
  const items = [
    { label: 'Total', value: data.total ?? 0, icon: <Activity className="w-4 h-4 text-singtel-light" />, color: 'text-singtel-light' },
    { label: 'Open', value: data.open ?? 0, icon: <Activity className="w-4 h-4 text-amber-400" />, color: 'text-amber-400' },
    { label: 'Pending Review', value: data.pending_review ?? 0, icon: <Users className="w-4 h-4 text-red-400" />, color: 'text-red-400' },
    { label: 'Resolved', value: data.resolved ?? 0, icon: <CheckCircle className="w-4 h-4 text-green-400" />, color: 'text-green-400' },
  ]
  return (
    <div className="grid grid-cols-2 gap-2 mt-3">
      {items.map((item) => (
        <div key={item.label} className="bg-slate-900 rounded-lg p-3 border border-slate-700 flex items-center gap-2">
          {item.icon}
          <div>
            <p className={`text-lg font-bold ${item.color}`}>{item.value}</p>
            <p className="text-xs text-slate-500">{item.label}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

function TicketListDataCard({ data }: { data: TriageSummary[] | TelcoTicket[] }) {
  const items = data.slice(0, 5)
  return (
    <div className="mt-3 space-y-2">
      {items.map((item: TriageSummary | TelcoTicket) => {
        const id = 'ticket_id' in item ? item.ticket_id : ''
        const node = 'affected_node' in item ? item.affected_node : ''
        const severity = 'severity' in item ? item.severity : ''
        const faultType = 'fault_type' in item ? item.fault_type : ''
        return (
          <div key={id} className="bg-slate-900 rounded-lg p-3 border border-slate-700">
            <div className="flex items-center justify-between mb-1">
              <span className="font-mono text-xs text-singtel-light">{id}</span>
              <SeverityBadge severity={severity} />
            </div>
            <p className="text-xs text-slate-300">{node}</p>
            <p className="text-xs text-slate-500">{faultType}</p>
          </div>
        )
      })}
    </div>
  )
}

function TicketDetailCard({ data }: { data: TelcoTicket }) {
  return (
    <div className="mt-3 bg-slate-900 rounded-lg border border-slate-700 p-4">
      <div className="flex items-start justify-between mb-3">
        <span className="font-mono text-sm text-singtel-light">{data.ticket_id}</span>
        <div className="flex gap-2">
          <SeverityBadge severity={data.severity} />
          <StatusBadge status={data.status} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        <div>
          <p className="text-slate-500">Node</p>
          <p className="text-slate-300">{data.affected_node}</p>
        </div>
        <div>
          <p className="text-slate-500">Fault Type</p>
          <p className="text-slate-300">{data.fault_type}</p>
        </div>
        <div>
          <p className="text-slate-500">Network</p>
          <p className="text-slate-300">{data.network_type ?? '—'}</p>
        </div>
        <div>
          <p className="text-slate-500">Assigned To</p>
          <p className="text-slate-300">{data.assigned_to ?? 'Unassigned'}</p>
        </div>
      </div>
      {data.description && (
        <p className="text-xs text-slate-400 mt-3 pt-3 border-t border-slate-700 line-clamp-2">{data.description}</p>
      )}
    </div>
  )
}

// ─── Execution Tree Card ──────────────────────────────────────────────────────

interface ExecutionTreeData {
  ticket_id: string
  mode: 'resolution' | 'pending'
  final_status: string
  alarm_name?: string | null
  affected_node?: string | null
  fault_type?: string | null
  network_type?: string | null
  gate_passed: boolean
  similar_ticket_ids?: string[]
  relevant_sops?: string[]
  confidence_score?: number
  dispatch_mode?: string | null
  reasoning?: string
  resolution_steps?: string[]
  pending_reasons?: string[]
  assigned_to?: string | null
  short_circuited?: boolean
  alarm_status?: string | null
  remote_feasible?: boolean | null
}

const REASON_LABELS: Record<string, string> = {
  no_similar_ticket:       'No historical ticket match (score < 0.60)',
  no_sop_match:            'No SOP match found (score < 0.45)',
  LOW_CONFIDENCE:          'Pipeline confidence below threshold',
  NO_SOP_MATCH:            'No matching SOP in knowledge base',
  NO_HISTORICAL_PRECEDENT: 'No similar resolved ticket in history',
  UNKNOWN_FAULT_TYPE:      'Fault type could not be classified',
}

function PipelineStage({
  step, label, content, status,
}: {
  step: number
  label: string
  content: React.ReactNode
  status: 'pass' | 'fail' | 'info' | 'neutral'
}) {
  const colors = {
    pass:    'border-green-500/40 bg-green-500/5',
    fail:    'border-red-500/40 bg-red-500/5',
    info:    'border-singtel/40 bg-singtel/5',
    neutral: 'border-slate-600/40 bg-slate-700/20',
  }
  const dotColors = {
    pass:    'bg-green-500',
    fail:    'bg-red-500',
    info:    'bg-singtel',
    neutral: 'bg-slate-500',
  }
  return (
    <div className={`rounded-lg border px-3 py-2.5 ${colors[status]}`}>
      <div className="flex items-start gap-2">
        <div className="flex items-center gap-1.5 flex-shrink-0 pt-0.5">
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${dotColors[status]}`} />
          <span className="text-xs font-mono text-slate-500 w-4">[{step}]</span>
          <span className="text-xs font-semibold text-slate-400 w-14">{label}</span>
        </div>
        <div className="text-xs text-slate-300 flex-1">{content}</div>
      </div>
    </div>
  )
}

function ExecutionTreeCard({ data }: { data: ExecutionTreeData }) {
  const isResolved = data.mode === 'resolution'
  const conf       = data.confidence_score ?? 0
  const simIds     = data.similar_ticket_ids ?? []
  const sops       = data.relevant_sops ?? []
  const steps      = data.resolution_steps ?? []
  const reasons    = data.pending_reasons ?? []
  const dispatch   = (data.dispatch_mode ?? '').toUpperCase()

  return (
    <div className="mt-3 bg-slate-900 rounded-xl border border-slate-700 overflow-hidden">
      {/* Header */}
      <div className={`flex items-center justify-between px-4 py-2.5 border-b border-slate-700 ${isResolved ? 'bg-green-900/20' : 'bg-red-900/20'}`}>
        <div className="flex items-center gap-2">
          <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${isResolved ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
            {isResolved ? 'RESOLVED' : 'PENDING REVIEW'}
          </span>
          <span className="font-mono text-xs text-singtel-light">{data.ticket_id}</span>
        </div>
        <span className="text-xs text-slate-500">Execution Tree</span>
      </div>

      {/* Pipeline stages */}
      <div className="p-3 space-y-2">
        {/* Stage 1: Fault */}
        <PipelineStage step={1} label="Fault" status="neutral" content={
          <span>
            <span className="text-white font-medium">{data.alarm_name || data.fault_type || 'Unknown'}</span>
            {' · '}
            <code className="bg-slate-800 px-1 rounded text-singtel-lighter">{data.affected_node}</code>
            {data.network_type && <span className="text-slate-500 ml-1">({data.network_type})</span>}
          </span>
        } />

        {/* Stage 2: Vector Search */}
        <PipelineStage step={2} label="Search" status={simIds.length > 0 || sops.length > 0 ? 'pass' : 'fail'} content={
          <div className="space-y-0.5">
            <div>
              <span className="text-slate-500">Similar ticket: </span>
              {simIds.length > 0
                ? <code className="bg-slate-800 px-1 rounded text-green-400">{simIds[0]}</code>
                : <span className="text-red-400">none found</span>}
            </div>
            <div>
              <span className="text-slate-500">SOP match: </span>
              {sops.length > 0
                ? <code className="bg-slate-800 px-1 rounded text-green-400">{sops[0]}</code>
                : <span className="text-slate-500">none</span>}
            </div>
          </div>
        } />

        {/* Stage 3: Gate */}
        <PipelineStage step={3} label="Gate" status={data.gate_passed ? 'pass' : 'fail'} content={
          <span>
            <span className={`font-semibold ${data.gate_passed ? 'text-green-400' : 'text-red-400'}`}>
              {data.gate_passed ? 'PASSED' : 'FAILED'}
            </span>
            {data.reasoning && (
              <span className="text-slate-400 ml-2">— {data.reasoning}</span>
            )}
          </span>
        } />

        {/* Stage 4: Decision / Result */}
        {isResolved ? (
          <PipelineStage step={4} label="Action" status="info" content={
            <div className="flex items-center gap-3">
              <span className="font-semibold text-singtel-light">{dispatch || 'N/A'}</span>
              <div className="flex items-center gap-1.5">
                <div className="w-20 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-singtel rounded-full"
                    style={{ width: `${Math.round(conf * 100)}%` }}
                  />
                </div>
                <span className="text-slate-400">{Math.round(conf * 100)}%</span>
              </div>
            </div>
          } />
        ) : (
          <PipelineStage step={4} label="Result" status="fail" content={
            <div className="space-y-1">
              <span className="text-red-400 font-semibold">Human Review Required</span>
              {reasons.length > 0 && (
                <ul className="space-y-0.5 mt-1">
                  {reasons.map((r) => (
                    <li key={r} className="text-slate-400">
                      · {REASON_LABELS[r] ?? r.replace(/_/g, ' ')}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          } />
        )}

        {/* Stage 5: Resolution Steps (resolved only) */}
        {isResolved && steps.length > 0 && (
          <PipelineStage step={5} label="Steps" status="neutral" content={
            <div>
              <span className="text-slate-400">{steps.length} steps · </span>
              <span className="text-slate-300">{steps[0].slice(0, 60)}{steps[0].length > 60 ? '…' : ''}</span>
              {steps.length > 1 && (
                <span className="text-slate-500"> + {steps.length - 1} more</span>
              )}
            </div>
          } />
        )}

        {/* Assignment (pending only) */}
        {!isResolved && (
          <PipelineStage step={5} label="Assign" status={data.assigned_to ? 'pass' : 'neutral'} content={
            data.assigned_to
              ? <span>Assigned to <code className="bg-slate-800 px-1 rounded text-slate-300">{data.assigned_to}</code></span>
              : <span className="text-slate-500">Unassigned — pending engineer routing</span>
          } />
        )}
      </div>
    </div>
  )
}

function DataCard({ intent, data }: { intent?: string; data?: unknown }) {
  if (!data) return null
  if (intent === 'stats' && typeof data === 'object' && data !== null) {
    return <StatsDataCard data={data as Record<string, number>} />
  }
  if ((intent === 'pending_queue' || intent === 'ticket_list') && Array.isArray(data)) {
    return <TicketListDataCard data={data as TriageSummary[] | TelcoTicket[]} />
  }
  if (intent === 'show_ticket' && typeof data === 'object' && data !== null && !Array.isArray(data)) {
    const d = data as Record<string, unknown>
    return <TicketDetailCard data={(d.ticket ?? d) as TelcoTicket} />
  }
  if ((intent === 'resolution_tree' || intent === 'pending_tree') && typeof data === 'object' && data !== null) {
    return <ExecutionTreeCard data={data as ExecutionTreeData} />
  }
  return null
}

// ─── Feedback Bar ──────────────────────────────────────────────────────────────

interface FeedbackBarProps {
  message: ChatMessage
  precedingUserText: string
}

function FeedbackBar({ message, precedingUserText }: FeedbackBarProps) {
  const [rated, setRated] = useState<1 | -1 | null>(null)
  const [comment, setComment] = useState('')
  const [commentSent, setCommentSent] = useState(false)
  const { showToast } = useToast()

  const mutation = useMutation({
    mutationFn: (req: ChatFeedbackRequest) => api.submitChatFeedback(req),
    onSuccess: (res) => {
      if (res.indexed) {
        showToast('Thanks! Your feedback will help improve future responses.', 'success')
      } else {
        showToast('Feedback saved.', 'info')
      }
    },
    onError: () => {
      showToast('Could not save feedback — please try again.', 'error')
      setRated(null)
    },
  })

  const submit = (rating: 1 | -1) => {
    if (rated !== null || !message.message_id) return
    setRated(rating)
    mutation.mutate({
      message_id: message.message_id,
      rating,
      query_text: precedingUserText,
      response_text: message.content,
      intent: message.intent,
      engineer_id: 'NOC Engineer',
    })
  }

  const submitComment = () => {
    if (!comment.trim() || commentSent || !message.message_id) return
    setCommentSent(true)
    mutation.mutate({
      message_id: `${message.message_id}-note`,
      rating: 1,
      comment: comment.trim(),
      query_text: precedingUserText,
      response_text: message.content,
      intent: message.intent,
      engineer_id: 'NOC Engineer',
    })
  }

  return (
    <div className="flex flex-col gap-1 mt-1.5 pl-1">
      <div className="flex items-center gap-2">
        <span className="text-xs text-slate-600">Was this helpful?</span>
        <button
          onClick={() => submit(1)}
          disabled={rated !== null || mutation.isPending}
          title="Helpful"
          className={`p-1 rounded transition-colors ${
            rated === 1
              ? 'text-green-400'
              : 'text-slate-600 hover:text-green-400 disabled:opacity-40'
          }`}
        >
          <ThumbsUp size={13} />
        </button>
        <button
          onClick={() => submit(-1)}
          disabled={rated !== null || mutation.isPending}
          title="Not helpful"
          className={`p-1 rounded transition-colors ${
            rated === -1
              ? 'text-red-400'
              : 'text-slate-600 hover:text-red-400 disabled:opacity-40'
          }`}
        >
          <ThumbsDown size={13} />
        </button>
      </div>

      {/* Optional comment input after thumbs-up */}
      {rated === 1 && !commentSent && (
        <div className="flex items-center gap-2 mt-1">
          <input
            type="text"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submitComment()}
            placeholder="Add a note (optional)"
            maxLength={500}
            className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-singtel"
          />
          <button
            onClick={submitComment}
            disabled={!comment.trim()}
            className="px-2 py-1.5 text-xs bg-singtel/20 hover:bg-singtel/40 text-singtel-light rounded-lg transition-colors disabled:opacity-40"
          >
            Send
          </button>
        </div>
      )}
      {commentSent && (
        <p className="text-xs text-green-500">Note sent ✓</p>
      )}
    </div>
  )
}

// ─── Message Bubble ────────────────────────────────────────────────────────────

function MessageBubble({
  message,
  precedingUserText,
  onSuggestedAction,
}: {
  message: ChatMessage
  precedingUserText: string
  onSuggestedAction: (text: string) => void
}) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${
          isUser ? 'bg-singtel text-white' : 'bg-slate-700 text-slate-300'
        }`}
      >
        {isUser ? 'NE' : <Bot className="w-4 h-4" />}
      </div>

      {/* Content */}
      <div className={`flex flex-col max-w-[80%] ${isUser ? 'items-end' : 'items-start'}`}>
        <div
          className={`rounded-2xl px-4 py-3 ${
            isUser
              ? 'bg-singtel text-white rounded-tr-sm'
              : 'bg-slate-800 border border-slate-700 rounded-tl-sm'
          }`}
        >
          {isUser ? (
            <p className="text-sm leading-relaxed">{message.content}</p>
          ) : (
            <div>{renderMarkdown(message.content)}</div>
          )}
        </div>

        {/* Data Card */}
        {!isUser && message.data && (
          <div className="w-full">
            <DataCard intent={message.intent} data={message.data} />
          </div>
        )}

        {/* Suggested action chips */}
        {!isUser && message.suggested_actions && message.suggested_actions.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2">
            {message.suggested_actions.map((action) => (
              <button
                key={action}
                onClick={() => onSuggestedAction(action)}
                className="text-xs px-3 py-1 bg-slate-700 hover:bg-slate-600 text-singtel-light border border-slate-600 rounded-full transition-colors"
              >
                {action}
              </button>
            ))}
          </div>
        )}

        {/* Feedback bar — only for assistant messages that have a message_id */}
        {!isUser && message.message_id && message.id !== 'welcome' && (
          <FeedbackBar message={message} precedingUserText={precedingUserText} />
        )}

        <p className="text-xs text-slate-600 mt-1 px-1">
          {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </p>
      </div>
    </div>
  )
}

// ─── Welcome Message ───────────────────────────────────────────────────────────

const WELCOME_MESSAGE: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  content: `👋 Welcome to the NOC Cognitive Assistant. I can help you:

- **Check ticket details** — \`show XLS-0001\`
- **Explain how a ticket was resolved** — \`how was XLS-0001 resolved?\`
- **Explain why a ticket needs human review** — \`why does XLS-0002 need human intervention?\`
- **View pending review queue** — \`show pending queue\`
- **Assign tickets** — \`assign XLS-0002 to ahmad.zulkifli\`
- **Dashboard stats** — \`show stats\`

Type **help** to see all available commands.`,
  timestamp: new Date().toISOString(),
}

// ─── Quick Reply Buttons ───────────────────────────────────────────────────────

const QUICK_REPLIES = [
  { label: 'Show stats', icon: <BarChart2 className="w-3.5 h-3.5" /> },
  { label: 'Show pending queue', icon: <List className="w-3.5 h-3.5" /> },
  { label: 'Help', icon: <HelpCircle className="w-3.5 h-3.5" /> },
]

// ─── Left Panel ────────────────────────────────────────────────────────────────

function LeftPanel({ onSend }: { onSend: (text: string) => void }) {
  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: api.getStats,
    refetchInterval: 30_000,
  })

  const { data: pending } = useQuery({
    queryKey: ['pending-review'],
    queryFn: () => api.getPendingReview(5),
    refetchInterval: 30_000,
  })

  const suggestions = [
    'Show all open tickets',
    'Show pending review queue',
    'How was XLS-0001 resolved?',
    'Why does XLS-0002 need human intervention?',
    'Show stats',
  ]

  return (
    <div className="flex flex-col h-full bg-slate-800/50 border-r border-slate-700/50 overflow-y-auto">
      <div className="p-4 border-b border-slate-700/50">
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Quick Actions</h3>
        <div className="space-y-2">
          {suggestions.map((s) => (
            <button
              key={s}
              onClick={() => onSend(s)}
              className="w-full text-left px-3 py-2 text-xs text-slate-300 bg-slate-800 hover:bg-slate-700 border border-slate-700/50 rounded-lg transition-colors flex items-center gap-2"
            >
              <Zap className="w-3 h-3 text-singtel-light flex-shrink-0" />
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Mini stats */}
      {stats && (
        <div className="p-4 border-b border-slate-700/50">
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Live Stats</h3>
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: 'Total', value: stats.total, color: 'text-singtel-light' },
              { label: 'Open', value: stats.open, color: 'text-amber-400' },
              { label: 'Pending', value: stats.pending_review, color: 'text-red-400' },
              { label: 'Resolved', value: stats.resolved, color: 'text-green-400' },
            ].map((item) => (
              <div key={item.label} className="bg-slate-800 rounded-lg p-2.5 text-center border border-slate-700/50">
                <p className={`text-xl font-bold ${item.color}`}>{item.value}</p>
                <p className="text-xs text-slate-500">{item.label}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent pending tickets */}
      {pending && pending.length > 0 && (
        <div className="p-4">
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Pending Review</h3>
          <div className="space-y-2">
            {pending.slice(0, 4).map((t) => (
              <button
                key={t.ticket_id}
                onClick={() => onSend(`Show details for ticket ${t.ticket_id}`)}
                className="w-full text-left bg-slate-800 border border-slate-700/50 hover:border-slate-600 rounded-lg p-3 transition-colors"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-xs text-singtel-light">{t.ticket_id}</span>
                  <SeverityBadge severity={t.severity} />
                </div>
                <p className="text-xs text-slate-400 truncate">{t.affected_node}</p>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main Chat Page ────────────────────────────────────────────────────────────

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE])
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const { showToast } = useToast()

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  const mutation = useMutation({
    mutationFn: (message: string) =>
      api.chat({
        message,
        engineer_id: 'NOC Engineer',
        history: messages
          .filter((m) => m.id !== 'welcome')
          .map((m) => ({ role: m.role, content: m.content }))
          .slice(-10),
      }),
    onSuccess: (response) => {
      const assistantMsg: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: response.reply,
        intent: response.intent,
        data: response.data,
        suggested_actions: response.suggested_actions,
        timestamp: response.timestamp,
        message_id: response.message_id,
      }
      setMessages((prev) => [...prev, assistantMsg])
    },
    onError: () => {
      showToast('Failed to send message. Check if the API is running.', 'error')
      const errorMsg: ChatMessage = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: 'Sorry, I encountered an error connecting to the backend. Please check that the API is running at `http://localhost:8000`.',
        timestamp: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, errorMsg])
    },
  })

  const sendMessage = useCallback(
    (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || mutation.isPending) return

      const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: trimmed,
        timestamp: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, userMsg])
      setInput('')
      mutation.mutate(trimmed)
    },
    [mutation]
  )

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  return (
    <div className="flex h-full -m-6 rounded-none overflow-hidden" style={{ height: 'calc(100vh - 73px)' }}>
      {/* Left panel */}
      <div className="w-72 flex-shrink-0">
        <LeftPanel onSend={sendMessage} />
      </div>

      {/* Right chat area */}
      <div className="flex flex-col flex-1 bg-slate-900 overflow-hidden">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {messages.map((message, idx) => {
            // Find the last user message before this assistant message
            const precedingUserText = message.role === 'assistant'
              ? (messages.slice(0, idx).reverse().find((m) => m.role === 'user')?.content ?? '')
              : ''
            return (
              <MessageBubble
                key={message.id}
                message={message}
                precedingUserText={precedingUserText}
                onSuggestedAction={sendMessage}
              />
            )
          })}

          {/* Loading */}
          {mutation.isPending && (
            <div className="flex gap-3">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center">
                <Bot className="w-4 h-4 text-slate-400" />
              </div>
              <div className="bg-slate-800 border border-slate-700 rounded-2xl rounded-tl-sm px-4 py-3">
                <div className="flex gap-1 items-center h-5">
                  <span className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input area */}
        <div className="flex-shrink-0 border-t border-slate-700/50 bg-slate-900 px-4 py-3">
          {/* Quick reply row */}
          <div className="flex gap-2 mb-3 overflow-x-auto pb-1 scrollbar-thin">
            {QUICK_REPLIES.map((qr) => (
              <button
                key={qr.label}
                onClick={() => sendMessage(qr.label)}
                disabled={mutation.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-400 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-full whitespace-nowrap transition-colors disabled:opacity-50"
              >
                {qr.icon}
                {qr.label}
              </button>
            ))}
          </div>

          {/* Text input row */}
          <div className="flex gap-3 items-end">
            <div className="flex-1 relative">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask anything about your network... (Enter to send, Shift+Enter for newline)"
                rows={1}
                disabled={mutation.isPending}
                className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-singtel transition-colors resize-none disabled:opacity-50 pr-12"
                style={{ maxHeight: '120px', overflowY: 'auto' }}
                onInput={(e) => {
                  const target = e.target as HTMLTextAreaElement
                  target.style.height = 'auto'
                  target.style.height = Math.min(target.scrollHeight, 120) + 'px'
                }}
              />
            </div>
            <button
              onClick={() => sendMessage(input)}
              disabled={!input.trim() || mutation.isPending}
              className="flex-shrink-0 w-10 h-10 bg-singtel hover:bg-singtel-hover disabled:opacity-50 disabled:cursor-not-allowed rounded-xl flex items-center justify-center transition-colors shadow-lg shadow-singtel/20"
            >
              <Send className="w-4 h-4 text-white" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
