from __future__ import annotations

import os
import re
import subprocess
import contextlib
from typing import Generator

ansi_escape_re = re.compile(r"\x1B(\[[0-?]*[ -/]*[@-~]|\(B)")


def kill_child_processes() -> None:
    subprocess.run(["kill_children"])


@contextlib.contextmanager
def redirect_output(fd: int) -> Generator[None, None, None]:
    old_stdout = os.dup(1)
    old_stderr = os.dup(2)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    try:
        yield
    finally:
        os.dup2(old_stdout, 1)
        os.dup2(old_stderr, 2)
        os.close(old_stdout)
        os.close(old_stderr)
