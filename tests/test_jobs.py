from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from rgcopy import jobs as jobs_module
from rgcopy.engine.rsync import BACKUP_SUFFIX
from rgcopy.jobs import JobManager, JobStatus, ManagerError
from tests.conftest import make_tree, needs_rsync, wait_for

pytestmark = needs_rsync


async def test_copy_folder_and_file(manager: JobManager, tree: Path):
    job = await manager.add_transfer(
        [str(tree / "src/album"), str(tree / "src/single.txt")], str(tree / "dst")
    )
    assert job.name == "album +1"
    await wait_for(manager, job)
    assert job.status == JobStatus.COMPLETED, job.error
    assert (tree / "dst/album/deep/ñandú b.txt").read_text() == "accents and spaces"
    assert (tree / "dst/single.txt").read_text() == "single"
    assert job.total_files == 4
    assert job.progress.percent == 100
    assert job.progress.files_done == 4
    assert job.progress.bytes_done == job.total_bytes == 3 + 200_000 + 18 + 6
    # Sources stay where they were
    assert (tree / "src/album/one.txt").exists()


async def test_move_within_one_filesystem_renames(manager: JobManager, tree: Path):
    job = await manager.add_transfer([str(tree / "src/album")], str(tree / "dst"), {"mode": "move"})
    await wait_for(manager, job)
    assert job.status == JobStatus.COMPLETED, job.error
    assert job.fast_move
    assert not (tree / "src/album").exists()
    assert (tree / "dst/album/two.bin").stat().st_size == 200_000
    assert "mv -- " in manager.command_text(job.id)


async def test_move_merging_into_an_existing_folder_uses_rsync(manager: JobManager, tree: Path):
    make_tree(tree / "dst/album", {"old.txt": "kept"})
    job = await manager.add_transfer([str(tree / "src/album")], str(tree / "dst"), {"mode": "move"})
    await wait_for(manager, job)
    assert job.status == JobStatus.COMPLETED, job.error
    assert not job.fast_move
    assert (tree / "dst/album/old.txt").read_text() == "kept"
    assert (tree / "dst/album/deep/ñandú b.txt").exists()
    # Every moved file and the emptied folders are gone from the source
    assert not (tree / "src/album").exists()


async def test_conflicts(manager: JobManager, tree: Path):
    make_tree(tree / "dst", {"single.txt": "existing"})
    skip = await manager.add_transfer([str(tree / "src/single.txt")], str(tree / "dst"), {"conflict": "skip"})
    await wait_for(manager, skip)
    assert skip.status == JobStatus.COMPLETED
    assert (tree / "dst/single.txt").read_text() == "existing"

    backup = await manager.add_transfer(
        [str(tree / "src/single.txt")], str(tree / "dst"), {"conflict": "backup"}
    )
    await wait_for(manager, backup)
    assert backup.status == JobStatus.COMPLETED, backup.error
    assert (tree / "dst/single.txt").read_text() == "single"
    assert (tree / f"dst/single.txt{BACKUP_SUFFIX}").read_text() == "existing"


async def test_rejects_impossible_transfers(manager: JobManager, tree: Path):
    with pytest.raises(ManagerError) as err:
        await manager.add_transfer([str(tree / "src/single.txt")], str(tree / "src"))
    assert err.value.code == "same_folder"
    with pytest.raises(ManagerError) as err:
        await manager.add_transfer([str(tree / "src/album")], str(tree / "src/album/deep"))
    assert err.value.code == "into_itself"
    make_tree(tree / "other", {"single.txt": "x"})
    with pytest.raises(ManagerError) as err:
        await manager.add_transfer(
            [str(tree / "src/single.txt"), str(tree / "other/single.txt")], str(tree / "dst")
        )
    assert err.value.code == "name_clash"


async def test_not_enough_space(manager: JobManager, tree: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(jobs_module, "free_space", lambda _path: 10)
    job = await manager.add_transfer([str(tree / "src/album")], str(tree / "dst"))
    await wait_for(manager, job)
    assert job.status == JobStatus.FAILED
    assert "Not enough free space" in (job.error or "")
    assert not (tree / "dst/album").exists()


async def test_pause_resume_and_cancel(manager: JobManager, tmp_path: Path):
    make_tree(tmp_path / "big", {"blob.bin": b"\0" * 4_000_000})
    (tmp_path / "out").mkdir()
    # 400 KiB/s: about ten seconds, plenty of time to pause and cancel
    job = await manager.add_transfer([str(tmp_path / "big")], str(tmp_path / "out"), {"bwlimit": 400})
    await wait_for(manager, job, lambda j: j.status == JobStatus.RUNNING and j.progress.bytes_done > 0)
    manager.pause_job(job.id)
    assert job.status == JobStatus.PAUSED
    paused_at = job.progress.bytes_done
    await asyncio.sleep(0.6)
    assert job.progress.bytes_done - paused_at < 200_000
    manager.resume_job(job.id)
    assert job.status == JobStatus.RUNNING
    await manager.cancel_job(job.id)
    assert job.status == JobStatus.CANCELED
    assert not manager._runs


async def test_failure_reports_rsync_error(manager: JobManager, tree: Path):
    target = tree / "dst"
    job = await manager.add_transfer([str(tree / "src/album")], str(target))
    # Make the destination read-only between queuing and running
    manager.pause_queue()
    target.chmod(0o500)
    try:
        await wait_for(manager, job, lambda j: j.status != JobStatus.SCANNING)
        manager.start_queue()
        await wait_for(manager, job)
    finally:
        target.chmod(0o700)
    if job.status == JobStatus.COMPLETED:
        pytest.skip("running as root: permissions are not enforced")
    assert job.status == JobStatus.FAILED
    assert job.error


async def test_retry_copies_again(manager: JobManager, tree: Path):
    job = await manager.add_transfer([str(tree / "src/single.txt")], str(tree / "dst"))
    await wait_for(manager, job)
    (tree / "dst/single.txt").unlink()
    manager.retry_job(job.id)
    await wait_for(manager, job, lambda j: j.status not in (JobStatus.SCANNING,))
    await wait_for(manager, job)
    assert job.status == JobStatus.COMPLETED
    assert (tree / "dst/single.txt").exists()


async def test_queue_events_and_clear(manager: JobManager, tree: Path):
    events = manager.subscribe()
    job = await manager.add_transfer([str(tree / "src/single.txt")], str(tree / "dst"))
    await wait_for(manager, job)
    seen = []
    while not events.empty():
        seen.append(events.get_nowait()["type"])
    assert "job" in seen and "queue" in seen and "queue_finished" in seen
    assert manager.all_done()
    assert await manager.clear(["completed"]) == [job.id]
    assert not manager.jobs


async def test_manual_start_when_auto_start_is_off(manager: JobManager, tree: Path):
    manager.settings.update({"auto_start": False})
    job = await manager.add_transfer([str(tree / "src/single.txt")], str(tree / "dst"))
    await wait_for(manager, job, lambda j: j.status == JobStatus.QUEUED)
    await asyncio.sleep(0.2)
    assert job.status == JobStatus.QUEUED
    manager.start_queue()
    await wait_for(manager, job)
    assert job.status == JobStatus.COMPLETED


async def test_rsync_error_is_summarized(manager: JobManager, tree: Path):
    fake = tree / "fake-rsync"
    fake.write_text(
        "#!/bin/sh\necho 'rsync: [receiver] mkstemp \"/x\" failed: Permission denied (13)' >&2\nexit 23\n"
    )
    fake.chmod(0o755)
    manager.rsync = jobs_module.RsyncInfo(path=str(fake), version="3.2.7", protocol=31)
    job = await manager.add_transfer([str(tree / "src/album")], str(tree / "dst"))
    await wait_for(manager, job)
    assert job.status == JobStatus.FAILED
    assert job.error is not None
    assert job.error.startswith("Some files could not be transferred")
    assert "Permission denied" in job.error
    assert manager.logs[job.id]


async def test_start_resumes_every_paused_transfer(manager: JobManager, tmp_path: Path):
    make_tree(tmp_path / "big", {"blob.bin": b"\0" * 3_000_000})
    (tmp_path / "out").mkdir()
    job = await manager.add_transfer([str(tmp_path / "big")], str(tmp_path / "out"), {"bwlimit": 500})
    await wait_for(manager, job, lambda j: j.status == JobStatus.RUNNING)
    manager.pause_job(job.id)
    manager.start_queue()
    assert job.status == JobStatus.RUNNING
    await manager.cancel_job(job.id)


async def test_file_states(manager: JobManager, tree: Path):
    make_tree(tree / "dst/album", {"one.txt": "one"})
    # Same size and date: rsync leaves one.txt alone
    import os

    stat = (tree / "src/album/one.txt").stat()
    os.utime(tree / "dst/album/one.txt", (stat.st_atime, stat.st_mtime))
    job = await manager.add_transfer([str(tree / "src/album")], str(tree / "dst"))
    await wait_for(manager, job)
    view = manager.file_states(job.id)
    states = {f["path"]: f["state"] for f in view["files"]}
    assert view["total"] == 3 and not view["truncated"]
    assert states == {"album/deep/ñandú b.txt": "done", "album/one.txt": "uptodate", "album/two.bin": "done"}
    assert manager.file_states(job.id, offset=1, limit=1)["files"][0]["path"] == "album/two.bin"


async def test_new_transfer_does_not_resume_a_paused_one(manager: JobManager, tree: Path, tmp_path: Path):
    make_tree(tmp_path / "big", {"blob.bin": b"\0" * 3_000_000})
    (tmp_path / "out").mkdir()
    manager.settings.update({"concurrency": 2})
    slow = await manager.add_transfer([str(tmp_path / "big")], str(tmp_path / "out"), {"bwlimit": 500})
    await wait_for(manager, slow, lambda j: j.status == JobStatus.RUNNING)
    manager.pause_job(slow.id)
    quick = await manager.add_transfer([str(tree / "src/single.txt")], str(tree / "dst"))
    await wait_for(manager, quick)
    assert slow.status == JobStatus.PAUSED
    await manager.cancel_job(slow.id)


async def test_existing_files_wait_for_a_decision(manager: JobManager, tree: Path):
    manager.settings.update({"conflict": "ask"})
    make_tree(tree / "dst/album", {"one.txt": "kept"})
    job = await manager.add_transfer([str(tree / "src/album")], str(tree / "dst"))
    await wait_for(manager, job, lambda j: j.status == JobStatus.CONFLICT)
    assert job.conflict_count == 1
    assert job.conflicts[0].path == "album/one.txt"
    assert job.conflicts[0].existing_size == 4 and job.conflicts[0].incoming_size == 3
    assert manager.busy()
    with pytest.raises(ManagerError):
        manager.verify_job(job.id)
    manager.resolve_conflict(job.id, "skip", remember=True)
    assert job.conflicts == []
    await wait_for(manager, job)
    assert job.status == JobStatus.COMPLETED
    assert (tree / "dst/album/one.txt").read_text() == "kept"
    assert (tree / "dst/album/two.bin").exists()
    # Remembered for the next transfers
    assert manager.settings.current.conflict == "skip"
    with pytest.raises(ManagerError) as err:
        manager.resolve_conflict(job.id, "overwrite")
    assert err.value.code == "no_conflict"


async def test_ask_copies_right_away_when_nothing_exists(manager: JobManager, tree: Path):
    manager.settings.update({"conflict": "ask"})
    job = await manager.add_transfer([str(tree / "src/album")], str(tree / "dst"))
    await wait_for(manager, job)
    assert job.status == JobStatus.COMPLETED
    assert job.options.conflict == "overwrite"


async def test_cancel_while_waiting_for_a_decision(manager: JobManager, tree: Path):
    manager.settings.update({"conflict": "ask"})
    make_tree(tree / "dst", {"single.txt": "old"})
    job = await manager.add_transfer([str(tree / "src/single.txt")], str(tree / "dst"))
    await wait_for(manager, job, lambda j: j.status == JobStatus.CONFLICT)
    await manager.cancel_job(job.id)
    assert job.status == JobStatus.CANCELED
    assert not manager.busy()


async def test_skip_the_file_being_copied(manager: JobManager, tmp_path: Path):
    # A name with rsync wildcards must be skipped literally
    make_tree(
        tmp_path / "big",
        {"a[1]*.bin": b"\0" * 1_500_000, "b.bin": b"\0" * 300_000, "c.bin": b"\0" * 300_000},
    )
    (tmp_path / "out").mkdir()
    job = await manager.add_transfer([str(tmp_path / "big")], str(tmp_path / "out"), {"bwlimit": 500})
    await wait_for(
        manager, job, lambda j: j.progress.current == "big/a[1]*.bin" and j.progress.bytes_done > 0
    )
    await manager.skip_file(job.id)
    assert job.skipped == ["big/a[1]*.bin"]
    await wait_for(manager, job, timeout=30)
    assert job.status == JobStatus.COMPLETED, job.error
    assert not (tmp_path / "out/big/a[1]*.bin").exists()
    assert (tmp_path / "out/big/b.bin").stat().st_size == 300_000
    assert (tmp_path / "out/big/c.bin").exists()
    states = {f["path"]: f["state"] for f in manager.file_states(job.id)["files"]}
    assert states == {"big/a[1]*.bin": "skipped", "big/b.bin": "done", "big/c.bin": "done"}
    assert any("--exclude=/big/a\\[1]\\*.bin" in part for part in manager.command(job))
    # Running it again copies what was skipped
    manager.retry_job(job.id)
    assert job.skipped == []
    await wait_for(manager, job, lambda j: j.status not in (JobStatus.SCANNING,))
    await wait_for(manager, job, timeout=30)
    assert (tmp_path / "out/big/a[1]*.bin").stat().st_size == 1_500_000


async def test_verify_compares_contents(manager: JobManager, tree: Path):
    job = await manager.add_transfer([str(tree / "src/album")], str(tree / "dst"))
    await wait_for(manager, job)
    manager.verify_job(job.id)
    await wait_for(manager, job, lambda j: j.verify != "running")
    assert job.verify == "ok", job.verify_detail
    # Same size and date, different bytes: only a content check notices
    copied = tree / "dst/album/one.txt"
    stat = copied.stat()
    copied.write_text("ONE")
    os.utime(copied, (stat.st_atime, stat.st_mtime))
    manager.verify_job(job.id)
    await wait_for(manager, job, lambda j: j.verify != "running")
    assert job.verify == "mismatch"
    assert "album/one.txt" in (job.verify_detail or "")
    # Nothing was copied by the check
    assert copied.read_text() == "ONE"


async def test_moves_cannot_be_verified(manager: JobManager, tree: Path):
    job = await manager.add_transfer([str(tree / "src/single.txt")], str(tree / "dst"), {"mode": "move"})
    await wait_for(manager, job)
    with pytest.raises(ManagerError) as err:
        manager.verify_job(job.id)
    assert err.value.code == "cannot_verify_move"


async def test_progress_of_the_file_in_flight(manager: JobManager, tmp_path: Path):
    make_tree(tmp_path / "big", {"a.bin": b"\0" * 400_000, "b.bin": b"\0" * 1_200_000})
    (tmp_path / "out").mkdir()
    job = await manager.add_transfer([str(tmp_path / "big")], str(tmp_path / "out"), {"bwlimit": 500})
    await wait_for(
        manager, job, lambda j: j.progress.current == "big/b.bin" and j.progress.current_bytes > 0, timeout=30
    )
    assert job.progress.current_size == 1_200_000
    # The first file is not counted as progress of the second one
    assert job.progress.current_bytes < job.progress.bytes_done
    await manager.cancel_job(job.id)
