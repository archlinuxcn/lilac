import subprocess
import traceback
from subprocess import CalledProcessError
import os
import logging
import sys
import smtplib
import signal
from types import SimpleNamespace
import importlib.util
import re
import fileinput
import contextlib
from collections import defaultdict
from io import BytesIO
import tarfile
from functools import partial
import shutil

import requests

from nicelogger import enable_pretty_logging
from htmlutils import parse_document_from_requests
from myutils import at_dir, execution_timeout
from mailutils import assemble_mail
from serializer import PickledData
import archpkg

UserAgent = 'lilac/0.1 (package auto-build bot, by lilydjwg)'

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

class Dependency:
  _CACHE = {}

  @classmethod
  def get(cls, topdir, what):
    if isinstance(what, tuple):
      pkgbase, pkgname = what
    else:
      pkgbase = pkgname = what

    key = pkgbase, pkgname
    if key not in cls._CACHE:
      cls._CACHE[key] = cls(topdir, pkgbase, pkgname)
    return cls._CACHE[key]

  def __init__(self, topdir, pkgbase, pkgname):
    self.pkgbase = pkgbase
    self.pkgname = pkgname
    self.directory = os.path.join(topdir, pkgbase)

  def resolve(self):
    try:
      return self._find_local_package()
    except FileNotFoundError:
      return None

  def _find_local_package(self):
    with at_dir(self.directory):
      fnames = [x for x in os.listdir() if x.endswith('.pkg.tar.xz')]
      pkgs = []
      for x in fnames:
        info = archpkg.PkgNameInfo.parseFilename(x)
        if info.name == self.pkgname:
          pkgs.append(x)

      if len(pkgs) == 1:
        return os.path.abspath(pkgs[0])
      elif not pkgs:
        raise FileNotFoundError
      else:
        ret = sorted(
          pkgs, reverse=True, key=lambda n: os.stat(n).st_mtime)[0]
        return os.path.abspath(ret)

class MissingDependencies(Exception):
  def __init__(self, pkgs):
    self.deps = pkgs

class BuildPrefixError(Exception):
  def __init__(self, build_prefix):
    self.build_prefix = build_prefix

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
    for filename in tarf.getnames():
      basename, remain = os.path.split(filename)
      if basename == '':
        continue
      if remain in ('.AURINFO', '.SRCINFO'):
        continue
      with open(remain, "wb") as f:
        f.write(tarf.extractfile(filename).read())
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
        pkgrel = float(l.rstrip().split('=', 1)[-1])
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
      rel = int(float(m.group())) + 1
    return str(rel)

  pkgbuild = re.sub(r'(?<=^pkgrel=)[\d.]+', replacer, pkgbuild, count=1, flags=re.MULTILINE)
  with open('PKGBUILD', 'w') as f:
    f.write(pkgbuild)
  logger.info('pkgrel updated to %s', rel)

def find_maintainer(me, file='*'):
  head = 'HEAD'
  while True:
    commit, author = get_commit_and_email(head, file)
    if not author.endswith(me):
      return author
    head = commit + '^'

def get_commit_and_email(head, file='*'):
  cmd = [
    "git", "log", "-1", "--format=%H %an <%ae>", head, "--", file,
  ]
  commit, author = run_cmd(cmd).rstrip().split(None, 1)
  return commit, author

def sendmail(to, from_, subject, msg):
  s = smtplib.SMTP()
  s.connect()
  if len(msg) > 5 * 1024 ** 2:
    msg = msg[:1024 ** 2] + '\n\n日志过长，省略ing……\n\n' + msg[-1024 ** 2:]
  msg = assemble_mail(subject, to, from_, text=msg)
  s.send_message(msg)
  s.quit()

def get_changed_packages(revisions, U=None):
  cmd = ["git", "diff", "--name-only", revisions]
  r = run_cmd(cmd).splitlines()
  ret = {x.split('/', 1)[0] for x in r}
  if U is not None:
    ret &= U
  return ret

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
  run_cmd(['git', 'add', '--'] + files)

def git_commit(*, check_status=True):
  if check_status:
    ret = [x for x in
           run_cmd(["git", "status", "-s", "."]).splitlines()
           if x.split(None, 1)[0] != '??']
    if not ret:
      return

  run_cmd(['git', 'commit', '-m', 'auto update for package %s' % (
    os.path.split(os.getcwd())[1])])

def git_pull():
  output = run_cmd(['git', 'pull', '--no-edit'])
  return 'up-to-date' not in output

def git_reset_hard():
  run_cmd(['git', 'reset', '--hard'])

def git_push():
  while True:
    try:
      run_cmd(['git', 'push'])
      break
    except CalledProcessError as e:
      if 'non-fast-forward' in e.output or 'fetch first' in e.output:
        run_cmd(["git", "pull", "--rebase"])
      else:
        raise

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

  new_pkgver = get_pkgver_and_pkgrel()[0]
  if pkgver and pkgver == new_pkgver:
    # change pkgrel to what specified in PKGBUILD
    update_pkgrel(pkgrel)

  if do_vcs_update and name.endswith(('-git', '-hg', '-svn', '-bzr')):
    vcs_update()

def vcs_update():
  run_cmd(['makepkg', '-od'], use_pty=True)

def aur_post_build():
  git_rm_files(_g.aur_pre_files)
  git_add_files(_g.aur_building_files)
  output = run_cmd(["git", "status", "-s", "."]).strip()
  if output:
    git_commit()
  del _g.aur_pre_files, _g.aur_building_files

def pypi_pre_build(depends=None, python2=False, pypi_name=None, arch=None,
                   makedepends=None, depends_setuptools=True,
                  ):
  if os.path.exists('PKGBUILD'):
    pkgver, pkgrel = get_pkgver_and_pkgrel()
  else:
    pkgver = None

  if pypi_name is None:
    name = os.path.basename(os.getcwd())
    pypi_name = name.split('-', 1)[-1]
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

  if depends:
    pkgbuild = pkgbuild.replace(
      "depends=('python')",
      "depends=('python' %s)" % ' '.join("'%s'" % x for x in depends))

  if makedepends:
    pkgbuild = pkgbuild.replace(
      '\nsource=',
      '\nmakedepends=(%s)\nsource=' %
      ' '.join("'%s'" % x for x in makedepends))

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

def lilac_build(repodir, build_prefix=None, oldver=None, newver=None, accept_noupdate=False, depends=()):
  with load_lilac() as mod:
    run_cmd(["sh", "-c", "rm -f -- *.pkg.tar.xz *.pkg.tar.xz.sig *.src.tar.gz"])
    success = False

    global build_output
    # reset in case no one cleans it up
    build_output = None

    try:
      if not hasattr(mod, '_G'):
        # fill nvchecker result unless already filled (e.g. by hand)
        mod._G = SimpleNamespace(oldver = oldver, newver = newver)
      mod.update_pkgver = partial(update_pkgver, newver=newver)
      if hasattr(mod, 'pre_build'):
        logger.debug('accept_noupdate=%r, oldver=%r, newver=%r', accept_noupdate, oldver, newver)
        mod.pre_build()
      recv_gpg_keys()

      pkgs_to_build = getattr(mod, 'packages', None)
      need_build_first = set()

      build_prefix = build_prefix or mod.build_prefix
      if not isinstance(build_prefix, str) or 'i686' in build_prefix:
        raise BuildPrefixError(build_prefix)

      depend_packages = []
      for x in depends:
        p = x.resolve()
        if p is None:
          need_build_first.add(x.pkgbase)
        else:
          depend_packages.append(p)
      if need_build_first:
        raise MissingDependencies(need_build_first)

      call_build_cmd(build_prefix, depend_packages, pkgs_to_build)
      pkgs = [x for x in os.listdir() if x.endswith('.pkg.tar.xz')]
      if not pkgs:
        raise Exception('no package built')
      if hasattr(mod, 'post_build'):
        mod.post_build()
      success = True
    finally:
      if hasattr(mod, 'post_build_always'):
        mod.post_build_always(success=success)

def call_build_cmd(tag, depends, pkgs_to_build=None):
  global build_output
  if tag == 'makepkg':
    cmd = ['makepkg', '--holdver']
    if pkgs_to_build:
      cmd.extend(['--pkg', ','.join(pkgs_to_build)])
  else:
    cmd = ['%s-build' % tag, '--']

    if depends:
      for x in depends:
        cmd += ['-I', x]

    cmd.extend(['--', '--holdver'])

    if pkgs_to_build:
      cmd.extend(['--pkg', ','.join(pkgs_to_build)])

  # NOTE that Ctrl-C here may not succeed
  build_output = run_cmd(cmd, use_pty=True)

def single_main(build_prefix='makepkg'):
  prepend_self_path()
  enable_pretty_logging('DEBUG')
  lilac_build(
    build_prefix = build_prefix,
    repodir = os.path.dirname(
      os.path.dirname(sys.modules['__main__'].__file__)),
    accept_noupdate = True,
  )

def prepend_self_path():
  mydir = os.path.realpath(os.path.dirname(__file__))
  path = os.environ['PATH']
  os.environ['PATH'] = mydir + os.pathsep + path

def run_cmd(cmd, *, use_pty=False, silent=False):
  logger.debug('running %r, %susing pty,%s showing output', cmd,
               '' if use_pty else 'not ',
               ' not' if silent else '')
  if use_pty:
    rfd, stdout = os.openpty()
    stdin = stdout
    # for fd leakage
    logger.debug('pty master fd=%d, slave fd=%d.', rfd, stdout)
  else:
    stdin = subprocess.DEVNULL
    stdout = subprocess.PIPE

  exited = False
  def child_exited(signum, sigframe):
    nonlocal exited
    exited = True
  old_hdl = signal.signal(signal.SIGCHLD, child_exited)

  p = subprocess.Popen(cmd, stdin = stdin, stdout = stdout, stderr = subprocess.STDOUT)
  if use_pty:
    os.close(stdout)
  else:
    rfd = p.stdout.fileno()
  out = []

  while not exited:
    try:
      r = os.read(rfd, 4096)
      if not r:
        # EOF
        break
    except InterruptedError:
      continue
    except OSError as e:
      if e.errno == 5: # Input/output error: no clients run
        break
      else:
        raise
    r = r.replace(b'\x0f', b'') # ^O
    if not silent:
      sys.stderr.buffer.write(r)
    out.append(r)

  code = p.wait()
  if use_pty:
    os.close(rfd)
  if old_hdl is not None:
    signal.signal(signal.SIGCHLD, old_hdl)

  out = b''.join(out)
  out = out.decode('utf-8', errors='replace')
  if code != 0:
      raise CalledProcessError(code, cmd, out)
  return out

def edit_file(filename):
  with fileinput.input(files=(filename,), inplace=True) as f:
    for line in f:
      yield line.rstrip('\n')

def update_pkgver(newver):
  for l in edit_file('PKGBUILD'):
    l = l.rstrip('\n')
    if l.startswith('pkgver='):
      l = 'pkgver=' + newver
    print(l)
  run_cmd(['updpkgsums'])

def recv_gpg_keys():
  run_cmd(['recv_gpg_keys'])

@contextlib.contextmanager
def load_lilac():
  try:
    spec = importlib.util.spec_from_file_location('lilac.py', 'lilac.py')
    mod = spec.loader.load_module()
    yield mod
  finally:
    try:
      del sys.modules['lilac.py']
    except KeyError:
      pass

def _update_aur_repo_real(pkgname):
  aurpath = os.path.join(AUR_REPO_DIR, pkgname)
  if not os.path.isdir(aurpath):
    logger.info('cloning AUR repo: %s', aurpath)
    with at_dir(AUR_REPO_DIR):
      run_cmd(['git', 'clone', 'aur@aur4.archlinux.org:%s.git' % pkgname])
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
    run_cmd(['mksrcinfo'])
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
