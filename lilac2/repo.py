import subprocess

def find_maintainer(me, file='*'):
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
