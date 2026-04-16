import React from 'react'
import { NavLink } from 'react-router-dom'
import { LayoutDashboard, AlertCircle, MessageSquare, Network, ClipboardList, Package } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'

export default function Sidebar() {
  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: api.getStats,
    refetchInterval: 30_000,
  })

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: api.getHealth,
    refetchInterval: 15_000,
    retry: 1,
  })

  const pendingCount = stats?.pending_review ?? 0
  const isHealthy = health?.status === 'ok'

  const navItems = [
    {
      to: '/dashboard',
      icon: <LayoutDashboard className="w-5 h-5" />,
      label: 'Dashboard',
      badge: null,
    },
    {
      to: '/triage',
      icon: <AlertCircle className="w-5 h-5" />,
      label: 'Triage Queue',
      badge: pendingCount > 0 ? pendingCount : null,
    },
    {
      to: '/chat',
      icon: <MessageSquare className="w-5 h-5" />,
      label: 'Chat Assistant',
      badge: null,
    },
    {
      to: '/sdlc',
      icon: <ClipboardList className="w-5 h-5" />,
      label: 'SDLC Dashboard',
      badge: null,
    },
    {
      to: '/deliverables',
      icon: <Package className="w-5 h-5" />,
      label: 'Deliverables',
      badge: null,
    },
  ]

  return (
    <aside className="flex flex-col w-64 bg-slate-900 border-r border-slate-700/50 h-full flex-shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-3 px-6 py-5 border-b border-slate-700/50">
        <div className="flex items-center justify-center w-9 h-9 bg-singtel rounded-lg shadow-md shadow-singtel/30">
          <Network className="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 className="text-base font-bold text-white leading-tight">NOC Platform</h1>
          <p className="text-xs text-slate-400">Operations Centre</p>
        </div>
      </div>

      {/* Nav */}
      <nav aria-label="Main navigation" className="flex-1 px-3 py-4 space-y-1">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex items-center justify-between gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                isActive
                  ? 'bg-singtel text-white shadow-lg shadow-singtel/20'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <div className="flex items-center gap-3">
                  <span
                    aria-hidden="true"
                    className={
                      isActive ? 'text-white' : 'text-slate-500 group-hover:text-slate-300'
                    }
                  >
                    {item.icon}
                  </span>
                  <span>{item.label}</span>
                </div>
                {item.badge !== null && (
                  <span
                    className={`inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full text-xs font-bold ${
                      isActive
                        ? 'bg-white/20 text-white'
                        : 'bg-red-500 text-white animate-pulse-slow'
                    }`}
                  >
                    {item.badge}
                    <span className="sr-only"> pending review tickets</span>
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Health status */}
      <div className="px-6 py-4 border-t border-slate-700/50">
        <div className="flex items-center gap-2">
          <div
            aria-hidden="true"
            className={`w-2 h-2 rounded-full flex-shrink-0 ${
              health === undefined
                ? 'bg-slate-500'
                : isHealthy
                ? 'bg-green-500 shadow-sm shadow-green-500/50'
                : 'bg-red-500 shadow-sm shadow-red-500/50'
            }`}
          />
          <span className="text-xs text-slate-400">
            {health === undefined
              ? 'Checking...'
              : isHealthy
              ? 'API Healthy'
              : 'API Unreachable'}
          </span>
        </div>
        <p className="text-xs text-slate-600 mt-1">v1.0.0</p>
      </div>
    </aside>
  )
}
