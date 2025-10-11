import os
import sys

from ..cmd import git_pull_override, run_cmd

def main():
  cmd = ['git', 'reset', '--hard', 'origin/master']
  run_cmd(cmd)
  git_pull_override()

if __name__ == '__main__':
  wd = sys.argv[1]
  os.chdir(wd)
