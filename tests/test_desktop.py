from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from rgcopy import desktop, instance
from rgcopy.config import AppConfig
from tests.conftest import needs_rsync


@needs_rsync
def test_second_launch_hands_the_paste_to_the_open_window(tree: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RGCOPY_RUNTIME_DIR", str(tree / "run"))
    config = AppConfig(roots=[tree], data_dir=tree / "data", auth_token="tok", port=desktop._free_port())
    config.desktop = True
    contexts: list = []
    first = desktop.PendingTransfer([str(tree / "src/single.txt")], str(tree / "dst"))
    server, thread = desktop._start_server(config, first, contexts)
    try:
        focused: list[bool] = []
        contexts[0].focus_window = lambda: focused.append(True)
        instance.publish(instance.Instance(port=config.port, token="tok", pid=os.getpid()))
        second = desktop.PendingTransfer([str(tree / "src/album")], str(tree / "dst"), {"conflict": "skip"})
        assert desktop.hand_over(second)
        manager = contexts[0].manager
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not (len(manager.jobs) == 2 and manager.all_done()):
            time.sleep(0.05)
        assert [j.name for j in manager.jobs.values()] == ["single.txt", "album"]
        assert manager.all_done()
        assert list(manager.jobs.values())[1].options.conflict == "skip"
        assert focused == [True]
    finally:
        desktop._stop_server(server, thread)
    # The server is gone: the next launch opens its own window
    assert not desktop.hand_over(None)
