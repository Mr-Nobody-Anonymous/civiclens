import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppProvider } from './lib/store'
import { I18nProvider } from './lib/i18n'
import Layout from './components/Layout'
import Landing from './pages/Landing'
import ReportWizard from './pages/ReportWizard'
import Reports from './pages/Reports'
import ReportDetail from './pages/ReportDetail'
import MapPage from './pages/MapPage'
import Login from './pages/Login'
import AdminDashboard from './pages/AdminDashboard'
import OrgDashboard from './pages/OrgDashboard'
import PriorityQueue from './pages/PriorityQueue'
import Settings from './pages/Settings'
import Privacy from './pages/Privacy'
import Transparency from './pages/Transparency'

export default function App() {
  return (
    <I18nProvider>
      <AppProvider>
        <BrowserRouter>
          <Layout>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/report" element={<ReportWizard />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/reports/:id" element={<ReportDetail />} />
              <Route path="/map" element={<MapPage />} />
              <Route path="/login" element={<Login />} />
              <Route path="/dashboard" element={<AdminDashboard />} />
              <Route path="/organization" element={<OrgDashboard />} />
              <Route path="/priority" element={<PriorityQueue />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/privacy" element={<Privacy />} />
              <Route path="/transparency" element={<Transparency />} />
            </Routes>
          </Layout>
        </BrowserRouter>
      </AppProvider>
    </I18nProvider>
  )
}
