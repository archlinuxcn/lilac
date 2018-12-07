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

from myutils import at_dir
from htmlutils import parse_document_from_requests

from .cmd import run_cmd, git_pull, git_push, git_reset_hard
from . import const
from .const import _G, SPECIAL_FILES

git_push

logger = logging.getLogger(__name__)

_g = SimpleNamespace()
UserAgent = 'lilac/0.2b (package auto-build bot, by lilydjwg)'

s = requests.Session()
s.headers['User-Agent'] = UserAgent

def _unquote_item(s: str) -> Optional[str]:
  m = re.search(r'''[ \t'"]*([^ '"]+)[ \t'"]*''', s)
  if m is not None:
    return m.group(1)
  else:
    return None

def add_into_array(line: str, values: Iterable[str]) -> str:
  l = line.find('(')
  r = line.rfind(')')
  arr_str = line[l+1:r].strip()
  arr = {_unquote_item(x) for x in arr_str.split(' ')}.union(values)
  arr_str = '('
  for item in arr:
    if item is None: continue
    arr_str += "'{}' ".format(item)
  arr_str += ')'
  line = line[:l] + arr_str
  return line

def _add_deps(which: str, extra_deps: Iterable[str]) -> None:
  '''
  Add more values into the dependency array
  '''
  field_appeared = False

  for line in edit_file('PKGBUILD'):
    if line.strip().startswith(which):
      line = add_into_array(line, extra_deps)
      field_appeared = True
    print(line)

  if not field_appeared:
    with open('PKGBUILD', 'a') as f:
      line = f'{which}=()'
      line = add_into_array(line, extra_deps)
      f.write(line + '\n')

def add_depends(extra_deps):
  _add_deps('depends', extra_deps)

def add_makedepends(extra_deps):
  _add_deps('makedepends', extra_deps)

def edit_file(filename: str) -> Iterator[str]:
  with fileinput.input(files=(filename,), inplace=True) as f:
    for line in f:
      yield line.rstrip('\n')

def obtain_array(name: str) -> Optional[List[str]]:
  '''
  Obtain an array variable from PKGBUILD.
  Works by calling bash to source PKGBUILD, writing the array to a temporary file, and reading from the file.
  '''
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
            (item.split(':', 1) for item in obtained_array)}
  else:
    return obtained_array

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

def git_add_files(
  files: Union[str, List[str]], *, force: bool = False,
) -> None:
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
  if check_status:
    ret = [x for x in
           run_cmd(["git", "status", "-s", "."]).splitlines()
           if x.split(None, 1)[0] != '??']
    if not ret:
      return

  run_cmd(['git', 'commit', '-m', 'auto update for package %s' % (
    os.path.split(os.getcwd())[1])])

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

def git_pkgbuild_commit() -> None:
  git_add_files('PKGBUILD')
  git_commit()

def _prepend_self_path() -> None:
  mydir = Path(__file__).resolve().parent.parent
  path = os.environ['PATH']
  os.environ['PATH'] = str(mydir / path)

def single_main(build_prefix: str = 'makepkg') -> None:
  from nicelogger import enable_pretty_logging
  from . import lilacpy
  from .building import lilac_build

  _prepend_self_path()
  enable_pretty_logging('DEBUG')
  with lilacpy.load_lilac(Path('.')) as mod:
    lilac_build(
      mod,
      build_prefix = build_prefix,
      accept_noupdate = True,
    )

def _clean_directory() -> List[str]:
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
      if remain in ('.AURINFO', '.SRCINFO', '.gitignore'):
        continue
      tarinfo.name = remain
      tarf.extract(tarinfo)
      files.append(remain)
  return files

def git_rm_files(files: List[str]) -> None:
  if files:
    run_cmd(['git', 'rm', '--cached', '--'] + files)

def aur_pre_build(
  name: Optional[str] = None, *, do_vcs_update: bool = True,
) -> None:
  if os.path.exists('PKGBUILD'):
    pkgver, pkgrel = get_pkgver_and_pkgrel()
  else:
    pkgver = None

  _g.aur_pre_files = _clean_directory()
  if name is None:
    name = os.path.basename(os.getcwd())
  _g.aur_building_files = _download_aur_pkgbuild(name)

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

def aur_post_build() -> None:
  git_rm_files(_g.aur_pre_files)
  git_add_files(_g.aur_building_files, force=True)
  output = run_cmd(["git", "status", "-s", "."]).strip()
  if output:
    git_commit()
  del _g.aur_pre_files, _g.aur_building_files

def download_official_pkgbuild(name: str) -> List[str]:
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

