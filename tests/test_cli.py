from __future__ import annotations

import os
from pathlib import Path

import pytest

from rgcopy import cli, clipboard, instance, integration
from rgcopy.clipboard import ClipboardFiles
from tests.conftest import needs_rsync


@needs_rsync
def test_copy_and_move(tree: Path, capsys: pytest.CaptureFixture[str]):
    assert cli.main(["copy", str(tree / "src/album"), str(tree / "dst")]) == 0
    assert (tree / "dst/album/deep/ñandú b.txt").exists()
    assert "Done:" in capsys.readouterr().out
    (tree / "moved").mkdir()
    assert cli.main(["move", str(tree / "src/single.txt"), str(tree / "moved")]) == 0
    assert (tree / "moved/single.txt").exists() and not (tree / "src/single.txt").exists()


@needs_rsync
def test_copy_errors_exit_non_zero(tree: Path, capsys: pytest.CaptureFixture[str]):
    assert cli.main(["copy", str(tree / "src/single.txt"), str(tree / "src")]) == 2
    assert "already in the destination" in capsys.readouterr().err


@needs_rsync
def test_paste_headless(tree: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        clipboard, "read", lambda: ClipboardFiles("cut", [str(tree / "src/single.txt")], "x11")
    )
    assert cli.main(["paste", "--headless", f"file://{tree / 'dst'}"]) == 0
    assert (tree / "dst/single.txt").exists()
    # A cut moves the files
    assert not (tree / "src/single.txt").exists()


def test_paste_with_empty_clipboard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(clipboard, "read", lambda: ClipboardFiles("copy", [], "wayland"))
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)
    assert cli.main(["paste", str(tmp_path)]) == 1


def test_destination_from_file_manager_env(tmp_path: Path):
    (tmp_path / "folder").mkdir()
    env = {
        "NAUTILUS_SCRIPT_CURRENT_URI": f"file://{tmp_path}",
        "NAUTILUS_SCRIPT_SELECTED_URIS": f"file://{tmp_path}/folder\n",
    }
    assert integration.destination_from_env(env) == f"{tmp_path}/folder"
    env["NAUTILUS_SCRIPT_SELECTED_URIS"] = f"file://{tmp_path}/a\nfile://{tmp_path}/b\n"
    assert integration.destination_from_env(env) == str(tmp_path)
    assert integration.destination_from_env({"NEMO_SCRIPT_CURRENT_URI": "file:///x%20y"}) == "/x y"
    assert integration.destination_from_env({}) is None


def test_integrate_and_uninstall(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(
        integration.shutil,
        "which",
        lambda name: "/usr/bin/rgcopy" if name in ("rgcopy", "nautilus") else None,
    )
    assert cli.main(["integrate"]) == 0
    script = tmp_path / "data/nautilus/scripts" / integration.SCRIPT_NAME
    assert script.exists() and os.access(script, os.X_OK)
    assert "/usr/bin/rgcopy paste" in script.read_text()
    entry = tmp_path / "data/applications" / f"{integration.APP_ID}.desktop"
    assert "Exec=/usr/bin/rgcopy" in entry.read_text()
    accels = (tmp_path / "config/nautilus/scripts-accels").read_text()
    assert accels == f"{integration.DEFAULT_ACCEL} {integration.SCRIPT_NAME}\n"
    # Installing twice does not duplicate the shortcut
    cli.main(["integrate"])
    assert (tmp_path / "config/nautilus/scripts-accels").read_text() == accels
    assert cli.main(["integrate", "--uninstall"]) == 0
    assert not script.exists() and not entry.exists()


def test_instance_file_is_private_and_stale_ones_are_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RGCOPY_RUNTIME_DIR", str(tmp_path))
    me = instance.Instance(port=1, token="t", pid=os.getpid())
    instance.publish(me)
    assert instance.read() == me
    assert (instance.instance_file().stat().st_mode & 0o777) == 0o600
    # Nothing listens on port 1
    assert instance.running() is None
    instance.withdraw(me)
    assert instance.read() is None
