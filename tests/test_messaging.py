"""Agent messaging tests."""

from __future__ import annotations


def _seed(client):
    org = client.post("/api/orgs", json={"name": "Msg Org"}).json()
    agent = client.post(
        "/api/agents",
        json={
            "organisation_id": org["id"],
            "name": "Writer",
            "role": "specialist",
            "system_prompt": "You write messages.",
        },
    ).json()
    channel = client.post(
        "/api/channels",
        json={"organisation_id": org["id"], "name": "general"},
    ).json()
    return org, agent, channel


def test_agent_post_and_list_messages(client):
    org, agent, channel = _seed(client)
    resp = client.post(
        "/api/messages",
        json={
            "channel_id": channel["id"],
            "agent_id": agent["id"],
            "content": "Hello from the agent",
        },
    )
    assert resp.status_code == 201, resp.text
    msg = resp.json()
    assert msg["content"] == "Hello from the agent"
    assert msg["agent_id"] == agent["id"]

    listed = client.get("/api/messages", params={"channel_id": channel["id"]})
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) == 1
    assert items[0]["id"] == msg["id"]


def test_message_requires_valid_channel_and_agent(client):
    org, agent, channel = _seed(client)
    bad_channel = client.post(
        "/api/messages",
        json={"channel_id": 99999, "agent_id": agent["id"], "content": "x"},
    )
    assert bad_channel.status_code == 404

    bad_agent = client.post(
        "/api/messages",
        json={"channel_id": channel["id"], "agent_id": 99999, "content": "x"},
    )
    assert bad_agent.status_code == 404
