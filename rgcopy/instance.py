"""One desktop window per user: later launches hand their transfer to the running app."""

from __future__ import annotations

import contextlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platformdirs import user_runtime_dir


@dataclass(frozen=True)
class Instance:
    port: int
    token: str
    pid: int

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def instance_file() -> Path:
    env = os.environ.get("RGCOPY_RUNTIME_DIR")
    return Path(env or user_runtime_dir("rgcopy", appauthor=False)) / "instance.json"


def publish(instance: Instance) -> None:
    path = instance_file()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    # The token grants full access to the app: only the user may read it
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"port": instance.port, "token": instance.token, "pid": instance.pid}, fh)
    os.replace(tmp, path)


def withdraw(instance: Instance) -> None:
    current = read()
    if current is not None and current.pid == instance.pid:
        with contextlib.suppress(OSError):
            instance_file().unlink()


def read() -> Instance | None:
    try:
        data = json.loads(instance_file().read_text("utf-8"))
        return Instance(port=int(data["port"]), token=str(data["token"]), pid=int(data["pid"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def call(instance: Instance, method: str, path: str, body: Any = None, timeout: float = 5) -> Any:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        instance.base_url + path,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {instance.token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw) if raw else None


def running() -> Instance | None:
    """The live desktop instance, or None (a stale file from a crashed app is ignored)."""

    instance = read()
    if instance is None:
        return None
    try:
        call(instance, "GET", "/api/system", timeout=2)
    except (OSError, urllib.error.URLError, ValueError):
        return None
    return instance
