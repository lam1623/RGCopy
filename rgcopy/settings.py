"""User preferences persisted as JSON."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

log = logging.getLogger(__name__)

Conflict = Literal["overwrite", "skip", "update", "backup"]


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Transfers running at the same time
    concurrency: int = Field(1, ge=1, le=4)
    # Start a transfer as soon as it is added (pasting files expects that)
    auto_start: bool = True
    # What to do with files that already exist at the destination
    conflict: Conflict = "overwrite"
    # Compare files by content instead of size and modification time
    checksum: bool = False
    # Keep permissions, owner, group and timestamps (rsync -a)
    preserve: bool = True
    # Bandwidth limit in KiB/s (0: unlimited)
    bwlimit: int = Field(0, ge=0, le=10_000_000)
    # Refuse to start a copy that does not fit in the free space of the destination
    check_space: bool = True
    notify_on_finish: bool = True
    # Desktop app: close the window once every transfer finished without errors
    close_when_done: bool = False
    theme: Literal["system", "dark", "light"] = "light"
    language: Literal["auto", "es", "en"] = "auto"


class SettingsPatch(BaseModel):
    """Partial update; only fields present in the request are applied."""

    model_config = ConfigDict(extra="forbid")

    concurrency: int | None = Field(None, ge=1, le=4)
    auto_start: bool | None = None
    conflict: Conflict | None = None
    checksum: bool | None = None
    preserve: bool | None = None
    bwlimit: int | None = Field(None, ge=0, le=10_000_000)
    check_space: bool | None = None
    notify_on_finish: bool | None = None
    close_when_done: bool | None = None
    theme: Literal["system", "dark", "light"] | None = None
    language: Literal["auto", "es", "en"] | None = None


class SettingsStore:
    """Settings persisted to ``path``; with ``path=None`` they live only in memory."""

    def __init__(self, path: Path | None, initial: Settings | None = None) -> None:
        self.path = path
        self._settings = initial or self._load()

    @property
    def current(self) -> Settings:
        return self._settings

    def _load(self) -> Settings:
        if self.path is None:
            return Settings()
        try:
            return Settings.model_validate_json(self.path.read_text("utf-8"))
        except FileNotFoundError:
            return Settings()
        except (OSError, ValidationError, ValueError) as exc:
            log.warning("Ignoring unreadable settings file %s: %s", self.path, exc)
            return Settings()

    def update(self, patch: dict[str, Any]) -> Settings:
        merged = Settings.model_validate({**self._settings.model_dump(), **patch})
        self._write(merged)
        self._settings = merged
        return merged

    def _write(self, settings: Settings) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".settings-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(settings.model_dump(), fh, indent=2)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
