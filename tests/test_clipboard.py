import pytest

from rgcopy import clipboard
from rgcopy.clipboard import gvfs_path, parse_gnome, uri_to_path


def test_gnome_copy():
    files = parse_gnome("copy\nfile:///home/me/Fotos%20de%20viaje\nfile:///home/me/a%C3%B1o.txt", uid=1000)
    assert files.action == "copy"
    assert files.paths == ["/home/me/Fotos de viaje", "/home/me/año.txt"]


def test_gnome_cut_with_crlf_and_trailing_newline():
    files = parse_gnome("cut\r\nfile:///tmp/x\r\n", uid=1000)
    assert files.action == "cut"
    assert files.paths == ["/tmp/x"]


def test_nautilus_45_plain_text_payload():
    files = parse_gnome("x-special/nautilus-clipboard\ncut\nfile:///tmp/y\n", uid=1000)
    assert files.action == "cut"
    assert files.paths == ["/tmp/y"]


def test_uri_list_defaults_to_copy():
    files = parse_gnome("file:///tmp/a\n# comment\nfile:///tmp/b\n", uid=1000)
    assert files.action == "copy"
    assert files.paths == ["/tmp/a", "/tmp/b"]


def test_gvfs_mounts():
    assert gvfs_path("smb://nas/Media/Pelis/x.mkv", uid=1000) == (
        "/run/user/1000/gvfs/smb-share:server=nas,share=media/Pelis/x.mkv"
    )
    assert gvfs_path("sftp://ana@srv:2222/home/ana/f.txt", uid=1000) == (
        "/run/user/1000/gvfs/sftp:host=srv,port=2222,user=ana/home/ana/f.txt"
    )
    assert gvfs_path("sftp://srv/etc", uid=1000) == "/run/user/1000/gvfs/sftp:host=srv/etc"
    assert gvfs_path("smb://nas", uid=1000) is None
    assert uri_to_path("trash:///x") is None
    assert uri_to_path("/plain/path") == "/plain/path"


def test_read_without_a_clipboard_tool(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    assert not clipboard.available()
    files = clipboard.read()
    assert files.source is None and files.paths == []


def test_read_wayland(monkeypatch: pytest.MonkeyPatch, tmp_path):
    target = tmp_path / "copied.txt"
    target.write_text("x")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: f"/usr/bin/{name}")
    outputs = {
        "--list-types": f"{clipboard.GNOME_TARGET}\ntext/plain\n",
        clipboard.GNOME_TARGET: f"cut\nfile://{target}\nfile://{tmp_path}/missing\n",
    }
    monkeypatch.setattr(clipboard, "_run", lambda argv: outputs.get(argv[-1]))
    files = clipboard.read()
    assert files.source == "wayland"
    assert files.action == "cut"
    # Files that no longer exist are dropped
    assert files.paths == [str(target)]
