import subprocess
import traceback
from subprocess import CalledProcessError
import os
import logging
from types import SimpleNamespace
import re
from io import BytesIO
import tarfile
import shutil

import requests

from nicelogger import enable_pretty_logging
from htmlutils import parse_document_from_requests
from myutils import at_dir

from lilac2 import lilacpy
from lilac2.api import (
  run_cmd, vcs_update,
  git_push, git_pull,
  add_into_array, edit_file,
  add_depends, add_makedepends,
)
git_push, add_into_array, add_depends, add_makedepends

UserAgent = 'lilac/0.2a (package auto-build bot, by lilydjwg)'

s = requests.Session()
s.headers['User-Agent'] = UserAgent
logger = logging.getLogger(__name__)
SPECIAL_FILES = ('package.list', 'lilac.py', '.gitignore')
EMPTY_COMMIT = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
_g = SimpleNamespace()
build_output = None
PYPI_URL = 'https://pypi.python.org/pypi/%s/json'

# to be override
AUR_REPO_DIR = '/tmp'

def send_error_report(name, *, msg=None, exc=None, subject=None):
  # exc_info used as such needs Python 3.5+
  logger.error('%s\n\n%s', subject, msg, exc_info=exc)

class MissingDependencies(Exception):
  def __init__(self, pkgs):
    self.deps = pkgs

class AurDownloadError(Exception):
  def __init__(self, pkgname):
    self.pkgname = pkgname

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

def get_pkgver_and_pkgrel():
  pkgrel = None
  pkgver = None
  with open('PKGBUILD') as f:
    for l in f:
      if l.startswith('pkgrel='):
        pkgrel = float(l.rstrip().split('=', 1)[-1].strip('\'"'))
        if int(pkgrel) == pkgrel:
            pkgrel = int(pkgrel)
      elif l.startswith('pkgver='):
        pkgver = l.rstrip().split('=', 1)[-1]
  return pkgver, pkgrel

def update_pkgrel(rel=None):
  with open('PKGBUILD') as f:
    pkgbuild = f.read()

  def replacer(m):
    nonlocal rel
    if rel is None:
      rel = int(float(m.group(1))) + 1
    return str(rel)

  pkgbuild = re.sub(r'''(?<=^pkgrel=)['"]?([\d.])+['"]?''', replacer, pkgbuild, count=1, flags=re.MULTILINE)
  with open('PKGBUILD', 'w') as f:
    f.write(pkgbuild)
  logger.info('pkgrel updated to %s', rel)

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

def git_add_files(files):
  if isinstance(files, str):
    files = [files]
  try:
    run_cmd(['git', 'add', '--'] + files)
  except CalledProcessError:
    # on error, there may be a partial add, e.g. some files are ignored
    run_cmd(['git', 'reset', '--'] + files)
    raise

def git_commit(*, check_status=True):
  if check_status:
    ret = [x for x in
           run_cmd(["git", "status", "-s", "."]).splitlines()
           if x.split(None, 1)[0] != '??']
    if not ret:
      return

  run_cmd(['git', 'commit', '-m', 'auto update for package %s' % (
    os.path.split(os.getcwd())[1])])

def git_reset_hard():
  run_cmd(['git', 'reset', '--hard'])

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
  git_add_files(_g.aur_building_files)
  output = run_cmd(["git", "status", "-s", "."]).strip()
  if output:
    git_commit()
  del _g.aur_pre_files, _g.aur_building_files

def pypi_pre_build(depends=None, python2=False, pypi_name=None, arch=None,
                   makedepends=None, depends_setuptools=True,
                   provides=None,
                   optdepends=None, license=None,
                  ):
  if os.path.exists('PKGBUILD'):
    pkgver, pkgrel = get_pkgver_and_pkgrel()
  else:
    pkgver = None

  pkgname = os.path.basename(os.getcwd())
  if pypi_name is None:
    pypi_name = pkgname.split('-', 1)[-1]
  pkgbuild = run_cmd(['pypi2pkgbuild', pypi_name], silent=True)

  if depends_setuptools:
    if depends is None:
      depends = ['python-setuptools']
    else:
      depends.append('python-setuptools')
  elif makedepends is None:
    makedepends = ['python-setuptools']
  elif makedepends:
    makedepends.append('python-setuptools')

  pkgbuild = re.sub(r'^pkgname=.*', f'pkgname={pkgname}',
                    pkgbuild, flags=re.MULTILINE)

  if license:
    pkgbuild = re.sub(r'^license=.*', f'license=({license})',
                      pkgbuild, flags=re.MULTILINE)

  if depends:
    pkgbuild = pkgbuild.replace(
      "depends=('python')",
      "depends=('python' %s)" % ' '.join(f"'{x}'" for x in depends))

  if makedepends:
    pkgbuild = pkgbuild.replace(
      '\nsource=',
      '\nmakedepends=(%s)\nsource=' %
      ' '.join("'%s'" % x for x in makedepends))

  if optdepends:
    pkgbuild = pkgbuild.replace(
      '\nsource=',
      '\noptdepends=(%s)\nsource=' %
      ' '.join("'%s'" % x for x in optdepends))

  if provides:
    pkgbuild = pkgbuild.replace(
      '\nsource=',
      '\nprovides=(%s)\nsource=' %
      ' '.join("'%s'" % x for x in provides))

  if python2:
    pkgbuild = re.sub(r'\bpython3?(?!\.)', 'python2', pkgbuild)
  if arch is not None:
    pkgbuild = pkgbuild.replace(
      "arch=('any')",
      "arch=(%s)" % ' '.join("'%s'" % x for x in arch))
  with open('PKGBUILD', 'w') as f:
    f.write(pkgbuild)

  new_pkgver = get_pkgver_and_pkgrel()[0]
  if pkgver and pkgver == new_pkgver:
    # change pkgrel to what specified in PKGBUILD
    update_pkgrel(pkgrel)

def pypi_post_build():
  git_add_files('PKGBUILD')
  git_commit()

def lilac_build(build_prefix=None, oldver=None, newver=None, accept_noupdate=False, depends=(), bindmounts=()):
  with lilacpy.load_lilac() as mod:
    run_cmd(["sh", "-c", "rm -f -- *.pkg.tar.xz *.pkg.tar.xz.sig *.src.tar.gz"])
    success = False

    global build_output
    # reset in case no one cleans it up
    build_output = None

    try:
      if not hasattr(mod, '_G'):
        # fill nvchecker result unless already filled (e.g. by hand)
        mod._G = SimpleNamespace(oldver = oldver, newver = newver)
      if hasattr(mod, 'pre_build'):
        logger.debug('accept_noupdate=%r, oldver=%r, newver=%r', accept_noupdate, oldver, newver)
        mod.pre_build()
      recv_gpg_keys()

      need_build_first = set()
      build_prefix = build_prefix or mod.build_prefix
      depend_packages = []

      for x in depends:
        p = x.resolve()
        if p is None:
          if not p.in_repo():
            # ignore depends that are not in repo
            continue
          need_build_first.add(x.pkgname)
        else:
          depend_packages.append(p)

      if need_build_first:
        raise MissingDependencies(need_build_first)
      logger.info('depends: %s', depend_packages)

      makechrootpkg_args = []
      if hasattr(mod, 'makechrootpkg_args'):
          makechrootpkg_args = mod.makechrootpkg_args

      call_build_cmd(build_prefix, depend_packages, bindmounts, makechrootpkg_args)
      pkgs = [x for x in os.listdir() if x.endswith('.pkg.tar.xz')]
      if not pkgs:
        raise Exception('no package built')
      if hasattr(mod, 'post_build'):
        mod.post_build()
      success = True
    finally:
      if hasattr(mod, 'post_build_always'):
        mod.post_build_always(success=success)

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
        cmd += ['-d', x]

    cmd.extend(makechrootpkg_args)
    cmd.extend(['--', '--holdver'])

  # NOTE that Ctrl-C here may not succeed
  try:
      build_output = run_cmd(cmd, use_pty=True)
  except CalledProcessError as e:
      build_output = e.output
      raise

def single_main(build_prefix='makepkg'):
  prepend_self_path()
  enable_pretty_logging('DEBUG')
  lilac_build(
    build_prefix = build_prefix,
    accept_noupdate = True,
  )

def prepend_self_path():
  mydir = os.path.realpath(os.path.dirname(__file__))
  path = os.environ['PATH']
  os.environ['PATH'] = mydir + os.pathsep + path

def recv_gpg_keys():
  run_cmd(['recv_gpg_keys'])

def _update_aur_repo_real(pkgname):
  aurpath = os.path.join(AUR_REPO_DIR, pkgname)
  if not os.path.isdir(aurpath):
    logger.info('cloning AUR repo: %s', aurpath)
    with at_dir(AUR_REPO_DIR):
      run_cmd(['git', 'clone', 'aur@aur.archlinux.org:%s.git' % pkgname])
  else:
    with at_dir(aurpath):
      git_reset_hard()
      git_pull()

  logger.info('copying files to AUR repo: %s', aurpath)
  files = run_cmd(['git', 'ls-files']).splitlines()
  for f in files:
    if f in SPECIAL_FILES:
      continue
    logger.debug('copying file %s', f)
    shutil.copy(f, aurpath)

  with at_dir(aurpath):
    with open('.SRCINFO', 'wb') as srcinfo:
      subprocess.run(
        ['makepkg', '--printsrcinfo'],
        stdout = srcinfo,
        check = True,
      )
    run_cmd(['git', 'add', '.'])
    run_cmd(['git', 'commit', '-m', 'update by lilac'])
    run_cmd(['git', 'push'])

def update_aur_repo():
  pkgname = os.path.basename(os.getcwd())
  try:
    _update_aur_repo_real(pkgname)
  except CalledProcessError as e:
    tb = traceback.format_exc()
    send_error_report(
      pkgname,
      exc = (e, tb),
      subject = '[lilac] 提交软件包 %s 到 AUR 时出错',
    )

def update_pkgver_and_pkgrel(newver):
  pkgver, pkgrel = get_pkgver_and_pkgrel()

  for line in edit_file('PKGBUILD'):
    if line.startswith('pkgver=') and pkgver != newver:
        line = f'pkgver={newver}'
    elif line.startswith('pkgrel='):
      if pkgver != newver:
        line = 'pkgrel=1'
      else:
        line = f'pkgrel={int(pkgrel)+1}'

    print(line)

  run_cmd(["updpkgsums"])
