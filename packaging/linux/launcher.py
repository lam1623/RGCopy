"""Entry point of the packaged app (PyInstaller bundle in /opt/rgcopy)."""

import os
import sys


def _sandbox_available() -> bool:
    """Whether Chromium (Qt WebEngine) can build its sandbox on this machine.

    It needs unprivileged user namespaces: Ubuntu 23.10+ restricts them through AppArmor,
    some kernels switch them off, and root can never use them.
    """

    if os.geteuid() == 0:
        return False
    for path, blocked in (
        ("/proc/sys/kernel/apparmor_restrict_unprivileged_userns", "1"),
        ("/proc/sys/kernel/unprivileged_userns_clone", "0"),
    ):
        try:
            with open(path, encoding="ascii") as fh:
                if fh.read().strip() == blocked:
                    return False
        except OSError:
            continue
    return True


os.environ.setdefault("QT_API", "pyqt6")
# The window only ever shows RGCopy's own local page; without a usable sandbox Chromium would
# refuse to start at all
if not _sandbox_available():
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

from rgcopy.cli import main  # noqa: E402

sys.exit(main())
