from __future__ import annotations

import asyncio
import shutil
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest

from rgcopy.engine.rsync import discover
from rgcopy.fs import FileSystem
from rgcopy.jobs import Job, JobManager, JobStatus
from rgcopy.settings import Settings, SettingsStore

needs_rsync = pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync is not installed")


def make_tree(root: Path, files: dict[str, bytes | str]) -> Path:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            content = content.encode()
        path.write_bytes(content)
    return root


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    make_tree(
        src / "album",
        {
            "one.txt": "one",
            "two.bin": b"x" * 200_000,
            "deep/ñandú b.txt": "accents and spaces",
        },
    )
    (src / "single.txt").write_text("single")
    (tmp_path / "dst").mkdir()
    return tmp_path


@pytest.fixture
async def manager(tmp_path: Path) -> AsyncIterator[JobManager]:
    manager = JobManager(
        rsync=discover(),
        # Tests about existing files set "ask" themselves
        settings=SettingsStore(None, Settings(auto_start=True, conflict="overwrite")),
        fs=FileSystem([tmp_path]),
    )
    await manager.start()
    try:
        yield manager
    finally:
        await manager.shutdown()


async def wait_for(
    manager: JobManager, job: Job, predicate: Callable[[Job], Any] | None = None, timeout: float = 20
) -> Job:
    """Wait until ``predicate(job)`` holds (default: the job finished)."""

    def done(j: Job) -> bool:
        return j.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED)

    check = predicate or done
    deadline = asyncio.get_running_loop().time() + timeout
    while not check(job):
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"timed out: {job.status} {job.error}")
        await asyncio.sleep(0.02)
    return job
