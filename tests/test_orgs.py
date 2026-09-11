"""Organisation CRUD tests."""

from __future__ import annotations


def test_create_org(client):
    resp = client.post("/api/orgs", json={"name": "Acme Corp", "description": "Demo"})
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Acme Corp"
    assert data["id"] >= 1
    assert data["description"] == "Demo"


def test_list_and_get_org(client):
    created = client.post("/api/orgs", json={"name": "Beta Inc"}).json()
    listed = client.get("/api/orgs")
    assert listed.status_code == 200
    assert any(o["id"] == created["id"] for o in listed.json())

    got = client.get(f"/api/orgs/{created['id']}")
    assert got.status_code == 200
    assert got.json()["name"] == "Beta Inc"


def test_update_and_delete_org(client):
    created = client.post("/api/orgs", json={"name": "Gamma LLC"}).json()
    updated = client.patch(
        f"/api/orgs/{created['id']}", json={"description": "Updated"}
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "Updated"

    deleted = client.delete(f"/api/orgs/{created['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/orgs/{created['id']}").status_code == 404


def test_duplicate_org_name_rejected(client):
    client.post("/api/orgs", json={"name": "Unique"}).raise_for_status()
    resp = client.post("/api/orgs", json={"name": "Unique"})
    assert resp.status_code == 400
