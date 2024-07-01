from __future__ import annotations

import logging
import shutil
import re
import os
import subprocess
from typing import Dict, List, Union
from typing import Tuple, Optional, Iterable, Iterator
import fileinput
import tempfile
from pathlib import Path
from types import SimpleNamespace
import tarfile
import io
from contextlib import suppress
from collections.abc import Container
from urllib.parse import quote

import requests

from .vendor.myutils import at_dir
from .vendor.htmlutils import parse_document_from_requests

from .cmd import git_pull, git_push, UNTRUSTED_PREFIX
from .cmd import run_cmd as _run_cmd
from . import const
from .const import _G, SPECIAL_FILES
from .typing import PkgRel, Cmd
from .pypi2pkgbuild import gen_pkgbuild
from . import mediawiki2pkgbuild
from .pkgbuild import get_srcinfo

git_push

logger = logging.getLogger(__name__)

_g = SimpleNamespace()
UserAgent = 'lilac/0.2b (package auto-build bot, by lilydjwg)'

s = requests.Session()
s.headers['User-Agent'] = UserAgent

VCS_SUFFIXES = ('-git', '-hg', '-svn', '-bzr')
AUR_BLACKLIST = {
  'dnrops': "creates packages that install packages into the packager's system",
}

def _unquote_item(s: str) -> Optional[str]:
  m = re.search(r'''[ \t'"]*([^ '"]+)[ \t'"]*''', s)
  if m is not None:
    return m.group(1)
  else:
    return None

def _add_into_array(line: str, values: Iterable[str]) -> str:
  l = line.find('(')
  r = line.rfind(')')
  if r != -1:
    line_l, line_m, line_r = line[:l+1], line[l+1:r], line[r:]
  else:
    line_l, line_m, line_r = line[:l+1], line[l+1:], ''
  arr = {_unquote_item(x) for x in line_m.split(' ')}.union(values)
  arr_nonone = [i for i in arr if i is not None]
  arr_nonone.sort()
  arr_elems_str = '"{}"'.format('" "'.join(arr_nonone))
  line = line_l + arr_elems_str + line_r
  return line

def add_into_array(which: str, extra: Iterable[str]) -> None:
  '''
  Add more values into the ``which`` shell array in the PKGBUILD file
  '''
  field_appeared = False

  pattern = re.compile(r'\s*' + re.escape(which) + r'=')
  for line in edit_file('PKGBUILD'):
    if pattern.match(line):
      line = _add_into_array(line, extra)
      field_appeared = True
    print(line)

  if not field_appeared:
    with open('PKGBUILD', 'a') as f:
      line = f'{which}=()'
      line = _add_into_array(line, extra)
      f.write(line + '\n')

def _build_add_into_array_func(name: str):
  source = f'''
def add_{name}(extra: Iterable[str]) -> None:
  """
  Add more values into the ``{name}`` shell array in the PKGBUILD file
  """
  add_into_array('{name}', extra)
'''

  exec(source, globals(), globals())

_build_add_into_array_func('arch')
_build_add_into_array_func('depends')
_build_add_into_array_func('makedepends')
_build_add_into_array_func('checkdepends')
_build_add_into_array_func('conflicts')
_build_add_into_array_func('replaces')
_build_add_into_array_func('provides')
_build_add_into_array_func('groups')

def edit_file(filename: str) -> Iterator[str]:
  '''Edit the file in a loop, e.g.:

  .. code-block:: python

      for line in edit_file('PKGBUILD'):
        if line.startswith('_name='):
          line = '_name=newname'
        print(line)
  '''
  with fileinput.input(files=(filename,), inplace=True) as f:
    for line in f:
      yield line.rstrip('\n')

def obtain_array(name: str) -> Optional[List[str]]:
  '''
  Obtain an array variable from PKGBUILD.

  Works by calling bash to source PKGBUILD, writing the array to a temporary file, and reading from the file.
  '''
  with tempfile.NamedTemporaryFile(dir='/tmp') as output_file:
    command_write_array_out = """printf "%s\\0" "${{{}[@]}}" > {}""" \
        .format(name, output_file.name)
    extra_binds = ['--bind', output_file.name, output_file.name, '--ro-bind', 'PKGBUILD', '/tmp/PKGBUILD', '--chdir', '/tmp']
    command_export_array = UNTRUSTED_PREFIX + extra_binds + [ # type: ignore
      '/bin/bash', '-c', "source PKGBUILD && {}".format(command_write_array_out)
    ]
    subprocess.run(command_export_array, stderr=subprocess.PIPE,
                   check=True)
    res = output_file.read().decode()
    if res == '\0':
      return None
    variable = res.split('\0')[:-1]
    return variable

def obtain_depends() -> Optional[List[str]]:
  return obtain_array('depends')

def obtain_makedepends() -> Optional[List[str]]:
  return obtain_array('makedepends')

def obtain_optdepends(
  parse_dict: bool=True
) -> Optional[Union[Dict[str, str], List[str]]]:
  obtained_array = obtain_array('optdepends')
  if not obtained_array:
    return obtained_array
  if parse_dict:
    return {pkg.strip(): desc.strip() for (pkg, desc) in
            (item.split(':', 1) if ':' in item else (item, '')
             for item in obtained_array)}
  else:
    return obtained_array

def vcs_update() -> None:
  '''update VCS sources'''
  # clean up the old source tree
  shutil.rmtree('src', ignore_errors=True)
  run_protected(['makepkg', '-od', '--noprepare', '-A'], use_pty=True)

def _is_tmpfs(d: str) -> bool:
  cmd = ['findmnt', '-n', '-o', 'FSTYPE', '--', d]
  p = subprocess.run(cmd, stdout=subprocess.PIPE)
  return p.returncode == 0 and p.stdout == b'tmpfs\n'

def run_protected(cmd: Cmd, **kwargs) -> str:
  '''run a command that sources PKGBUILD and thus is protected by bwrap'''
  # clean up the old source tree
  pwd = os.getcwd()
  basename = os.path.basename(pwd)
  extra_args = [
    '--share-net', '--bind', pwd, f'/tmp/{basename}', '--chdir', f'/tmp/{basename}',
    '--ro-bind', const.mydir / 'gnupg', os.path.expanduser('~/.gnupg'),
  ]
  if _is_tmpfs('/var/lib/archbuild'):
    extra_args.extend(['--tmpfs', f'/tmp/{basename}/src'])
  return _run_cmd(UNTRUSTED_PREFIX + extra_args + # type: ignore
                  cmd, **kwargs)

def run_cmd(cmd: Cmd, **kwargs) -> str:
  if cmd == ['updpkgsums'] or any(
    x.startswith('makepkg ') for x in cmd if isinstance(x, str)
  ):
    return run_protected(cmd, **kwargs)
  else:
    return _run_cmd(cmd, **kwargs)

def get_pkgver_and_pkgrel() -> Tuple[Optional[str], Optional[PkgRel]]:
  pkgrel: Optional[PkgRel] = None
  pkgver = None
  cmd = 'source PKGBUILD && declare -p pkgver pkgrel || :'
  output = run_protected(['/bin/bash', '-c', cmd], silent = True)
  pattern = re.compile('declare -- pkg(ver|rel)="([^"]+)"')
  for line in output.splitlines():
    m = pattern.fullmatch(line)
    if m:
      value = m.group(2)
      if m.group(1) == "rel":
        try:
          pkgrel = int(value)
        except (ValueError, TypeError):
          pkgrel = value
      else:
        pkgver = value

  return pkgver, pkgrel

def _next_pkgrel(rel: PkgRel) -> int:
  if isinstance(rel, int):
    return rel + 1

  first_segment = rel.split('.')[0]
  return int(first_segment) + 1

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
        line = f'pkgrel={_next_pkgrel(pkgrel)}'

    print(line)

  if updpkgsums:
    run_protected(["updpkgsums"])

def update_pkgrel(
  rel: Optional[PkgRel] = None,
) -> None:
  with open('PKGBUILD', errors='replace') as f:
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
  conflicts: Optional[Iterable[str]] = None,
  prepare: Optional[str] = None,
  check: Optional[str] = None,
  optdepends: Optional[List[str]] = None,
  license: Optional[str] = None,
  license_file: Optional[str] = None,
  pep517: bool = False,
) -> None:
  if python2:
    raise ValueError('pypi_pre_build no longer supports python2')

  pkgname = os.path.basename(os.getcwd())
  if pypi_name is None:
    pypi_name = pkgname.split('-', 1)[-1]

  _new_pkgver, pkgbuild = gen_pkgbuild(
    pypi_name,
    pkgname = pkgname,
    depends = depends,
    arch = arch,
    makedepends = makedepends,
    depends_setuptools = depends_setuptools,
    provides = provides,
    conflicts = conflicts,
    prepare = prepare,
    check = check,
    optdepends = optdepends,
    license = license,
    license_file = license_file,
    pep517 = pep517,
  )

  with open('PKGBUILD', 'w') as f:
    f.write(pkgbuild)

def pypi_post_build() -> None:
  git_add_files('PKGBUILD')
  git_commit()

def git_add_files(
  files: Union[str, List[str]], *, force: bool = False,
) -> None:
  if isinstance(files, str):
    files = [files]
  try:
    if force:
      _run_cmd(['git', 'add', '-f', '--'] + files)
    else:
      _run_cmd(['git', 'add', '--'] + files)
  except subprocess.CalledProcessError:
    # on error, there may be a partial add, e.g. some files are ignored
    _run_cmd(['git', 'reset', '--'] + files)
    raise

def git_commit(*, check_status: bool = True) -> None:
  if check_status:
    ret = [x for x in
           _run_cmd(["git", "status", "-s", "."]).splitlines()
           if x.split(None, 1)[0] != '??']
    if not ret:
      return

  pkgbase = os.path.basename(os.getcwd())
  msg = f'{_G.commit_msg_prefix}{pkgbase}: auto updated to {_G.built_version}'
  _run_cmd(['git', 'commit', '--no-gpg-sign', '-m', msg])

class AurDownloadError(Exception):
  def __init__(self, pkgname: str) -> None:
    self.pkgname = pkgname

def _allow_update_aur_repo(pkgname: str, diff: str) -> bool:
  is_vcs = pkgname.endswith(VCS_SUFFIXES)
  for line in diff.splitlines():
    if not line.startswith(('+', '-')) or line.startswith(('+++', '---')):
      # Not a changed line
      continue
    line = line[1:]  # remove the +/- marker
    if is_vcs and not line.startswith(('pkgver=', 'pkgrel=')):
      return True
    if not is_vcs and not line.startswith('pkgrel='):
      return True
  return False

def _aur_exists(pkgbase: str) -> bool:
  arg = quote(pkgbase)
  url = f'https://aur.archlinux.org/pkgbase/{arg}'
  # The API uses only pkgname, not pkgbase
  # url = f'https://aur.archlinux.org/rpc/?v=5&type=info&arg[]={arg}'
  r = s.get(url)
  code = r.status_code
  if code >= 500:
    r.raise_for_status()
  return r.status_code != 404

def _update_aur_repo_real(pkgbase: str) -> None:
  if not _aur_exists(pkgbase):
    raise Exception('AUR package not exists, not updating!', pkgbase)

  aurpath = const.AUR_REPO_DIR / pkgbase
  if not aurpath.is_dir():
    logger.info('cloning AUR repo: %s', aurpath)
    with at_dir(const.AUR_REPO_DIR):
      _run_cmd(['git', 'clone', f'aur@aur.archlinux.org:{pkgbase}.git'])
  else:
    with at_dir(aurpath):
      # reset everything, dropping local commits
      _run_cmd(['git', 'reset', '--hard', 'origin/master'])
      git_pull()

  with at_dir(aurpath):
    oldfiles = set(_run_cmd(['git', 'ls-files']).splitlines())

  newfiles = set()
  logger.info('copying files to AUR repo: %s', aurpath)
  files = _run_cmd(['git', 'ls-files']).splitlines()
  for f in files:
    if f in SPECIAL_FILES:
      continue
    logger.debug('copying file %s', f)
    shutil.copy(f, aurpath)
    newfiles.add(f)

  with at_dir(aurpath):
    for f in oldfiles - newfiles:
      if f in ['.SRCINFO', '.gitignore']:
        continue
      logger.debug('removing file %s', f)
      try:
        os.unlink(f)
      except OSError as e:
        logger.warning('failed to remove file %s: %s', f, e)

    if not _allow_update_aur_repo(pkgbase, _run_cmd(['git', 'diff'])):
      return

    with open('.SRCINFO', 'wb') as srcinfo:
      srcinfo.write(get_srcinfo())

    _run_cmd(['git', 'add', '.'])
    p = subprocess.run(['git', 'diff-index', '--quiet', 'HEAD'])
    if p.returncode != 0:
      msg = f'[lilac] updated to {_G.built_version}'
      _run_cmd(['git', 'commit', '--no-gpg-sign', '-m', msg])
      _run_cmd(['git', 'push'])

def update_aur_repo() -> None:
  '''update the package on AUR if suitable.

  ``lilac`` must have the permission to do so, i.e. added as a co-maintainer.

  For VCS packages, if only the version changes, the package on AUR won't be updated.
  '''
  pkgbase = os.path.basename(os.getcwd())
  try:
    _update_aur_repo_real(pkgbase)
  except subprocess.CalledProcessError as e:
    _G.repo.send_error_report(
      _G.mod,
      exc = e,
      subject = 'Pushing package %s to AUR faces error',
    )

def git_pkgbuild_commit() -> None:
  git_add_files('PKGBUILD')
  git_commit()

def _prepend_self_path() -> None:
  mydir = Path(__file__).resolve().parent.parent
  path = os.environ['PATH']
  os.environ['PATH'] = str(mydir / path)

def single_main(build_prefix: str = 'makepkg') -> None:
  from .vendor.nicelogger import enable_pretty_logging
  from . import lilacpy
  from .worker import lilac_build

  _prepend_self_path()
  enable_pretty_logging('DEBUG')
  with lilacpy.load_lilac(Path('.')) as mod:
    lilac_build(
      0,
      mod,
      build_prefix = build_prefix,
    )

def clean_directory() -> List[str]:
  '''clean all PKGBUILD and related files'''
  files = _run_cmd(['git', 'ls-files']).splitlines()
  logger.info('clean directory')
  ret = []
  for f in files:
    if f in SPECIAL_FILES:
      continue
    logger.debug('unlink file %s', f)
    ret.append(f)
    with suppress(FileNotFoundError):
      os.unlink(f)
  return ret

def _try_aur_url(name: str) -> bytes:
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
  content = io.BytesIO(_try_aur_url(name))
  files = []
  with tarfile.open(
    name=name+".tar.gz", mode="r:gz", fileobj=content
  ) as tarf:
    for tarinfo in tarf:
      basename, remain = os.path.split(tarinfo.name)
      if basename == '':
        continue
      if remain in SPECIAL_FILES + ('.AURINFO', '.SRCINFO', '.gitignore'):
        continue
      tarinfo.name = remain
      tarf.extract(tarinfo, filter='tar')
      files.append(remain)
  return files

def git_rm_files(files: List[str]) -> None:
  if files:
    _run_cmd(['git', 'rm', '--cached', '--'] + files)

def _get_aur_packager(name: str) -> Tuple[Optional[str], str]:
  doc = parse_document_from_requests(f'https://aur.archlinux.org/pkgbase/{name}', s)
  maintainer_cell = doc.xpath('//th[text()="Maintainer:"]/following::td[1]')[0]
  maintainer: Optional[str] = maintainer_cell.text_content().strip().split(None, 1)[0]
  last_packager_cell = doc.xpath('//th[text()="Last Packager:"]/following::td[1]')[0]
  last_packager = last_packager_cell.text_content().strip()
  if not maintainer:
    maintainer = None
  return maintainer, last_packager

def aur_pre_build(
  name: Optional[str] = None, *, do_vcs_update: Optional[bool] = None,
  maintainers: Union[str, Container[str]] = (),
) -> None:
  # import pyalpm here so that lilac can be easily used on non-Arch
  # systems (e.g. Travis CI)
  import pyalpm

  if name is None:
    name = os.path.basename(os.getcwd())

  maintainer, last_packager = _get_aur_packager(name)
  if last_packager == 'lilac':
    who = maintainer
  else:
    who = last_packager

  if maintainers:
    error = False
    if isinstance(maintainers, str):
      error = who != maintainers
    else:
      error = who not in maintainers
    if error:
      raise Exception('unexpected AUR package maintainer / packager', who)

  if who and (msg := AUR_BLACKLIST.get(who)):
    raise Exception('blacklisted AUR package maintainer / packager', who, msg)

  pkgver, pkgrel = get_pkgver_and_pkgrel()
  _g.aur_pre_files = clean_directory()
  _g.aur_building_files = _download_aur_pkgbuild(name)

  aur_pkgver, aur_pkgrel = get_pkgver_and_pkgrel()
  if pkgver and pkgver == aur_pkgver:
    if pyalpm.vercmp(f'1-{pkgrel}', f'1-{aur_pkgrel}') < 0:
      # use aur pkgrel
      pass
    else:
      # bump
      update_pkgrel()

  if do_vcs_update is None:
    do_vcs_update = name.endswith(VCS_SUFFIXES)

  if do_vcs_update:
    vcs_update()
    # recheck after sync, because AUR pkgver may lag behind
    new_pkgver, new_pkgrel = get_pkgver_and_pkgrel()
    if pkgver and pkgver == new_pkgver:
      if pkgrel is None:
        next_pkgrel = 1
      else:
        next_pkgrel = _next_pkgrel(pkgrel)
      if pyalpm.vercmp(f'1-{next_pkgrel}', f'1-{new_pkgrel}') > 0:
        update_pkgrel(next_pkgrel)

def aur_post_build() -> None:
  git_rm_files(_g.aur_pre_files)
  existing_files = [x for x in _g.aur_building_files if os.path.exists(x)]
  git_add_files(existing_files, force=True)
  output = _run_cmd(["git", "status", "-s", "."]).strip()
  if output:
    git_commit()
  del _g.aur_pre_files, _g.aur_building_files

def download_official_pkgbuild(name: str) -> list[str]:
  url = 'https://archlinux.org/packages/search/json/?name=' + name
  logger.info('download PKGBUILD for %s.', name)
  info = s.get(url).json()
  pkg = [r for r in info['results'] if not r['repo'].endswith('testing')][0]
  pkgbase = pkg['pkgbase']
  epoch = pkg['epoch']
  pkgver = pkg['pkgver']
  pkgrel = pkg['pkgrel']
  if epoch:
    tag = f'{epoch}-{pkgver}-{pkgrel}'
  else:
    tag = f'{pkgver}-{pkgrel}'

  tarball_url = 'https://gitlab.archlinux.org/archlinux/packaging/packages/{0}/-/archive/{1}/{0}-{1}.tar.bz2'.format(pkgbase, tag)
  logger.debug('downloading Arch package tarball from: %s', tarball_url)
  tarball = s.get(tarball_url).content
  path = f'{pkgbase}-{tag}'
  files = []

  with tarfile.open(
    name=f"{pkgbase}-{tag}.tar.bz2", fileobj=io.BytesIO(tarball)
  ) as tarf:
    for tarinfo in tarf:
      dirname, filename = os.path.split(tarinfo.name)
      if dirname != path:
        continue
      if filename in ('.SRCINFO', '.gitignore', '.nvchecker.toml'):
        continue
      tarinfo.name = filename
      logger.debug('extract file %s.', filename)
      tarf.extract(tarinfo, filter='tar')
      files.append(filename)

  return files

def check_library_provides() -> None:
  pkg_pattern = re.compile(r'\.pkg\.tar\.[^.]+$')
  provides_pattern = re.compile(r'^provides = .*\.so$')
  pkgs = [n for n in os.listdir() if pkg_pattern.search(n)]
  for pkg in pkgs:
    pkginfo = _run_cmd(['tar', 'xOf', pkg, '--force-local', '.PKGINFO'])
    for line in pkginfo.splitlines():
      if provides_pattern.match(line):
        raise Exception(f'{pkg} has an unversioned library "provides" entry: {line[11:]}')

def mediawiki_pre_build(
  name: str,
  mwver: str,
  desc: str,
  license: str,
) -> None:
  pkgbuild = mediawiki2pkgbuild.gen_pkgbuild(name, mwver, desc, license, s)
  with open('PKGBUILD', 'w') as f:
    f.write(pkgbuild)
  run_protected(["updpkgsums"])

def mediawiki_post_build() -> None:
  git_add_files('PKGBUILD')
  git_commit()

