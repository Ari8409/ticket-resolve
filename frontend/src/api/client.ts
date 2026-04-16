import axios from 'axios'

// Uses Vite proxy in dev (/api → http://localhost:8000/api).
// In production, deploy the frontend behind the same origin as the backend
// or set VITE_API_BASE env var.
const BASE_URL = import.meta.env.VITE_API_BASE ?? '/api/v1'

export const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ─── Types ────────────────────────────────────────────────────────────────────

export interface TicketStats {
  total: number
  open: number
  in_progress: number
  pending_review: number
  resolved: number
  escalated: number
  closed: number
  failed: number
  by_status: Record<string, number>
  by_fault_type?: Record<string, number>
  by_alarm?: Record<string, number>
  by_network?: Record<string, number>
}

export interface DispatchStats {
  remote: number
  on_site: number
  hold: number
  total: number
  remote_pct: number
  on_site_pct: number
  remote_avg_confidence: number
  on_site_avg_confidence: number
  by_fault_type: Record<string, { remote: number; on_site: number }>
  by_network: Record<string, { remote: number; on_site: number }>
}

export interface LocationSummaryItem {
  address: string
  lat: number
  lng: number
  display_name: string
  ticket_count: number
  pending_count: number
  open_count: number
  resolved_count: number
}

export interface LocationSummaryResponse {
  locations: LocationSummaryItem[]
  geocoded: number
  pending_geocode: number
  total_tickets_with_location: number
}

export interface TelcoTicket {
  ticket_id: string
  affected_node: string
  fault_type: string
  severity: 'info' | 'minor' | 'medium' | 'low' | 'major' | 'high' | 'critical'
  status:
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
  network_type: string | null
  alarm_name: string | null
  alarm_category: string | null
  location_details: string | null
  location_id: string | null
  description: string
  assigned_to: string | null
  sop_id: string | null
  primary_cause: string | null
  pending_review_reasons: string[]
  created_at: string
  updated_at: string | null
}

export interface TriageSummary {
  ticket_id: string
  affected_node: string
  fault_type: string
  severity: string
  network_type: string | null
  alarm_name: string | null
  alarm_category: string | null
  location_details: string | null
  description: string
  reasons: string[]
  confidence_score: number
  sop_candidates_found: number
  similar_tickets_found: number
  flagged_at: string
  assigned_to: string | null
  assigned_at: string | null
}

export interface TicketReview {
  ticket: TelcoTicket
  recommendation: Record<string, unknown>
  available_actions: string[]
}

export interface AuditLogEntry {
  id: number
  ticket_id: string
  event_type: 'status_change' | 'assignment' | 'flag_review' | 'escalation' | 'resolution'
  from_status: string | null
  to_status: string | null
  changed_by: string | null
  reason: string | null
  created_at: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  intent?: string
  data?: unknown
  suggested_actions?: string[]
  timestamp: string
  message_id?: string
}

export interface ChatResponse {
  reply: string
  intent: string
  data: unknown
  suggested_actions: string[]
  timestamp: string
  message_id: string
}

export interface ChatFeedbackRequest {
  message_id: string
  rating: 1 | -1
  comment?: string
  engineer_id?: string
  query_text: string
  response_text: string
  ticket_context?: string
  intent?: string
}

export interface ChatFeedbackResponse {
  message_id: string
  rating: number
  indexed: boolean
  message: string
}

// ─── SLA Types (R-15) ─────────────────────────────────────────────────────────

export interface SLAFaultSummary {
  fault_type: string
  target_hours: number
  description: string
  total_resolved: number
  within_sla: number
  breached: number
  compliance_rate: number     // 0–100
  avg_resolution_hours: number
}

export interface SLASummaryResponse {
  total_resolved: number
  within_sla: number
  breached: number
  compliance_rate: number
  avg_resolution_hours: number
  by_fault_type: SLAFaultSummary[]
}

export interface SLATarget {
  fault_type: string
  target_hours: number
  description: string
  updated_at: string
}

export interface SLATargetsResponse {
  targets: SLATarget[]
}

// ─── API Functions ─────────────────────────────────────────────────────────────

export const api = {
  // Stats
  getStats: async (): Promise<TicketStats> => {
    const { data } = await apiClient.get<TicketStats>('/stats')
    return data
  },

  // Tickets
  getTickets: async (params?: {
    status?: string
    limit?: number
    offset?: number
  }): Promise<{ tickets: TelcoTicket[]; total: number; limit: number; offset: number }> => {
    const { data } = await apiClient.get('/telco-tickets', { params })
    return data
  },

  // Pending Review queue
  getPendingReview: async (limit = 100): Promise<TriageSummary[]> => {
    const { data } = await apiClient.get('/telco-tickets/pending-review', {
      params: { limit },
    })
    return data
  },

  // Single ticket review
  getTicketReview: async (id: string): Promise<TicketReview> => {
    const { data } = await apiClient.get(`/telco-tickets/${id}/review`)
    return data
  },

  // Assign ticket
  assignTicket: async (
    id: string,
    payload: { assign_to: string; notes?: string }
  ): Promise<unknown> => {
    const { data } = await apiClient.post(`/telco-tickets/${id}/assign`, payload)
    return data
  },

  // Manual resolve
  manualResolve: async (
    id: string,
    payload: {
      resolved_by: string
      resolution_steps: string[]
      sop_reference?: string
      primary_cause?: string
      resolution_code?: string
      notes?: string
    }
  ): Promise<unknown> => {
    const { data } = await apiClient.post(`/telco-tickets/${id}/manual-resolve`, payload)
    return data
  },

  // Review action
  reviewTicket: async (
    id: string,
    payload: {
      action: 'approve' | 'override' | 'escalate'
      reviewed_by?: string
      [key: string]: unknown
    }
  ): Promise<unknown> => {
    const { data } = await apiClient.post(`/telco-tickets/${id}/review`, payload)
    return data
  },

  // Audit log
  getAuditLog: async (ticketId: string): Promise<AuditLogEntry[]> => {
    const { data } = await apiClient.get<AuditLogEntry[]>(`/telco-tickets/${ticketId}/audit-log`)
    return data
  },

  // Dispatch stats (remote vs field)
  getDispatchStats: async (): Promise<DispatchStats> => {
    const { data } = await apiClient.get<DispatchStats>('/dispatch-stats')
    return data
  },

  // Health
  getHealth: async (): Promise<{ status: string }> => {
    const { data } = await apiClient.get('/health')
    return data
  },

  // Chat
  chat: async (payload: {
    message: string
    engineer_id?: string
    context?: string
    history?: Array<{ role: string; content: string }>
  }): Promise<ChatResponse> => {
    const { data } = await apiClient.post<ChatResponse>('/chat', payload)
    return data
  },

  // Chat feedback
  submitChatFeedback: async (req: ChatFeedbackRequest): Promise<ChatFeedbackResponse> => {
    const { data } = await apiClient.post<ChatFeedbackResponse>('/chat/feedback', req)
    return data
  },

  // Location geocoding summary
  getLocationSummary: async (): Promise<LocationSummaryResponse> => {
    const { data } = await apiClient.get<LocationSummaryResponse>('/telco-tickets/location-summary')
    return data
  },

  // SLA tracking (R-15)
  getSLASummary: async (): Promise<SLASummaryResponse> => {
    const { data } = await apiClient.get<SLASummaryResponse>('/sla/summary')
    return data
  },

  getSLATargets: async (): Promise<SLATargetsResponse> => {
    const { data } = await apiClient.get<SLATargetsResponse>('/sla/targets')
    return data
  },

  updateSLATarget: async (
    faultType: string,
    payload: { target_hours: number; description?: string }
  ): Promise<SLATarget> => {
    const { data } = await apiClient.put<SLATarget>(`/sla/targets/${faultType}`, payload)
    return data
  },
}
