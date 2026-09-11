"""Typer CLI: grok-org bootstrap | serve | desktop | run-demo."""

from __future__ import annotations

import threading
import time
import webbrowser
from typing import Optional

import typer
import uvicorn

from grok_org_os.bootstrap import bootstrap_sample_org
from grok_org_os.config import get_settings
from grok_org_os.db import SessionLocal, init_db
from grok_org_os.llm import LLMClient, set_llm_client
from grok_org_os.models import Message, Task, TaskStatus
from grok_org_os.task_runner import TaskRunner

app = typer.Typer(
    name="grok-org",
    help="Grok Org OS — portable multi-agent AI organization platform",
    no_args_is_help=True,
)


@app.command()
def bootstrap(
    name: str = typer.Option("Grok Demo Org", help="Organisation name"),
) -> None:
    """Create sample org: CEO (human), CoS, Ops/Research/Comms agents, HQ channel."""
    init_db()
    db = SessionLocal()
    try:
        data = bootstrap_sample_org(db, name=name)
        org = data["organisation"]
        typer.echo(f"Bootstrapped organisation #{org.id}: {org.name}")
        typer.echo(f"  Channel: {data['channel'].name} (#{data['channel'].id})")
        for key, agent in data["agents"].items():
            typer.echo(
                f"  Agent [{key}]: {agent.name} role={agent.role.value} "
                f"human={agent.is_human} id={agent.id}"
            )
        for tname, team in data["teams"].items():
            typer.echo(f"  Team: {tname} (#{team.id})")
    finally:
        db.close()


def _serve_url(host: str, port: int) -> str:
    display_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    return f"http://{display_host}:{port}"


@app.command()
def serve(
    host: Optional[str] = typer.Option(None, help="Bind host"),
    port: Optional[int] = typer.Option(None, help="Bind port"),
    reload: bool = typer.Option(False, help="Auto-reload"),
    open_browser: bool = typer.Option(
        True, "--open/--no-open", help="Open GUI in default browser"
    ),
) -> None:
    """Start the FastAPI server with full GUI at / (Swagger at /docs)."""
    settings = get_settings()
    bind_host = host or settings.host
    bind_port = port or settings.port
    init_db()
    url = _serve_url(bind_host, bind_port)
    typer.echo(f"Serving Grok Org OS GUI on {url}")
    typer.echo(f"API: {url}/api  ·  OpenAPI: {url}/openapi.json  ·  Swagger: {url}/docs")

    if open_browser:

        def _open() -> None:
            time.sleep(1.2)
            try:
                webbrowser.open(url)
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(
        "grok_org_os.api.app:app",
        host=bind_host,
        port=bind_port,
        reload=reload,
    )


@app.command()
def desktop(
    host: Optional[str] = typer.Option(None, help="Bind host"),
    port: Optional[int] = typer.Option(None, help="Bind port"),
) -> None:
    """Open a native desktop window (pywebview) pointing at the local GUI server."""
    settings = get_settings()
    bind_host = host or "127.0.0.1"
    bind_port = port or settings.port
    init_db()
    url = _serve_url(bind_host, bind_port)

    def run_server() -> None:
        uvicorn.run(
            "grok_org_os.api.app:app",
            host=bind_host,
            port=bind_port,
            log_level="info",
        )

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    time.sleep(1.0)

    try:
        import webview  # type: ignore
    except ImportError:
        typer.echo("pywebview not installed — opening browser instead.")
        typer.echo("Install with: pip install 'grok-org-os[desktop]'")
        webbrowser.open(url)
        typer.echo(f"GUI: {url}  (Ctrl+C to stop)")
        try:
            while thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            typer.echo("Stopped.")
        return

    typer.echo(f"Desktop window → {url}")
    window = webview.create_window("Grok Org OS", url, width=1280, height=800)
    webview.start()
    _ = window


@app.command("run-demo")
def run_demo(
    title: str = typer.Option(
        "Launch Q4 product pilot",
        help="Demo task title",
    ),
    description: str = typer.Option(
        "Coordinate Ops, Research, and Comms to prepare a Q4 product pilot plan.",
        help="Demo task description",
    ),
) -> None:
    """Create a task, assign to Chief of Staff, run collaboration, print messages."""
    set_llm_client(LLMClient())
    init_db()
    db = SessionLocal()
    try:
        data = bootstrap_sample_org(db)
        org = data["organisation"]
        cos = data["agents"]["chief_of_staff"]
        channel = data["channel"]
        ceo = data["agents"]["ceo"]

        runner = TaskRunner(db)
        runner.post_message(
            channel,
            ceo,
            f"Directive: {title}\n{description}\nPlease coordinate the teams.",
        )

        task = Task(
            organisation_id=org.id,
            title=title,
            description=description,
            status=TaskStatus.pending,
            channel_id=channel.id,
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        typer.echo(f"=== Demo: org={org.name} task=#{task.id} ===")
        typer.echo(f"Assigning to {cos.name} and running collaboration (mock LLM ok)...\n")

        result = runner.assign_task(task, cos, channel, run=True)

        messages = (
            db.query(Message)
            .filter(Message.channel_id == channel.id)
            .order_by(Message.id)
            .all()
        )
        typer.echo("--- Channel messages ---")
        for msg in messages:
            agent = msg.agent
            role = agent.role.value if agent else "?"
            name = agent.name if agent else "?"
            typer.echo(f"[{msg.id}] {name} ({role}):")
            typer.echo(f"  {msg.content}\n")

        typer.echo("--- Task summary ---")
        typer.echo(f"Parent task #{result.id} status={result.status.value}")
        if result.result:
            typer.echo(f"Result:\n{result.result}")

        subs = db.query(Task).filter(Task.parent_task_id == result.id).all()
        for sub in subs:
            assignee = sub.assignee.name if sub.assignee else "?"
            typer.echo(f"  Subtask #{sub.id} [{assignee}] status={sub.status.value}")

        typer.echo("\nDemo complete.")
    finally:
        db.close()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
