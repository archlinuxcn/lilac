from __future__ import annotations

import logging
import shutil
import re
import os
import subprocess
import traceback
from typing import Dict, List, Union
from typing import Tuple, Optional, Iterable, Iterator
import fileinput
import tempfile
from pathlib import Path
from types import SimpleNamespace
import tarfile
import io

import requests
import pyalpm

from myutils import at_dir
from htmlutils import parse_document_from_requests

from .cmd import run_cmd, git_pull, git_push, git_reset_hard
from . import const
from .const import _G, SPECIAL_FILES
from .typing import PkgRel

git_push

logger = logging.getLogger(__name__)

_g = SimpleNamespace()
UserAgent = 'lilac/0.2b (package auto-build bot, by lilydjwg)'

s = requests.Session()
s.headers['User-Agent'] = UserAgent

def _unquote_item(s: str) -> Optional[str]:
  """
  unquote string
  :param s:
  :return:
  """
  m = re.search(r'''[ \t'"]*([^ '"]+)[ \t'"]*''', s)
  if m is not None:
    return m.group(1)
  else:
    return None

def _add_into_array(line: str, values: Iterable[str]) -> str:
  """
  add entries into a shell array ("(...)")
  :param line: the shell array (in string)
  :param values: the values to be added
  :return: the processed shell array
  """
  l = line.find('(')
  r = line.rfind(')')
  if r != -1:
    line_l, line_m, line_r = line[:l+1], line[l+1:r], line[r:]
  else:
    line_l, line_m, line_r = line[:l+1], line[l+1:], ''
  arr = {_unquote_item(x) for x in line_m.split(' ')}.union(values)
  arr_nonone = [i for i in arr if i is not None]
  arr_nonone.sort()
  arr_elems_str = "'{}'".format("' '".join(arr_nonone))
  line = line_l + arr_elems_str + line_r
  return line

def add_into_array(which: str, extra_deps: Iterable[str]) -> None:
  """
  add entries into PKGBUILD's array
  :param which: which field in PKGBUILD to add to
  :param extra_deps: the entries
  :return:
  """
  field_appeared = False

  pattern = re.compile(r'\s*' + re.escape(which) + r'=')
  for line in edit_file('PKGBUILD'):
    if pattern.match(line):
      line = _add_into_array(line, extra_deps)
      field_appeared = True
    print(line)

  if not field_appeared:
    with open('PKGBUILD', 'a') as f:
      line = f'{which}=()'
      line = _add_into_array(line, extra_deps)
      f.write(line + '\n')

def add_arch(extra_arches: Iterable[str]) -> None:
  """
  Add architectures to PKGBUILD
  :param extra_arches:
  :return:
  """
  add_into_array('arch', extra_arches)

def add_depends(extra_deps: Iterable[str]) -> None:
  """
  Add dependencies to PKGBUILD
  :param extra_deps:
  :return:
  """
  add_into_array('depends', extra_deps)

def add_makedepends(extra_deps: Iterable[str]) -> None:
  """
  Add build dependencies to PKGBUILD
  :param extra_deps:
  :return:
  """
  add_into_array('makedepends', extra_deps)

def edit_file(filename: str) -> Iterator[str]:
  """
  open a file as an iterator
  :param filename: name of the file
  :return: iterator of lines
  """
  with fileinput.input(files=(filename,), inplace=True) as f:
    for line in f:
      yield line.rstrip('\n')

def obtain_array(name: str) -> Optional[List[str]]:
  """
  Parses the PKGBUILD for an array with a specific name
  Works by calling bash to source PKGBUILD, writing the array to a temporary file, and reading from the file.
  :param name: the name of the variable
  :return: a list of string, if parse succeeded, None otherwise
  """
  with tempfile.NamedTemporaryFile() as output_file:
    command_write_array_out = """printf "%s\\0" "${{{}[@]}}" > {}""" \
        .format(name, output_file.name)
    command_export_array = ['bash', '-c', "source PKGBUILD && {}".format(
      command_write_array_out)]
    subprocess.run(command_export_array, stderr=subprocess.PIPE,
                   check=True)
    res = output_file.read().decode()
    if res == '\0':
      return None
    variable = res.split('\0')[:-1]
    return variable

def obtain_depends() -> Optional[List[str]]:
  """
  gets the 'depends' field of the PKGBUILD
  :return: list of 'depends'
  """
  return obtain_array('depends')

def obtain_makedepends() -> Optional[List[str]]:
  """
  gets the 'makedepends' field of the PKGBUILD
  :return: list of 'makedepends'
  """
  return obtain_array('makedepends')

def obtain_optdepends(
  parse_dict: bool=True
) -> Optional[Union[Dict[str, str], List[str]]]:
  """
  gets the 'optdepends' field of the PKGBUILD
  :param parse_dict: whether to parse the descriptions of optdepends into a dict
  :return: dict from optdepends to descriptions or list of unparsed optdepends
  """
  obtained_array = obtain_array('optdepends')
  if not obtained_array:
    return obtained_array
  if parse_dict:
    return {pkg.strip(): desc.strip() for (pkg, desc) in
            (item.split(':', 1) for item in obtained_array)}
  else:
    return obtained_array

def vcs_update() -> None:
  """
  update the vcs repo by removing 'src' and using makepkg to repull it
  :return:
  """
  # clean up the old source tree
  shutil.rmtree('src', ignore_errors=True)
  run_cmd(['makepkg', '-od', '--noprepare'], use_pty=True)

def get_pkgver_and_pkgrel(
) -> Tuple[Optional[str], Optional[PkgRel]]:
  pkgrel = None
  pkgver = None
  with open('PKGBUILD') as f:
    for l in f:
      if l.startswith('pkgrel='):
        pkgrel = l.rstrip().split('=', 1)[-1].strip('\'"')
        try:
          pkgrel = int(pkgrel) # type: ignore
        except (ValueError, TypeError):
          pass
      elif l.startswith('pkgver='):
        pkgver = l.rstrip().split('=', 1)[-1]

  return pkgver, pkgrel

def _next_pkgrel(rel: PkgRel) -> int:
  """
  bump pkgrel
  :param rel: the current pkgrel
  :return: updated pkgrel
  """
  if isinstance(rel, int):
    return rel + 1

  first_segment = rel.split('.')[0]
  return int(first_segment) + 1

def update_pkgver_and_pkgrel(
  newver: str, *, updpkgsums: bool = True) -> None:
  """
  update pkgver and pkgrel of a PKGBUILD script
  :param newver: the new pkgver
  :param updpkgsums: whether to update the checksum of files
  :return:
  """

  pkgver, pkgrel = get_pkgver_and_pkgrel()
  assert pkgver is not None and pkgrel is not None

  for line in edit_file('PKGBUILD'):
    if line.startswith('pkgver=') and pkgver != newver:
        line = f'pkgver={newver}'
    elif line.startswith('pkgrel='):
      if pkgver != newver:
        line = 'pkgrel=1'
      else:
        line = f'pkgrel={_next_pkgrel(pkgrel)}'

    print(line)

  if updpkgsums:
    run_cmd(["updpkgsums"])

def update_pkgrel(
  rel: Optional[PkgRel] = None,
) -> None:
  """
  update pkgrel of a PKGBUILD
  :param rel: new pkgrel, set to None if you just want to bump it
  :return:
  """
  with open('PKGBUILD') as f:
    pkgbuild = f.read()

  def replacer(m):
    nonlocal rel
    if rel is None:
      rel = _next_pkgrel(m.group(1))
    return str(rel)

  pkgbuild = re.sub(r'''(?<=^pkgrel=)['"]?([\d.]+)['"]?''', replacer, pkgbuild, count=1, flags=re.MULTILINE)
  with open('PKGBUILD', 'w') as f:
    f.write(pkgbuild)
  logger.info('pkgrel updated to %s', rel)

def pypi_pre_build(
  depends: Optional[List[str]] = None,
  python2: bool = False,
  pypi_name: Optional[str] = None,
  arch: Optional[Iterable[str]] = None,
  makedepends: Optional[List[str]] = None,
  depends_setuptools: bool = True,
  provides: Optional[Iterable[str]] = None,
  check: Optional[str] = None, # TODO 3.8: use Literal
  optdepends: Optional[List[str]] = None,
  license: Optional[str] = None,
) -> None:
  """
  pre build hook for pypi based packages
  :param depends: dependencies of this package
  :param python2: whether this is a python2 package/module
  :param pypi_name: the pypi name of this package
  :param arch: the architectures it supports
  :param makedepends: build dependencies
  :param depends_setuptools: whether this package depends on 'python-setuptools'
  :param provides: the packages that this package provides
  :param check: checkdepends of this package
  :param optdepends: optional dependencies of this package
  :param license: the license type of this package
  :return:
  """
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
    update_pkgrel()

def pypi_post_build() -> None:
  """
  post build hook of pypi based packages, updates the pkgbuild
  :return:
  """
  git_add_files('PKGBUILD')
  git_commit()

def git_add_files(
  files: Union[str, List[str]], *, force: bool = False,
) -> None:
  """
  Track specified files in git repo
  :param files: files to be tracked
  :param force: whether to use the -f flag
  :return:
  """
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

def git_commit(*, check_status: bool = True) -> None:
  """
  Commit a repo
  :param check_status: whether to check if there are any untracked files in the current directory
  refuses to commit if there are any
  :return:
  """
  if check_status:
    ret = [x for x in
           run_cmd(["git", "status", "-s", "."]).splitlines()
           if x.split(None, 1)[0] != '??']
    if not ret:
      return

  run_cmd(['git', 'commit', '-m', 'auto update for package %s' % (
    os.path.split(os.getcwd())[1])])

class AurDownloadError(Exception):
  def __init__(self, pkgname: str) -> None:
    self.pkgname = pkgname

def _update_aur_repo_real(pkgname: str) -> None:
  """
  updates the aur repo of a specific package
  :param pkgname: name of the package
  :return:
  """
  aurpath = const.AUR_REPO_DIR / pkgname
  if not aurpath.is_dir():
    logger.info('cloning AUR repo: %s', aurpath)
    with at_dir(const.AUR_REPO_DIR):
      run_cmd(['git', 'clone', f'aur@aur.archlinux.org:{pkgname}.git'])
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
  """
  updates the aur repo
  :return:
  """
  pkgbase = _G.mod.pkgbase
  try:
    _update_aur_repo_real(pkgbase)
  except subprocess.CalledProcessError as e:
    tb = traceback.format_exc()
    _G.repo.send_error_report(
      _G.mod,
      exc = (e, tb),
      subject = '提交软件包 %s 到 AUR 时出错',
    )

def git_pkgbuild_commit() -> None:
  """
  track and commit the PKGBUILD file in current dir
  :return:
  """
  git_add_files('PKGBUILD')
  git_commit()

def _prepend_self_path() -> None:
  """
  adds this dir to the PATH environment variable
  :return:
  """
  mydir = Path(__file__).resolve().parent.parent
  path = os.environ['PATH']
  os.environ['PATH'] = str(mydir / path)

def single_main(build_prefix: str = 'makepkg') -> None:
  """
  build a single package located at this directory
  :param build_prefix: see call_build_cmd
  :return:
  """
  from nicelogger import enable_pretty_logging
  from . import lilacpy
  from .building import lilac_build

  _prepend_self_path()
  enable_pretty_logging('DEBUG')
  with lilacpy.load_lilac(Path('.')) as mod:
    lilac_build(
      mod, None,
      build_prefix = build_prefix,
      accept_noupdate = True,
    )

def clean_directory() -> List[str]:
  """
  unlink all files in the current directory
  :return: list of all unlinked files
  """
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

def _try_aur_url(name: str) -> bytes:
  """
  download an aur tarball
  :param name: name of the aur package
  :return:
  """
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

def _download_aur_pkgbuild(name: str) -> List[str]:
  """
  downloads the PKGBUILD of an aur pakcage
  :param name: name of the aur package
  :return:
  """
  content = io.BytesIO(_try_aur_url(name))
  files = []
  with tarfile.open(
    name=name+".tar.gz", mode="r:gz", fileobj=content
  ) as tarf:
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

def git_rm_files(files: List[str]) -> None:
  """
  remove files from git stage
  :param files: the files to be removed
  :return:
  """
  if files:
    run_cmd(['git', 'rm', '--cached', '--'] + files)

def aur_pre_build(
  name: Optional[str] = None, *, do_vcs_update: Optional[bool] = None,
) -> None:
  """
  aur package pre build hook, update vcs and PKGBUILD script
  :param name: name of the aur package
  :param do_vcs_update: whether to update vcs repo
  :return:
  """
  if os.path.exists('PKGBUILD'):
    pkgver, pkgrel = get_pkgver_and_pkgrel()
  else:
    pkgver = None

  _g.aur_pre_files = clean_directory()
  if name is None:
    name = os.path.basename(os.getcwd())
  _g.aur_building_files = _download_aur_pkgbuild(name)

  aur_pkgver, aur_pkgrel = get_pkgver_and_pkgrel()
  if pkgver and pkgver == aur_pkgver:
    # change to larger pkgrel
    if pyalpm.vercmp(f'1-{pkgrel}', f'1-{aur_pkgrel}') > 0:
      update_pkgrel(pkgrel)

  if do_vcs_update is None:
    do_vcs_update = name.endswith(('-git', '-hg', '-svn', '-bzr'))

  if do_vcs_update:
    vcs_update()
    # recheck after sync, because AUR pkgver may lag behind
    new_pkgver, new_pkgrel = get_pkgver_and_pkgrel()
    if pkgver and pkgver == new_pkgver:
      if pyalpm.vercmp(f'1-{pkgrel}', f'1-{new_pkgrel}') > 0:
        update_pkgrel(pkgrel)

def aur_post_build() -> None:
  """
  aur package post build hook, commits the updated PKGBUILD script
  :return:
  """
  git_rm_files(_g.aur_pre_files)
  git_add_files(_g.aur_building_files, force=True)
  output = run_cmd(["git", "status", "-s", "."]).strip()
  if output:
    git_commit()
  del _g.aur_pre_files, _g.aur_building_files

def download_official_pkgbuild(name: str) -> List[str]:
  """
  downloads the PKGBUILD script of a package in official repo
  :param name: name of the package
  :return: list of PKGBUILDs
  """
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

