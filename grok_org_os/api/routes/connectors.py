from __future__ import annotations

from fastapi import APIRouter, HTTPException

from grok_org_os.connectors.registry import (
    get_connector,
    list_connectors,
    register_builtins,
    set_connector_enabled,
)
from grok_org_os.schemas import ConnectorEnable, ConnectorInvoke

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.get("")
def get_connectors():
    register_builtins()
    return list_connectors()


@router.post("/{name}/enable")
def enable_connector(name: str, payload: ConnectorEnable):
    try:
        return set_connector_enabled(name, payload.enabled)
    except KeyError:
        raise HTTPException(status_code=404, detail="Connector not found") from None


@router.post("/{name}/invoke")
def invoke_connector(name: str, payload: ConnectorInvoke):
    c = get_connector(name)
    if not c:
        raise HTTPException(status_code=404, detail="Connector not found")
    return c.invoke(payload.payload)
