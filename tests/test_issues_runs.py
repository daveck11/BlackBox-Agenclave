# Persistence + ownership tests for issues and runs.
#
# Uses the in-memory `client` fixture. The Stage 2 dispatch + Chairman judge are
# monkeypatched so no provider APIs are ever hit.

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _auth(client, email):
    # Register a user and return an Authorization header dict.
    resp = client.post("/auth/register", json={"email": email, "password": "supersecret1"})
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


_ISSUE_PAYLOAD = {
    "title": "App crashes on launch",
    "body": "Null pointer on startup.",
    "label": "bug",
    "confidence": 0.91,
    "severity": None,
    "top_tokens": ["crash", "null"],
    "recommendations": [
        {"title": "Reproduce", "detail": "Confirm steps.", "kind": "action"}
    ],
}


# --- issues -------------------------------------------------------------------
def test_save_issue_and_owner_isolation(client):
    alice = _auth(client, "alice@example.com")
    bob = _auth(client, "bob@example.com")

    created = client.post("/issues", json=_ISSUE_PAYLOAD, headers=alice)
    assert created.status_code == 201
    issue = created.json()
    assert issue["label"] == "bug"
    assert issue["recommendations"][0]["kind"] == "action"
    issue_id = issue["id"]

    # Alice sees it; Bob does not.
    assert [i["id"] for i in client.get("/issues", headers=alice).json()] == [issue_id]
    assert client.get("/issues", headers=bob).json() == []

    # Bob can't read or delete Alice's issue (404, not 403, to avoid leaking ids).
    assert client.get(f"/issues/{issue_id}", headers=bob).status_code == 404
    assert client.delete(f"/issues/{issue_id}", headers=bob).status_code == 404

    # Alice can fetch and then delete it.
    assert client.get(f"/issues/{issue_id}", headers=alice).status_code == 200
    assert client.delete(f"/issues/{issue_id}", headers=alice).status_code == 204
    assert client.get("/issues", headers=alice).json() == []


def test_anonymous_cannot_save_issue(client):
    assert client.post("/issues", json=_ISSUE_PAYLOAD).status_code == 401


# --- runs ---------------------------------------------------------------------
def _patch_stage2(monkeypatch):
    # Force a deterministic bug triage + fake out the live Stage 2 dispatch/judge.
    from agenclave.api.routes import runs as runs_mod

    monkeypatch.setattr(
        runs_mod,
        "predict_triage",
        lambda title, body="": {
            "label": "bug",
            "label_confidence": 0.9,
            "severity": None,
            "top_tokens": ["crash"],
        },
    )
    monkeypatch.setattr(runs_mod, "build_agents", lambda provider, models: ["agent"])

    async def _fake_dispatch(task, agents):
        return [
            SimpleNamespace(agent_name="claude-sonnet-4-6", ok=True, error=None, patch="diff")
        ]

    class _FakeChairman:
        def __init__(self, model, **kwargs):
            self.model = model

        async def judge(self, task, candidates):
            return SimpleNamespace(
                selected_agent="claude-sonnet-4-6",
                ranking=["claude-sonnet-4-6"],
                rationale="best",
                synthesized_patch=None,
            )

    monkeypatch.setattr(runs_mod, "dispatch", _fake_dispatch)
    monkeypatch.setattr(runs_mod, "Chairman", _FakeChairman)


def test_run_save_list_and_delete(client, monkeypatch):
    _patch_stage2(monkeypatch)
    alice = _auth(client, "alice@example.com")

    resp = client.post(
        "/runs", json={"title": "Crash", "body": "boom", "live": True}, headers=alice
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ran_live"] is True
    assert body["gate"]["passed"] is True
    # Runs are no longer auto-saved: nothing persists until the user opts in.
    assert "run_id" not in body
    assert client.get("/runs", headers=alice).json() == []

    # Trust-scored routing is attached, selects a subset of the panel, and cost is
    # projected over the routed subset (+1 for the chairman).
    from agenclave.config import settings

    routing = body["routing"]
    assert routing is not None and routing["reason"]
    assert set(routing["selected"]) <= set(settings.agent_model_list)
    assert body["cost"]["calls"] == len(routing["selected"]) + 1

    # Explicit save persists the run and returns its id.
    saved = client.post(
        "/runs/save",
        json={"title": "Crash", "body": "boom", "result": body},
        headers=alice,
    )
    assert saved.status_code == 200
    run_id = saved.json()["run_id"]

    listed = client.get("/runs", headers=alice).json()
    assert [r["id"] for r in listed] == [run_id]
    assert listed[0]["ran_live"] is True
    assert listed[0]["gate_passed"] is True

    one = client.get(f"/runs/{run_id}", headers=alice)
    assert one.status_code == 200
    assert one.json()["result"]["selected_patch"] == "diff"

    # The owner can delete it; afterwards the list is empty.
    assert client.delete(f"/runs/{run_id}", headers=alice).status_code == 204
    assert client.get("/runs", headers=alice).json() == []


def test_anonymous_cannot_save_run(client):
    assert (
        client.post(
            "/runs/save", json={"title": "x", "body": "y", "result": {}}
        ).status_code
        == 401
    )


def test_anonymous_run_works_without_persisting(client, monkeypatch):
    # Preserve existing behaviour: anonymous /runs returns the pipeline result and
    # never persists (no run_id, and a fresh user has an empty run list).
    _patch_stage2(monkeypatch)
    resp = client.post("/runs", json={"title": "Crash", "body": "boom", "live": False})
    assert resp.status_code == 200
    body = resp.json()
    assert "run_id" not in body
    assert body["ran_live"] is False

    alice = _auth(client, "alice@example.com")
    assert client.get("/runs", headers=alice).json() == []


def test_dry_run_shows_routing_projection_without_spending(client, monkeypatch):
    # A dry run (live=False) still routes and shows the projected subset - the
    # transparency payoff - but dispatches nothing and spends $0.
    _patch_stage2(monkeypatch)
    resp = client.post("/runs", json={"title": "Crash", "body": "boom", "live": False})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ran_live"] is False
    assert body["cost"]["spent_usd"] == 0.0
    routing = body["routing"]
    assert routing is not None and routing["reason"]
    assert routing["selected"] and body["candidates"] == []


def test_web_run_never_writes_reliability(client, monkeypatch):
    # Guardrail: a free-text web run has no in-loop verification, so it must never
    # record outcomes into reliability. If it tried, this raising stub would surface it.
    # patch the name runs.py imported, not reliability.record_outcome
    _patch_stage2(monkeypatch)
    from agenclave.api.routes import runs as runs_mod

    def _boom(*a, **k):  # pragma: no cover - only fires on a violation
        raise AssertionError("web run must not write reliability (read-only prior)")

    monkeypatch.setattr(runs_mod, "record_outcome", _boom)
    alice = _auth(client, "alice@example.com")
    resp = client.post(
        "/runs", json={"title": "Crash", "body": "boom", "live": True}, headers=alice
    )
    assert resp.status_code == 200
    assert resp.json()["ran_live"] is True


def _patch_fixture_run(monkeypatch, *, triage_label, applies, tests_passed):
    # live fixture run with dispatch, verify and the judge stubbed out
    from types import SimpleNamespace

    from agenclave.api.routes import runs as runs_mod

    monkeypatch.setattr(
        runs_mod,
        "predict_triage",
        lambda title, body="": {
            "label": triage_label,
            "label_confidence": 0.6,
            "severity": None,
            "top_tokens": [],
        },
    )
    monkeypatch.setattr(runs_mod, "build_agents", lambda provider, models: ["agent"])

    async def _fake_dispatch(task, agents):
        return [SimpleNamespace(agent_name="m1", ok=True, error=None, patch="diff")]

    monkeypatch.setattr(runs_mod, "dispatch", _fake_dispatch)
    monkeypatch.setattr(
        runs_mod,
        "verify_patch",
        lambda *a, **k: SimpleNamespace(
            applies=applies, tests_passed=tests_passed, passed=int(tests_passed),
            total=1, evidence="", error=None,
        ),
    )
    recorded = []
    monkeypatch.setattr(
        runs_mod, "record_outcome", lambda m, c, p: recorded.append((m, c, p))
    )

    class _FakeChairman:
        def __init__(self, model, **kwargs):
            pass

        async def explain(self, task, candidates, vrs, winner):
            return SimpleNamespace(
                selected_agent="m1", ranking=[winner], rationale="ok", synthesized_patch=None
            )

        async def judge(self, task, candidates):
            return SimpleNamespace(
                selected_agent="m1", ranking=["m1"], rationale="read", synthesized_patch=None
            )

    monkeypatch.setattr(runs_mod, "Chairman", _FakeChairman)
    return recorded


def test_fixture_gate_uses_fixture_category(client, monkeypatch):
    # the classifier reads some fixtures as documentation; that can't block them
    recorded = _patch_fixture_run(
        monkeypatch, triage_label="documentation", applies=True, tests_passed=True
    )
    alice = _auth(client, "alice@example.com")
    resp = client.post(
        "/runs",
        json={"title": "t", "body": "b", "live": True, "fixture_id": "calc-add"},
        headers=alice,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["triage"]["label"] == "documentation"
    assert body["gate"]["passed"] is True
    assert "documentation" in body["gate"]["reason"]
    assert body["verified_winner"] == "m1"
    assert recorded == [("m1", "bug", True)]


def test_no_verified_winner_when_nothing_applies(client, monkeypatch):
    recorded = _patch_fixture_run(
        monkeypatch, triage_label="bug", applies=False, tests_passed=False
    )
    alice = _auth(client, "alice@example.com")
    resp = client.post(
        "/runs",
        json={"title": "t", "body": "b", "live": True, "fixture_id": "calc-add"},
        headers=alice,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verification"][0]["tier"] == "broken"
    assert body["verified_winner"] is None
    assert recorded == [("m1", "bug", False)]


# --- live-run gate: login + one global cap per UTC day -------------------------
_LIVE = {"title": "Crash", "body": "boom", "live": True}


def test_anonymous_live_run_is_unauthorized(client, monkeypatch):
    # live=True spends credits, so it needs a logged-in user: 401 without a token.
    # Nothing is dispatched, and a dry run from the same anonymous caller still works.
    _patch_stage2(monkeypatch)
    resp = client.post("/runs", json=_LIVE)
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Bearer"
    dry = client.post("/runs", json={**_LIVE, "live": False})
    assert dry.status_code == 200 and dry.json()["ran_live"] is False


def test_bearer_token_as_sent_by_the_ui_passes_the_live_gate(client, monkeypatch):
    # frontend/src/api.js attaches `Authorization: Bearer <token>` by default whenever
    # a token is stored, so the UI needs no change for the gate. Pin that contract
    # and check the exact header shape it sends is what the gate accepts.
    _patch_stage2(monkeypatch)
    api_js = (ROOT / "frontend" / "src" / "api.js").read_text(encoding="utf-8")
    assert "headers['Authorization'] = `Bearer ${token}`" in api_js
    assert "const wantAuth = auth === undefined ? Boolean(token) : auth" in api_js

    reg = client.post(
        "/auth/register", json={"email": "alice@example.com", "password": "supersecret1"}
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    resp = client.post("/runs", json=_LIVE, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ran_live"] is True


def test_live_cap_is_global_and_returns_429(client, monkeypatch):
    # The cap is shared by every user (registration is open). Over it, a live run
    # is 429 for anyone, while dry runs stay anonymous and free.
    _patch_stage2(monkeypatch)
    from agenclave.config import settings

    monkeypatch.setattr(settings, "live_daily_cap", 2)
    alice = _auth(client, "alice@example.com")
    bob = _auth(client, "bob@example.com")

    assert client.post("/runs", json=_LIVE, headers=alice).status_code == 200
    assert client.post("/runs", json=_LIVE, headers=bob).status_code == 200

    over = client.post("/runs", json=_LIVE, headers=alice)
    assert over.status_code == 429
    assert "cap" in over.json()["detail"]
    assert client.post("/runs", json=_LIVE, headers=bob).status_code == 429

    dry = client.post("/runs", json={**_LIVE, "live": False})
    assert dry.status_code == 200 and dry.json()["cost"]["spent_usd"] == 0.0


def test_live_cap_is_counted_in_the_database(client, monkeypatch):
    # The count is a row per live dispatch in `live_runs`, keyed by UTC day, so it
    # survives a restart. Only runs that actually dispatch count: a live request
    # that fails the triage gate, and a dry run, add no row.
    _patch_stage2(monkeypatch)
    from sqlalchemy import func, select

    from agenclave.api import db
    from agenclave.api.models import LiveRun
    from agenclave.api.routes import runs as runs_mod

    alice = _auth(client, "alice@example.com")
    for _ in range(2):
        assert client.post("/runs", json=_LIVE, headers=alice).status_code == 200
    assert client.post("/runs", json={**_LIVE, "live": False}, headers=alice).status_code == 200

    monkeypatch.setattr(
        runs_mod,
        "predict_triage",
        lambda title, body="": {
            "label": "documentation",
            "label_confidence": 0.8,
            "severity": None,
            "top_tokens": ["docs"],
        },
    )
    gated = client.post("/runs", json=_LIVE, headers=alice)
    assert gated.status_code == 200
    assert gated.json()["gate"]["passed"] is False and gated.json()["ran_live"] is False

    async def _rows():
        async with db.async_session_factory() as s:
            q = select(LiveRun.day, func.count(LiveRun.id)).group_by(LiveRun.day)
            return (await s.execute(q)).all()

    # Run the query on the app's own event loop (same in-memory connection).
    rows = client.portal.call(_rows)
    assert rows == [(runs_mod._utc_day(), 2)]


def test_run_owner_isolation(client, monkeypatch):
    _patch_stage2(monkeypatch)
    alice = _auth(client, "alice@example.com")
    bob = _auth(client, "bob@example.com")

    run = client.post(
        "/runs", json={"title": "Crash", "body": "boom", "live": False}, headers=alice
    ).json()
    saved = client.post(
        "/runs/save",
        json={"title": "Crash", "body": "boom", "result": run},
        headers=alice,
    )
    run_id = saved.json()["run_id"]

    # Bob can neither see, read, nor delete Alice's run.
    assert client.get("/runs", headers=bob).json() == []
    assert client.get(f"/runs/{run_id}", headers=bob).status_code == 404
    assert client.delete(f"/runs/{run_id}", headers=bob).status_code == 404
