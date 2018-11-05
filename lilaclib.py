from subprocess import CalledProcessError
import os
import logging
from types import SimpleNamespace
from io import BytesIO
import tarfile
from pathlib import Path
from typing import Iterable, Optional, List

import requests

from nicelogger import enable_pretty_logging
from htmlutils import parse_document_from_requests
from myutils import at_dir

from lilac2 import lilacpy
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
  AurDownloadError,
  update_aur_repo,
)
from lilac2.const import SPECIAL_FILES
from lilac2.typing import LilacMod
from lilac2.packages import Dependency
git_push, add_into_array, add_depends, add_makedepends
git_pull, git_reset_hard
edit_file, update_pkgver_and_pkgrel
obtain_array, obtain_depends, obtain_makedepends, obtain_optdepends
pypi_pre_build, pypi_post_build
at_dir, update_aur_repo

UserAgent = 'lilac/0.2a (package auto-build bot, by lilydjwg)'

s = requests.Session()
s.headers['User-Agent'] = UserAgent
logger = logging.getLogger(__name__)
EMPTY_COMMIT = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
_g = SimpleNamespace()
build_output = None
PYPI_URL = 'https://pypi.python.org/pypi/%s/json'

class MissingDependencies(Exception):
  def __init__(self, pkgs):
    self.deps = pkgs

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

def git_last_commit(ref=None):
  cmd = ['git', 'log', '-1', '--format=%H']
  if ref:
    cmd.append(ref)
  return run_cmd(cmd).strip()

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

def lilac_build(mod: LilacMod, build_prefix: Optional[str] = None,
                oldver: Optional[str] = None, newver: Optional[str] = None,
                accept_noupdate: bool = False,
                depends: Iterable[Dependency] = (),
                bindmounts: Iterable[str] = (),
               ) -> None:
  run_cmd(["sh", "-c", "rm -f -- *.pkg.tar.xz *.pkg.tar.xz.sig *.src.tar.gz"])
  success = False

  global build_output
  # reset in case no one cleans it up
  build_output = None

  try:
    if not hasattr(mod, '_G'):
      # fill nvchecker result unless already filled (e.g. by hand)
      mod._G = SimpleNamespace(oldver = oldver, newver = newver)
    pre_build = getattr(mod, 'pre_build', None)
    if pre_build is not None:
      logger.debug('accept_noupdate=%r, oldver=%r, newver=%r', accept_noupdate, oldver, newver)
      pre_build()
    recv_gpg_keys()

    need_build_first = set()
    build_prefix = build_prefix or getattr(
      mod, 'build_prefix', 'extra-x86_64')
    depend_packages = []

    for x in depends:
      p = x.resolve()
      if p is None:
        if not x.managed():
          # ignore depends that are not in repo
          continue
        need_build_first.add(x.pkgname)
      else:
        depend_packages.append(p)

    if need_build_first:
      raise MissingDependencies(need_build_first)
    logger.info('depends: %s, resolved: %s', depends, depend_packages)

    makechrootpkg_args: List[str] = []
    if hasattr(mod, 'makechrootpkg_args'):
        makechrootpkg_args = mod.makechrootpkg_args

    call_build_cmd(build_prefix, depend_packages, bindmounts, makechrootpkg_args)
    pkgs = [x for x in os.listdir() if x.endswith('.pkg.tar.xz')]
    if not pkgs:
      raise Exception('no package built')
    post_build = getattr(mod, 'post_build', None)
    if post_build is not None:
      post_build()
    success = True
  finally:
    post_build_always = getattr(mod, 'post_build_always', None)
    if post_build_always is not None:
      post_build_always(success=success)

def call_build_cmd(tag, depends, bindmounts=(), makechrootpkg_args=[]):
  global build_output
  if tag == 'makepkg':
    cmd = ['makepkg', '--holdver']
  else:
    cmd = ['%s-build' % tag, '--']

    if depends:
      for x in depends:
        cmd += ['-I', x]

    if bindmounts:
      for x in bindmounts:
        # Skipping non-existent source paths
        # See --bind in systemd-nspawn(1) for bindmount spec details
        # Note that this check does not consider all possible formats
        source_dir = x.split(':')[0]
        if not os.path.exists(source_dir):
          logger.warn('Invalid bindmount spec %s: source dir does not exist', x)
          continue
        cmd += ['-d', x]

    cmd.extend(makechrootpkg_args)
    cmd.extend(['--', '--holdver'])

  # NOTE that Ctrl-C here may not succeed
  try:
    build_output = run_cmd(cmd, use_pty=True)
  except CalledProcessError:
    build_output = None
    raise

def single_main(build_prefix='makepkg'):
  prepend_self_path()
  enable_pretty_logging('DEBUG')
  with lilacpy.load_lilac(Path('.')) as mod:
    lilac_build(
      mod,
      build_prefix = build_prefix,
      accept_noupdate = True,
    )

def prepend_self_path():
  mydir = os.path.realpath(os.path.dirname(__file__))
  path = os.environ['PATH']
  os.environ['PATH'] = mydir + os.pathsep + path

def recv_gpg_keys():
  run_cmd(['recv_gpg_keys'])

