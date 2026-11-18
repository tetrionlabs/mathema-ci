# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tetrion Ltd
"""Replacing a file whole, so a reader sees its old bytes or its new ones
and never a part: the data goes to a temporary file beside it, which then
takes the file's place in one rename."""
from __future__ import annotations

import contextlib
import os
import stat
import tempfile

__all__ = ["atomic_write"]


def _new_file_mode() -> int:
    """Intent:
        The mode `open` gives a new file under the current umask.
    """
    umask = os.umask(0)
    os.umask(umask)
    return 0o666 & ~umask


def atomic_write(path: str | os.PathLike, data: str | bytes) -> None:
    """Write `data` (text as UTF-8, with no newline translation) to `path`,
    or for a link to the file it points to, replacing it whole. An
    existing file keeps its mode; a new one gets the mode the umask
    gives. On any failure the file is left as it was and the temporary
    file is removed."""
    target = os.path.realpath(path)
    try:
        mode = stat.S_IMODE(os.stat(target).st_mode)
    except FileNotFoundError:
        mode = _new_file_mode()
    payload = data.encode("utf-8") if isinstance(data, str) else data
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target),
                               prefix="." + os.path.basename(target) + ".")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
        os.chmod(tmp, mode)
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise
