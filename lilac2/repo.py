import subprocess
import os

class Repo:
  def __init__(self, config):
    self.myaddress = config.get('lilac', 'email')
    self.repodir = os.path.expanduser(
      config.get('repository', 'repodir'))

  def find_maintainer(self, file='*'):
    me = self.myaddress

    cmd = [
      "git", "log", "--format=%H %an <%ae>", "--", file,
    ]
    p = subprocess.Popen(
      cmd, stdout=subprocess.PIPE, universal_newlines=True)

    try:
      while True:
        line = p.stdout.readline()
        commit, author = line.rstrip().split(None, 1)
        if me not in author:
          return author
    finally:
      p.terminate()
