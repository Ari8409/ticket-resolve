/**
 * TicketLocationMapWidget — interactive Leaflet map of Singapore
 * showing geocoded ticket locations as circle markers.
 *
 * Fetches GET /api/v1/telco-tickets/location-summary which handles
 * Nominatim geocoding + SQLite caching server-side. After first load
 * all coordinates are cached and the endpoint responds instantly.
 */

import 'leaflet/dist/leaflet.css'
import React from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import { useQuery } from '@tanstack/react-query'
import { MapPin, Loader2 } from 'lucide-react'
import { api } from '../api/client'
import type { LocationSummaryItem } from '../api/client'

// ── Marker helpers ────────────────────────────────────────────────────────────

function markerRadius(ticketCount: number, maxCount: number): number {
  const MIN_R = 6
  const MAX_R = 20
  if (maxCount <= 1) return MIN_R
  return MIN_R + (MAX_R - MIN_R) * (ticketCount / maxCount)
}

function markerColor(item: LocationSummaryItem): string {
  if (item.pending_count > 0) return '#E60028'  // red — pending review
  if (item.open_count > 0)    return '#f59e0b'  // amber — open/in-progress
  return '#22c55e'                              // green — all resolved
}

// ── Map component ─────────────────────────────────────────────────────────────

export function TicketLocationMapWidget(): React.ReactElement {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['location-summary'],
    queryFn: api.getLocationSummary,
    staleTime: 5 * 60_000,
    retry: 1,
  })

  const locations = data?.locations ?? []
  const maxCount  = locations.reduce((m, l) => Math.max(m, l.ticket_count), 0)

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 shadow-lg">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2">
            <MapPin size={15} className="text-blue-400" />
            Ticket Locations
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Geographic distribution of network faults across Singapore
          </p>
        </div>
        {/* Legend */}
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full bg-red-600 inline-block flex-shrink-0" />
            Pending
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block flex-shrink-0" />
            Open
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full bg-green-500 inline-block flex-shrink-0" />
            Resolved
          </span>
        </div>
      </div>

      {/* Stats bar */}
      {data && !isLoading && (
        <div className="flex flex-wrap items-center gap-4 mb-3 text-xs text-slate-500">
          <span>
            <span className="text-white font-semibold">{data.locations.length}</span> locations mapped
          </span>
          <span>
            <span className="text-white font-semibold">{data.total_tickets_with_location}</span> tickets with location data
          </span>
          {data.pending_geocode > 0 && (
            <span className="text-amber-400">
              {data.pending_geocode} address{data.pending_geocode !== 1 ? 'es' : ''} pending geocode
            </span>
          )}
        </div>
      )}

      {/* Map / states */}
      {isLoading ? (
        <div className="h-[420px] flex flex-col items-center justify-center gap-3 bg-slate-900/40 rounded-lg border border-slate-700/50">
          <Loader2 className="w-8 h-8 text-slate-400 animate-spin" />
          <p className="text-sm text-slate-400">Geocoding ticket locations…</p>
          <p className="text-xs text-slate-600">This may take a moment on first load</p>
        </div>
      ) : isError ? (
        <div className="h-[420px] flex items-center justify-center text-slate-500 text-sm bg-slate-900/40 rounded-lg border border-slate-700/50">
          Location data unavailable — check backend logs
        </div>
      ) : locations.length === 0 ? (
        <div className="h-[420px] flex items-center justify-center text-slate-500 text-sm bg-slate-900/40 rounded-lg border border-slate-700/50">
          No location data found in tickets
        </div>
      ) : (
        /* z-index:0 prevents Leaflet's internal z-indexes bleeding into the fixed dashboard header */
        <div className="relative" style={{ zIndex: 0 }}>
          <MapContainer
            center={[1.3521, 103.8198]}
            zoom={11}
            scrollWheelZoom={false}
            style={{ height: '420px', width: '100%', borderRadius: '0.5rem' }}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {locations.map((item) => (
              <CircleMarker
                key={item.address}
                center={[item.lat, item.lng]}
                radius={markerRadius(item.ticket_count, maxCount)}
                pathOptions={{
                  color:       markerColor(item),
                  fillColor:   markerColor(item),
                  fillOpacity: 0.7,
                  weight:      1.5,
                  opacity:     0.9,
                }}
              >
                <Popup>
                  <div style={{ minWidth: 190, fontFamily: 'ui-monospace, monospace', fontSize: 12, lineHeight: 1.6 }}>
                    <p style={{ fontWeight: 700, marginBottom: 2, color: '#1e293b' }}>{item.address}</p>
                    <p style={{ color: '#64748b', marginBottom: 6, fontSize: 11 }}>{item.display_name}</p>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      <span style={{ color: '#334155' }}>
                        Total: <strong>{item.ticket_count}</strong>
                      </span>
                      {item.pending_count > 0 && (
                        <span style={{ color: '#dc2626' }}>
                          Pending review: {item.pending_count}
                        </span>
                      )}
                      {item.open_count > 0 && (
                        <span style={{ color: '#d97706' }}>
                          Open / active: {item.open_count}
                        </span>
                      )}
                      <span style={{ color: '#16a34a' }}>
                        Resolved: {item.resolved_count}
                      </span>
                    </div>
                  </div>
                </Popup>
              </CircleMarker>
            ))}
          </MapContainer>
        </div>
      )}
    </div>
  )
}
