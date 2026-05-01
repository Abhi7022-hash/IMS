import requests, time, random

API = "http://localhost:5000/ingest"

print("Simulating RDBMS outage — sending 100 signals in 10 seconds...")
for i in range(100):
    requests.post(API, json={
        "component_id": "RDBMS_PRIMARY_01",
        "error": "Connection timeout",
        "severity": "critical",
        "host": "db-prod-01"
    })
    time.sleep(0.1)

print("Simulating Cache failure — sending 50 signals...")
for i in range(50):
    requests.post(API, json={
        "component_id": "CACHE_CLUSTER_01",
        "error": "Cache miss rate too high",
        "severity": "warning",
        "host": "cache-prod-01"
    })
    time.sleep(0.1)

print("Done! Check http://localhost:5000/incidents")
