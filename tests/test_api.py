from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rgcopy.api import create_app
from rgcopy.config import AppConfig
from tests.conftest import needs_rsync


@pytest.fixture
def client(tmp_path: Path, tree: Path):
    config = AppConfig(auth_token="secret", roots=[tmp_path], data_dir=tmp_path / "data")
    with TestClient(create_app(config)) as test_client:
        yield test_client


AUTH = {"Authorization": "Bearer secret"}


def test_requires_authentication(client: TestClient):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/system").status_code == 401
    assert client.get("/api/auth/status").json() == {"required": True, "authenticated": False}
    assert client.post("/api/auth/login", json={"token": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"token": "secret"}).status_code == 204
    # The session cookie now authenticates
    assert client.get("/api/system").status_code == 200


def test_auth_link_sets_cookie(client: TestClient):
    response = client.get("/auth?token=secret", follow_redirects=False)
    assert response.status_code == 303
    assert "rgcopy_session" in response.headers["set-cookie"]


def test_system_and_settings(client: TestClient):
    system = client.get("/api/system", headers=AUTH).json()
    assert system["desktop"] is False
    assert system["clipboard"] is False
    settings = client.put("/api/settings", json={"conflict": "skip", "concurrency": 2}, headers=AUTH).json()
    assert settings["conflict"] == "skip" and settings["concurrency"] == 2
    assert client.put("/api/settings", json={"concurrency": 99}, headers=AUTH).status_code == 422
    assert client.put("/api/settings", json={"unknown": 1}, headers=AUTH).status_code == 422


def test_browse_and_mkdir(client: TestClient, tree: Path):
    listing = client.get("/api/fs/list", params={"path": str(tree / "src")}, headers=AUTH).json()
    assert [e["name"] for e in listing["entries"]] == ["album", "single.txt"]
    created = client.post("/api/fs/mkdir", json={"parent": str(tree / "dst"), "name": "Nueva"}, headers=AUTH)
    assert created.status_code == 201
    assert (tree / "dst/Nueva").is_dir()
    assert (
        client.post(
            "/api/fs/mkdir", json={"parent": str(tree / "dst"), "name": "Nueva"}, headers=AUTH
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/fs/mkdir", json={"parent": str(tree / "dst"), "name": "../x"}, headers=AUTH
        ).status_code
        == 400
    )
    outside = client.get("/api/fs/list", params={"path": "/"}, headers=AUTH)
    assert outside.status_code == 403


def test_clipboard_only_in_desktop_mode(client: TestClient):
    assert client.get("/api/clipboard", headers=AUTH).status_code == 409


@needs_rsync
def test_transfer_lifecycle(client: TestClient, tree: Path):
    response = client.post(
        "/api/jobs",
        json={
            "sources": [str(tree / "src/album")],
            "destination": str(tree / "dst"),
            "options": {"mode": "copy"},
        },
        headers=AUTH,
    )
    assert response.status_code == 201, response.text
    job_id = response.json()["id"]
    deadline = time.monotonic() + 20
    while True:
        job = client.get(f"/api/jobs/{job_id}", headers=AUTH).json()
        if job["status"] in ("completed", "failed") or time.monotonic() > deadline:
            break
        time.sleep(0.05)
    assert job["status"] == "completed", job["error"]
    assert (tree / "dst/album/one.txt").exists()
    log = client.get(f"/api/jobs/{job_id}/log", headers=AUTH).json()
    assert log["command"].startswith(("rsync", "/"))
    assert "--info=progress2,name1" in log["command"]
    assert client.post("/api/queue/clear", json={"statuses": ["completed"]}, headers=AUTH).json() == {
        "removed": [job_id]
    }


@needs_rsync
def test_transfer_errors(client: TestClient, tree: Path):
    same = client.post(
        "/api/jobs",
        json={"sources": [str(tree / "src/single.txt")], "destination": str(tree / "src")},
        headers=AUTH,
    )
    assert same.status_code == 422 and same.json()["code"] == "same_folder"
    outside = client.post(
        "/api/jobs", json={"sources": ["/etc/hostname"], "destination": str(tree / "dst")}, headers=AUTH
    )
    assert outside.status_code == 403
    missing = client.post("/api/jobs/nope/pause", headers=AUTH)
    assert missing.status_code == 404


def test_events_websocket(client: TestClient):
    with client.websocket_connect("/api/events", headers=AUTH) as ws:
        first = ws.receive_json()
    assert first["type"] == "snapshot"
    assert first["queue"]["counts"]["queued"] == 0


@needs_rsync
def test_conflict_skip_and_verify_endpoints(client: TestClient, tree: Path):
    (tree / "dst/single.txt").write_text("old")
    job = client.post(
        "/api/jobs",
        json={"sources": [str(tree / "src/single.txt")], "destination": str(tree / "dst")},
        headers=AUTH,
    ).json()
    deadline = time.monotonic() + 20
    while job["status"] == "scanning" and time.monotonic() < deadline:
        time.sleep(0.05)
        job = client.get(f"/api/jobs/{job['id']}", headers=AUTH).json()
    # The default is to ask
    assert job["status"] == "conflict" and job["conflict_count"] == 1
    assert (
        client.post(f"/api/jobs/{job['id']}/resolve", json={"rule": "ask"}, headers=AUTH).status_code == 422
    )
    resolved = client.post(f"/api/jobs/{job['id']}/resolve", json={"rule": "overwrite"}, headers=AUTH).json()
    assert resolved["options"]["conflict"] == "overwrite"
    while job["status"] not in ("completed", "failed") and time.monotonic() < deadline:
        time.sleep(0.05)
        job = client.get(f"/api/jobs/{job['id']}", headers=AUTH).json()
    assert (tree / "dst/single.txt").read_text() == "single"
    assert client.post(f"/api/jobs/{job['id']}/skip", headers=AUTH).status_code == 409
    assert client.post(f"/api/jobs/{job['id']}/verify", headers=AUTH).json()["verify"] == "running"
    # Only the desktop app may shut the computer down
    assert client.post("/api/system/poweroff", headers=AUTH).status_code == 409
