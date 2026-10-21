"""REST endpoints. Everything here requires authentication (see ``app.py``)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from .. import __version__, clipboard
from ..fs import Entry, Listing, PathError, Root
from ..jobs import JobStatus, ManagerError
from ..settings import Settings, SettingsPatch
from .context import AppContext, get_ctx

router = APIRouter(prefix="/api")


class AddTransferRequest(BaseModel):
    sources: list[str] = Field(min_length=1, max_length=5000)
    destination: str = Field(min_length=1)
    options: dict[str, Any] = {}


class IdsRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=2000)


class ClearRequest(BaseModel):
    statuses: list[JobStatus] = [JobStatus.COMPLETED]


class MkdirRequest(BaseModel):
    parent: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=255)


@router.get("/system")
async def system_info(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    rsync = ctx.rsync
    return {
        "version": __version__,
        "platform": sys.platform,
        "desktop": ctx.config.desktop,
        "data_dir": str(ctx.config.data_dir),
        "home": str(Path.home()),
        "roots": [r.model_dump() for r in ctx.fs.root_views()],
        "rsync": {
            "available": rsync is not None,
            "version": rsync.version if rsync else None,
            "path": rsync.path if rsync else None,
            "error": ctx.rsync_error,
        },
        # The desktop clipboard is only meaningful when the server runs in the user's session
        "clipboard": ctx.config.desktop and clipboard.available(),
    }


@router.get("/settings")
async def get_settings(ctx: AppContext = Depends(get_ctx)) -> Settings:
    return ctx.settings.current


@router.put("/settings")
async def put_settings(body: SettingsPatch, ctx: AppContext = Depends(get_ctx)) -> Settings:
    updated = ctx.settings.update(body.model_dump(exclude_unset=True))
    ctx.manager.settings_changed()
    return updated


@router.get("/fs/roots")
def fs_roots(ctx: AppContext = Depends(get_ctx)) -> list[Root]:
    return ctx.fs.root_views()


@router.get("/fs/list")
def fs_list(path: str, hidden: bool = False, ctx: AppContext = Depends(get_ctx)) -> Listing:
    return ctx.fs.list_dir(path, show_hidden=hidden)


@router.post("/fs/mkdir", status_code=status.HTTP_201_CREATED)
def fs_mkdir(body: MkdirRequest, ctx: AppContext = Depends(get_ctx)) -> Entry:
    name = body.name.strip()
    if not name or name in (".", "..") or "/" in name or "\x00" in name:
        raise PathError("bad_name", "Invalid folder name")
    parent = ctx.fs.resolve(body.parent, kind="dir")
    target = parent / name
    try:
        target.mkdir()
    except FileExistsError as exc:
        raise ManagerError("exists", f"{name} already exists", 409) from exc
    except PermissionError as exc:
        raise PathError("forbidden", f"Permission denied: {parent}") from exc
    return Entry(name=name, path=str(target), kind="dir", modified=target.stat().st_mtime)


@router.get("/clipboard")
async def read_clipboard(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    if not ctx.config.desktop:
        raise ManagerError("clipboard_unavailable", "The clipboard is only available in the desktop app", 409)
    files = await asyncio.to_thread(clipboard.read)
    paths = []
    for raw in files.paths:
        try:
            paths.append(str(ctx.fs.resolve(raw, follow=False)))
        except PathError:
            continue
    return {"action": files.action, "paths": paths, "source": files.source}


@router.post("/window/focus", status_code=status.HTTP_204_NO_CONTENT)
async def focus_window(ctx: AppContext = Depends(get_ctx)) -> None:
    if ctx.focus_window:
        ctx.focus_window()


@router.get("/jobs")
async def list_jobs(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    manager = ctx.manager
    return {"jobs": [manager.dump(j) for j in manager.jobs.values()], "queue": manager.queue_state()}


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
async def add_job(payload: AddTransferRequest, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    job = await ctx.manager.add_transfer(payload.sources, payload.destination, payload.options)
    return ctx.manager.dump(job)


@router.post("/jobs/remove")
async def remove_jobs(payload: IdsRequest, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return {"removed": await ctx.manager.remove_jobs(payload.ids)}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return ctx.manager.dump(ctx.manager.get(job_id))


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str, ctx: AppContext = Depends(get_ctx)) -> None:
    ctx.manager.get(job_id)
    await ctx.manager.remove_jobs([job_id])


@router.post("/jobs/{job_id}/pause")
async def pause_job(job_id: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return ctx.manager.dump(ctx.manager.pause_job(job_id))


@router.post("/jobs/{job_id}/resume")
async def resume_job(job_id: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return ctx.manager.dump(ctx.manager.resume_job(job_id))


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return ctx.manager.dump(await ctx.manager.cancel_job(job_id))


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return ctx.manager.dump(ctx.manager.retry_job(job_id))


@router.get("/jobs/{job_id}/log")
async def job_log(job_id: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    manager = ctx.manager
    job = manager.get(job_id)
    return {
        "log": manager.logs.get(job_id, []),
        "error": job.error,
        "command": manager.command_text(job_id),
    }


@router.get("/jobs/{job_id}/files")
async def job_files(
    job_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=5000),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    return ctx.manager.file_states(job_id, offset, limit)


@router.post("/queue/start")
async def queue_start(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    ctx.manager.start_queue()
    return ctx.manager.queue_state()


@router.post("/queue/pause")
async def queue_pause(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    ctx.manager.pause_queue()
    return ctx.manager.queue_state()


@router.post("/queue/clear")
async def queue_clear(payload: ClearRequest, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return {"removed": await ctx.manager.clear(payload.statuses)}


@router.post("/queue/reorder", status_code=status.HTTP_204_NO_CONTENT)
async def queue_reorder(payload: IdsRequest, ctx: AppContext = Depends(get_ctx)) -> None:
    ctx.manager.reorder(payload.ids)
