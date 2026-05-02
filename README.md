# Incident Management System (IMS)

# What this System does
This system monitors a distributed infrastructure stack and manages incident workflows. When servers or databases fail, signals are ingested, grouped, and tracked from detection to resolution with a mandatory Root Cause Analysis.

# Project Stracture
ims/
├── backend/
│   ├── app.py          ← All Flask logic, LLD patterns, retry logic
│   ├── tests/          ← 12 unit tests
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── Dashboard.jsx
│       ├── IncidentDetail.jsx
│       └── RCAForm.jsx
├── scripts/
│   └── mock_failure.py
├── docs/
│   ├── architecture.svg
│   └── PROMPTS.md
└── docker-compose.yml

## Quick Start
```bash
docker-compose up --build
```
Then open http://localhost:3000

## Architecture
See docs/architecture.png

## How Backpressure Works
Signals → asyncio.Queue (in-memory, 50k capacity) → Background worker drains to MongoDB.
If MongoDB is slow, queue absorbs the burst. The /ingest endpoint never blocks.

## Endpoints
| Method | URL | Description |
|--------|-----|-------------|
| GET | /health | System health |
| POST | /ingest | Ingest a signal |
| GET | /incidents | All incidents |
| GET | /incidents/:id | Single incident + signals |
| PATCH | /incidents/:id/status | Update status |
| POST | /incidents/:id/rca | Submit RCA |

## Run Tests
```bash
cd backend && python -m pytest tests/ -v
```

## Simulate Failure
```bash
python scripts/mock_failure.py
```

## Tech Stack
- Backend: Python Flask
- Databases: PostgreSQL + MongoDB + Redis
- Frontend: React + Vite
- Packaging: Docker Compose
