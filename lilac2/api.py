import logging
import shutil

from .cmd import run_cmd, git_pull, git_push
assert git_push
assert git_pull

logger = logging.getLogger(__name__)

def vcs_update():
  # clean up the old source tree
  shutil.rmtree('src', ignore_errors=True)
  run_cmd(['makepkg', '-od'], use_pty=True)

