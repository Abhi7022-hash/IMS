import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import axios from 'axios'
import RCAForm from './RCAForm'

const API = 'http://localhost:5000'

export default function IncidentDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [incident, setIncident] = useState(null)
  const [showRCA, setShowRCA] = useState(false)
  const [message, setMessage] = useState('')

  const fetchIncident = () => {
    axios.get(`${API}/incidents/${id}`).then(r => setIncident(r.data))
  }

  useEffect(() => { fetchIncident() }, [id])

  const updateStatus = (newStatus) => {
    axios.patch(`${API}/incidents/${id}/status`, { status: newStatus })
      .then(() => { fetchIncident(); setMessage('') })
      .catch(e => setMessage(e.response?.data?.error || 'Error'))
  }

  if (!incident) return <p>Loading...</p>

  const transitions = {
    OPEN: 'INVESTIGATING',
    INVESTIGATING: 'RESOLVED',
    RESOLVED: 'CLOSED'
  }
  const nextStatus = transitions[incident.status]

  return (
    <div>
      <button onClick={() => navigate('/')} style={{ marginBottom: 16 }}>← Back</button>
      <h2>{incident.component_id}</h2>
      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        <span>Status: <strong>{incident.status}</strong></span>
        <span>Priority: <strong>{incident.priority}</strong></span>
        <span>Signals: <strong>{incident.signal_count}</strong></span>
      </div>

      {message && <p style={{ color: 'red', marginBottom: 12 }}>{message}</p>}

      {nextStatus && nextStatus !== 'CLOSED' && (
        <button onClick={() => updateStatus(nextStatus)}
          style={{ padding: '8px 16px', background: '#0066cc', color: '#fff',
            border: 'none', borderRadius: 6, cursor: 'pointer', marginRight: 8 }}>
          Move to {nextStatus}
        </button>
      )}

      {incident.status === 'RESOLVED' && (
        <>
          <button onClick={() => setShowRCA(!showRCA)}
            style={{ padding: '8px 16px', background: '#009933', color: '#fff',
              border: 'none', borderRadius: 6, cursor: 'pointer', marginRight: 8 }}>
            {showRCA ? 'Hide RCA Form' : 'Fill RCA'}
          </button>
          <button onClick={() => updateStatus('CLOSED')}
            style={{ padding: '8px 16px', background: '#666', color: '#fff',
              border: 'none', borderRadius: 6, cursor: 'pointer' }}>
            Move to CLOSED
          </button>
        </>
      )}

      {showRCA && <RCAForm incidentId={id} onSubmit={fetchIncident} />}

      <h3>Raw Signals (latest 50)</h3>
      <div style={{ maxHeight: 300, overflowY: 'auto', background: '#f5f5f5',
        borderRadius: 8, padding: 12 }}>
        {(incident.signals || []).map((s, i) => (
          <pre key={i} style={{ margin: '4px 0', fontSize: 12 }}>
            {JSON.stringify(s, null, 2)}
          </pre>
        ))}
        {(!incident.signals || incident.signals.length === 0) && (
          <p style={{ color: '#888' }}>No raw signals yet</p>
        )}
      </div>
    </div>
  )
}
