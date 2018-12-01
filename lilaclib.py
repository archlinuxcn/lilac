import os
import logging
from types import SimpleNamespace
from io import BytesIO
import tarfile

import requests

from htmlutils import parse_document_from_requests
from myutils import at_dir

from lilac2.api import (
  run_cmd, vcs_update,
  git_push, git_pull, git_reset_hard,
  add_into_array, edit_file,
  add_depends, add_makedepends,
  obtain_array, obtain_depends, obtain_makedepends, obtain_optdepends,
  get_pkgver_and_pkgrel,
  update_pkgver_and_pkgrel,
  update_pkgrel,
  pypi_pre_build, pypi_post_build,
  git_add_files, git_commit,
  git_pkgbuild_commit,
  AurDownloadError,
  update_aur_repo,
  single_main,
)
from lilac2.const import SPECIAL_FILES

git_push, add_into_array, add_depends, add_makedepends
git_pull, git_reset_hard
edit_file, update_pkgver_and_pkgrel
obtain_array, obtain_depends, obtain_makedepends, obtain_optdepends
pypi_pre_build, pypi_post_build
at_dir, update_aur_repo, git_pkgbuild_commit
single_main

UserAgent = 'lilac/0.2a (package auto-build bot, by lilydjwg)'

s = requests.Session()
s.headers['User-Agent'] = UserAgent
logger = logging.getLogger(__name__)
EMPTY_COMMIT = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
_g = SimpleNamespace()
PYPI_URL = 'https://pypi.python.org/pypi/%s/json'

def download_official_pkgbuild(name):
  url = 'https://www.archlinux.org/packages/search/json/?name=' + name
  logger.info('download PKGBUILD for %s.', name)
  info = s.get(url).json()
  r = [r for r in info['results'] if r['repo'] != 'testing'][0]
  repo = r['repo']
  arch = r['arch']
  if repo in ('core', 'extra'):
    gitrepo = 'packages'
  else:
    gitrepo = 'community'
  pkgbase = [r['pkgbase'] for r in info['results'] if r['repo'] != 'testing'][0]

  tree_url = 'https://projects.archlinux.org/svntogit/%s.git/tree/repos/%s-%s?h=packages/%s' % (
    gitrepo, repo, arch, pkgbase)
  doc = parse_document_from_requests(tree_url, s)
  blobs = doc.xpath('//div[@class="content"]//td/a[contains(concat(" ", normalize-space(@class), " "), " ls-blob ")]')
  files = [x.text for x in blobs]
  for filename in files:
    blob_url = 'https://projects.archlinux.org/svntogit/%s.git/plain/repos/%s-%s/%s?h=packages/%s' % (
      gitrepo, repo, arch, filename, pkgbase)
    with open(filename, 'wb') as f:
      logger.debug('download file %s.', filename)
      data = s.get(blob_url).content
      f.write(data)
  return files

def try_aur_url(name):
  aur4url = 'https://aur.archlinux.org/cgit/aur.git/snapshot/{name}.tar.gz'
  templates = [aur4url]
  urls = [url.format(first_two=name[:2], name=name) for url in templates]
  for url in urls:
    response = s.get(url)
    if response.status_code == 200:
      logger.debug("downloaded aur tarball '%s' from url '%s'", name, url)
      return response.content
  logger.error("failed to find aur url for '%s'", name)
  raise AurDownloadError(name)

def download_aur_pkgbuild(name):
  content = BytesIO(try_aur_url(name))
  files = []
  with tarfile.open(name=name+".tar.gz", mode="r:gz", fileobj=content) as tarf:
    for tarinfo in tarf:
      basename, remain = os.path.split(tarinfo.name)
      if basename == '':
        continue
      if remain in ('.AURINFO', '.SRCINFO', '.gitignore'):
        continue
      tarinfo.name = remain
      tarf.extract(tarinfo)
      files.append(remain)
  return files

def get_pypi_info(name):
  return s.get(PYPI_URL % name).json()

def pkgrel_changed(revisions, pkgname):
  cmd = ["git", "diff", "-p", revisions, '--', pkgname + '/PKGBUILD']
  r = run_cmd(cmd, silent=True).splitlines()
  return any(x.startswith('+pkgrel=') for x in r)

def clean_directory():
  '''clean all PKGBUILD and related files'''
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
  if files:
    run_cmd(['git', 'rm', '--cached', '--'] + files)

def aur_pre_build(name=None, *, do_vcs_update=True):
  if os.path.exists('PKGBUILD'):
    pkgver, pkgrel = get_pkgver_and_pkgrel()
  else:
    pkgver = None

  _g.aur_pre_files = clean_directory()
  if name is None:
    name = os.path.basename(os.getcwd())
  _g.aur_building_files = download_aur_pkgbuild(name)

  new_pkgver, new_pkgrel = get_pkgver_and_pkgrel()
  if pkgver and pkgver == new_pkgver:
    # change to larger pkgrel
    update_pkgrel(max(pkgrel, new_pkgrel))

  if do_vcs_update and name.endswith(('-git', '-hg', '-svn', '-bzr')):
    vcs_update()
    # recheck after sync, because AUR pkgver may lag behind
    new_pkgver, new_pkgrel = get_pkgver_and_pkgrel()
    if pkgver and pkgver == new_pkgver:
      update_pkgrel(max(pkgrel, new_pkgrel))

def aur_post_build():
  git_rm_files(_g.aur_pre_files)
  git_add_files(_g.aur_building_files, force=True)
  output = run_cmd(["git", "status", "-s", "."]).strip()
  if output:
    git_commit()
  del _g.aur_pre_files, _g.aur_building_files

