import logging
import shutil

from .cmd import run_cmd, git_pull, git_push
from .pkgbuild import (
  add_into_array, add_depends, add_makedepends,
  edit_file,
)
git_push, git_pull, add_into_array, add_depends, add_makedepends
edit_file

logger = logging.getLogger(__name__)

def vcs_update():
  # clean up the old source tree
  shutil.rmtree('src', ignore_errors=True)
  run_cmd(['makepkg', '-od'], use_pty=True)

