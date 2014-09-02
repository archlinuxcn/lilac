import subprocess
from subprocess import CalledProcessError
import os
import logging
import sys

import requests

from htmlutils import parse_document_from_requests
from myutils import msg, msg2
# TODO: move to entry point
from nicelogger import enable_pretty_logging
enable_pretty_logging('DEBUG')

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
  '''clean all PKGBUILD and related files'''
  files = run_cmd(['git', 'ls-files']).splitlines()
  logger.info('clean directory')
  for f in files:
    if f in SPECIAL_FILES:
      continue
    try:
      logger.debug('unlink file %s', f)
      os.unlink(f)
    except FileNotFoundError:
      pass
  return files

def git_rm_files(files):
  run_cmd(['git', 'rm', '--cached', '--'] + files)

def git_add_files(files):
  run_cmd(['git', 'add', '--'] + files)

def git_commit():
  run_cmd(['git', 'commit', '-m', 'auto update for package %s' % (
    os.path.split(os.getcwd())[1])])

def run_cmd(cmd):
  logger.debug('running %r', cmd)
  subprocess.check_output(cmd, stderr=subprocess.STDOUT)
  p = subprocess.Popen(
    cmd,
    stdout = subprocess.PIPE,
    stderr = subprocess.STDOUT,
  )
  out = []
  for l in p.stdout:
    sys.stderr.buffer.write(l)
    out.append(l)

  code = p.wait()
  out = b''.join(out)
  out = out.decode('utf-8', errors='replace')
  if code != 0:
      raise CalledProcessError(code, cmd, out)
  return out
