"""Additional GUI / system smoke tests (complements test_ui.py)."""

from __future__ import annotations


def test_root_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    body = resp.text
    assert "Grok Org OS" in body
    assert "Bootstrap" in body
    assert "Run Demo" in body


def test_static_css_js(client):
    css = client.get("/static/css/app.css")
    assert css.status_code == 200
    assert "--bg" in css.text or "background" in css.text
    js = client.get("/static/js/app.js")
    assert js.status_code == 200
    assert "refreshAll" in js.text


def test_settings_endpoint(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "has_llm_key" in data
    assert data["has_llm_key"] is False
    assert "openai_model" in data


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
