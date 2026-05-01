import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import (app, db, WorkItem, RCA,
                 IncidentStateMachine,
                 get_alert_strategy,
                 P0Strategy, P1Strategy, P2Strategy,
                 save_with_retry)
import pytest


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
        yield client


# ── Health check ─────────────────────────────────────────────────
def test_health(client):
    r = client.get('/health')
    assert r.status_code == 200


# ── RCA Validation ───────────────────────────────────────────────
def test_cannot_close_without_rca(client):
    with app.app_context():
        item = WorkItem(
            component_id='TEST_01', status='RESOLVED', priority='P1'
        )
        db.session.add(item)
        db.session.commit()
        r = client.patch(
            f'/incidents/{item.id}/status',
            json={'status': 'CLOSED'},
            content_type='application/json'
        )
        assert r.status_code == 400
        assert b'RCA' in r.data


# ── State Machine Tests ──────────────────────────────────────────
def test_valid_state_transition():
    sm = IncidentStateMachine('OPEN')
    result = sm.transition('INVESTIGATING')
    assert result == 'INVESTIGATING'

def test_invalid_state_transition():
    sm = IncidentStateMachine('OPEN')
    with pytest.raises(ValueError):
        sm.transition('CLOSED')

def test_cannot_transition_from_closed():
    sm = IncidentStateMachine('CLOSED')
    with pytest.raises(ValueError):
        sm.transition('OPEN')

def test_full_lifecycle():
    sm = IncidentStateMachine('OPEN')
    sm.transition('INVESTIGATING')
    sm.transition('RESOLVED')
    sm.transition('CLOSED')
    assert sm.current() == 'CLOSED'


# ── Strategy Pattern Tests ───────────────────────────────────────
def test_rdbms_gets_p0():
    strategy = get_alert_strategy('RDBMS_PRIMARY_01')
    assert isinstance(strategy, P0Strategy)
    assert strategy.get_priority() == 'P0'

def test_cache_gets_p2():
    strategy = get_alert_strategy('CACHE_CLUSTER_01')
    assert isinstance(strategy, P2Strategy)
    assert strategy.get_priority() == 'P2'

def test_api_gets_p1():
    strategy = get_alert_strategy('API_GATEWAY_01')
    assert isinstance(strategy, P1Strategy)
    assert strategy.get_priority() == 'P1'

def test_unknown_component_defaults_p2():
    strategy = get_alert_strategy('UNKNOWN_SERVICE_99')
    assert strategy.get_priority() == 'P2'


# ── Retry Logic Test ─────────────────────────────────────────────
def test_retry_succeeds_on_second_attempt():
    attempts = {"count": 0}

    def flaky_fn():
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise Exception("Transient error")
        return "success"

    result = save_with_retry(flaky_fn, retries=3, delay=0)
    assert result == "success"
    assert attempts["count"] == 2

def test_retry_raises_after_all_attempts():
    def always_fails():
        raise Exception("Permanent error")

    with pytest.raises(Exception, match="Permanent error"):
        save_with_retry(always_fails, retries=3, delay=0)
