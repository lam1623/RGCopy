import os
from pathlib import Path

import pytest

from rgcopy.fs import FileSystem, PathError, scan
from tests.conftest import make_tree


def test_scan_counts_bytes_files_and_dirs(tmp_path: Path):
    make_tree(tmp_path / "a", {"x.txt": "12345", "b/y.bin": b"0" * 10})
    os.symlink(tmp_path / "a" / "x.txt", tmp_path / "a" / "link")
    result = scan([tmp_path / "a", tmp_path / "a" / "x.txt"])
    # Links count as files of 0 bytes: rsync copies the link, not its target
    assert result.total_files == 4
    assert result.total_bytes == 20
    assert result.total_dirs == 2


def test_resolve_stays_inside_roots(tmp_path: Path):
    (tmp_path / "in").mkdir()
    fs = FileSystem([tmp_path / "in"])
    assert fs.resolve(str(tmp_path / "in")) == (tmp_path / "in").resolve()
    with pytest.raises(PathError) as err:
        fs.resolve(str(tmp_path))
    assert err.value.code == "outside_roots"
    with pytest.raises(PathError):
        fs.resolve("relative/path")
    with pytest.raises(PathError) as err:
        fs.resolve(str(tmp_path / "in" / "nope"))
    assert err.value.code == "not_found"


def test_resolve_keeps_symlinks_when_asked(tmp_path: Path):
    (tmp_path / "real").mkdir()
    os.symlink(tmp_path / "real", tmp_path / "link")
    fs = FileSystem([tmp_path])
    assert fs.resolve(str(tmp_path / "link"), follow=False) == tmp_path.resolve() / "link"
    assert fs.resolve(str(tmp_path / "link")) == (tmp_path / "real").resolve()


def test_list_dir(tmp_path: Path):
    make_tree(tmp_path, {"b10.txt": "", "b2.txt": "", ".hidden": "", "dir/x": ""})
    fs = FileSystem([tmp_path])
    listing = fs.list_dir(str(tmp_path))
    assert [e.name for e in listing.entries] == ["dir", "b2.txt", "b10.txt"]
    assert listing.parent is None
    assert ".hidden" in [e.name for e in fs.list_dir(str(tmp_path), show_hidden=True).entries]
