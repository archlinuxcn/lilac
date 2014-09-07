import subprocess
from subprocess import CalledProcessError
import os
import logging
import sys
import smtplib
import signal

import requests

from htmlutils import parse_document_from_requests
from myutils import msg, msg2
from mailutils import assemble_mail

UserAgent = 'lilac/0.1 (package auto-build bot, by lilydjwg)'

s = requests.Session()
s.headers['User-Agent'] = UserAgent
logger = logging.getLogger(__name__)
SPECIAL_FILES = ('package.list', 'lilac.py')

def download_official_pkgbuild(name):
  url = 'https://www.archlinux.org/packages/search/json/?name=' + name
  logger.info('download PKGBUILD for %s.', name)
  info = s.get(url).json()
  result = info['results'][0]
  repo = result['repo']
  if repo in ('core', 'extra'):
    repo = 'packages'
  else:
    repo = 'community'

  tree_url = 'https://projects.archlinux.org/svntogit/%s.git/tree/trunk?h=packages/%s' % (repo, name)
  doc = parse_document_from_requests(tree_url, s)
  blobs = doc.xpath('//div[@class="content"]//td/a[contains(concat(" ", normalize-space(@class), " "), " ls-blob ")]')
  files = [x.text for x in blobs]
  for filename in files:
    blob_url = 'https://projects.archlinux.org/svntogit/%s.git/plain/trunk/%s?h=packages/%s' % (repo, filename, name)
    with open(filename, 'wb') as f:
      logger.debug('download file %s.', filename)
      data = s.get(blob_url).content
      f.write(data)
  return files

def clean_directory():
  '''clean all PKGBUILD, built packages and related files'''
  files = run_cmd(['git', 'ls-files']).splitlines()
  logger.info('clean directory')
  ret = []
  for f in files:
    if f in SPECIAL_FILES:
      continue
    try:
      logger.debug('unlink file %s', f)
      os.unlink(f)
      ret.append(f)
    except FileNotFoundError:
      pass
  return ret

def git_rm_files(files):
  run_cmd(['git', 'rm', '--cached', '--'] + files)

def git_add_files(files):
  if isinstance(files, str):
    files = [files]
  run_cmd(['git', 'add', '--'] + files)

def git_commit():
  run_cmd(['git', 'commit', '-m', 'auto update for package %s' % (
    os.path.split(os.getcwd())[1])])

def run_cmd(cmd, *, use_pty=False):
  logger.debug('running %r', cmd)
  if use_pty:
    rfd, stdout = os.openpty()
  else:
    stdout = subprocess.PIPE

  exited = False
  def child_exited(signum, sigframe):
    nonlocal exited
    exited = True
  old_hdl = signal.signal(signal.SIGCHLD, child_exited)

  p = subprocess.Popen(cmd, stdout = stdout, stderr = subprocess.STDOUT)
  if not use_pty:
    rfd = p.stdout.fileno()
  out = []
  while not exited:
    try:
      r = os.read(rfd, 4096)
    except InterruptedError:
      continue
    if not r:
      break
    sys.stderr.buffer.write(r)
    out.append(r)

  code = p.wait()
  if old_hdl is not None:
    signal.signal(signal.SIGCHLD, old_hdl)

  out = b''.join(out)
  out = out.decode('utf-8', errors='replace')
  if code != 0:
      raise CalledProcessError(code, cmd, out)
  return out

def find_maintainer(me):
  head = 'HEAD'
  while True:
    commit, author = get_commit_and_email(head)
    if not author.endswith(me):
      return author
    head = commit + '^'

def get_commit_and_email(head):
  cmd = [
    "git", "log", "-1", "--format=%H %an <%ae>", head,
    "--", "PKGBUILD", "lilac.py",
  ]
  commit, author = run_cmd(cmd).rstrip().split(None, 1)
  return commit, author

def sendmail(to, from_, subject, msg):
  s = smtplib.SMTP()
  s.connect()
  msg = assemble_mail(subject, to, from_, text=msg)
  s.send_message(msg)
  s.quit()
