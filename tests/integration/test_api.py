"""API contract tests with a scripted LLM (no models, no network)."""

import pytest
from fastapi.testclient import TestClient

import app.api.main as api
from app.agent.graph import Agent
from app.store import Store
from tests.unit.test_agent import DEBIT_UNAUTH, GOOD, ScriptedLLM, SparseRetriever


@pytest.fixture()
def client(monkeypatch):
    agent = Agent(llm=ScriptedLLM(DEBIT_UNAUTH, [GOOD] * 10), retriever=SparseRetriever())
    monkeypatch.setattr(api, "get_agent", lambda: agent)
    monkeypatch.setattr(api, "store", Store("sqlite:///:memory:"))
    api._ready.set()
    api._hits.clear()
    return TestClient(api.app)


def test_health_and_metrics(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").status_code == 200
    assert "assistant_requests_total" in client.get("/metrics").text


def test_chat_round_trip_with_audit(client):
    r = client.post("/v1/chat", json={"message": "debit card charge I didn't make, statement Sept 30"})
    assert r.status_code == 200
    body = r.json()
    res = body["result"]
    assert res["regime"] == "reg_e" and res["deadlines"] and "open_dispute_case" in res["suggested_actions"]
    assert body["online_scores"]["citation_validity"] == 1.0
    trail = client.get(f"/v1/sessions/{body['session_id']}/audit").json()
    assert trail[0]["kind"] == "turn" and trail[0]["detail"]["regime"] == "reg_e"


def test_actions_require_confirmation(client):
    sid = client.post("/v1/chat", json={"message": "unauthorized debit charge"}).json()["session_id"]
    declined = client.post("/v1/actions", json={"session_id": sid, "action": "block_card", "confirm": False}).json()
    assert declined["status"] == "declined"
    done = client.post("/v1/actions", json={"session_id": sid, "action": "block_card", "confirm": True}).json()
    assert done["status"] == "done" and done["reference"].startswith("BLO-")
    kinds = [e["kind"] for e in client.get(f"/v1/sessions/{sid}/audit").json()]
    assert kinds == ["turn", "action_declined", "action_confirmed"]


def test_feedback(client):
    assert client.post("/v1/feedback", json={"rating": 1, "comment": "clear"}).json() == {"ok": True}


def test_validation_and_rate_limit(client, monkeypatch):
    assert client.post("/v1/chat", json={"message": ""}).status_code == 422
    api._hits.clear()
    monkeypatch.setattr(api.get_settings(), "rate_limit_per_min", 2)
    codes = [client.post("/v1/feedback", json={"rating": 0}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_demo_token(client, monkeypatch):
    monkeypatch.setattr(api.get_settings(), "demo_token", "s3cret")
    assert client.post("/v1/feedback", json={"rating": 0}).status_code == 401
    ok = client.post("/v1/feedback", json={"rating": 0}, headers={"X-Demo-Token": "s3cret"})
    assert ok.status_code == 200
