"""Run one rsync transfer with live progress, pause/resume and cancellation."""

from __future__ import annotations

import asyncio
import collections
import contextlib
import os
import signal
import time
from collections.abc import AsyncIterator, Callable
from typing import NamedTuple

from .rsync import Progress, is_file_name, parse_progress_line, popen_kwargs

MAX_LINE = 16384
# Weight of the newest sample in the smoothed speed (higher reacts faster)
SPEED_SMOOTHING = 0.3


class RunResult(NamedTuple):
    returncode: int
    canceled: bool
    log: list[str]


class RsyncRun:
    """A single rsync invocation in its own process group (rsync forks a receiver and a generator)."""

    def __init__(
        self,
        argv: list[str],
        total_bytes: int,
        total_files: int,
        on_progress: Callable[[Progress], None] | None = None,
        log_lines: int = 300,
    ) -> None:
        self.argv = argv
        self.total_bytes = total_bytes
        self.total_files = total_files
        self.on_progress = on_progress
        self.log: collections.deque[str] = collections.deque(maxlen=log_lines)
        self.progress = Progress(total_bytes=total_bytes, total_files=total_files)
        self._proc: asyncio.subprocess.Process | None = None
        self._cancel_requested = False
        self._paused_at: float | None = None
        self._paused_total = 0.0
        self._started_at = 0.0
        # Every file rsync started, in order (the last one is being transferred)
        self.names: list[str] = []
        self._speed: float | None = None

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc else None

    @property
    def paused(self) -> bool:
        return self._paused_at is not None

    def elapsed(self) -> float:
        if not self._started_at:
            return 0.0
        now = self._paused_at or time.monotonic()
        return max(0.0, now - self._started_at - self._paused_total)

    async def run(self) -> RunResult:
        """Start rsync and wait for it. ``OSError`` propagates if it cannot start."""

        self._proc = await asyncio.create_subprocess_exec(
            *self.argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            **popen_kwargs(),
        )
        self._started_at = time.monotonic()
        if self._cancel_requested:
            await self._terminate()  # canceled while the process was starting
        try:
            await asyncio.gather(self._read_progress(), self._read_log())
            returncode = await self._proc.wait()
        except asyncio.CancelledError:
            await self._terminate()
            raise
        return RunResult(returncode, self._cancel_requested, list(self.log))

    def _update(self, line: str) -> None:
        parsed = parse_progress_line(line)
        progress = self.progress
        if parsed is None:
            if is_file_name(line):
                self.names.append(line.strip())
                progress.current = line.strip()
                progress.files_done = min(self.total_files, max(progress.files_done, len(self.names) - 1))
                self._emit()
            return
        progress.bytes_done = max(progress.bytes_done, parsed.bytes_done)
        if parsed.transferred is not None:
            progress.files_done = min(self.total_files, max(progress.files_done, parsed.transferred))
        own = progress.bytes_done / self.total_bytes * 100 if self.total_bytes else 0.0
        # rsync's figure also counts files it skipped; ours is exact for plain copies
        progress.percent = round(min(99.9, max(own, float(parsed.percent))), 2)
        if parsed.speed > 0:
            self._speed = (
                parsed.speed
                if self._speed is None
                else SPEED_SMOOTHING * parsed.speed + (1 - SPEED_SMOOTHING) * self._speed
            )
        progress.speed = round(self._speed, 1) if self._speed else None
        remaining = max(0, self.total_bytes - progress.bytes_done)
        progress.eta_s = round(remaining / self._speed, 1) if self._speed else None
        self._emit()

    def _emit(self) -> None:
        self.progress.elapsed_s = round(self.elapsed(), 1)
        if self.on_progress:
            self.on_progress(self.progress.model_copy())

    async def _read_progress(self) -> None:
        assert self._proc and self._proc.stdout
        async for line in _lines(self._proc.stdout):
            self._update(line)

    async def _read_log(self) -> None:
        assert self._proc and self._proc.stderr
        async for line in _lines(self._proc.stderr):
            if line.strip():
                self.log.append(line.rstrip())

    def _signal(self, sig: signal.Signals) -> None:
        if self._proc is None or self._proc.returncode is not None:
            return
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(self._proc.pid, sig)

    def pause(self) -> None:
        if self._proc is None or self._proc.returncode is not None or self.paused:
            return
        self._signal(signal.SIGSTOP)
        self._paused_at = time.monotonic()
        self.progress.speed = None
        self.progress.eta_s = None
        self._speed = None

    def resume(self) -> None:
        if self._proc is None or not self.paused:
            return
        self._signal(signal.SIGCONT)
        assert self._paused_at is not None
        self._paused_total += time.monotonic() - self._paused_at
        self._paused_at = None

    async def cancel(self) -> None:
        self._cancel_requested = True
        await self._terminate()

    async def _terminate(self, grace: float = 5.0) -> None:
        proc = self._proc
        if proc is None or proc.returncode is not None:
            return
        if self.paused:
            self.resume()  # a stopped process never handles SIGTERM
        self._signal(signal.SIGTERM)
        try:
            await asyncio.wait_for(proc.wait(), grace)
        except TimeoutError:
            self._signal(signal.SIGKILL)
            await proc.wait()


async def _lines(stream: asyncio.StreamReader, max_line: int = MAX_LINE) -> AsyncIterator[str]:
    """Yield decoded lines split on ``\\n`` or ``\\r`` (rsync redraws its progress with ``\\r``)."""

    buffer = b""
    while chunk := await stream.read(65536):
        buffer += chunk.replace(b"\r", b"\n")
        *complete, buffer = buffer.split(b"\n")
        for raw in complete:
            if raw:
                yield raw[:max_line].decode("utf-8", "replace")
        if len(buffer) > max_line:
            buffer = buffer[:max_line]
    if buffer:
        yield buffer[:max_line].decode("utf-8", "replace")
