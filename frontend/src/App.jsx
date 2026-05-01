import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Dashboard from './Dashboard'
import IncidentDetail from './IncidentDetail'

export default function App() {
  return (
    <BrowserRouter>
      <div style={{ fontFamily: 'sans-serif', maxWidth: 900, margin: '0 auto', padding: 20 }}>
        <h1 style={{ borderBottom: '2px solid #333', paddingBottom: 10 }}>
          IMS — Incident Management System
        </h1>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/incidents/:id" element={<IncidentDetail />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}
