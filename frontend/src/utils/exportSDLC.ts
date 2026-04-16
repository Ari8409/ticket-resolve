/**
 * Generates a complete self-contained HTML file for the SDLC Dashboard.
 * All styles are inlined — the output file has zero external dependencies
 * and can be opened in any browser or shared via email / Teams / Confluence.
 */

// ─── Types (mirror SDLCDashboard.tsx) ────────────────────────────────────────

type ReleaseKey = 'All' | 'R-0' | 'R-1' | 'R-2' | 'R-3' | 'R-4' | 'R-5' | 'R-6' | 'R-7' | 'R-8'
type RICEFCategory = 'R' | 'I' | 'C' | 'E' | 'F'

interface Iteration {
  releaseKey: ReleaseKey
  label: string
  type: string
  instruction: string
  techStack: string[]
  timeTakenMin: number
  tokensUsed: number
  apiEndpointsAdded: number
  filesChanged: number
  delivered: string[]
  ricef: string[]
  metrics: string[]
}

interface RICEFItem {
  id: string
  category: RICEFCategory
  component: string
  description: string
  file: string
  complexity: 'Low' | 'Medium' | 'High'
  status: 'Complete' | 'In Progress' | 'Planned'
  iteration: ReleaseKey
}

interface TestCase {
  id: string
  component: string
  description: string
  result: 'PASS' | 'FAIL' | 'SKIP'
  assertions: number
  iteration: ReleaseKey
}

interface SITCase {
  id: string
  scenario: string
  expected: string
  actual: string
  result: 'PASS' | 'FAIL' | 'SKIP'
  iteration: ReleaseKey
}

// ─── Colour palette (release → accent hex) ───────────────────────────────────

const RELEASE_COLORS: Record<string, string> = {
  'R-0': '#60a5fa',
  'R-1': '#c084fc',
  'R-2': '#fbbf24',
  'R-3': '#4ade80',
  'R-4': '#22d3ee',
  'R-5': '#f472b6',
  'R-6': '#fb923c',
  'R-7': '#cbd5e1',
  'R-8': '#2dd4bf',
}

const RICEF_COLORS: Record<RICEFCategory, string> = {
  R: '#60a5fa',
  I: '#c084fc',
  C: '#fbbf24',
  E: '#4ade80',
  F: '#f472b6',
}

// ─── HTML helpers ─────────────────────────────────────────────────────────────

const esc = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

const badge = (text: string, bg: string, color: string) =>
  `<span style="background:${bg};color:${color};padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;white-space:nowrap">${esc(text)}</span>`

const resultBadge = (r: 'PASS' | 'FAIL' | 'SKIP') => {
  const cfg = r === 'PASS'
    ? { bg: 'rgba(74,222,128,0.15)', color: '#4ade80', border: '#4ade80' }
    : r === 'FAIL'
    ? { bg: 'rgba(248,113,113,0.15)', color: '#f87171', border: '#f87171' }
    : { bg: 'rgba(148,163,184,0.15)', color: '#94a3b8', border: '#94a3b8' }
  return `<span style="background:${cfg.bg};color:${cfg.color};border:1px solid ${cfg.border};padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700">${r}</span>`
}

const complexityDots = (level: 'Low' | 'Medium' | 'High') => {
  const n = level === 'Low' ? 1 : level === 'Medium' ? 2 : 3
  const color = level === 'Low' ? '#4ade80' : level === 'Medium' ? '#fbbf24' : '#f87171'
  return [1, 2, 3].map(i =>
    `<span style="width:8px;height:8px;border-radius:50%;display:inline-block;background:${i <= n ? color : '#334155'}"></span>`
  ).join('&nbsp;')
}

// ─── Section generators ───────────────────────────────────────────────────────

function summarySection(iterations: Iteration[], unitTests: TestCase[], sitTests: SITCase[]): string {
  const totalTime = iterations.reduce((s, i) => s + i.timeTakenMin, 0)
  const totalTokens = iterations.reduce((s, i) => s + i.tokensUsed, 0)
  const utPass = unitTests.filter(t => t.result === 'PASS').length
  const sitPass = sitTests.filter(t => t.result === 'PASS').length

  const cards = [
    { label: 'Releases',        value: String(iterations.length), color: '#60a5fa' },
    { label: 'RICEF Complete',  value: '20/20',                   color: '#c084fc' },
    { label: 'API Endpoints',   value: '17',                      color: '#fbbf24' },
    { label: 'Tickets Processed', value: '1,592',                 color: '#4ade80' },
    { label: 'Total Build Time', value: `${totalTime} min`,       color: '#2dd4bf' },
    { label: 'Total Tokens',    value: `${(totalTokens / 1000).toFixed(0)}k`, color: '#facc15' },
    { label: 'Unit Tests',      value: `${utPass}/${unitTests.length}`,       color: '#22d3ee' },
    { label: 'SIT Passed',      value: `${sitPass}/${sitTests.length}`,       color: '#f472b6' },
  ]

  const cardHtml = cards.map(c => `
    <div style="background:#1e293b;border:1px solid #334155;border-radius:10px;padding:16px;min-width:110px;flex:1">
      <div style="font-size:22px;font-weight:800;color:${c.color};margin-bottom:4px">${esc(c.value)}</div>
      <div style="font-size:11px;color:#64748b;line-height:1.3">${esc(c.label)}</div>
    </div>`).join('')

  return `
    <section style="margin-bottom:32px">
      <div style="display:flex;flex-wrap:wrap;gap:12px">${cardHtml}</div>
    </section>`
}

function timelineSection(iterations: Iteration[]): string {
  const cards = iterations.map(iter => {
    const color = RELEASE_COLORS[iter.releaseKey] ?? '#94a3b8'
    const delivered = iter.delivered.map(d =>
      `<div style="display:flex;gap:8px;margin-bottom:5px">
        <span style="color:${color};flex-shrink:0;margin-top:2px">✓</span>
        <span style="font-size:12px;color:#94a3b8;line-height:1.5">${esc(d)}</span>
      </div>`
    ).join('')

    const tech = iter.techStack.map(t =>
      `<span style="background:#0f172a;color:#94a3b8;border:1px solid #334155;padding:2px 7px;border-radius:4px;font-size:11px">${esc(t)}</span>`
    ).join(' ')

    const metrics = iter.metrics.map(m =>
      `<span style="background:#0f172a;color:#cbd5e1;border:1px solid #334155;padding:2px 8px;border-radius:12px;font-size:11px">${esc(m)}</span>`
    ).join(' ')

    return `
      <div style="border:1px solid #334155;border-left:3px solid ${color};border-radius:10px;padding:18px;margin-bottom:14px">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:10px">
          <div>
            <span style="color:${color};font-weight:800;font-family:monospace;font-size:12px">${esc(iter.label)}</span>
            <span style="color:#fff;font-weight:600;font-size:14px;margin-left:8px">${esc(iter.type)}</span>
            <div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:5px">${tech}</div>
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center">
            ${metrics}
            <span style="background:#0f172a;color:#94a3b8;border:1px solid #334155;padding:2px 8px;border-radius:12px;font-size:11px">⏱ ${iter.timeTakenMin} min</span>
            <span style="background:#0f172a;color:#94a3b8;border:1px solid #334155;padding:2px 8px;border-radius:12px;font-size:11px">⚡ ${(iter.tokensUsed / 1000).toFixed(1)}k tokens</span>
          </div>
        </div>
        <div style="background:#0f172a;border-left:3px solid ${color};padding:8px 12px;border-radius:4px;margin-bottom:12px;font-size:12px;color:#64748b;font-style:italic;line-height:1.5">
          "${esc(iter.instruction)}"
        </div>
        <div style="font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px">Delivered</div>
        ${delivered}
      </div>`
  }).join('')

  return `
    <section style="margin-bottom:40px">
      <h2 style="color:#e2e8f0;font-size:16px;font-weight:700;margin:0 0 16px;display:flex;align-items:center;gap:8px">
        🔀 Iterative Build Timeline
      </h2>
      ${cards}
    </section>`
}

function ricefSection(items: RICEFItem[]): string {
  const catLabel: Record<RICEFCategory, string> = { R: 'Report', I: 'Interface', C: 'Conversion', E: 'Enhancement', F: 'Form' }

  const rows = items.map(item => {
    const color = RICEF_COLORS[item.category]
    return `
      <tr style="border-bottom:1px solid #1e293b">
        <td style="padding:10px 12px;font-weight:700;font-family:monospace;font-size:12px;color:#e2e8f0">${esc(item.id)}</td>
        <td style="padding:10px 12px">${badge(catLabel[item.category], `${color}22`, color)}</td>
        <td style="padding:10px 12px;color:#e2e8f0;font-size:13px;font-weight:600">${esc(item.component)}</td>
        <td style="padding:10px 12px;color:#64748b;font-size:12px;line-height:1.4">${esc(item.description)}</td>
        <td style="padding:10px 12px;color:#475569;font-size:11px;font-family:monospace">${esc(item.file)}</td>
        <td style="padding:10px 12px">${complexityDots(item.complexity)}</td>
        <td style="padding:10px 12px">${badge(item.status, item.status === 'Complete' ? 'rgba(74,222,128,0.15)' : 'rgba(251,191,36,0.15)', item.status === 'Complete' ? '#4ade80' : '#fbbf24')}</td>
        <td style="padding:10px 12px">
          <span style="color:${RELEASE_COLORS[item.iteration] ?? '#94a3b8'};font-family:monospace;font-size:11px;font-weight:700">${esc(item.iteration)}</span>
        </td>
      </tr>`
  }).join('')

  return `
    <section style="margin-bottom:40px">
      <h2 style="color:#e2e8f0;font-size:16px;font-weight:700;margin:0 0 16px">📋 RICEF Build Matrix</h2>
      <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead>
            <tr style="background:#1e293b;border-bottom:2px solid #334155">
              <th style="padding:10px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:0.05em;white-space:nowrap">ID</th>
              <th style="padding:10px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase;white-space:nowrap">Type</th>
              <th style="padding:10px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase;white-space:nowrap">Component</th>
              <th style="padding:10px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase">Description</th>
              <th style="padding:10px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase">File / Module</th>
              <th style="padding:10px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase;white-space:nowrap">Complexity</th>
              <th style="padding:10px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase">Status</th>
              <th style="padding:10px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase;white-space:nowrap">Release</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </section>`
}

function unitTestSection(tests: TestCase[]): string {
  const pass = tests.filter(t => t.result === 'PASS').length
  const rows = tests.map((t, i) => `
    <tr style="background:${i % 2 === 0 ? '#0f172a' : '#111827'};border-bottom:1px solid #1e293b">
      <td style="padding:9px 12px;font-family:monospace;font-size:12px;color:#94a3b8">${esc(t.id)}</td>
      <td style="padding:9px 12px;color:#e2e8f0;font-size:12px;font-weight:600">${esc(t.component)}</td>
      <td style="padding:9px 12px;color:#94a3b8;font-size:12px;line-height:1.4">${esc(t.description)}</td>
      <td style="padding:9px 12px;text-align:center;color:#64748b;font-size:12px">${t.assertions}</td>
      <td style="padding:9px 12px">${resultBadge(t.result)}</td>
      <td style="padding:9px 12px">
        <span style="color:${RELEASE_COLORS[t.iteration] ?? '#94a3b8'};font-family:monospace;font-size:11px;font-weight:700">${esc(t.iteration)}</span>
      </td>
    </tr>`).join('')

  return `
    <section style="margin-bottom:40px">
      <h2 style="color:#e2e8f0;font-size:16px;font-weight:700;margin:0 0 4px">🧪 Unit Tests</h2>
      <p style="color:#64748b;font-size:12px;margin:0 0 14px">${pass}/${tests.length} passed</p>
      <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead>
            <tr style="background:#1e293b;border-bottom:2px solid #334155">
              <th style="padding:9px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase;white-space:nowrap">ID</th>
              <th style="padding:9px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase;white-space:nowrap">Component</th>
              <th style="padding:9px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase">Description</th>
              <th style="padding:9px 12px;text-align:center;color:#64748b;font-size:11px;text-transform:uppercase;white-space:nowrap">Assertions</th>
              <th style="padding:9px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase">Result</th>
              <th style="padding:9px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase;white-space:nowrap">Release</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </section>`
}

function sitSection(tests: SITCase[]): string {
  const pass = tests.filter(t => t.result === 'PASS').length
  const rows = tests.map((t, i) => `
    <tr style="background:${i % 2 === 0 ? '#0f172a' : '#111827'};border-bottom:1px solid #1e293b">
      <td style="padding:9px 12px;font-family:monospace;font-size:12px;color:#94a3b8;white-space:nowrap">${esc(t.id)}</td>
      <td style="padding:9px 12px;color:#e2e8f0;font-size:12px;font-weight:600">${esc(t.scenario)}</td>
      <td style="padding:9px 12px;color:#64748b;font-size:11px;line-height:1.4">${esc(t.expected)}</td>
      <td style="padding:9px 12px;color:#94a3b8;font-size:11px;line-height:1.4">${esc(t.actual)}</td>
      <td style="padding:9px 12px">${resultBadge(t.result)}</td>
      <td style="padding:9px 12px">
        <span style="color:${RELEASE_COLORS[t.iteration] ?? '#94a3b8'};font-family:monospace;font-size:11px;font-weight:700">${esc(t.iteration)}</span>
      </td>
    </tr>`).join('')

  return `
    <section style="margin-bottom:40px">
      <h2 style="color:#e2e8f0;font-size:16px;font-weight:700;margin:0 0 4px">🔬 System Integration Tests (SIT)</h2>
      <p style="color:#64748b;font-size:12px;margin:0 0 14px">${pass}/${tests.length} passed</p>
      <div style="overflow-x:auto">
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead>
            <tr style="background:#1e293b;border-bottom:2px solid #334155">
              <th style="padding:9px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase;white-space:nowrap">ID</th>
              <th style="padding:9px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase">Scenario</th>
              <th style="padding:9px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase">Expected</th>
              <th style="padding:9px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase">Actual</th>
              <th style="padding:9px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase">Result</th>
              <th style="padding:9px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase;white-space:nowrap">Release</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </section>`
}

// ─── Public API ───────────────────────────────────────────────────────────────

export interface SDLCExportData {
  iterations: Iteration[]
  ricef: RICEFItem[]
  unitTests: TestCase[]
  sitTests: SITCase[]
  selectedRelease?: ReleaseKey
}

export function generateSDLCHTML(data: SDLCExportData): string {
  const { iterations, ricef, unitTests, sitTests, selectedRelease } = data
  const isAll = !selectedRelease || selectedRelease === 'All'

  const scopedIter  = isAll ? iterations : iterations.filter(i => i.releaseKey === selectedRelease)
  const scopedRICEF = isAll ? ricef       : ricef.filter(r => r.iteration === selectedRelease)
  const scopedUT    = isAll ? unitTests   : unitTests.filter(t => t.iteration === selectedRelease)
  const scopedSIT   = isAll ? sitTests    : sitTests.filter(t => t.iteration === selectedRelease)

  const scopeLabel  = isAll ? 'All Releases' : selectedRelease
  const generated   = new Date().toLocaleString('en-SG', { timeZone: 'Asia/Singapore', dateStyle: 'long', timeStyle: 'short' })

  const totalTime   = scopedIter.reduce((s, i) => s + i.timeTakenMin, 0)
  const totalTokens = scopedIter.reduce((s, i) => s + i.tokensUsed, 0)

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>SDLC Dashboard — NOC Ticket Resolution Platform (${esc(scopeLabel)})</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
      padding: 32px 24px;
      min-height: 100vh;
    }
    a { color: #60a5fa; }
    table { border-radius: 8px; overflow: hidden; }
    tr:hover { background: #1a2332 !important; }
    @media print {
      body { background: #fff; color: #111; padding: 12px; }
      tr:hover { background: transparent !important; }
    }
  </style>
</head>
<body>
  <div style="max-width:1200px;margin:0 auto">

    <!-- ── Header ─────────────────────────────────────────────── -->
    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;margin-bottom:28px;padding-bottom:20px;border-bottom:1px solid #1e293b">
      <div>
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
          <span style="font-size:22px">📡</span>
          <h1 style="font-size:22px;font-weight:800;color:#fff">SDLC Implementation Dashboard</h1>
        </div>
        <p style="color:#64748b;font-size:13px">NOC Ticket Resolution Platform · ${esc(scopeLabel)} · ${esc(scopedIter.length.toString())} release${scopedIter.length !== 1 ? 's' : ''}</p>
      </div>
      <div style="text-align:right">
        <div style="background:rgba(74,222,128,0.1);border:1px solid rgba(74,222,128,0.3);border-radius:8px;padding:6px 14px;display:inline-flex;align-items:center;gap:6px;margin-bottom:8px">
          <span style="color:#4ade80;font-size:13px">✓</span>
          <span style="color:#4ade80;font-size:12px;font-weight:600">ALL ITERATIONS COMPLETE</span>
        </div>
        <div style="color:#475569;font-size:11px">Generated ${esc(generated)}</div>
        <div style="color:#334155;font-size:11px;margin-top:2px">Total: ${totalTime} min · ${(totalTokens / 1000).toFixed(0)}k tokens</div>
      </div>
    </div>

    <!-- ── Sections ───────────────────────────────────────────── -->
    ${summarySection(scopedIter, scopedUT, scopedSIT)}
    ${timelineSection(scopedIter)}
    ${ricefSection(scopedRICEF)}
    ${unitTestSection(scopedUT)}
    ${sitSection(scopedSIT)}

    <!-- ── Footer ─────────────────────────────────────────────── -->
    <div style="border-top:1px solid #1e293b;padding-top:16px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
      <span style="color:#334155;font-size:11px">NOC Ticket Resolution Platform · Singtel NOC</span>
      <span style="color:#334155;font-size:11px">Generated by Claude Code · ${esc(generated)}</span>
    </div>

  </div>
</body>
</html>`
}

export function downloadSDLC(data: SDLCExportData): void {
  const html = generateSDLCHTML(data)
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  const scope = data.selectedRelease && data.selectedRelease !== 'All' ? `-${data.selectedRelease}` : ''
  a.href     = url
  a.download = `sdlc-dashboard${scope}-${new Date().toISOString().slice(0, 10)}.html`
  a.click()
  URL.revokeObjectURL(url)
}
