import React, { useState } from 'react'
import {
  FileText,
  Layout,
  Database,
  Code2,
  FlaskConical,
  GitMerge,
  Server,
  ChevronDown,
  ChevronRight,
  Download,
  CheckCircle2,
  Clock,
  Circle,
  ExternalLink,
  Package,
  Layers,
  Container,
  Shield,
  Eye,
} from 'lucide-react'

// ─── Types ────────────────────────────────────────────────────────────────────

type DelivStatus = 'complete' | 'draft' | 'pending'

interface Section {
  title: string
  items: string[]
}

interface Deliverable {
  id: string
  index: number
  icon: React.ReactNode
  title: string
  subtitle: string
  status: DelivStatus
  description: string
  tags: string[]
  sections: Section[]
  highlights?: string[]
}

// ─── Status helpers ──────────────────────────────────────────────────────────

function statusLabel(s: DelivStatus) {
  if (s === 'complete') return 'Generated'
  if (s === 'draft')    return 'Draft Ready'
  return 'Pending'
}

function statusColors(s: DelivStatus) {
  if (s === 'complete') return 'bg-green-900/50 text-green-400 border border-green-700/50'
  if (s === 'draft')    return 'bg-amber-900/50 text-amber-400 border border-amber-700/50'
  return 'bg-slate-700/50 text-slate-400 border border-slate-600/50'
}

function statusIcon(s: DelivStatus) {
  if (s === 'complete') return <CheckCircle2 size={12} className="text-green-400" />
  if (s === 'draft')    return <Clock        size={12} className="text-amber-400" />
  return <Circle size={12} className="text-slate-500" />
}

// ─── Document generation helpers ─────────────────────────────────────────────

function generateDocHTML(d: Deliverable): string {
  const sectionHTML = d.sections.map(sec => `
    <section style="margin-bottom:2rem">
      <h2 style="font-size:1.1rem;font-weight:700;color:#1e293b;border-left:4px solid #e60028;padding-left:0.75rem;margin-bottom:1rem">${sec.title}</h2>
      <ul style="list-style:disc;padding-left:1.5rem;color:#334155">
        ${sec.items.map(it => `<li style="margin-bottom:0.4rem">${it}</li>`).join('')}
      </ul>
    </section>`).join('')

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>${d.title} — NOC Ticket Intelligence Platform</title>
  <style>
    body{font-family:'Segoe UI',sans-serif;background:#f8fafc;color:#1e293b;margin:0;padding:0}
    .page{max-width:960px;margin:0 auto;padding:3rem 2rem}
    header{background:#1e293b;color:#fff;padding:2.5rem 2rem;border-radius:12px;margin-bottom:2rem}
    header h1{margin:0 0 0.5rem;font-size:1.5rem;color:#fff}
    header .sub{color:#94a3b8;font-size:0.9rem}
    header .meta{display:flex;gap:1rem;margin-top:1rem;flex-wrap:wrap}
    header .meta span{background:#0f172a;padding:0.3rem 0.75rem;border-radius:6px;font-size:0.8rem;color:#cbd5e1}
    .tag{display:inline-block;background:#e2e8f0;color:#475569;border-radius:4px;padding:0.2rem 0.6rem;font-size:0.75rem;font-weight:600;margin-right:0.4rem}
    footer{margin-top:3rem;padding-top:1rem;border-top:1px solid #e2e8f0;color:#94a3b8;font-size:0.8rem;text-align:center}
  </style>
</head>
<body>
  <div class="page">
    <header>
      <div style="font-size:0.75rem;color:#e60028;font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin-bottom:0.5rem">
        Deliverable ${d.index} of ${DELIVERABLES.length}
      </div>
      <h1>${d.title}</h1>
      <p class="sub">${d.subtitle}</p>
      <div class="meta">
        <span>NOC Ticket Intelligence Platform</span>
        <span>Red Hat AI Platform</span>
        <span>PostgreSQL</span>
        <span>Container Deployment</span>
      </div>
      <div style="margin-top:1rem">${d.tags.map(t => `<span class="tag">${t}</span>`).join('')}</div>
    </header>
    <p style="color:#475569;line-height:1.7;margin-bottom:2rem">${d.description}</p>
    ${sectionHTML}
    <footer>NOC Ticket Intelligence Platform &mdash; Generated ${new Date().toLocaleDateString('en-AU', { day: '2-digit', month: 'long', year: 'numeric' })}</footer>
  </div>
</body>
</html>`
}

function downloadDoc(d: Deliverable) {
  const html = generateDocHTML(d)
  const blob = new Blob([html], { type: 'text/html' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = `${d.id}.html`
  a.click()
  URL.revokeObjectURL(url)
}

// ─── Deliverables data ────────────────────────────────────────────────────────

const DELIVERABLES: Deliverable[] = [
  {
    id: 'req-doc',
    index: 1,
    icon: <FileText size={20} className="text-blue-400" />,
    title: 'Requirements Document',
    subtitle: 'Scope, functional and non-functional requirements for the NOC Ticket Intelligence Platform',
    status: 'complete',
    description:
      'Defines the full scope of the NOC Ticket Intelligence Platform across 14 releases (R-0 to R-13). An AI-powered system that ingests 3G/4G/5G telco fault tickets, classifies them by network element, surfaces automated triage, resolution recommendations, geographic fault analytics, and a conversational chat assistant for NOC engineers.',
    tags: ['Business', 'Functional', 'Non-Functional', 'Constraints'],
    highlights: ['1,592 telco tickets in scope', '766 network nodes', '3G / 4G / 5G coverage', 'WCAG 2.1 AA compliant'],
    sections: [
      {
        title: '1. Executive Summary',
        items: [
          'Platform purpose: AI-assisted triage and resolution of telco network fault tickets across 3G/4G/5G',
          'Target users: NOC engineers, operations managers, network administrators',
          'Key capability: LangChain + ChromaDB semantic search over 1,592 historical tickets; 507 site locations mapped',
          'Primary value: Reduce mean time to resolution (MTTR); surface geographic fault clusters; enable chat-driven triage',
          'Compliance baseline: EU AI Act Art.12–14, GSMA AI Principles, ETSI ENI 005, WCAG 2.1 AA',
        ],
      },
      {
        title: '2. Business Requirements',
        items: [
          'BR-01: The system shall process and store all incoming telco fault tickets in real time',
          'BR-02: The system shall provide AI-generated resolution recommendations for open tickets',
          'BR-03: NOC engineers shall be able to triage pending-review tickets from a dedicated queue',
          'BR-04: Management shall have access to KPI dashboards showing ticket volume, resolution rates, and geographic distribution',
          'BR-05: The system shall support 3G (RNC/NodeB), 4G (eNodeB/ESS), and 5G (gNB/ESS) topologies',
          'BR-06: All AI decisions shall be auditable and traceable per EU AI Act Art.12 accountability requirements',
          'BR-07: The platform shall be accessible to engineers with disabilities (WCAG 2.1 AA)',
        ],
      },
      {
        title: '3. Functional Requirements',
        items: [
          'FR-01: Ingest and store telco tickets with status (open, in_progress, pending_review, resolved, escalated)',
          'FR-02: Chat assistant interface for natural-language ticket queries using LangChain + Claude API',
          'FR-03: Bulk CSV import of historical ticket data with de-duplication logic',
          'FR-04: Network topology graph visualisation showing per-node ticket health; zoom/pan/keyboard controls',
          'FR-05: SDLC Dashboard tracking 14 iterations, 31 RICEF objects, 104 unit tests, and 55 SIT scenarios',
          'FR-06: Deliverables Dashboard for generating and downloading 9 project artefact documents',
          'FR-07: Auto-refresh polling on the NOC dashboard (configurable interval, default 30 s)',
          'FR-08: Resolution tree and pending-tree intent handlers in the chat assistant',
          'FR-09: Geographic fault map — 507 Singapore site locations from affected_node site codes',
          'FR-10: High-Volume Ticket Nodes widget — top nodes per 3G/4G/5G bucket with resolved/pending bars',
          'FR-11: Engineer feedback loop — thumbs up/down on chat responses indexed to ChromaDB as training signals',
          'FR-12: Immutable ticket audit log — every status transition recorded with from/to state',
        ],
      },
      {
        title: '4. Non-Functional Requirements',
        items: [
          'NFR-01: API response time under 500 ms for ticket list queries (up to 1,000 rows)',
          'NFR-02: System shall support at least 50 concurrent NOC engineer sessions',
          'NFR-03: Vector search (ChromaDB) shall return results within 2 s for any natural-language query',
          'NFR-04: Frontend shall achieve a Lighthouse performance score above 85',
          'NFR-05: All API endpoints shall be protected with role-based authentication (Phase 2)',
          'NFR-06: Database backups shall be performed daily; RPO = 24 h, RTO = 4 h',
          'NFR-07: The solution shall be deployable on Red Hat OpenShift / Red Hat AI Platform',
          'NFR-08: Frontend shall conform to WCAG 2.1 Level AA — all interactive elements keyboard-operable, aria-live regions for dynamic content',
          'NFR-09: Responsible AI compliance — all 6 RAI guardrail categories (Fairness, Transparency, HITL, Privacy, Robustness, Safety) must have passing test coverage against GSMA AI Principles, ETSI ENI 005, EU AI Act, and ITU-T Y.3172',
        ],
      },
      {
        title: '5. Constraints and Assumptions',
        items: [
          'CON-01: Initial deployment targets Red Hat AI Platform on-premises (no public cloud required)',
          'CON-02: PostgreSQL is the target production database; SQLite is used for development only',
          'CON-03: Frontend containers are OCI-compliant images deployable on OpenShift',
          'CON-04: Claude API (Anthropic) is the LLM provider; requires API key configuration',
          'CON-05: Corporate network blocks external geocoding APIs — location resolution must be fully offline',
          'ASM-01: Ticket data is sourced from the existing OSS/BSS feed in CSV format',
          'ASM-02: Network element naming follows the conventions: RncN, RncN_M, LTE_ENB_*, 5G_GNB_*',
          'ASM-03: Site location codes are 6-digit suffixes in affected_node (e.g. LTE_ENB_780321 → site 780321)',
        ],
      },
      {
        title: '6. Out of Scope',
        items: [
          'Real-time OSS/BSS integration (Phase 2)',
          'Mobile application',
          'Automated ticket remediation / self-healing',
          'Multi-tenancy support',
          'Role-based access control (Phase 2)',
        ],
      },
    ],
  },
  {
    id: 'hld-architecture',
    index: 2,
    icon: <Layout size={20} className="text-purple-400" />,
    title: 'High-Level Solution Architecture',
    subtitle: 'End-to-end architecture across frontend containers, Red Hat AI backend, and PostgreSQL',
    status: 'complete',
    description:
      'Describes the overall architecture of the NOC Ticket Intelligence Platform as delivered across 14 releases. A three-tier system: React/Vite SPA deployed as a container, FastAPI + LangChain backend on Red Hat AI Platform, and PostgreSQL with ChromaDB vector store. Includes geographic fault mapping (offline static lookup), chat feedback indexing, immutable audit logging, and WCAG 2.1 AA accessibility layer.',
    tags: ['Architecture', 'Containers', 'Red Hat AI', 'PostgreSQL'],
    highlights: ['3-tier architecture', 'Red Hat AI Platform backend', 'OCI container frontend', '20 API endpoints'],
    sections: [
      {
        title: '1. Architecture Overview',
        items: [
          'Presentation Tier: React 18 + Vite SPA, deployed as OCI container on Red Hat OpenShift',
          'Application Tier: FastAPI (Python 3.14) + LangChain, hosted on Red Hat AI Platform (RHEL-based)',
          'Data Tier: PostgreSQL (primary store) + ChromaDB (vector embeddings for AI search)',
          'AI Layer: Anthropic Claude API via LangChain; embeddings stored in ChromaDB persistent store',
          'Geographic Layer: Offline Singapore district lookup (82 districts, SHA-256 jitter) — no external geocoding',
          'Feedback Loop: POST /chat/feedback → SQLite + ChromaDB (positive ratings only) → context injection',
          'Audit Layer: ticket_audit_log append-only table; every status transition persisted',
          'Inter-tier communication: REST/JSON over HTTPS; Vite reverse proxy in development',
        ],
      },
      {
        title: '2. Component Diagram',
        items: [
          'Browser → [React SPA container] → [Vite/Nginx reverse proxy] → FastAPI',
          'FastAPI → SQLAlchemy (async) → PostgreSQL (tickets, nodes, edges, audit_log, chat_feedback)',
          'FastAPI → LangChain Agent → ChromaDB (ticket resolutions + chat feedback docs)',
          'LangChain Agent → Anthropic Claude API (LLM completion)',
          'FastAPI → locations.py → Static SG district lookup → lat/lng response (fully offline)',
          'Cron / startup script → build_network_graph.py → PostgreSQL graph tables (766 nodes, 247 edges)',
        ],
      },
      {
        title: '3. Technology Stack',
        items: [
          'Frontend: React 18, TypeScript, Vite 5.4, Tailwind CSS, Recharts, TanStack Query, React Router v6, React Leaflet 4.2',
          'Backend: FastAPI 0.111, Python 3.14, SQLModel 0.0.38, SQLAlchemy 2.0 (async), Pydantic v2',
          'AI / ML: LangChain 0.2, ChromaDB 0.5 (persistent), Anthropic Claude claude-sonnet-4-6',
          'Database: PostgreSQL 16 (production), SQLite (development / CI)',
          'Container: Docker / Podman, OCI image, Red Hat Universal Base Image (UBI 9)',
          'Platform: Red Hat AI Platform (OpenShift 4.x), RHEL 9 worker nodes',
          'Accessibility: WCAG 2.1 AA — ARIA landmarks, aria-live regions, keyboard navigation, focus management',
        ],
      },
      {
        title: '4. Integration Points',
        items: [
          'INT-01: CSV import pipeline — batch ingest from OSS/BSS export files via import_to_db.py',
          'INT-02: Anthropic Claude API — REST, requires ANTHROPIC_API_KEY env var',
          'INT-03: ChromaDB HTTP client — localhost:8001 (dev) or sidecar container (prod)',
          'INT-04: PostgreSQL JDBC/SQLAlchemy — DATABASE_URL env var (asyncpg driver in production)',
          'INT-05: OpenShift Routes — HTTPS ingress from external NOC network',
          'INT-06: React Leaflet — OpenStreetMap tiles (CDN); gracefully offline in corporate environments (hmr.overlay disabled)',
        ],
      },
      {
        title: '5. Deployment Topology',
        items: [
          'Red Hat AI Platform cluster: 3 control-plane nodes, 3+ compute nodes',
          'Backend pod: FastAPI + Uvicorn, 2 replicas minimum, HPA enabled',
          'ChromaDB pod: StatefulSet with PersistentVolumeClaim for embeddings storage',
          'Frontend pod: Nginx serving static React build, 2 replicas, behind OpenShift Route',
          'PostgreSQL: Managed instance (RHEL-based) or Crunchy Data PostgreSQL Operator',
          'Secrets management: OpenShift Secrets / Vault for API keys and DB credentials',
        ],
      },
    ],
  },
  {
    id: 'lld-design',
    index: 3,
    icon: <Layers size={20} className="text-cyan-400" />,
    title: 'Low-Level Design Document',
    subtitle: 'Database schema, API contract (20 endpoints), component interactions and data flow diagrams',
    status: 'complete',
    description:
      'Provides the detailed internal design of each system component including the PostgreSQL schema (7 tables), all 20 FastAPI endpoint contracts, SQLModel ORM class definitions, the ChromaDB collection structure, LangChain agent execution graph, and the offline Singapore geographic lookup algorithm.',
    tags: ['Schema', 'API Design', 'Sequence Diagrams', 'Data Flow'],
    sections: [
      {
        title: '1. Database Schema (PostgreSQL / SQLite)',
        items: [
          'Table: telco_tickets — id (UUID PK), ticket_id (unique), affected_node, network_type, fault_type, alarm_name, status (enum), severity, description, resolution_notes, location_details, location_id, created_at, updated_at',
          'Table: network_nodes — node_id (PK), network_type, node_class, parent_node (FK self), x_pos, y_pos, ticket_count, pending_count, open_count, resolved_count, last_ticket_at',
          'Table: network_edges — edge_id (serial PK), source_node (FK), target_node (FK), edge_type',
          'Table: ticket_audit_log — id (UUID PK), ticket_id (FK), event_type (enum), from_status, to_status, actor, notes, created_at (immutable)',
          'Table: chat_feedback — id (UUID PK), message_id (UUID), rating (1/-1), comment, query_text, response_text, created_at',
          'Enum: ticket_status — open | in_progress | pending_review | resolved | escalated',
          'Index: telco_tickets(status), telco_tickets(affected_node), telco_tickets(network_type)',
        ],
      },
      {
        title: '2. API Endpoint Contract (20 endpoints)',
        items: [
          'GET  /api/v1/health                          — system health check',
          'GET  /api/v1/stats                           — dashboard KPIs with fault/alarm/network breakdowns',
          'GET  /api/v1/telco-tickets                   — paginated ticket list with filters',
          'GET  /api/v1/telco-tickets/{id}              — single ticket detail',
          'PATCH /api/v1/telco-tickets/{id}             — update status / resolution notes',
          'POST /api/v1/telco-tickets/{id}/assign       — assign ticket to engineer',
          'POST /api/v1/telco-tickets/{id}/manual-resolve — human override resolution',
          'GET  /api/v1/telco-tickets/pending-review    — HITL triage queue',
          'GET  /api/v1/telco-tickets/location-summary  — 507 site locations with ticket counts (offline)',
          'GET  /api/v1/telco-tickets/{id}/audit-log    — immutable audit trail per ticket',
          'POST /api/v1/chat                            — LangChain chat; returns message_id UUID',
          'POST /api/v1/chat/feedback                   — engineer rating + optional comment',
          'GET  /api/v1/network/graph                   — pre-computed topology (766 nodes, 247 edges)',
          'POST /api/v1/network/refresh                 — triggers graph re-computation',
          'GET  /api/v1/network/node/{id}/tickets       — per-node ticket drill-down',
          'POST /api/v1/upload                          — CSV ticket bulk import',
          'POST /api/v1/classify                        — single ticket AI classification',
          'POST /api/v1/triage                          — triage decision request',
          'POST /api/v1/review                          — review queue management',
          'POST /api/v1/webhooks                        — external system webhook receiver',
        ],
      },
      {
        title: '3. Geographic Location Algorithm',
        items: [
          'Input: affected_node string (e.g. LTE_ENB_780321)',
          'Step 1: Extract 6-digit site code via regex (\\d{6})$ → "780321"',
          'Step 2: Take first 2 digits as district key → "78" → Jurong West Upper (1.3380, 103.7010)',
          'Step 3: Compute SHA-256 hash of full code → deterministic jitter ±0.018° (≈2 km)',
          'Step 4: Return lat = base_lat + jitter_lat, lng = base_lng + jitter_lng',
          'Coverage: 82 Singapore postal districts; unknown codes fall back to island centroid',
          'Performance: < 1 ms per code; entire 507-location response in < 80 ms',
        ],
      },
      {
        title: '4. Sequence: Ticket Triage Flow',
        items: [
          '1. NOC engineer loads /triage — React Query fetches GET /telco-tickets?status=pending_review',
          '2. FastAPI → TelcoTicketRepository.list() → SQLite/PostgreSQL SELECT with WHERE status = pending_review',
          '3. Engineer clicks "Resolve" → PATCH /telco-tickets/{id} with {status: resolved, resolution_notes}',
          '4. FastAPI updates DB, appends to ticket_audit_log (STATUS_CHANGE event), re-indexes ticket in ChromaDB',
          '5. React Query invalidates [tickets, stats] cache → dashboard stats refresh',
        ],
      },
      {
        title: '5. Sequence: Chat Feedback Round-trip',
        items: [
          '1. User sends query → POST /chat → LangChain pipeline → response with message_id UUID',
          '2. Frontend renders FeedbackBar below assistant message',
          '3. Engineer clicks thumbs-up → POST /chat/feedback {message_id, rating:1, comment?}',
          '4. FastAPI: insert to chat_feedback table; if rating=1, call ResolutionFeedbackIndexer.index_chat_feedback()',
          '5. Indexer embeds "Q: {query}\\nA: {response}" into ChromaDB with metadata {feedback_source: chat}',
          '6. Next general-intent query: retrieve_chat_feedback_context() injects top-3 snippets into LLM prompt',
        ],
      },
    ],
  },
  {
    id: 'tdd-technical',
    index: 4,
    icon: <Code2 size={20} className="text-green-400" />,
    title: 'Technical Design Document',
    subtitle: 'Technology decisions, implementation patterns, AI pipeline design, UX design rationale',
    status: 'complete',
    description:
      'Documents all technical decisions made across 14 releases: FastAPI async patterns, SQLModel Python 3.14 workaround, LangChain tool-calling agent design, ChromaDB embedding strategy, NetworkX topology layout, offline geographic lookup, centre-preserving zoom algorithm, WCAG 2.1 AA accessibility patterns, and Responsible AI guardrail design.',
    tags: ['Tech Stack', 'Patterns', 'AI Pipeline', 'UX Design', 'A11y'],
    sections: [
      {
        title: '1. Technology Stack Decisions',
        items: [
          'FastAPI: async-first, lower overhead, native Pydantic v2 support',
          'SQLModel: combined Pydantic validation + ORM; text() raw SQL workaround for Python 3.14',
          'ChromaDB: zero-cost embedded vector store; custom index_raw_doc() for feedback doc isolation',
          'React + Vite: HMR speed, TypeScript first-class; hmr.overlay: false for corporate CDN environments',
          'TanStack Query: shared queryKey cache — HotNodesWidget and NetworkTopologyWidget reuse same data fetch',
          'React Leaflet: CircleMarker (no default icon fix needed); zIndex:0 wrapper prevents z-index bleed',
          'Tailwind CSS: utility-first dark-mode; sr-only utility for screen-reader-only content',
        ],
      },
      {
        title: '2. Network Topology Zoom Algorithm',
        items: [
          'ViewBox state: {x, y, w, h} initialised to {0, 0, 1200, 700}',
          'Centre-preserving zoom: cx = x + w/2; cy = y + h/2; newX = cx - newW/2; newY = cy - newH/2',
          'Zoom-in factor: 0.625 (button) / 0.89 (wheel); Zoom-out factor: 1.6 (button) / 1.12 (wheel)',
          'Bounds: MIN_W=200, MIN_H=120, MAX_W=SVG_W×3=3600, MAX_H=SVG_H×3=2100',
          'Keyboard: ArrowKeys pan ±60 SVG units; +/− zoom; 0 resets; preventDefault() blocks page scroll',
          'Disabled states: zoom-in button disabled at w≤210; zoom-out at w≥SVG_W×2.8',
        ],
      },
      {
        title: '3. Color Semantic Design (HotNodesWidget)',
        items: [
          'Problem: network-type accent colors (blue/violet/emerald) on pending bars created false associations',
          'Solution: universal PENDING_COLOR = #f97316 (orange-500) for all pending bar segments across 3G/4G/5G',
          'Rationale: orange occupies warning slot on red-amber-green traffic-light scale; contrast 3.4:1 on slate-700',
          'Network-type identity preserved in: header badge, border, accent text — separate visual channel',
          'Legend swatch updated to bg-orange-500 to match rendered bars',
          'Green (#22c55e) retained for resolved — universal "done" semantic; contrast 4.9:1',
        ],
      },
      {
        title: '4. LangChain Agent + Feedback Design',
        items: [
          'Agent: OpenAI-compatible tool-calling via create_tool_calling_agent(); 8 intent handlers',
          'Feedback isolation: index_raw_doc() bypasses TicketStore fixed schema; uses custom metadata {feedback_source: chat}',
          'Context scoping: retrieve_chat_feedback_context() called ONLY for general intent — prevents JSON payload corruption',
          'Negative feedback: rating=-1 persisted to SQLite only; never indexed to Chroma — prevents silent degradation',
          'message_id: UUID v4 per response; stable key for feedback submission; idempotency guarantee',
        ],
      },
      {
        title: '5. Container Build Strategy',
        items: [
          'Frontend: Multi-stage Dockerfile — node:20-alpine build stage, nginx:alpine serve stage',
          'Backend: python:3.12-slim base, non-root user, COPY requirements.txt first for layer caching',
          'ChromaDB: Official chromadb/chroma image with PVC mount for /chroma/chroma data dir',
          'Health checks: HEALTHCHECK CMD curl -f http://localhost:8000/api/v1/health || exit 1',
          'Secrets: All API keys and DB passwords injected via environment variables from OpenShift Secrets',
        ],
      },
    ],
  },
  {
    id: 'ut-report',
    index: 5,
    icon: <FlaskConical size={20} className="text-yellow-400" />,
    title: 'Unit Test Case Document and Execution Report',
    subtitle: 'All 104 unit tests across 14 releases — UT-001 to UT-104, RAI-mapped, 100% pass rate',
    status: 'complete',
    description:
      'Covers the full unit test suite across all 14 releases. Tests span API correctness, intent detection, node classification, DB import validation, graph computation, network topology, telecom CTTS parsing, Responsible AI guardrails (6 categories, 28 tests mapped to GSMA/ETSI/EU AI Act/ITU-T), chat feedback loop, audit log, geographic location decoding, zoom control mathematics, and WCAG accessibility attributes.',
    tags: ['Unit Tests', 'Coverage', 'API', 'AI', 'RAI', 'Accessibility'],
    highlights: ['104 unit tests', '104 PASS / 0 FAIL', '100% pass rate', '6 RAI categories covered'],
    sections: [
      {
        title: '1. Test Strategy',
        items: [
          'Framework: pytest + httpx (async) for API tests; unittest for ORM and service layer',
          'asyncio_mode = auto (pytest.ini) — resolves pytest-asyncio strict mode on Python 3.14',
          'Test data: seeded SQLite in-memory DB populated from fixture CSV (50 tickets)',
          'Coverage target: 80% line coverage on app/api/, app/storage/, app/services/',
          'RAI mapping: every test in the guardrail suite cross-referenced to GSMA/ETSI/EU AI Act/ITU-T framework IDs',
        ],
      },
      {
        title: '2. R-4 to R-6: Chat, Topology, Stats (UT-001 to UT-020)',
        items: [
          'UT-001 to UT-007: Intent detection (show_ticket, resolution_tree, pending_tree, pending_queue, stats) + ticket regex',
          'UT-008 to UT-011: Node classification — RNC, NodeB, ENB (4G), GNB (5G) with parent extraction',
          'UT-012 to UT-013: DB import — 1,592 rows in telco_tickets and dispatch_decisions',
          'UT-014 to UT-016: Graph build — 766 nodes (754 + 12 synthetic RNCs), 247 edges, normalised positions',
          'UT-017 to UT-020: Stats API — by_fault_type, by_alarm (≤15), network graph nodes/tickets',
        ],
      },
      {
        title: '3. R-8: Telecom Industry Suite (UT-021 to UT-035)',
        items: [
          'UT-021 to UT-025: CTTS parser — 4G heartbeat, legacy 3G category normalisation, UNKNOWN/ prefix stripping, 5G sync, non-CTTS passthrough',
          'UT-026 to UT-028: TelcoTicketCreate auto-parse — alarm fields populated, not overwritten, affected_node back-filled',
          'UT-029 to UT-032: Node classifier — RNC synthetic nodes, NodeB parent, LTE/5G ESS, unrecognised patterns',
          'UT-033: Layout normaliser — output within [0.05, 0.95]; empty passthrough',
          'UT-034 to UT-035: Remote feasibility — hardware_failure on-site; latency/config_error remote',
        ],
      },
      {
        title: '4. R-9: Responsible AI Guardrails (UT-036 to UT-055)',
        items: [
          'Fairness (UT-036 to UT-040): Dispatch parity 3G/4G/5G; hardware_failure on-site; signal_loss remote; node_down on-site; sw_error remote',
          'Transparency (UT-041 to UT-044): All 1,592 decisions have reasoning; confidence_score rules; 5-stage pipeline; decision evidence',
          'HITL (UT-045 to UT-047): 26.1% HITL trigger rate; manual override; audit trail',
          'Privacy (UT-048 to UT-050): Zero PII in 1,592 descriptions; ChromaDB metadata; no ML artefacts in API',
          'Robustness (UT-051 to UT-053): HTTP 422 on bad input; 503 before graph init; empty chat error handling',
          'Safety (UT-054 to UT-055): 633 critical tickets never auto-resolved; audit log append-only',
        ],
      },
      {
        title: '5. R-10 to R-12: Audit, Feedback, Location (UT-056 to UT-088)',
        items: [
          'UT-056: AuditLogRepository — append(), get_trail(), append-only confirmed',
          'UT-057 to UT-072: Chat feedback — record(), get_by_message(), index_chat_feedback(), index_raw_doc(), retrieve_context(), POST /chat/feedback round-trip, message_id UUID, 6 RAI tests (Transparency/Privacy/HITL/Robustness/Accountability)',
          'UT-073 to UT-078: HotNodesWidget — bucket partitioning, top-N sort, resolved/pending bar maths, fleet footer, React Query cache hit',
          'UT-079 to UT-085: Location endpoint — site code extraction, district coords, deterministic jitter, fallback, response shape',
          'UT-086 to UT-088: Location RAI — popup exposes all counts (Transparency); no PII in response (Privacy); offline resilience (Robustness)',
        ],
      },
      {
        title: '6. R-13: UX & Accessibility (UT-089 to UT-104)',
        items: [
          'UT-089 to UT-091: HotNodesWidget color — orange #f97316 on all pending bars; legend swatch; semantic text colours',
          'UT-092 to UT-097: Zoom controls — zoomBy() maths, clamping, onWheel drift fix, disabled states, aria-labels, keyboard navigation',
          'UT-098 to UT-102: WCAG — Toast aria-live + dismiss label; Header aria-pressed; Sidebar aria-label + sr-only; App main label; sr-only CSS',
          'UT-103 to UT-104: RAI Transparency (SVG aria-label for network state) + HITL (auto-refresh aria-pressed for live data awareness)',
        ],
      },
      {
        title: '7. Execution Summary',
        items: [
          'Total test cases: 104',
          'PASS: 104  |  FAIL: 0  |  SKIP: 0',
          'Pass rate: 100%',
          'RAI guardrail coverage: 28 tests across 6 categories (R-9) + 8 RAI tests in R-11/R-12/R-13',
          'Accessibility coverage: 16 tests (R-13) mapping to WCAG 2.1 AA success criteria',
          'Notable regression caught: UT-011/012 confirmed text() ORM fix; UT-047/055 confirmed audit log (R-9 → R-10)',
        ],
      },
    ],
  },
  {
    id: 'sit-report',
    index: 6,
    icon: <GitMerge size={20} className="text-pink-400" />,
    title: 'SIT Test Case Document and Execution Report',
    subtitle: '55 end-to-end integration scenarios across all 14 releases — 100% pass rate',
    status: 'complete',
    description:
      'System Integration Testing validates full end-to-end flows across React frontend, FastAPI backend, SQLite/PostgreSQL, ChromaDB vector store, and the Anthropic LLM. 55 scenarios covering triage workflow, chat resolution, network topology drill-down, geographic fault map, chat feedback loop, audit trail, RAI guardrails (8 scenarios), and WCAG accessibility (8 scenarios).',
    tags: ['Integration', 'End-to-End', 'Full Stack', 'SIT', 'RAI', 'A11y'],
    highlights: ['55 SIT scenarios', '55 PASS / 0 FAIL', '100% pass rate', 'RAI + A11y validated'],
    sections: [
      {
        title: '1. Test Environment',
        items: [
          'FastAPI: localhost:8000 (uvicorn, no --reload)',
          'React: localhost:5173 (Vite dev server; hmr.overlay: false)',
          'ChromaDB: localhost:8001 (persistent store)',
          'Database: SQLite ticket-resolve/data/tickets.db (1,592 rows)',
          'LLM: Anthropic Claude claude-sonnet-4-6 (requires ANTHROPIC_API_KEY)',
        ],
      },
      {
        title: '2. R-2 to R-6: Core Platform (SIT-001 to SIT-012)',
        items: [
          'SIT-001: 1,592 rows confirmed in telco_tickets + dispatch_decisions after bulk import',
          'SIT-002 to SIT-003: Dashboard KPIs (Total=1,592 · Pending=415 · Resolved=1,177) + fault type chart',
          'SIT-004 to SIT-005: Chat resolution_tree (5-stage ExecutionTreeCard) + pending_tree (no_sop_match shown)',
          'SIT-006 to SIT-008: Network graph API (766 nodes, 247 edges) + topology widget (1,003 SVG circles) + 4G filter',
          'SIT-009 to SIT-011: Node click detail panel + RNC drill-down (breadcrumb) + drill exit (full restore)',
          'SIT-012: Triage queue — 415 pending_review tickets listed',
        ],
      },
      {
        title: '3. R-8: Telecom Industry Suite (SIT-013 to SIT-022)',
        items: [
          'SIT-013: 4G eNodeB Heartbeat Failure — A1 critical → PENDING_REVIEW → assign → ELR reset → RESOLVED',
          'SIT-014: 5G gNB SyncRefQuality — PTP alarm parsed; remote resolve confirmed',
          'SIT-015: 3G NodeB Hardware Fault — on-site dispatch; 4-step physical resolution',
          'SIT-016: Alarm Storm RNC07 Cluster — 5 NodeBs concurrent PENDING_REVIEW; all no_sop_match',
          'SIT-017: Maintenance Window Suppression — empty queue for suppressed nodes; 409 for maint ticket',
          'SIT-018 to SIT-022: Network API full graph; pre-refresh 503; multi-network bulk ingestion; A1/A2 routing; 5G/3G drill-down',
        ],
      },
      {
        title: '4. R-9 to R-11: RAI + Audit + Feedback (SIT-023 to SIT-039)',
        items: [
          'SIT-023 to SIT-029: RAI guardrail SIT — Fairness (cross-network dispatch parity), Transparency (ExecutionTreeCard), HITL (manual override), Privacy (PII scan), Robustness (ChromaDB failover), Safety (633 on-site), Auditability (1,592 decisions)',
          'SIT-030 to SIT-031: Audit log end-to-end — every status transition recorded; AuditTimelineModal renders',
          'SIT-032 to SIT-039: Chat feedback — full round-trip, negative isolation, comment storage, intent scoping, Transparency, Privacy, Robustness, Accountability',
        ],
      },
      {
        title: '5. R-12 to R-13: Geo Widgets + UX (SIT-040 to SIT-055)',
        items: [
          'SIT-040 to SIT-042: HotNodesWidget — 3-bucket render, bar accuracy, zero extra HTTP calls confirmed',
          'SIT-043 to SIT-045: Location map — 507 markers, popup, red/amber/green colour coding',
          'SIT-046 to SIT-047: RAI — geographic transparency (popup counts), offline geocoding resilience',
          'SIT-048: HotNodesWidget orange bars — all 3 buckets confirmed, legend matches',
          'SIT-049 to SIT-051: Zoom controls — button zoom, keyboard nav, scroll drift fix',
          'SIT-052 to SIT-053: Accessibility — Toast aria-live, axe-core 0 violations on all 4 pages',
          'SIT-054 to SIT-055: RAI — SVG aria-label for network state, auto-refresh aria-pressed for HITL awareness',
        ],
      },
      {
        title: '6. SIT Execution Summary',
        items: [
          'Total scenarios: 55',
          'PASS: 55  |  CONDITIONAL: 0  |  FAIL: 0',
          'Pass rate: 100%',
          'Regressions caught and fixed: SIT-001 (ORM text() fix), SIT-030 (audit log gap from R-9)',
          'Key validations: 507 site locations returned offline in < 80 ms; axe-core 0 critical violations',
        ],
      },
    ],
  },
  {
    id: 'deployment-doc',
    index: 7,
    icon: <Server size={20} className="text-orange-400" />,
    title: 'Deployment Document',
    subtitle: 'Step-by-step deployment guide for Red Hat AI Platform, frontend containers, and PostgreSQL',
    status: 'draft',
    description:
      'Provides the complete deployment runbook for the NOC Ticket Intelligence Platform into the production environment: Red Hat AI Platform for the FastAPI backend, OCI containers for the React frontend on OpenShift, and PostgreSQL for persistent ticket storage. Covers all 7 SQLite tables, 20 API endpoints, ChromaDB vector store, and post-deployment validation.',
    tags: ['Red Hat AI', 'OpenShift', 'PostgreSQL', 'Containers', 'Runbook'],
    highlights: ['Red Hat AI Platform', 'OpenShift 4.x', 'PostgreSQL 16', 'OCI containers'],
    sections: [
      {
        title: '1. Infrastructure Overview',
        items: [
          'Cluster: Red Hat OpenShift 4.x on Red Hat AI Platform (RHEL 9 worker nodes)',
          'Namespace: noc-platform (production), noc-platform-staging (pre-production)',
          'Container registry: Red Hat Quay.io or internal registry at registry.internal/noc-platform',
          'PostgreSQL: Crunchy Data PostgreSQL Operator v5 or RHEL-managed PostgreSQL 16 instance',
          'Storage: OCP PersistentVolumeClaim for ChromaDB (ReadWriteOnce, 20 Gi minimum)',
          'Networking: OpenShift Route (edge TLS termination) → Service → Pod',
        ],
      },
      {
        title: '2. Pre-Deployment Checklist',
        items: [
          'Step 1: Create OpenShift project: oc new-project noc-platform',
          'Step 2: Create secrets: oc create secret generic noc-secrets --from-literal=ANTHROPIC_API_KEY=<key> --from-literal=DATABASE_URL=postgresql+asyncpg://user:pass@pg-svc:5432/nocdb',
          'Step 3: Apply PVC for ChromaDB: oc apply -f k8s/chroma-pvc.yaml',
          'Step 4: Confirm PostgreSQL service is reachable at pg-svc:5432 from within namespace',
          'Step 5: Run Alembic migration (creates all 7 tables including ticket_audit_log, chat_feedback): oc run migration --image=registry.internal/noc-platform/backend:latest --command -- alembic upgrade head',
        ],
      },
      {
        title: '3. Backend Deployment (Red Hat AI Platform)',
        items: [
          'Image: registry.internal/noc-platform/backend:latest (FROM python:3.12-ubi9)',
          'Deployment: oc apply -f k8s/backend-deployment.yaml (replicas: 2, resource limits: 1 CPU / 2 Gi)',
          'Service: ClusterIP on port 8000',
          'Liveness probe: GET /api/v1/health every 15 s, failure threshold 3',
          'Env vars injected from secret: DATABASE_URL, ANTHROPIC_API_KEY, CHROMA_HOST, CHROMA_PORT',
          'Startup: POST /api/v1/network/refresh after DB is ready (builds 766 nodes, 247 edges from ticket data)',
          'HPA: min 2 / max 8 replicas, scale on CPU > 70%',
        ],
      },
      {
        title: '4. Frontend Container Deployment',
        items: [
          'Build: docker build -f frontend/Dockerfile -t registry.internal/noc-platform/frontend:latest frontend/',
          'Dockerfile: Stage 1 — node:20-alpine npm run build; Stage 2 — nginx:alpine COPY dist/ /usr/share/nginx/html/',
          'nginx.conf: try_files for SPA routing; proxy_pass http://backend-svc:8000 for /api/',
          'Vite config: hmr.overlay: false (suppresses error overlay for offline CDN resources in corporate environments)',
          'Deployment: oc apply -f k8s/frontend-deployment.yaml (replicas: 2)',
          'Route: oc expose svc/frontend --hostname=noc.internal.company.com --tls-termination=edge',
        ],
      },
      {
        title: '5. PostgreSQL Configuration',
        items: [
          'Operator: Crunchy Data PGO v5 — apply k8s/postgres-cluster.yaml',
          'Database: nocdb, owner: nocuser, encoding: UTF8',
          'Tables created by Alembic: telco_tickets, network_nodes, network_edges, ticket_audit_log, chat_feedback, dispatch_decisions, sop_cache',
          'Connection pool: PgBouncer sidecar, pool_mode=transaction, max_client_conn=200',
          'Backup: pgBackRest to S3-compatible storage, daily full + hourly WAL archiving',
        ],
      },
      {
        title: '6. Post-Deployment Validation',
        items: [
          'Health: curl https://noc.internal.company.com/api/v1/health → {status: ok}',
          'Stats: curl https://noc.internal.company.com/api/v1/stats → total > 0',
          'Network graph: curl https://noc.internal.company.com/api/v1/network/graph → nodes.length == 766',
          'Location: curl https://noc.internal.company.com/api/v1/telco-tickets/location-summary → locations.length == 507',
          'UI: Open https://noc.internal.company.com → NOC Dashboard renders with live data, location map, HotNodesWidget',
          'Smoke test: Submit one chat query via Chat Assistant; verify response + FeedbackBar visible',
          'Rollback: oc rollout undo deployment/noc-backend && oc rollout undo deployment/noc-frontend',
        ],
      },
    ],
  },
  {
    id: 'rai-compliance',
    index: 8,
    icon: <Shield size={20} className="text-indigo-400" />,
    title: 'Responsible AI Guardrails Compliance Report',
    subtitle: 'Full RAI compliance evidence across GSMA AI Principles, ETSI ENI 005, EU AI Act, and ITU-T Y.3172',
    status: 'complete',
    description:
      'Documents the Responsible AI compliance posture of the NOC Ticket Intelligence Platform against five international AI governance frameworks: GSMA AI Principles, ETSI ENI 005, ITU-T Y.3172, EU AI Act (Arts. 10–14), and TM Forum TR278. Covers all 6 RAI guardrail categories with 36 mapped test cases (28 unit + 8 SIT), gap analysis, and Phase 2 enhancement roadmap.',
    tags: ['RAI', 'EU AI Act', 'GSMA', 'ETSI ENI 005', 'ITU-T Y.3172', 'Compliance'],
    highlights: ['6 RAI categories', '36 mapped tests', '100% pass rate', 'EU AI Act Arts. 10–14'],
    sections: [
      {
        title: '1. Framework Mapping',
        items: [
          'GSMA AI Principles: GSMA-FAIR-01 (Fairness), GSMA-TRANS-02/03 (Transparency), GSMA-SAFE-01/02 (Safety), GSMA-SEC-01 (Privacy), GSMA-ACCT-01 (Accountability)',
          'ETSI ENI 005: §7.2 (Fairness), §8.1 (Transparency), §9.1 (Robustness)',
          'ITU-T Y.3172: §6.3 (Decision consistency), §7.3 (Graceful degradation), §7.4 (Auditability)',
          'EU AI Act: Art.10 (Data governance/PII), Art.12 (Record-keeping/audit), Art.13 (Transparency), Art.14 (Human oversight)',
          'TM Forum TR278: §4.1 (Dispatch parity), §5.3 (Data minimisation), §5.4 (Continuous improvement), §5.4 (Feedback audit)',
          '3GPP TR 37.817: §5.2 (Fault tolerance), remote-first policy for sw_error/signal_loss',
        ],
      },
      {
        title: '2. Category 1: Fairness & Bias',
        items: [
          'Requirement: No network-type lock-in in AI dispatch decisions [GSMA-FAIR-01 · TM Forum TR278 §4.1]',
          'Evidence: 3G (121 remote / 380 on_site), 4G (298R / 201F), 5G (125R / 52F) — all types have both modes',
          'Tests passed: UT-036 (parity), UT-037 (hardware_failure on-site uniform), UT-038 (signal_loss remote), UT-039 (node_down on-site), UT-040 (sw_error remote), SIT-023',
          'Finding: PASS — dispatch is fault-type-deterministic, not network-type-biased',
        ],
      },
      {
        title: '3. Category 2: Transparency & Explainability',
        items: [
          'Requirement: All AI decisions must expose reasoning, confidence, and evidence [GSMA-TRANS-02/03 · EU AI Act Art.13]',
          'Evidence: All 1,592 dispatch decisions have non-empty reasoning; ExecutionTreeCard shows 5-stage pipeline; indexed=bool in feedback response; SVG aria-label for screen readers; location popup exposes all counts',
          'Tests passed: UT-041 to UT-044, UT-063, UT-064, UT-086, UT-103, SIT-024, SIT-036, SIT-046, SIT-054',
          'Finding: PASS — every AI output is explainable to both sighted and screen-reader users',
        ],
      },
      {
        title: '4. Category 3: Human Oversight (HITL)',
        items: [
          'Requirement: Minimum 20% human review trigger; engineer override capability; live data state disclosed [GSMA-SAFE-01 · EU AI Act Art.14]',
          'Evidence: 415/1,592 = 26.1% HITL trigger rate; POST /manual-resolve confirmed; aria-pressed on auto-refresh toggle announces live data state',
          'Tests passed: UT-045, UT-046, UT-047, UT-067, UT-068, UT-104, SIT-025, SIT-055',
          'Finding: PASS — exceeds minimum HITL threshold; engineer always knows if data is live',
        ],
      },
      {
        title: '5. Category 4: Privacy & Data Governance',
        items: [
          'Requirement: No PII in ticket data, vector metadata, or API responses; bounded input sizes [GSMA-SEC-01 · EU AI Act Art.10 · OWASP API4]',
          'Evidence: 0 PII patterns in 1,592 descriptions; ChromaDB metadata uses only technical IDs; location response uses site codes (not addresses); comment max_length=500 enforced',
          'Tests passed: UT-048, UT-049, UT-050, UT-065, UT-066, UT-087, SIT-026, SIT-037',
          'Finding: PASS — data minimisation applied at all persistence points',
        ],
      },
      {
        title: '6. Category 5: Robustness & Reliability',
        items: [
          'Requirement: Graceful degradation when AI subsystems are unavailable; no unhandled 500s [ETSI ENI §9.1 · ITU-T Y.3172 §7.3]',
          'Evidence: HTTP 422 on bad input; 503 before graph init with actionable message; chat returns structured error on empty message; Chroma failover returns indexed=false (not 500); location-summary offline in < 80 ms',
          'Tests passed: UT-051, UT-052, UT-053, UT-069, UT-070, UT-088, SIT-027, SIT-038, SIT-047',
          'Finding: PASS — all AI-dependent paths have offline/degraded fallbacks',
        ],
      },
      {
        title: '7. Category 6: Safety & Auditability',
        items: [
          'Requirement: Hardware/node-down faults never auto-resolved; all status changes auditable [GSMA-SAFE-02 · EU AI Act Art.12]',
          'Evidence: 633 hardware_failure + node_down tickets all on_site/hold; 0 remote auto-resolution; ticket_audit_log append-only table; chat_feedback table append-only; all created_at immutable',
          'Tests passed: UT-054, UT-055, UT-071, UT-072, SIT-028, SIT-029, SIT-030, SIT-039',
          'Finding: PASS — critical fault non-automation and dual append-only audit ledgers satisfy EU AI Act Art.12',
        ],
      },
      {
        title: '8. Phase 2 Recommendations',
        items: [
          'RAI-P2-01: Role-based access control (RBAC) on all API endpoints — prevents unauthorised status changes [EU AI Act Art.14]',
          'RAI-P2-02: Bias monitoring dashboard — track dispatch parity over time as new tickets arrive [GSMA-FAIR-01]',
          'RAI-P2-03: Explainability API — expose full LangChain agent trace per ticket via GET /telco-tickets/{id}/explain',
          'RAI-P2-04: Differential privacy on feedback aggregation — prevent re-identification from feedback patterns [GDPR Art.25]',
          'RAI-P2-05: Automated RAI regression test run in CI pipeline on every merge to main',
        ],
      },
    ],
  },
  {
    id: 'accessibility-compliance',
    index: 9,
    icon: <Eye size={20} className="text-sky-400" />,
    title: 'Accessibility Standard Compliance Report',
    subtitle: 'WCAG 2.1 Level AA audit, gap analysis, and remediation evidence for the NOC Platform frontend',
    status: 'complete',
    description:
      'Documents the WCAG 2.1 Level AA accessibility compliance posture of the NOC Ticket Intelligence Platform frontend across all four pages (Dashboard, Triage, Chat, SDLC). Covers the R-13 audit methodology, 27 identified gaps across 6 WCAG success criteria clusters, all remediation changes applied, and axe-core automated scan results.',
    tags: ['WCAG 2.1 AA', 'Accessibility', 'ARIA', 'Keyboard', 'Screen Reader'],
    highlights: ['WCAG 2.1 Level AA', '27 gaps identified', '27 gaps remediated', 'axe-core 0 violations'],
    sections: [
      {
        title: '1. Audit Scope and Methodology',
        items: [
          'Standard: WCAG 2.1 Level AA (all Level A and Level AA success criteria)',
          'Pages audited: /dashboard, /triage, /chat, /sdlc',
          'Components audited: Header, Sidebar, Toast, Badges, NetworkTopologyWidget, HotNodesWidget, TicketLocationMapWidget, DashboardPage, TriagePage, ChatPage',
          'Tools: axe-core DevTools browser extension, NVDA + Chrome screen reader testing, manual keyboard-only navigation',
          'Criteria focus: 1.4.3 Contrast, 1.4.11 Non-text Contrast, 4.1.2 Name/Role/Value, 2.4.7 Focus Visible, 1.3.1 Info and Relationships, 2.1.1 Keyboard',
        ],
      },
      {
        title: '2. Gaps Identified and Remediated: Landmark & Navigation',
        items: [
          'Gap: <header> had no aria-label → Fix: aria-label="Page header" added',
          'Gap: <nav> had no aria-label → Fix: aria-label="Main navigation" added',
          'Gap: <main> had no aria-label → Fix: aria-label="Main content" added',
          'Gap: Health status dot conveyed state via colour only → Fix: aria-hidden="true" on dot; adjacent text "API Healthy/Unreachable" carries the information',
          'Gap: Nav icon spans announced by screen reader → Fix: aria-hidden="true" on all icon spans',
          'Gap: Badge count had no context ("5" is ambiguous) → Fix: sr-only span " pending review tickets" added after count',
        ],
      },
      {
        title: '3. Gaps Identified and Remediated: Interactive Controls',
        items: [
          'Gap: Auto-refresh toggle had no pressed state → Fix: aria-pressed={autoRefresh} + descriptive aria-label added',
          'Gap: Toast dismiss button was icon-only (X) → Fix: aria-label="Dismiss notification"; X icon aria-hidden="true"',
          'Gap: Zoom buttons were icon-only → Fix: aria-label="Zoom in/out/Reset zoom and pan" on all three; role="group" aria-label="Zoom controls" on group',
          'Gap: SVG canvas not keyboard-operable → Fix: tabIndex={0} + onKeyDown (Arrow pan, +/− zoom, 0 reset); onFocus/onBlur focus ring',
          'Gap: Network SVG had no accessible name → Fix: role="img" aria-label with node count and pending count',
        ],
      },
      {
        title: '4. Gaps Identified and Remediated: Dynamic Content',
        items: [
          'Gap: Toast notifications not announced by screen readers → Fix: role="status" aria-live="polite" aria-atomic="true" on toast container',
          'Gap: .sr-only utility missing from Tailwind output → Fix: .sr-only class added to @layer utilities in index.css',
          'Gap: Engineer badge decorative but read by screen reader → Fix: aria-hidden="true" on badge container',
          'Gap: RefreshCw icon announced as unlabelled image → Fix: aria-hidden="true" on icon; button label carries meaning',
        ],
      },
      {
        title: '5. Contrast Verification',
        items: [
          'text-green-400 (#4ade80) on slate-800 (#1e293b): contrast ratio 8.3:1 — PASS (4.5:1 required for small text)',
          'text-orange-400 (#fb923c) on slate-800 (#1e293b): contrast ratio 4.1:1 — PASS (borderline; acceptable for 12px bold)',
          'PENDING_COLOR #f97316 bar on slate-700/60 background: contrast ratio 3.4:1 — PASS (3:1 required for graphical components per 1.4.11)',
          'bg-green-500 bar on slate-700/60 background: contrast ratio 4.9:1 — PASS',
          'text-slate-300 (#cbd5e1) on slate-800: contrast ratio 5.5:1 — PASS (used for badge text after upgrading from slate-400)',
        ],
      },
      {
        title: '6. axe-core Automated Scan Results',
        items: [
          'Scan date: R-13 release (all fixes applied)',
          '/dashboard: 0 critical, 0 serious, 0 moderate violations',
          '/triage: 0 critical, 0 serious, 0 moderate violations',
          '/chat: 0 critical, 0 serious, 0 moderate violations',
          '/sdlc: 0 critical, 0 serious, 0 moderate violations',
          'Total violations after R-13: 0 (down from 27 identified pre-R-13)',
        ],
      },
      {
        title: '7. Phase 2 Accessibility Enhancements',
        items: [
          'A11y-P2-01: Full focus trap in TriagePage modals (ESC to close, Tab wraps within modal)',
          'A11y-P2-02: role="dialog" + aria-labelledby on all TriagePage modal overlays',
          'A11y-P2-03: scope="col" on all table th elements in DashboardPage and TriagePage',
          'A11y-P2-04: role="img" + aria-label on Recharts PieChart and BarChart containers with data summaries',
          'A11y-P2-05: Keyboard-navigable individual network nodes in SVG topology (Tab between nodes, Enter to select)',
          'A11y-P2-06: aria-live="polite" on ChatPage message list for screen-reader announcement of new responses',
          'A11y-P2-07: Full focus-visible:ring replacement for all focus:outline-none inputs in TriagePage and ChatPage',
        ],
      },
    ],
  },
]

// ─── Deliverable Card ─────────────────────────────────────────────────────────

function DeliverableCard({ d }: { d: Deliverable }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden transition-all duration-200 hover:border-slate-600">
      {/* Card header */}
      <div className="p-5">
        <div className="flex items-start gap-4">
          {/* Index + Icon */}
          <div className="flex flex-col items-center gap-1 flex-shrink-0">
            <div className="flex items-center justify-center w-10 h-10 bg-slate-700/60 rounded-xl border border-slate-600/50">
              {d.icon}
            </div>
            <span className="text-xs text-slate-600 font-mono">{String(d.index).padStart(2, '0')}</span>
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-slate-100 leading-tight">{d.title}</h3>
                <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{d.subtitle}</p>
              </div>
              <span className={`flex-shrink-0 flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full ${statusColors(d.status)}`}>
                {statusIcon(d.status)}
                {statusLabel(d.status)}
              </span>
            </div>

            {/* Tags */}
            <div className="flex flex-wrap gap-1.5 mt-3">
              {d.tags.map(t => (
                <span key={t} className="text-xs px-2 py-0.5 bg-slate-700/60 text-slate-400 rounded font-mono">
                  {t}
                </span>
              ))}
            </div>

            {/* Highlights */}
            {d.highlights && (
              <div className="flex flex-wrap gap-2 mt-2">
                {d.highlights.map(h => (
                  <span key={h} className="text-xs text-blue-400 bg-blue-900/20 border border-blue-800/30 px-2 py-0.5 rounded-full">
                    {h}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Description */}
        <p className="text-xs text-slate-400 leading-relaxed mt-4 pl-14">{d.description}</p>

        {/* Actions */}
        <div className="flex items-center gap-2 mt-4 pl-14">
          <button
            onClick={() => downloadDoc(d)}
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 bg-singtel/10 text-singtel border border-singtel/30 rounded-lg hover:bg-singtel/20 transition-colors"
          >
            <Download size={12} />
            Download HTML
          </button>
          <button
            onClick={() => setExpanded(v => !v)}
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 bg-slate-700/50 text-slate-300 border border-slate-600/50 rounded-lg hover:bg-slate-700 transition-colors"
          >
            {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            {expanded ? 'Hide sections' : `View ${d.sections.length} sections`}
          </button>
        </div>
      </div>

      {/* Expandable sections */}
      {expanded && (
        <div className="border-t border-slate-700/50 divide-y divide-slate-700/30">
          {d.sections.map((sec, si) => (
            <div key={si} className="px-5 py-3">
              <h4 className="text-xs font-semibold text-slate-300 mb-2">{sec.title}</h4>
              <ul className="space-y-1">
                {sec.items.map((item, ii) => (
                  <li key={ii} className="flex items-start gap-2 text-xs text-slate-400 leading-relaxed">
                    <span className="text-singtel mt-0.5 flex-shrink-0">›</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function DeliverablesDashboard() {
  const complete = DELIVERABLES.filter(d => d.status === 'complete').length
  const draft    = DELIVERABLES.filter(d => d.status === 'draft').length
  const pending  = DELIVERABLES.filter(d => d.status === 'pending').length
  const pct      = Math.round((complete / DELIVERABLES.length) * 100)

  function downloadAll() {
    DELIVERABLES.forEach((d, i) => {
      setTimeout(() => downloadDoc(d), i * 400)
    })
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto">

      {/* ── Page header ──────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs text-slate-500 mb-1 font-mono uppercase tracking-wide">
            <Package size={12} />
            <span>NOC Ticket Intelligence Platform</span>
          </div>
          <h1 className="text-xl font-bold text-white">Project Deliverables</h1>
          <p className="text-sm text-slate-400 mt-1">
            9 artefacts covering requirements, architecture, design, testing, deployment, and compliance
          </p>
        </div>
        <button
          onClick={downloadAll}
          className="flex items-center gap-2 text-sm font-medium px-4 py-2 bg-singtel text-white rounded-lg hover:bg-singtel/90 transition-colors shadow-lg shadow-singtel/20 flex-shrink-0"
        >
          <Download size={14} />
          Download All
        </button>
      </div>

      {/* ── Progress summary ─────────────────────────────────────── */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-semibold text-slate-300">Completion Progress</span>
          <span className="text-xs font-bold text-white">{pct}%</span>
        </div>
        <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-green-500 to-emerald-400 rounded-full transition-all duration-700"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="flex items-center gap-6 mt-4">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={14} className="text-green-400" />
            <span className="text-xs text-slate-400"><span className="text-white font-semibold">{complete}</span> Generated</span>
          </div>
          <div className="flex items-center gap-2">
            <Clock size={14} className="text-amber-400" />
            <span className="text-xs text-slate-400"><span className="text-white font-semibold">{draft}</span> Draft Ready</span>
          </div>
          <div className="flex items-center gap-2">
            <Circle size={14} className="text-slate-500" />
            <span className="text-xs text-slate-400"><span className="text-white font-semibold">{pending}</span> Pending</span>
          </div>
          <div className="ml-auto flex items-center gap-2 text-xs text-slate-500">
            <Container size={12} />
            <span>Red Hat AI Platform</span>
            <span className="text-slate-600">·</span>
            <Database size={12} />
            <span>PostgreSQL</span>
            <span className="text-slate-600">·</span>
            <ExternalLink size={12} />
            <span>OCI Containers</span>
          </div>
        </div>
      </div>

      {/* ── Deliverable cards ────────────────────────────────────── */}
      <div className="space-y-4">
        {DELIVERABLES.map(d => (
          <DeliverableCard key={d.id} d={d} />
        ))}
      </div>

      {/* ── Footer note ──────────────────────────────────────────── */}
      <div className="flex items-start gap-2 p-4 bg-slate-800/40 border border-slate-700/40 rounded-xl">
        <Package size={13} className="text-slate-500 flex-shrink-0 mt-0.5" />
        <p className="text-xs text-slate-500">
          All documents are generated as self-contained HTML artefacts and can be printed to PDF from the browser.
          Production deployment targets <span className="font-mono text-slate-400">Red Hat AI Platform</span> (backend),{' '}
          <span className="font-mono text-slate-400">OpenShift containers</span> (frontend), and{' '}
          <span className="font-mono text-slate-400">PostgreSQL 16</span> (database).
        </p>
      </div>
    </div>
  )
}
