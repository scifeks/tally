import { Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import Dashboard from './pages/Dashboard'
import Findings from './pages/Findings'
import UrlLists from './pages/UrlLists'
import Scans from './pages/Scans'
import Triage from './pages/Triage'
import Reports from './pages/Reports'
import Chat from './pages/Chat'
import Config from './pages/Config'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="findings" element={<Findings />} />
        <Route path="urls" element={<UrlLists />} />
        <Route path="scans" element={<Scans />} />
        <Route path="triage" element={<Triage />} />
        <Route path="reports" element={<Reports />} />
        <Route path="chat" element={<Chat />} />
        <Route path="config" element={<Config />} />
      </Route>
    </Routes>
  )
}
