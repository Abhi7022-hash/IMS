import { useState } from 'react'
import axios from 'axios'

const API = 'http://localhost:5000'
const categories = [
  'Hardware failure', 'Software bug', 'Configuration error',
  'Network issue', 'Capacity overload', 'Human error', 'Third party failure'
]

export default function RCAForm({ incidentId, onSubmit }) {
  const [form, setForm] = useState({
    root_cause_category: '',
    fix_applied: '',
    prevention_steps: '',
    incident_start: '',
    incident_end: ''
  })
  const [message, setMessage] = useState('')

  const handleSubmit = () => {
    if (!form.root_cause_category || !form.fix_applied ||
        !form.prevention_steps || !form.incident_start || !form.incident_end) {
      setMessage('All fields are required!')
      return
    }
    axios.post(`${API}/incidents/${incidentId}/rca`, form)
      .then(r => {
        setMessage(`RCA saved! MTTR: ${r.data.mttr_minutes.toFixed(1)} minutes`)
        onSubmit()
      })
      .catch(e => setMessage(e.response?.data?.error || 'Error'))
  }

  const inputStyle = {
    width: '100%', padding: 8, margin: '4px 0 12px',
    border: '1px solid #ccc', borderRadius: 6,
    fontSize: 14, boxSizing: 'border-box'
  }

  return (
    <div style={{ background: '#f9f9f9', border: '1px solid #ddd',
      borderRadius: 8, padding: 20, marginTop: 16 }}>
      <h3>Root Cause Analysis</h3>

      <label>Root cause category</label>
      <select style={inputStyle}
        value={form.root_cause_category}
        onChange={e => setForm({...form, root_cause_category: e.target.value})}>
        <option value="">-- Select --</option>
        {categories.map(c => <option key={c}>{c}</option>)}
      </select>

      <label>Fix applied</label>
      <textarea style={{...inputStyle, height: 80}}
        placeholder="What did you do to fix it?"
        value={form.fix_applied}
        onChange={e => setForm({...form, fix_applied: e.target.value})} />

      <label>Prevention steps</label>
      <textarea style={{...inputStyle, height: 80}}
        placeholder="How to prevent this next time?"
        value={form.prevention_steps}
        onChange={e => setForm({...form, prevention_steps: e.target.value})} />

      <label>Incident start time</label>
      <input type="datetime-local" style={inputStyle}
        value={form.incident_start}
        onChange={e => setForm({...form, incident_start: e.target.value})} />

      <label>Incident end time</label>
      <input type="datetime-local" style={inputStyle}
        value={form.incident_end}
        onChange={e => setForm({...form, incident_end: e.target.value})} />

      <button onClick={handleSubmit}
        style={{ padding: '10px 24px', background: '#009933', color: '#fff',
          border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 15 }}>
        Submit RCA
      </button>

      {message && (
        <p style={{ marginTop: 12,
          color: message.includes('Error') || message.includes('required') ? 'red' : 'green' }}>
          {message}
        </p>
      )}
    </div>
  )
}
