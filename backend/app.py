import os, time, threading, queue, logging
from datetime import datetime
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pymongo import MongoClient
import redis as redis_client
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
CORS(app)

# ── Config ──────────────────────────────────────────────────────
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('POSTGRES_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

mongo = MongoClient(os.getenv('MONGO_URL'))
mongo_db = mongo['imsdb']

r = redis_client.from_url(os.getenv('REDIS_URL'))

limiter = Limiter(get_remote_address, app=app, default_limits=["200/minute"])

# ── In-Memory Queue (Backpressure buffer) ────────────────────────
signal_queue = queue.Queue(maxsize=50000)
signal_counter = {"count": 0, "last_reset": time.time()}


# ════════════════════════════════════════════════════════════════
# LLD — STRATEGY PATTERN (Alerting)
# Each priority level is a separate class with its own alert logic.
# To add a new alert type, just add a new class — no existing
# code needs to change. This is the Open/Closed principle.
# ════════════════════════════════════════════════════════════════

class AlertStrategy:
    """Base strategy — all alert types inherit from this."""
    priority = 'P2'

    def alert(self, component_id):
        logging.info(f"[ALERT][{self.priority}] Component: {component_id}")

    def get_priority(self):
        return self.priority


class P0Strategy(AlertStrategy):
    """
    P0 — Critical. Used for RDBMS failures.
    In production this would page on-call immediately via PagerDuty.
    """
    priority = 'P0'

    def alert(self, component_id):
        logging.critical(
            f"[P0 CRITICAL] {component_id} is DOWN — "
            f"Paging on-call engineer NOW"
        )


class P1Strategy(AlertStrategy):
    """
    P1 — High. Used for API / Queue failures.
    In production this would send SMS + Slack alert.
    """
    priority = 'P1'

    def alert(self, component_id):
        logging.error(
            f"[P1 HIGH] {component_id} degraded — "
            f"Sending Slack + SMS alert"
        )


class P2Strategy(AlertStrategy):
    """
    P2 — Medium. Used for Cache / NoSQL failures.
    In production this would send an email alert.
    """
    priority = 'P2'

    def alert(self, component_id):
        logging.warning(
            f"[P2 MEDIUM] {component_id} warning — "
            f"Sending email alert"
        )


# Strategy selector — picks the right class based on component name
COMPONENT_STRATEGY_MAP = {
    'RDBMS':  P0Strategy,
    'DB':     P0Strategy,
    'API':    P1Strategy,
    'QUEUE':  P1Strategy,
    'CACHE':  P2Strategy,
    'NOSQL':  P2Strategy,
    'MONGO':  P2Strategy,
}

def get_alert_strategy(component_id: str) -> AlertStrategy:
    """
    Factory function — returns the correct strategy object
    for a given component. Defaults to P2 if unknown.
    """
    component_upper = component_id.upper()
    for keyword, strategy_class in COMPONENT_STRATEGY_MAP.items():
        if keyword in component_upper:
            return strategy_class()
    return P2Strategy()


# ════════════════════════════════════════════════════════════════
# LLD — STATE PATTERN (Incident Lifecycle)
# Each state knows which transitions are valid FROM it.
# Calling transition() on the wrong state raises an error.
# This prevents skipping states (e.g. OPEN → CLOSED directly).
# ════════════════════════════════════════════════════════════════

class IncidentState:
    """Base state — all incident states inherit from this."""
    name = 'UNKNOWN'

    def transition(self, target: str):
        raise ValueError(
            f"Cannot transition from {self.name} to {target}"
        )

    def get_allowed_transitions(self):
        return []


class OpenState(IncidentState):
    name = 'OPEN'

    def transition(self, target: str):
        if target == 'INVESTIGATING':
            return InvestigatingState()
        raise ValueError(f"Cannot go from OPEN to {target}")

    def get_allowed_transitions(self):
        return ['INVESTIGATING']


class InvestigatingState(IncidentState):
    name = 'INVESTIGATING'

    def transition(self, target: str):
        if target == 'RESOLVED':
            return ResolvedState()
        raise ValueError(f"Cannot go from INVESTIGATING to {target}")

    def get_allowed_transitions(self):
        return ['RESOLVED']


class ResolvedState(IncidentState):
    name = 'RESOLVED'

    def transition(self, target: str):
        if target == 'CLOSED':
            return ClosedState()
        raise ValueError(f"Cannot go from RESOLVED to {target}")

    def get_allowed_transitions(self):
        return ['CLOSED']


class ClosedState(IncidentState):
    name = 'CLOSED'

    def transition(self, target: str):
        raise ValueError("Incident is CLOSED. No further transitions allowed.")

    def get_allowed_transitions(self):
        return []


# Map state name strings to state classes
STATE_MAP = {
    'OPEN':          OpenState,
    'INVESTIGATING': InvestigatingState,
    'RESOLVED':      ResolvedState,
    'CLOSED':        ClosedState,
}

class IncidentStateMachine:
    """
    Wraps an incident's current state and validates transitions.
    Usage:
        sm = IncidentStateMachine('OPEN')
        sm.transition('INVESTIGATING')  # ok
        sm.transition('CLOSED')         # raises ValueError
    """
    def __init__(self, current_status: str):
        state_class = STATE_MAP.get(current_status, OpenState)
        self.state = state_class()

    def transition(self, target: str) -> str:
        """
        Attempt a transition. Returns new status string if valid.
        Raises ValueError if transition is not allowed.
        """
        new_state = self.state.transition(target)
        self.state = new_state
        return self.state.name

    def current(self) -> str:
        return self.state.name

    def allowed(self):
        return self.state.get_allowed_transitions()


# ════════════════════════════════════════════════════════════════
# RETRY LOGIC
# Wraps any DB write with automatic retries + exponential backoff.
# If MongoDB is slow or PostgreSQL hiccups, we retry 3 times
# before giving up. This prevents data loss on transient errors.
# ════════════════════════════════════════════════════════════════

def save_with_retry(fn, retries=3, delay=1, backoff=2):
    """
    Retry wrapper for database writes.

    Args:
        fn       : callable — the DB operation to attempt
        retries  : how many times to try before raising
        delay    : initial wait in seconds between attempts
        backoff  : multiply delay by this after each failure (exponential)

    Example:
        save_with_retry(lambda: db.session.commit())
        save_with_retry(lambda: mongo_db.signals.insert_one(doc))
    """
    current_delay = delay
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            return fn()
        except Exception as e:
            last_error = e
            logging.warning(
                f"[RETRY] Attempt {attempt}/{retries} failed: {e}. "
                f"Retrying in {current_delay}s..."
            )
            if attempt < retries:
                time.sleep(current_delay)
                current_delay *= backoff

    logging.error(f"[RETRY] All {retries} attempts failed: {last_error}")
    raise last_error


# ── Models ───────────────────────────────────────────────────────
class WorkItem(db.Model):
    __tablename__ = 'work_items'
    id           = db.Column(db.Integer, primary_key=True)
    component_id = db.Column(db.String(100), nullable=False)
    status       = db.Column(db.String(20), default='OPEN')
    priority     = db.Column(db.String(5),  default='P2')
    signal_count = db.Column(db.Integer,    default=1)
    created_at   = db.Column(db.DateTime,   default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime,   default=datetime.utcnow)
    rca_id       = db.Column(db.Integer, db.ForeignKey('rcas.id'), nullable=True)


class RCA(db.Model):
    __tablename__ = 'rcas'
    id                   = db.Column(db.Integer,  primary_key=True)
    work_item_id         = db.Column(db.Integer,  nullable=False)
    root_cause_category  = db.Column(db.String(100), nullable=False)
    fix_applied          = db.Column(db.Text,     nullable=False)
    prevention_steps     = db.Column(db.Text,     nullable=False)
    incident_start       = db.Column(db.DateTime, nullable=False)
    incident_end         = db.Column(db.DateTime, nullable=False)
    mttr_minutes         = db.Column(db.Float,    nullable=True)
    created_at           = db.Column(db.DateTime, default=datetime.utcnow)


# ── Debounce Logic ────────────────────────────────────────────────
DEBOUNCE_WINDOW = 10  # seconds

def get_or_create_work_item(component_id, signal_data):
    debounce_key  = f"debounce:{component_id}"
    existing_id   = r.get(debounce_key)

    if existing_id:
        work_item = WorkItem.query.get(int(existing_id))
        if work_item:
            work_item.signal_count += 1
            work_item.updated_at = datetime.utcnow()
            # ── retry wrapping postgres commit ──
            save_with_retry(lambda: db.session.commit())
            return work_item, False

    # New work item — use strategy to determine priority
    strategy = get_alert_strategy(component_id)
    strategy.alert(component_id)  # fire alert

    work_item = WorkItem(
        component_id=component_id,
        priority=strategy.get_priority(),
        status='OPEN'
    )
    db.session.add(work_item)
    # ── retry wrapping postgres commit ──
    save_with_retry(lambda: db.session.commit())

    r.setex(debounce_key, DEBOUNCE_WINDOW, work_item.id)
    return work_item, True


# ── Background Worker ─────────────────────────────────────────────
def process_signals():
    with app.app_context():
        while True:
            try:
                signal = signal_queue.get(timeout=1)
                component_id = signal.get('component_id', 'UNKNOWN')

                # ── retry wrapping MongoDB insert ──
                save_with_retry(
                    lambda: mongo_db.signals.insert_one(
                        {**signal, 'received_at': datetime.utcnow()}
                    )
                )

                get_or_create_work_item(component_id, signal)
                signal_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"[WORKER] Error processing signal: {e}")


# ── Throughput Logger (every 5 seconds) ──────────────────────────
def log_throughput():
    while True:
        time.sleep(5)
        now     = time.time()
        elapsed = now - signal_counter["last_reset"]
        rate    = signal_counter["count"] / elapsed if elapsed > 0 else 0
        print(
            f"[THROUGHPUT] {rate:.1f} signals/sec | "
            f"Queue size: {signal_queue.qsize()}"
        )
        signal_counter["count"]      = 0
        signal_counter["last_reset"] = now


# ── Start background threads ──────────────────────────────────────
threading.Thread(target=process_signals, daemon=True).start()
threading.Thread(target=log_throughput,  daemon=True).start()


# ════════════════════════════════════════════════════════════════
# API ROUTES
# ════════════════════════════════════════════════════════════════

def check_postgres():
    try:
        db.session.execute(db.text('SELECT 1'))
        return True
    except:
        return False

def check_mongo():
    try:
        mongo.admin.command('ping')
        return True
    except:
        return False

@app.route('/health')
def health():
    return jsonify({
        "status": "ok",
        "queue_size": signal_queue.qsize(),
        "throughput_per_sec": round(
            signal_counter["count"] /
            max(time.time() - signal_counter["last_reset"], 1), 2
        ),
        "databases": {
            "postgres": "ok" if check_postgres() else "error",
            "mongo":    "ok" if check_mongo()    else "error",
            "redis":    "ok" if r.ping()          else "error"
        },
        "timestamp": datetime.utcnow().isoformat()
    })


@app.route('/ingest', methods=['POST'])
@limiter.limit("500/minute")
def ingest():
    data = request.get_json()
    if not data or 'component_id' not in data:
        return jsonify({"error": "component_id required"}), 400

    data['timestamp'] = datetime.utcnow().isoformat()

    try:
        signal_queue.put_nowait(data)
        signal_counter["count"] += 1
        return jsonify({"status": "queued"}), 202
    except queue.Full:
        return jsonify({"error": "queue full, try again"}), 503


@app.route('/incidents', methods=['GET'])
def get_incidents():
    cache_key = "dashboard:incidents"
    cached    = r.get(cache_key)
    if cached:
        import json
        return jsonify(json.loads(cached))

    items = WorkItem.query.order_by(
        WorkItem.priority, WorkItem.created_at.desc()
    ).all()

    result = [{
        "id":           i.id,
        "component_id": i.component_id,
        "status":       i.status,
        "priority":     i.priority,
        "signal_count": i.signal_count,
        "created_at":   i.created_at.isoformat(),
        "allowed_transitions": IncidentStateMachine(i.status).allowed()
    } for i in items]

    import json
    r.setex(cache_key, 10, json.dumps(result))
    return jsonify(result)


@app.route('/incidents/<int:incident_id>', methods=['GET'])
def get_incident(incident_id):
    item    = WorkItem.query.get_or_404(incident_id)
    signals = list(
        mongo_db.signals.find(
            {"component_id": item.component_id}, {"_id": 0}
        ).limit(50)
    )
    return jsonify({
        "id":           item.id,
        "component_id": item.component_id,
        "status":       item.status,
        "priority":     item.priority,
        "signal_count": item.signal_count,
        "created_at":   item.created_at.isoformat(),
        "allowed_transitions": IncidentStateMachine(item.status).allowed(),
        "signals":      signals
    })


@app.route('/incidents/<int:incident_id>/status', methods=['PATCH'])
def update_status(incident_id):
    item       = WorkItem.query.get_or_404(incident_id)
    data       = request.get_json()
    new_status = data.get('status')

    # ── Use State Machine to validate transition ──
    sm = IncidentStateMachine(item.status)
    try:
        sm.transition(new_status)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # ── Block CLOSED unless RCA exists ──
    if new_status == 'CLOSED':
        rca = RCA.query.filter_by(work_item_id=incident_id).first()
        if not rca:
            return jsonify({
                "error": "RCA is required before closing this incident"
            }), 400

    item.status     = new_status
    item.updated_at = datetime.utcnow()

    # ── retry wrapping postgres commit ──
    save_with_retry(lambda: db.session.commit())

    r.delete("dashboard:incidents")
    return jsonify({"status": "updated", "new_status": new_status})


@app.route('/incidents/<int:incident_id>/rca', methods=['POST'])
def submit_rca(incident_id):
    WorkItem.query.get_or_404(incident_id)
    data = request.get_json()

    required = [
        'root_cause_category', 'fix_applied',
        'prevention_steps', 'incident_start', 'incident_end'
    ]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"{field} is required"}), 400

    start      = datetime.fromisoformat(data['incident_start'])
    end        = datetime.fromisoformat(data['incident_end'])
    mttr       = (end - start).total_seconds() / 60

    rca = RCA(
        work_item_id        = incident_id,
        root_cause_category = data['root_cause_category'],
        fix_applied         = data['fix_applied'],
        prevention_steps    = data['prevention_steps'],
        incident_start      = start,
        incident_end        = end,
        mttr_minutes        = round(mttr, 2)
    )
    db.session.add(rca)

    # ── retry wrapping postgres commit ──
    save_with_retry(lambda: db.session.commit())

    return jsonify({
        "status":       "rca saved",
        "mttr_minutes": round(mttr, 2)
    }), 201


@app.route('/incidents/<int:incident_id>/rca', methods=['GET'])
def get_rca(incident_id):
    rca = RCA.query.filter_by(work_item_id=incident_id).first()
    if not rca:
        return jsonify({"error": "No RCA found"}), 404
    return jsonify({
        "root_cause_category": rca.root_cause_category,
        "fix_applied":         rca.fix_applied,
        "prevention_steps":    rca.prevention_steps,
        "incident_start":      rca.incident_start.isoformat(),
        "incident_end":        rca.incident_end.isoformat(),
        "mttr_minutes":        rca.mttr_minutes
    })


# ── Init DB + Run ─────────────────────────────────────────────────
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
