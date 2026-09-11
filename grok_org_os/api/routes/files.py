from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from grok_org_os.config import get_settings

router = APIRouter(prefix="/files", tags=["files"])


def _root() -> Path:
    return get_settings().workspace_path()


def _safe(rel: str) -> Path:
    root = _root()
    target = (root / (rel or ".")).resolve()
    if not str(target).startswith(str(root)):
        raise HTTPException(status_code=400, detail="Path escapes workspace")
    return target


@router.get("")
def list_files(path: str = "."):
    target = _safe(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Not found")
    if target.is_file():
        return {"path": path, "type": "file", "size": target.stat().st_size}
    entries = []
    for child in sorted(target.iterdir()):
        entries.append(
            {
                "name": child.name,
                "path": str(Path(path) / child.name).replace("\\", "/"),
                "type": "dir" if child.is_dir() else "file",
                "size": child.stat().st_size if child.is_file() else None,
            }
        )
    return {"path": path, "workspace": str(_root()), "entries": entries}


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), path: str = ""):
    root = _root()
    dest_dir = _safe(path) if path else root
    if dest_dir.is_file():
        raise HTTPException(status_code=400, detail="path must be a directory")
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = Path(file.filename or "upload.bin").name
    dest = (dest_dir / name).resolve()
    if not str(dest).startswith(str(root)):
        raise HTTPException(status_code=400, detail="Invalid filename")
    data = await file.read()
    dest.write_bytes(data)
    rel = str(dest.relative_to(root)).replace("\\", "/")
    return {"ok": True, "path": rel, "bytes": len(data)}


@router.get("/download")
def download_file(path: str):
    target = _safe(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target, filename=target.name)


@router.delete("")
def delete_file(path: str):
    target = _safe(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Not found")
    if target.is_dir():
        raise HTTPException(status_code=400, detail="Refusing to delete directories")
    target.unlink()
    return {"ok": True}
