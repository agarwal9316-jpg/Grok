"""v2.0: tool calling, approvals, routines, files, connectors, multi-agent."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from grok_org_os.bootstrap import bootstrap_sample_org
from grok_org_os.llm import LLMClient
from grok_org_os.models import ApprovalStatus, Task, TaskStatus
from grok_org_os.runtime import AgentRuntime
from grok_org_os.tools import TOOL_DEFINITIONS, ToolContext, ToolExecutor


def test_tool_calling_mock_openai_http(client, mock_llm, db, tmp_path, monkeypatch):
    """When API key set, chat_message posts tools and executes tool_calls from response."""
    data = bootstrap_sample_org(db, name="Tool Org")
    agent = data["agents"]["ops"]
    channel = data["channel"]
    task = Task(
        organisation_id=data["organisation"].id,
        title="Fetch and note",
        description="Use tools",
        status=TaskStatus.assigned,
        assignee_id=agent.id,
        channel_id=channel.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    fake_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "send_message",
                                "arguments": json.dumps({"content": "Tool hello"}),
                            },
                        }
                    ],
                }
            }
        ]
    }
    final_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "[Ops] Done with tools",
                }
            }
        ]
    }

    calls = {"n": 0}

    class FakeResp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            calls["n"] += 1
            assert "/chat/completions" in url
            assert "tools" in json
            if calls["n"] == 1:
                return FakeResp(fake_response)
            return FakeResp(final_response)

    llm = LLMClient(api_key="sk-test", base_url="https://api.openai.com/v1", model="gpt-4o-mini")
    with patch("grok_org_os.llm.httpx.Client", FakeClient):
        runtime = AgentRuntime(llm=llm)
        result = runtime.run_agent_on_task(db, task, agent)

    assert result.status == TaskStatus.done
    assert "Done with tools" in (result.result or "")
    msgs = client.get("/api/messages", params={"channel_id": channel.id}).json()
    assert any("Tool hello" in m["content"] for m in msgs)


def test_multi_agent_demo_posts(client, mock_llm):
    resp = client.post("/api/demo", json={"org_name": "Demo Multi"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["task"]["status"] in ("done", "awaiting_approval")
    assert body["message_count"] >= 3
    assert body.get("used_tools") is True
    channel_id = body["channel"]["id"]
    messages = client.get("/api/messages", params={"channel_id": channel_id}).json()
    assert len(messages) >= 3
    # CoS + specialists should have posted
    agents = {m.get("agent_name") for m in messages}
    assert len(agents) >= 2


def test_approval_flow(client, mock_llm, db):
    data = bootstrap_sample_org(db, name="Approval Org")
    org = data["organisation"]
    cos = data["agents"]["chief_of_staff"]
    created = client.post(
        "/api/approvals",
        json={
            "organisation_id": org.id,
            "title": "Spend $10k",
            "description": "Needs CEO OK",
            "requester_agent_id": cos.id,
        },
    )
    assert created.status_code == 201, created.text
    aid = created.json()["id"]
    listed = client.get("/api/approvals", params={"organisation_id": org.id, "status": "pending"})
    assert listed.status_code == 200
    assert any(a["id"] == aid for a in listed.json())

    approved = client.post(f"/api/approvals/{aid}/approve", json={"decision_note": "OK"})
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    # reject path
    created2 = client.post(
        "/api/approvals",
        json={"organisation_id": org.id, "title": "No", "requester_agent_id": cos.id},
    ).json()
    rejected = client.post(f"/api/approvals/{created2['id']}/reject", json={})
    assert rejected.json()["status"] == "rejected"


def test_request_approval_tool(db, mock_llm):
    data = bootstrap_sample_org(db, name="Appr Tool Org")
    agent = data["agents"]["ops"]
    channel = data["channel"]
    task = Task(
        organisation_id=data["organisation"].id,
        title="Need approval",
        description="Please request approval for budget",
        status=TaskStatus.assigned,
        assignee_id=agent.id,
        channel_id=channel.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    ctx = ToolContext(db, agent, channel=channel, task=task)
    ex = ToolExecutor(ctx)
    out = json.loads(ex("request_approval", {"title": "Budget", "description": "yes"}))
    assert out["ok"] is True
    assert out["approval_id"]
    from grok_org_os.models import Approval

    a = db.get(Approval, out["approval_id"])
    assert a.status == ApprovalStatus.pending


def test_routine_crud_and_fire(client, mock_llm, db):
    data = bootstrap_sample_org(db, name="Routine Org")
    org = data["organisation"]
    cos = data["agents"]["chief_of_staff"]
    channel = data["channel"]
    created = client.post(
        "/api/routines",
        json={
            "organisation_id": org.id,
            "name": "Pulse",
            "prompt": "Post a status pulse",
            "every_seconds": 3600,
            "target_agent_id": cos.id,
            "channel_id": channel.id,
            "enabled": True,
        },
    )
    assert created.status_code == 201, created.text
    rid = created.json()["id"]
    listed = client.get("/api/routines", params={"organisation_id": org.id})
    assert any(r["id"] == rid for r in listed.json())

    fired = client.post(f"/api/routines/{rid}/run")
    assert fired.status_code == 200, fired.text
    assert fired.json()["last_run_at"] is not None
    messages = client.get("/api/messages", params={"channel_id": channel.id}).json()
    assert any("Routine" in m["content"] or "Pulse" in m["content"] for m in messages)

    deleted = client.delete(f"/api/routines/{rid}")
    assert deleted.status_code == 204


def test_files_upload_list(client, mock_llm, tmp_path, monkeypatch):
    from grok_org_os.config import reset_settings_cache
    import os

    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("WORKSPACE_DIR", str(ws))
    reset_settings_cache()

    listed = client.get("/api/files")
    assert listed.status_code == 200
    up = client.post(
        "/api/files/upload",
        files={"file": ("hello.txt", b"hello workspace", "text/plain")},
    )
    assert up.status_code == 200, up.text
    assert up.json()["path"] == "hello.txt"
    listed2 = client.get("/api/files")
    names = [e["name"] for e in listed2.json()["entries"]]
    assert "hello.txt" in names


def test_connectors_files_web(client, mock_llm):
    cons = client.get("/api/connectors")
    assert cons.status_code == 200
    names = {c["name"] for c in cons.json()}
    assert "files" in names and "web" in names and "smtp_email" in names and "rest" in names

    files = client.post(
        "/api/connectors/files/invoke",
        json={"payload": {"action": "list", "path": "."}},
    )
    assert files.status_code == 200

    with patch("grok_org_os.connectors.web.httpx.Client") as Fake:
        inst = Fake.return_value.__enter__.return_value
        resp = MagicMock()
        resp.status_code = 200
        resp.url = "https://example.com"
        resp.headers = {"content-type": "text/html"}
        resp.text = "<html>ok</html>"
        inst.get.return_value = resp
        web = client.post(
            "/api/connectors/web/invoke",
            json={"payload": {"url": "https://example.com", "max_chars": 100}},
        )
        assert web.status_code == 200
        assert web.json()["status_code"] == 200


def test_openai_settings_test_endpoint(client, mock_llm):
    res = client.post("/api/settings/test")
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert res.json()["mode"] == "mock"


def test_threaded_reply(client, mock_llm, db):
    data = bootstrap_sample_org(db, name="Thread Org")
    channel = data["channel"]
    ceo = data["agents"]["ceo"]
    parent = client.post(
        "/api/messages",
        json={"channel_id": channel.id, "agent_id": ceo.id, "content": "Parent note"},
    ).json()
    reply = client.post(
        "/api/messages",
        json={
            "channel_id": channel.id,
            "agent_id": ceo.id,
            "content": "Child reply",
            "parent_id": parent["id"],
        },
    )
    assert reply.status_code == 201
    assert reply.json()["parent_id"] == parent["id"]


def test_tool_definitions_include_required():
    names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
    for required in (
        "send_message",
        "create_task",
        "handoff_task",
        "read_channel",
        "list_agents",
        "http_fetch",
        "fs_list",
        "fs_read",
        "fs_write",
        "request_approval",
    ):
        assert required in names


def test_concurrent_workers_submit(db, mock_llm):
    """Multiple specialist tasks can be submitted to the thread pool."""
    import time
    from grok_org_os.runtime import AgentRuntime

    data = bootstrap_sample_org(db, name="Concurrent Org")
    org = data["organisation"]
    channel = data["channel"]
    specialists = [data["agents"]["ops"], data["agents"]["research"], data["agents"]["comms"]]
    runtime = AgentRuntime(llm=mock_llm, max_workers=3)
    ids = []
    for sp in specialists:
        task = Task(
            organisation_id=org.id,
            title=f"Work for {sp.name}",
            description="Parallel specialist work",
            status=TaskStatus.assigned,
            assignee_id=sp.id,
            channel_id=channel.id,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        ids.append(task.id)
        runtime.submit_task(task.id)

    # Wait for pool jobs
    deadline = time.time() + 15
    while time.time() < deadline:
        db.expire_all()
        statuses = [db.get(Task, i).status for i in ids]
        if all(s == TaskStatus.done for s in statuses):
            break
        time.sleep(0.2)
    runtime.stop()
    db.expire_all()
    assert all(db.get(Task, i).status == TaskStatus.done for i in ids)
    assert all(db.get(Task, i).result for i in ids)


def test_live_tool_payload_includes_tools(monkeypatch):
    """With API key, request body must include tools for function calling."""
    from grok_org_os.llm import LLMClient
    from unittest.mock import patch

    captured = {}

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {"message": {"role": "assistant", "content": "ok", "tool_calls": []}}
                ]
            }

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            captured["json"] = json
            captured["headers"] = headers
            return FakeResp()

    client = LLMClient(api_key="sk-live", base_url="https://api.openai.com/v1", model="gpt-4o-mini")
    with patch("grok_org_os.llm.httpx.Client", FakeClient):
        client.chat_message(
            [{"role": "user", "content": "hi"}],
            tools=TOOL_DEFINITIONS,
        )
    assert "tools" in captured["json"]
    assert captured["json"]["tool_choice"] == "auto"
    assert captured["headers"]["Authorization"].startswith("Bearer sk-live")
    names = {t["function"]["name"] for t in captured["json"]["tools"]}
    assert "request_approval" in names and "http_fetch" in names
