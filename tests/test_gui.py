"""GUI static mount and system endpoint smoke tests."""

from __future__ import annotations


def test_root_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    body = resp.text
    assert "Grok Org OS" in body
    assert "Bootstrap" in body
    assert "Run Demo" in body
    assert "/static/js/app.js" in body


def test_static_css_js(client):
    css = client.get("/static/css/app.css")
    assert css.status_code == 200
    assert "--bg" in css.text or "background" in css.text
    js = client.get("/static/js/app.js")
    assert js.status_code == 200
    assert "refreshAll" in js.text or "loadOrgs" in js.text


def test_docs_still_available(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_settings_and_config_aliases(client):
    for path in ("/api/settings", "/api/config"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        data = resp.json()
        assert "openai_model" in data
        assert data.get("has_llm_key") is False or data.get("use_mock") is True


def test_bootstrap_and_demo(client, mock_llm):
    boot = client.post("/api/bootstrap", json={"name": "GUI Org"})
    assert boot.status_code == 200, boot.text
    body = boot.json()
    assert body["organisation"]["name"] == "GUI Org"
    assert "channel" in body
    assert body["channel"]["name"] == "HQ"
    assert "chief_of_staff" in body["agents"]

    demo = client.post(
        "/api/demo",
        json={
            "org_name": "GUI Org",
            "title": "GUI demo directive",
            "description": "Watch agents collaborate",
        },
    )
    assert demo.status_code == 200, demo.text
    d = demo.json()
    assert d["task"]["status"] == "done"
    assert d["message_count"] >= 4
    assert d["channel"]["id"] == body["channel"]["id"]

    messages = client.get(
        "/api/messages", params={"channel_id": d["channel"]["id"]}
    ).json()
    assert len(messages) >= 4
    assert any(m.get("agent_name") for m in messages)


def test_auto_bootstrap_on_empty(client):
    orgs = client.get("/api/orgs").json()
    assert len(orgs) >= 1
