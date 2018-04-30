import logging
import shutil

from .cmd import run_cmd, git_pull, git_push
from .pkgbuild import add_into_array, add_depends, add_makedepends
assert git_push
assert git_pull
assert add_into_array
assert add_depends
assert add_makedepends

logger = logging.getLogger(__name__)

def vcs_update():
  # clean up the old source tree
  shutil.rmtree('src', ignore_errors=True)
  run_cmd(['makepkg', '-od'], use_pty=True)

