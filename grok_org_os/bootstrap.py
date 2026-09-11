"""Sample organisation bootstrap."""

from __future__ import annotations

from sqlalchemy.orm import Session

from grok_org_os.models import Agent, AgentRole, Channel, Organisation, Team


def bootstrap_sample_org(db: Session, name: str = "Grok Demo Org") -> dict:
    """Create CEO (human), Chief of Staff, Ops/Research/Comms teams + agents, HQ channel.

    Returns a dict of created entity ids and names for CLI/demo use.
    """
    existing = db.query(Organisation).filter(Organisation.name == name).first()
    if existing:
        org = existing
    else:
        org = Organisation(
            name=name,
            description="Sample multi-agent organisation for demos and tests",
        )
        db.add(org)
        db.commit()
        db.refresh(org)

    def get_or_create_team(team_name: str, description: str) -> Team:
        team = (
            db.query(Team)
            .filter(Team.organisation_id == org.id, Team.name == team_name)
            .first()
        )
        if team:
            return team
        team = Team(organisation_id=org.id, name=team_name, description=description)
        db.add(team)
        db.commit()
        db.refresh(team)
        return team

    def get_or_create_agent(
        agent_name: str,
        role: AgentRole,
        *,
        team: Team | None = None,
        is_human: bool = False,
        system_prompt: str | None = None,
    ) -> Agent:
        agent = (
            db.query(Agent)
            .filter(Agent.organisation_id == org.id, Agent.name == agent_name)
            .first()
        )
        if agent:
            return agent
        agent = Agent(
            organisation_id=org.id,
            team_id=team.id if team else None,
            name=agent_name,
            role=role,
            is_human=is_human,
            system_prompt=system_prompt,
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)
        return agent

    ops = get_or_create_team("Ops", "Operations and execution")
    research = get_or_create_team("Research", "Research and analysis")
    comms = get_or_create_team("Comms", "Communications and stakeholder updates")

    ceo = get_or_create_agent(
        "CEO",
        AgentRole.ceo,
        is_human=True,
        system_prompt="You are the human CEO. Set direction and approve plans.",
    )
    cos = get_or_create_agent(
        "Chief of Staff",
        AgentRole.chief_of_staff,
        system_prompt=(
            "You are the Chief of Staff. Decompose CEO directives into subtasks, "
            "assign work to Ops/Research/Comms specialists, and synthesize results."
        ),
    )
    ops_agent = get_or_create_agent(
        "Ops Specialist",
        AgentRole.specialist,
        team=ops,
        system_prompt=(
            "You are an Ops specialist focused on operations, logistics, and execution readiness."
        ),
    )
    research_agent = get_or_create_agent(
        "Research Specialist",
        AgentRole.specialist,
        team=research,
        system_prompt=(
            "You are a Research specialist focused on gathering facts, options, and analysis."
        ),
    )
    comms_agent = get_or_create_agent(
        "Comms Specialist",
        AgentRole.specialist,
        team=comms,
        system_prompt=(
            "You are a Comms specialist focused on clear stakeholder communication."
        ),
    )

    channel = (
        db.query(Channel)
        .filter(Channel.organisation_id == org.id, Channel.name == "HQ")
        .first()
    )
    if not channel:
        channel = Channel(
            organisation_id=org.id,
            name="HQ",
            description="Primary coordination channel",
        )
        db.add(channel)
        db.commit()
        db.refresh(channel)

    return {
        "organisation": org,
        "teams": {"Ops": ops, "Research": research, "Comms": comms},
        "agents": {
            "ceo": ceo,
            "chief_of_staff": cos,
            "ops": ops_agent,
            "research": research_agent,
            "comms": comms_agent,
        },
        "channel": channel,
    }
