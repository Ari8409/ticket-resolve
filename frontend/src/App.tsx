import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/layout/Sidebar'
import Header from './components/layout/Header'
import DashboardPage from './pages/DashboardPage'
import TriagePage from './pages/TriagePage'
import ChatPage from './pages/ChatPage'
import SDLCDashboard from './pages/SDLCDashboard'
import DeliverablesDashboard from './pages/DeliverablesDashboard'
import { useAutoRefresh } from './hooks/useAutoRefresh'
import { ToastProvider } from './components/shared/Toast'

function AppLayout() {
  const { autoRefresh, setAutoRefresh, lastUpdated } = useAutoRefresh()

  return (
    <div className="flex h-screen bg-slate-900 overflow-hidden">
      <Sidebar />
      <div className="flex flex-col flex-1 overflow-hidden">
        <Header
          autoRefresh={autoRefresh}
          setAutoRefresh={setAutoRefresh}
          lastUpdated={lastUpdated}
        />
        <main aria-label="Main content" className="flex-1 overflow-auto p-6">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage autoRefresh={autoRefresh} />} />
            <Route path="/triage" element={<TriagePage autoRefresh={autoRefresh} />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/sdlc" element={<SDLCDashboard />} />
            <Route path="/deliverables" element={<DeliverablesDashboard />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <AppLayout />
    </ToastProvider>
  )
}
