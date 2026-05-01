import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'

const API = 'http://localhost:5000'
const priorityColor = { P0: '#ff4444', P1: '#ff8800', P2: '#0088ff' }
const statusColor = { OPEN: '#ff4444', INVESTIGATING: '#ff8800', RESOLVED: '#00aa00', CLOSED: '#888' }

export default function Dashboard() {
  const [incidents, setIncidents] = useState([])
  const navigate = useNavigate()

  const fetchIncidents = () => {
    axios.get(`${API}/incidents`).then(r => setIncidents(r.data))
  }

  useEffect(() => {
    fetchIncidents()
    const interval = setInterval(fetchIncidents, 5000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div>
      <h2>Live Incidents</h2>
      <button onClick={fetchIncidents} style={{ marginBottom: 16, padding: '8px 16px' }}>
        Refresh
      </button>
      {incidents.length === 0 && <p>No incidents yet. Run mock_failure.py to generate some.</p>}
      {incidents.map(inc => (
        <div key={inc.id}
          onClick={() => navigate(`/incidents/${inc.id}`)}
          style={{
            border: '1px solid #ddd', borderRadius: 8, padding: 16,
            marginBottom: 12, cursor: 'pointer',
            borderLeft: `5px solid ${priorityColor[inc.priority] || '#888'}`
          }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <strong>{inc.component_id}</strong>
            <span style={{ background: priorityColor[inc.priority], color: '#fff',
              borderRadius: 4, padding: '2px 8px', fontSize: 12 }}>
              {inc.priority}
            </span>
          </div>
          <div style={{ marginTop: 8, display: 'flex', gap: 16, fontSize: 14, color: '#555' }}>
            <span style={{ color: statusColor[inc.status] }}>{inc.status}</span>
            <span>{inc.signal_count} signals</span>
            <span>{new Date(inc.created_at).toLocaleString()}</span>
          </div>
        </div>
      ))}
    </div>
  )
}
