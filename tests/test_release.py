"""Releases are published for __version__ in rgcopy/__init__.py: everything else must follow it."""

import tomllib
from pathlib import Path

import pytest

from rgcopy import __version__

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging" / "linux"


def test_the_version_has_a_single_source() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert "version" not in project
    assert "version" in project["dynamic"]


def test_the_metainfo_lists_the_current_release() -> None:
    # Software centers (GNOME Software, Discover) show this history: every release adds its entry
    metainfo = PACKAGING / "io.github.lam1623.rgcopy.metainfo.xml"
    if not metainfo.exists():
        pytest.skip("packaging/ is only part of a source checkout")
    assert f'<release version="{__version__}"' in metainfo.read_text(encoding="utf-8")


def test_every_package_requires_rsync() -> None:
    nfpm = PACKAGING / "nfpm.yaml"
    if not nfpm.exists():
        pytest.skip("packaging/ is only part of a source checkout")
    text = nfpm.read_text(encoding="utf-8")
    for requirement in ("- rsync (>= 3.1)", "- /usr/bin/rsync", "      - rsync\n"):
        assert requirement in text


def test_the_packaged_desktop_entry_matches_the_one_integrate_writes() -> None:
    from rgcopy import integration

    # Same file name: a user's `rgcopy integrate` replaces the package's entry instead of adding one
    assert (PACKAGING / f"{integration.APP_ID}.desktop").exists()
