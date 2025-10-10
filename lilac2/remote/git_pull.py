import os
import sys

from ..cmd import git_pull_override

if __name__ == '__main__':
  wd = sys.argv[1]
  os.chdir(wd)
  git_pull_override()
