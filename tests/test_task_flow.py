"""Task flow with mock LLM — CoS decompose, specialists, handoff."""

from __future__ import annotations

from grok_org_os.bootstrap import bootstrap_sample_org
from grok_org_os.db import SessionLocal
from grok_org_os.models import Task, TaskStatus
from grok_org_os.task_runner import TaskRunner


def test_task_flow_with_mock_llm(client, mock_llm, db):
    data = bootstrap_sample_org(db, name="Flow Org")
    org = data["organisation"]
    cos = data["agents"]["chief_of_staff"]
    channel = data["channel"]

    # Create task via API
    resp = client.post(
        "/api/tasks",
        json={
            "organisation_id": org.id,
            "title": "Prepare launch checklist",
            "description": "Coordinate teams for launch readiness",
            "channel_id": channel.id,
        },
    )
    assert resp.status_code == 201, resp.text
    task_id = resp.json()["id"]

    # Assign to CoS and run
    assign = client.post(
        f"/api/tasks/{task_id}/assign",
        json={"assignee_id": cos.id, "channel_id": channel.id},
        params={"run": True},
    )
    assert assign.status_code == 200, assign.text
    body = assign.json()
    assert body["status"] == "done"
    assert body["result"]

    # Subtasks should exist and be done
    listed = client.get("/api/tasks", params={"organisation_id": org.id}).json()
    subs = [t for t in listed if t.get("parent_task_id") == task_id]
    assert len(subs) >= 3
    assert all(t["status"] == "done" for t in subs)

    # Channel should have collaboration messages
    messages = client.get(
        "/api/messages", params={"channel_id": channel.id}
    ).json()
    assert len(messages) >= 4
    contents = " ".join(m["content"] for m in messages)
    assert "Decomposition" in contents or "Assigned subtask" in contents
    assert "Executive summary" in contents or "Completed task" in contents


def test_specialist_direct_run(client, mock_llm, db):
    data = bootstrap_sample_org(db, name="Spec Org")
    org = data["organisation"]
    ops = data["agents"]["ops"]
    channel = data["channel"]

    task = client.post(
        "/api/tasks",
        json={
            "organisation_id": org.id,
            "title": "Check capacity",
            "description": "Ops capacity check",
            "channel_id": channel.id,
            "assignee_id": ops.id,
            "status": "assigned",
        },
    ).json()

    run = client.post(f"/api/tasks/{task['id']}/run")
    assert run.status_code == 200, run.text
    assert run.json()["status"] == "done"
    assert "Ops" in (run.json()["result"] or "")


def test_handoff(client, mock_llm, db):
    data = bootstrap_sample_org(db, name="Handoff Org")
    org = data["organisation"]
    ops = data["agents"]["ops"]
    research = data["agents"]["research"]
    channel = data["channel"]

    # Create assigned to ops but do not auto-run via assign endpoint with run=false
    created = client.post(
        "/api/tasks",
        json={
            "organisation_id": org.id,
            "title": "Needs research",
            "channel_id": channel.id,
        },
    ).json()

    client.post(
        f"/api/tasks/{created['id']}/assign",
        json={"assignee_id": ops.id, "channel_id": channel.id},
        params={"run": False},
    ).raise_for_status()

    handoff = client.post(
        f"/api/tasks/{created['id']}/handoff",
        json={"to_agent_id": research.id, "note": "Please research this"},
        params={"run": True},
    )
    assert handoff.status_code == 200, handoff.text
    result = handoff.json()
    assert result["assignee_id"] == research.id
    assert result["status"] == "done"
    assert "Research" in (result["result"] or "")

    messages = client.get(
        "/api/messages", params={"channel_id": channel.id}
    ).json()
    assert any("Handing off" in m["content"] for m in messages)


def test_runner_unit_bootstrap(db, mock_llm):
    data = bootstrap_sample_org(db, name="Unit Org")
    runner = TaskRunner(db, llm=mock_llm)
    task = Task(
        organisation_id=data["organisation"].id,
        title="Unit task",
        description="Direct runner test",
        channel_id=data["channel"].id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    result = runner.assign_task(
        task, data["agents"]["chief_of_staff"], data["channel"], run=True
    )
    assert result.status == TaskStatus.done
    subs = db.query(Task).filter(Task.parent_task_id == result.id).all()
    assert len(subs) == 3
    assert all(s.status == TaskStatus.done for s in subs)
