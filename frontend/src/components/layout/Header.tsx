import React from 'react'
import { useLocation } from 'react-router-dom'
import { RefreshCw, User } from 'lucide-react'

interface HeaderProps {
  autoRefresh: boolean
  setAutoRefresh: (v: boolean) => void
  lastUpdated: Date
}

const pageTitles: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/triage': 'Triage Queue',
  '/chat': 'Chat Assistant',
}

function formatLastUpdated(date: Date): string {
  const now = new Date()
  const diffSeconds = Math.floor((now.getTime() - date.getTime()) / 1000)
  if (diffSeconds < 5) return 'just now'
  if (diffSeconds < 60) return `${diffSeconds}s ago`
  const diffMinutes = Math.floor(diffSeconds / 60)
  if (diffMinutes < 60) return `${diffMinutes}m ago`
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function Header({ autoRefresh, setAutoRefresh, lastUpdated }: HeaderProps) {
  const location = useLocation()
  const title = pageTitles[location.pathname] ?? 'NOC Platform'

  return (
    <header aria-label="Page header" className="flex items-center justify-between px-6 py-4 bg-slate-900 border-b border-slate-700/50 flex-shrink-0">
      <h2 className="text-xl font-semibold text-white">{title}</h2>

      <div className="flex items-center gap-4">
        {/* Last updated */}
        <span className="text-xs text-slate-500">
          Updated{' '}
          <span className="text-slate-400">{formatLastUpdated(lastUpdated)}</span>
        </span>

        {/* Auto-refresh toggle */}
        <button
          onClick={() => setAutoRefresh(!autoRefresh)}
          aria-pressed={autoRefresh}
          aria-label={`Auto-refresh ${autoRefresh ? 'on' : 'off'} — toggles 30-second interval`}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
            autoRefresh
              ? 'bg-singtel/10 text-singtel-light border border-singtel/30 hover:bg-singtel/20'
              : 'bg-slate-800 text-slate-400 border border-slate-700 hover:bg-slate-700'
          }`}
        >
          <RefreshCw
            aria-hidden="true"
            className={`w-3.5 h-3.5 ${autoRefresh ? 'animate-spin' : ''}`}
            style={autoRefresh ? { animationDuration: '3s' } : {}}
          />
          Auto-refresh {autoRefresh ? 'ON' : 'OFF'}
        </button>

        {/* Engineer badge */}
        <div aria-hidden="true" className="flex items-center gap-2 bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5">
          <div className="flex items-center justify-center w-6 h-6 bg-singtel rounded-full">
            <User className="w-3.5 h-3.5 text-white" />
          </div>
          <span className="text-sm text-slate-300 font-medium">NOC Engineer</span>
        </div>
      </div>
    </header>
  )
}
