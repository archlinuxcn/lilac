import logging
import shutil
import re
import os
import subprocess
import traceback
from typing import Tuple, Optional

from myutils import at_dir

from .cmd import run_cmd, git_pull, git_push
from .pkgbuild import (
  add_into_array, add_depends, add_makedepends,
  edit_file,
  obtain_array, obtain_depends, obtain_makedepends, obtain_optdepends,
)
from . import const
from .const import _G

git_push, add_into_array, add_depends, add_makedepends
obtain_array, obtain_depends, obtain_makedepends, obtain_optdepends

logger = logging.getLogger(__name__)

def vcs_update() -> None:
  # clean up the old source tree
  shutil.rmtree('src', ignore_errors=True)
  run_cmd(['makepkg', '-od'], use_pty=True)

def get_pkgver_and_pkgrel(
) -> Tuple[Optional[str], Optional[float]]:
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

def update_pkgver_and_pkgrel(
  newver: str, *, updpkgsums: bool = True) -> None:

  pkgver, pkgrel = get_pkgver_and_pkgrel()
  assert pkgver is not None and pkgrel is not None

  for line in edit_file('PKGBUILD'):
    if line.startswith('pkgver=') and pkgver != newver:
        line = f'pkgver={newver}'
    elif line.startswith('pkgrel='):
      if pkgver != newver:
        line = 'pkgrel=1'
      else:
        line = f'pkgrel={int(pkgrel)+1}'

    print(line)

  if updpkgsums:
    run_cmd(["updpkgsums"])

def update_pkgrel(rel=None):
  with open('PKGBUILD') as f:
    pkgbuild = f.read()

  def replacer(m):
    nonlocal rel
    if rel is None:
      rel = int(float(m.group(1))) + 1
    return str(rel)

  pkgbuild = re.sub(r'''(?<=^pkgrel=)['"]?([\d.]+)['"]?''', replacer, pkgbuild, count=1, flags=re.MULTILINE)
  with open('PKGBUILD', 'w') as f:
    f.write(pkgbuild)
  logger.info('pkgrel updated to %s', rel)

def pypi_pre_build(depends=None, python2=False, pypi_name=None, arch=None,
                   makedepends=None, depends_setuptools=True,
                   provides=None, check=None,
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

  if check is not None:
    if check == 'nose':
      pkgbuild = pkgbuild.replace(
        '\nsource=',
        "\ncheckdepends=('python-nose')\nsource=",
      )
    else:
      raise ValueError(f'check={check} not recognized')

    pkgbuild = pkgbuild.replace(
      '# vim:set sw=2 et:',
      '''\
check() {
  cd $pkgname-$pkgver
  python -m unittest discover tests
}

# vim:set sw=2 et:''')

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

def git_add_files(files, *, force=False):
  if isinstance(files, str):
    files = [files]
  try:
    if force:
      run_cmd(['git', 'add', '-f', '--'] + files)
    else:
      run_cmd(['git', 'add', '--'] + files)
  except subprocess.CalledProcessError:
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

class AurDownloadError(Exception):
  def __init__(self, pkgname):
    self.pkgname = pkgname

def _update_aur_repo_real(pkgname: str) -> None:
  aurpath = const.AUR_REPO_DIR / pkgname
  if not os.path.isdir(aurpath):
    logger.info('cloning AUR repo: %s', aurpath)
    with at_dir(const.AUR_REPO_DIR):
      run_cmd(['git', 'clone', 'aur@aur.archlinux.org:%s.git' % pkgname])
  else:
    with at_dir(aurpath):
      git_reset_hard()
      git_pull()

  logger.info('copying files to AUR repo: %s', aurpath)
  files = run_cmd(['git', 'ls-files']).splitlines()
  for f in files:
    if f in const.SPECIAL_FILES:
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
    run_cmd(['bash', '-c', 'git diff-index --quiet HEAD || git commit -m "update by lilac"'])
    run_cmd(['git', 'push'])

def update_aur_repo() -> None:
  pkgbase = _G.mod.pkgbase
  try:
    _update_aur_repo_real(pkgbase)
  except subprocess.CalledProcessError as e:
    tb = traceback.format_exc()
    _G.repo.send_error_report(
      pkgbase,
      exc = (e, tb),
      subject = '[lilac] 提交软件包 %s 到 AUR 时出错',
    )

