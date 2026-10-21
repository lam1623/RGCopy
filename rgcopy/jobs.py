"""Transfer queue: jobs, scheduling, lifecycle and change events."""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import os
import time
import uuid
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .engine.rsync import (
    Progress,
    RsyncInfo,
    TransferOptions,
    build_command,
    display_command,
)
from .engine.runner import RsyncRun, RunResult
from .fs import FileSystem, PathError, ScanResult, free_space, same_device, scan
from .settings import SettingsStore

log = logging.getLogger(__name__)

Event = dict[str, Any]

# rsync exit codes (see `man rsync`, EXIT VALUES)
RSYNC_PARTIAL = 23
RSYNC_VANISHED = 24
RSYNC_ERRORS = {
    1: "Syntax or usage error",
    2: "Protocol incompatibility",
    3: "Errors selecting input/output files or folders",
    5: "Error starting the client-server protocol",
    10: "Error in socket I/O",
    11: "Error in file I/O",
    12: "Error in the rsync data stream",
    13: "Errors with program diagnostics",
    14: "Error in IPC code",
    20: "Interrupted",
    21: "Some error returned by waitpid()",
    22: "Error allocating core memory buffers",
    RSYNC_PARTIAL: "Some files could not be transferred",
    RSYNC_VANISHED: "Some source files vanished before they could be transferred",
    25: "The --max-delete limit stopped deletions",
    30: "Timeout in data send/receive",
    35: "Timeout waiting for daemon connection",
}


class JobStatus(StrEnum):
    # Sizes are still being counted
    SCANNING = "scanning"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


ACTIVE = frozenset({JobStatus.RUNNING, JobStatus.PAUSED})
FINISHED = frozenset({JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED})


class Job(BaseModel):
    id: str
    # "photos", or "photos and 3 more"
    name: str
    sources: list[str]
    destination: str
    options: TransferOptions
    status: JobStatus = JobStatus.SCANNING
    progress: Progress = Field(default_factory=Progress)
    total_bytes: int = 0
    total_files: int = 0
    total_dirs: int = 0
    error: str | None = None
    # Non-fatal notes, e.g. files that vanished during the copy
    warning: str | None = None
    # A move within one filesystem renames instead of copying
    fast_move: bool = False
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    # Bumped on every published change so clients can drop stale copies (e.g. late HTTP responses)
    revision: int = 0


class ManagerError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def summarize_error(result: RunResult | None, fallback: str) -> str:
    if result is None:
        return fallback
    lines = [
        line.strip()
        for line in result.log
        if line.strip() and not line.startswith("rsync error:") and "see previous errors" not in line
    ]
    reason = RSYNC_ERRORS.get(result.returncode, f"rsync exited with code {result.returncode}")
    if not lines:
        return reason
    return f"{reason}: {' · '.join(lines[-3:])}"[:600]


def _job_name(sources: list[Path]) -> str:
    first = sources[0].name or str(sources[0])
    return first if len(sources) == 1 else f"{first} +{len(sources) - 1}"


def _remove_empty_dirs(root: Path) -> None:
    """After a move, remove the folders rsync emptied (bottom-up); folders with leftovers stay."""

    if root.is_symlink() or not root.is_dir():
        return
    for dirpath, _dirnames, _filenames in os.walk(root, topdown=False):
        with contextlib.suppress(OSError):
            os.rmdir(dirpath)


def _rename_new(source: Path, target: Path) -> None:
    if os.path.lexists(target):
        raise FileExistsError(f"{target} appeared during the move")
    os.rename(source, target)


class JobManager:
    def __init__(
        self,
        *,
        rsync: RsyncInfo | None,
        settings: SettingsStore,
        fs: FileSystem,
    ) -> None:
        self.rsync = rsync
        self.settings = settings
        self.fs = fs
        self.jobs: dict[str, Job] = {}
        self.logs: dict[str, list[str]] = {}
        # The files of each transfer (from the scan) and the ones rsync transferred
        self.files: dict[str, ScanResult] = {}
        self._transferred: dict[str, list[str]] = {}
        self.queue_running = False
        self._runs: dict[str, RsyncRun] = {}
        self._job_tasks: dict[str, asyncio.Task[None]] = {}
        self._background: set[asyncio.Task[Any]] = set()
        self._cancel_requested: set[str] = set()
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._dirty: set[str] = set()
        self._flusher: asyncio.Task[None] | None = None
        self._launched_since_start = False
        self._closing = False

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        self._flusher = asyncio.create_task(self._flush_progress())

    async def shutdown(self) -> None:
        """Stop everything and make sure no rsync process outlives the app."""

        self._closing = True
        self.queue_running = False
        for run in list(self._runs.values()):
            with contextlib.suppress(Exception):
                await run.cancel()
        job_tasks = list(self._job_tasks.values())
        if job_tasks:
            await asyncio.wait(job_tasks, timeout=10)
        pending = [
            t for t in [*job_tasks, *self._background, self._flusher] if t is not None and not t.done()
        ]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    # ------------------------------------------------------------------ events

    def subscribe(self) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=1000)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Event]) -> None:
        self._subscribers.discard(queue)

    def _publish(self, event: Event) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Slow client: drop its backlog and ask it to reload a snapshot
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait({"type": "resync"})

    def snapshot(self) -> Event:
        return {
            "type": "snapshot",
            "jobs": [self.dump(j) for j in self.jobs.values()],
            "queue": self.queue_state(),
        }

    def queue_state(self) -> dict[str, Any]:
        counts = {status.value: 0 for status in JobStatus}
        for job in self.jobs.values():
            counts[job.status.value] += 1
        # Overall figures of the transfers that are still to do (or being done)
        pending = [j for j in self.jobs.values() if j.status in ACTIVE or j.status == JobStatus.QUEUED]
        speed = sum(j.progress.speed or 0 for j in pending if j.status == JobStatus.RUNNING)
        return {
            "running": self.queue_running,
            "counts": counts,
            "total_bytes": sum(j.total_bytes for j in pending),
            "bytes_done": sum(j.progress.bytes_done for j in pending),
            "speed": speed or None,
        }

    @staticmethod
    def dump(job: Job) -> dict[str, Any]:
        return job.model_dump(mode="json")

    def _emit_job(self, job: Job) -> None:
        if job.id in self.jobs:
            job.revision += 1
            self._publish({"type": "job", "job": self.dump(job)})

    def _emit_queue(self) -> None:
        self._publish({"type": "queue", "queue": self.queue_state()})

    def settings_changed(self) -> None:
        self._publish({"type": "settings", "settings": self.settings.current.model_dump()})
        self._schedule()

    async def _flush_progress(self) -> None:
        while True:
            await asyncio.sleep(0.25)
            if not self._dirty:
                continue
            items = [
                {"id": job_id, "progress": self.jobs[job_id].progress.model_dump()}
                for job_id in self._dirty
                if job_id in self.jobs
            ]
            self._dirty.clear()
            if items:
                self._publish({"type": "progress", "items": items})
                self._emit_queue()

    def _on_progress(self, job_id: str, progress: Progress) -> None:
        job = self.jobs.get(job_id)
        if job is not None and job.status in ACTIVE:
            if job.status == JobStatus.PAUSED:
                progress = progress.model_copy(update={"speed": None, "eta_s": None})
            job.progress = progress
            self._dirty.add(job_id)

    def _spawn(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    # ------------------------------------------------------------------ helpers

    def get(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None:
            raise ManagerError("not_found", "No such transfer", 404)
        return job

    def _require_rsync(self) -> RsyncInfo:
        if self.rsync is None:
            raise ManagerError("rsync_missing", "rsync is not installed", 503)
        return self.rsync

    def default_options(self, patch: dict[str, Any] | None = None) -> TransferOptions:
        current = self.settings.current
        base = {
            "mode": "copy",
            "conflict": current.conflict,
            "checksum": current.checksum,
            "preserve": current.preserve,
            "bwlimit": current.bwlimit,
        }
        try:
            return TransferOptions.model_validate({**base, **(patch or {})})
        except ValidationError as exc:
            raise ManagerError("invalid_options", str(exc), 422) from exc

    def command(self, job: Job) -> list[str]:
        rsync = self.rsync.path if self.rsync else "rsync"
        return build_command(rsync, [Path(s) for s in job.sources], Path(job.destination), job.options)

    def command_text(self, job_id: str) -> str:
        job = self.get(job_id)
        if job.fast_move:
            return "\n".join(f"mv -- {s} {job.destination}/" for s in job.sources)
        return display_command(self.command(job))

    def _check_sources(self, raw_sources: list[str], destination: Path) -> list[Path]:
        sources: list[Path] = []
        for raw in raw_sources:
            source = self.fs.resolve(raw, follow=False)
            if source in sources:
                continue
            if source == destination or source.parent == destination:
                raise ManagerError("same_folder", f"{source.name} is already in the destination folder", 422)
            if source.is_dir() and not source.is_symlink() and destination.is_relative_to(source):
                raise ManagerError(
                    "into_itself", f"A folder cannot be copied into itself: {source.name}", 422
                )
            sources.append(source)
        if not sources:
            raise ManagerError("no_sources", "Nothing to copy", 422)
        # Two sources with the same name would land on the same destination path
        names = [s.name for s in sources]
        clash = next((n for n in names if names.count(n) > 1), None)
        if clash:
            raise ManagerError("name_clash", f"Two items are called {clash}", 422)
        return sources

    # ------------------------------------------------------------------ jobs

    async def add_transfer(
        self, raw_sources: list[str], raw_destination: str, patch: dict[str, Any] | None = None
    ) -> Job:
        self._require_rsync()
        destination = self.fs.resolve(raw_destination, kind="dir")
        if not os.access(destination, os.W_OK | os.X_OK):
            raise ManagerError("not_writable", f"Cannot write to {destination}", 403)
        sources = self._check_sources(raw_sources, destination)
        options = self.default_options(patch)
        job = Job(
            id=uuid.uuid4().hex[:12],
            name=_job_name(sources),
            sources=[str(s) for s in sources],
            destination=str(destination),
            options=options,
            created_at=time.time(),
        )
        self.jobs[job.id] = job
        self._emit_job(job)
        self._emit_queue()
        self._spawn(self._scan(job))
        return job

    async def _scan(self, job: Job) -> None:
        try:
            result: ScanResult = await asyncio.to_thread(scan, [Path(s) for s in job.sources])
        except Exception as exc:  # a broken mount must not leave the job scanning forever
            log.exception("Scanning %s failed", job.name)
            if job.id in self.jobs:
                self._finish(job, JobStatus.FAILED, error=f"Cannot read the files: {exc}")
            return
        if job.id not in self.jobs or job.status != JobStatus.SCANNING:
            return
        self.files[job.id] = result
        job.total_bytes = result.total_bytes
        job.total_files = result.total_files
        job.total_dirs = result.total_dirs
        job.progress = Progress(total_bytes=job.total_bytes, total_files=job.total_files)
        job.status = JobStatus.QUEUED
        self._emit_job(job)
        if self.settings.current.auto_start:
            self.start_queue(resume=False)
        else:
            self._emit_queue()

    def start_queue(self, *, resume: bool = True) -> None:
        """Run the queue. ``resume`` also resumes every paused transfer (the "Start" button);
        a transfer that starts by itself must not resume the ones the user paused."""

        self._require_rsync()
        self.queue_running = True
        if resume:
            for job in list(self.jobs.values()):
                if job.status == JobStatus.PAUSED:
                    with contextlib.suppress(ManagerError):
                        self.resume_job(job.id)
        self._emit_queue()
        self._schedule()

    def pause_queue(self) -> None:
        self.queue_running = False
        for job in self.jobs.values():
            if job.status == JobStatus.RUNNING:
                with contextlib.suppress(ManagerError):
                    self.pause_job(job.id)
        self._emit_queue()

    def _schedule(self) -> None:
        if self._closing or not self.queue_running:
            return
        active = sum(1 for j in self.jobs.values() if j.status in ACTIVE)
        slots = self.settings.current.concurrency - active
        for job in list(self.jobs.values()):
            if slots <= 0:
                break
            if job.status == JobStatus.QUEUED:
                self._launch(job)
                slots -= 1
        busy = {JobStatus.SCANNING, JobStatus.QUEUED, *ACTIVE}
        if not any(j.status in busy for j in self.jobs.values()):
            self.queue_running = False
            self._emit_queue()
            if self._launched_since_start:
                self._launched_since_start = False
                self._publish({"type": "queue_finished", "counts": self.queue_state()["counts"]})

    def _launch(self, job: Job) -> None:
        self._launched_since_start = True
        self._cancel_requested.discard(job.id)
        job.status = JobStatus.RUNNING
        job.progress = Progress(total_bytes=job.total_bytes, total_files=job.total_files)
        job.error = job.warning = None
        job.started_at = time.time()
        job.finished_at = None
        task = asyncio.create_task(self._run(job))
        self._job_tasks[job.id] = task
        task.add_done_callback(functools.partial(self._forget_task, job.id))

    def _forget_task(self, job_id: str, _task: asyncio.Task[None]) -> None:
        self._job_tasks.pop(job_id, None)

    def _can_rename(self, job: Job) -> bool:
        """A move inside one filesystem whose targets do not exist yet is a plain rename."""

        if job.options.mode != "move":
            return False
        destination = Path(job.destination)
        return all(
            same_device(Path(s), destination) and not os.path.lexists(destination / Path(s).name)
            for s in job.sources
        )

    def _check_space(self, job: Job) -> None:
        if not self.settings.current.check_space or job.fast_move:
            return
        free = free_space(Path(job.destination))
        if free is not None and job.total_bytes > free:
            raise ManagerError(
                "no_space",
                f"Not enough free space: {job.total_bytes} bytes needed, {free} available",
                507,
            )

    async def _run(self, job: Job) -> None:
        job.fast_move = self._can_rename(job)
        try:
            self.fs.resolve(job.destination, kind="dir")
            self._check_space(job)
        except (PathError, ManagerError) as exc:
            self._finish(job, JobStatus.FAILED, error=exc.message)
            return
        self._emit_job(job)
        self._emit_queue()
        if job.fast_move:
            await self._rename(job)
            return

        result: RunResult | None = None
        start_error = ""
        run = RsyncRun(
            self.command(job),
            job.total_bytes,
            job.total_files,
            on_progress=functools.partial(self._on_progress, job.id),
        )
        self._runs[job.id] = run
        try:
            result = await run.run()
        except OSError as exc:
            start_error = f"Cannot start rsync: {exc}"
        finally:
            self._runs.pop(job.id, None)
            self._transferred[job.id] = run.names
        self.logs[job.id] = result.log if result else [start_error]

        if (result is not None and result.canceled) or job.id in self._cancel_requested:
            self._finish(job, JobStatus.CANCELED)
            return
        if result is not None and result.returncode in (0, RSYNC_VANISHED):
            if job.options.mode == "move":
                await asyncio.to_thread(self._cleanup_sources, job)
            job.progress = job.progress.model_copy(
                update={
                    "percent": 100.0,
                    "eta_s": 0.0,
                    "bytes_done": max(job.progress.bytes_done, job.total_bytes),
                    "files_done": job.total_files,
                    "current": None,
                }
            )
            if result.returncode == RSYNC_VANISHED:
                job.warning = RSYNC_ERRORS[RSYNC_VANISHED]
            self._finish(job, JobStatus.COMPLETED)
            return
        self._finish(job, JobStatus.FAILED, error=summarize_error(result, start_error))

    @staticmethod
    def _cleanup_sources(job: Job) -> None:
        for source in job.sources:
            _remove_empty_dirs(Path(source))

    async def _rename(self, job: Job) -> None:
        destination = Path(job.destination)
        moved: list[str] = []
        try:
            for source in job.sources:
                target = destination / Path(source).name
                await asyncio.to_thread(_rename_new, Path(source), target)
                moved.append(f"{source} -> {target}")
        except OSError as exc:
            self.logs[job.id] = [*moved, str(exc)]
            self._finish(job, JobStatus.FAILED, error=f"Cannot move: {exc}")
            return
        self.logs[job.id] = moved
        job.progress = job.progress.model_copy(
            update={
                "percent": 100.0,
                "bytes_done": job.total_bytes,
                "files_done": job.total_files,
                "eta_s": 0.0,
            }
        )
        self._finish(job, JobStatus.COMPLETED)

    def _finish(self, job: Job, status: JobStatus, error: str | None = None) -> None:
        job.status = status
        job.error = error
        job.finished_at = time.time()
        update: dict[str, Any] = {"speed": None, "eta_s": None}
        if job.started_at:
            update["elapsed_s"] = round(job.finished_at - job.started_at, 1)
        job.progress = job.progress.model_copy(update=update)
        self._dirty.discard(job.id)
        self._emit_job(job)
        self._emit_queue()
        self._schedule()

    def pause_job(self, job_id: str) -> Job:
        job = self.get(job_id)
        run = self._runs.get(job_id)
        if job.status != JobStatus.RUNNING or run is None:
            raise ManagerError("not_running", "Only running transfers can be paused", 409)
        run.pause()
        job.status = JobStatus.PAUSED
        job.progress = job.progress.model_copy(update={"speed": None, "eta_s": None})
        self._emit_job(job)
        self._emit_queue()
        return job

    def resume_job(self, job_id: str) -> Job:
        job = self.get(job_id)
        run = self._runs.get(job_id)
        if job.status != JobStatus.PAUSED or run is None:
            raise ManagerError("not_paused", "Only paused transfers can be resumed", 409)
        run.resume()
        job.status = JobStatus.RUNNING
        self._emit_job(job)
        self._emit_queue()
        return job

    async def cancel_job(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.status in (JobStatus.QUEUED, JobStatus.SCANNING):
            self._finish(job, JobStatus.CANCELED)
        elif job.status in ACTIVE:
            self._cancel_requested.add(job_id)
            run = self._runs.get(job_id)
            if run is not None:
                await run.cancel()
            task = self._job_tasks.get(job_id)
            if task is not None:
                await asyncio.wait([task], timeout=10)
        else:
            raise ManagerError("not_cancelable", "This transfer has already finished", 409)
        return job

    def retry_job(self, job_id: str) -> Job:
        """Run a finished transfer again: rsync only copies what is still missing."""

        job = self.get(job_id)
        if job.status not in FINISHED:
            raise ManagerError("not_finished", "Only finished transfers can be run again", 409)
        missing = [s for s in job.sources if os.path.lexists(s)]
        if not missing:
            raise ManagerError("sources_gone", "The source files no longer exist", 409)
        job.sources = missing
        job.status = JobStatus.SCANNING
        job.error = job.warning = None
        job.started_at = job.finished_at = None
        job.fast_move = False
        self.logs.pop(job_id, None)
        self._transferred.pop(job_id, None)
        self._emit_job(job)
        self._emit_queue()
        self._spawn(self._scan(job))
        return job

    async def remove_jobs(self, job_ids: Iterable[str]) -> list[str]:
        removed = []
        for job_id in list(job_ids):
            job = self.jobs.get(job_id)
            if job is None:
                continue
            if job.status in ACTIVE:
                await self.cancel_job(job_id)
            self.jobs.pop(job_id, None)
            self.logs.pop(job_id, None)
            self.files.pop(job_id, None)
            self._transferred.pop(job_id, None)
            self._dirty.discard(job_id)
            removed.append(job_id)
        if removed:
            self._publish({"type": "removed", "ids": removed})
            self._emit_queue()
            self._schedule()
        return removed

    async def clear(self, statuses: Iterable[str]) -> list[str]:
        wanted = {JobStatus(s) for s in statuses} & FINISHED
        return await self.remove_jobs([j.id for j in self.jobs.values() if j.status in wanted])

    def reorder(self, job_ids: list[str]) -> None:
        """Move the given jobs to the front, in the given order."""

        front = {job_id: self.jobs[job_id] for job_id in job_ids if job_id in self.jobs}
        rest = {job_id: job for job_id, job in self.jobs.items() if job_id not in front}
        self.jobs = {**front, **rest}
        self._publish(self.snapshot())

    def file_states(self, job_id: str, offset: int = 0, limit: int = 500) -> dict[str, Any]:
        """The files of a transfer with what happened to each: done, current, pending or skipped.

        rsync names the files it transfers; at the end, the ones it never named were already
        up to date at the destination (or kept because of the conflict rule).
        """

        job = self.get(job_id)
        scanned = self.files.get(job_id)
        if scanned is None:
            return {"total": 0, "listed": 0, "truncated": False, "files": []}
        run = self._runs.get(job_id)
        names = run.names if run is not None else self._transferred.get(job_id, [])
        current = names[-1] if run is not None and names else None
        done = set(names) - ({current} if current else set())
        rest = "pending"
        if job.status == JobStatus.COMPLETED:
            rest = "done" if job.fast_move else "skipped"
        files = []
        for name, size in scanned.files[offset : offset + limit]:
            state = "done" if name in done else "current" if name == current else rest
            files.append({"path": name, "size": size, "state": state})
        return {
            "total": job.total_files,
            "listed": len(scanned.files),
            "truncated": scanned.truncated,
            "files": files,
        }

    def all_done(self) -> bool:
        """Nothing left to do and nothing failed (the desktop app may close itself)."""

        return bool(self.jobs) and all(j.status == JobStatus.COMPLETED for j in self.jobs.values())
