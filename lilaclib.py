import subprocess
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

import requests

from nicelogger import enable_pretty_logging
from htmlutils import parse_document_from_requests
from myutils import at_dir
from mailutils import assemble_mail
from serializer import PickledData
import archpkg

UserAgent = 'lilac/0.1 (package auto-build bot, by lilydjwg)'

s = requests.Session()
s.headers['User-Agent'] = UserAgent
logger = logging.getLogger(__name__)
SPECIAL_FILES = ('package.list', 'lilac.py')
EMPTY_COMMIT = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
_g = SimpleNamespace()
build_output = None
PYPI_URL = 'https://pypi.python.org/pypi/%s/json'

class TryNextRound(Exception):
  def __init__(self, pkgs):
    self.deps = pkgs

def download_official_pkgbuild(name):
  url = 'https://www.archlinux.org/packages/search/json/?name=' + name
  logger.info('download PKGBUILD for %s.', name)
  info = s.get(url).json()
  repo = [r['repo'] for r in info['results'] if r['repo'] != 'testing'][0]
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

def download_aur_pkgbuild(name):
  url = 'https://aur.archlinux.org/packages/{first_two}/{name}/{name}.tar.gz'
  url = url.format(first_two=name[:2], name=name)
  lilac_aur = "lilac_aur"
  run_cmd(['sh', '-c', "curl '%s' | tar xzv --one-top-level='%s' --strip-components=1" % (url, lilac_aur)])
  try:
    os.unlink(os.path.join(lilac_aur, '.AURINFO'))
  except FileNotFoundError:
    pass
  files = os.listdir(lilac_aur)
  for f in files:
    os.rename(os.path.join(lilac_aur, f), f)
  os.rmdir(lilac_aur)
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
      elif l.startswith('pkgvel='):
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
           run_cmd(["git", "status", "-s"]).splitlines()
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
  _g.aur_pre_files = clean_directory()
  if name is None:
    name = os.path.basename(os.getcwd())
  _g.aur_building_files = download_aur_pkgbuild(name)
  if do_vcs_update and name.endswith(('-git', '-hg', '-svn', '-bzr')):
    vcs_update()

def vcs_update():
  run_cmd(['makepkg', '-o'], use_pty=True)
  output = run_cmd(["git", "status", "-s", "PKGBUILD"]).strip()
  if not output:
    raise RuntimeError('no update available. something goes wrong?')

def aur_post_build():
  git_rm_files(_g.aur_pre_files)
  git_add_files(_g.aur_building_files)
  output = run_cmd(["git", "status", "-s", "."]).strip()
  if output:
    git_commit()
  del _g.aur_pre_files, _g.aur_building_files

def pypi_pre_build(depends=None, python2=False):
  if os.path.exists('PKGBUILD'):
    pkgver, pkgrel = get_pkgver_and_pkgrel()
  else:
    pkgver = None

  name = os.path.basename(os.getcwd())
  pypi_name = name.split('-', 1)[-1]
  pkgbuild = run_cmd(['pypi2pkgbuild', pypi_name], silent=True)
  if depends is None:
    depends = ['python-setuptools']
  else:
    depends.append('python-setuptools')
  pkgbuild = pkgbuild.replace(
    "depends=('python')",
    "depends=('python' %s)" % ' '.join("'%s'" % x for x in depends))
  if python2:
    pkgbuild = re.sub(r'\bpython3?(?!.)', 'python2', pkgbuild)
  with open('PKGBUILD', 'w') as f:
    f.write(pkgbuild)

  new_pkgver = get_pkgver_and_pkgrel()[0]
  if pkgver == new_pkgver:
    # change pkgrel to what specified in PKGBUILD
    update_pkgrel(pkgrel)

def pypi_post_build():
  git_add_files('PKGBUILD')
  git_commit()

def lilac_build(repodir, build_prefix=None, skip_depends=False, oldver=None, newver=None):
  spec = importlib.util.spec_from_file_location('lilac.py', 'lilac.py')
  mod = spec.loader.load_module()
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
      mod.pre_build()

    # we don't install any dependencies when testing
    if skip_depends:
      depends = ()
    else:
      depends = getattr(mod, 'depends', ())
    pkgs_to_build = getattr(mod, 'packages', None)
    depend_packages = []
    need_build_first = set()
    for x in depends:
      p = find_local_package(repodir, x)
      if not p:
        if isinstance(x, tuple):
          x = x[0]
        need_build_first.add(x)
      else:
        depend_packages.append(p)
    if need_build_first:
      raise TryNextRound(need_build_first)

    build_prefix = build_prefix or mod.build_prefix
    if isinstance(build_prefix, str):
      build_prefix = [build_prefix]

    for bp in build_prefix:
      call_build_cmd(bp, depend_packages, pkgs_to_build)
    pkgs = [x for x in os.listdir() if x.endswith('.pkg.tar.xz')]
    if not pkgs:
      raise Exception('no package built')
    if hasattr(mod, 'post_build'):
      mod.post_build()
    success = True
  finally:
    del sys.modules['lilac.py']
    if hasattr(mod, 'post_build_always'):
      mod.post_build_always(success=success)

def call_build_cmd(tag, depends, pkgs_to_build=None):
  global build_output
  if tag == 'makepkg':
    cmd = ['makepkg']
    if pkgs_to_build:
      cmd.extend(['--pkg', ','.join(pkgs_to_build)])
  else:
    cmd = ['sudo', '%s-build' % tag]

    if depends or pkgs_to_build:
      cmd.append('--')

    if depends:
      for x in depends:
        cmd += ['-I', x]

    if pkgs_to_build:
      cmd.extend(['--', '--pkg', ','.join(pkgs_to_build)])

  # NOTE that Ctrl-C here may not succeed
  build_output = run_cmd(cmd, use_pty=True)

def find_local_package(repodir, pkgname):
  by = os.path.basename(os.getcwd())
  if isinstance(pkgname, tuple):
    d, name = pkgname
  else:
    d = name = pkgname

  with at_dir(repodir):
    if not os.path.isdir(d):
      raise FileNotFoundError(
        'no idea to satisfy denpendency %s for %s' % (pkgname, by))

    with at_dir(d):
      names = [x for x in os.listdir() if x.endswith('.pkg.tar.xz')]
      pkgs = [x for x in names
              if archpkg.PkgNameInfo.parseFilename(x).name == name]
      if len(pkgs) == 1:
        return os.path.abspath(pkgs[0])
      elif not pkgs:
        return
      else:
        ret = sorted(
          pkgs, reverse=True, key=lambda n: os.stat(n).st_mtime)[0]
        return os.path.abspath(ret)

def single_main(build_prefix='makepkg'):
  enable_pretty_logging('DEBUG')
  lilac_build(
    build_prefix = build_prefix,
    repodir = os.path.dirname(
      os.path.dirname(sys.modules['__main__'].__file__)),
    skip_depends = True,
  )

def run_cmd(cmd, *, use_pty=False, silent=False):
  logger.debug('running %r, %susing pty,%s showing output', cmd,
               '' if use_pty else 'not ',
               ' not' if silent else '')
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
    r = r.replace(b'\x0f', b'') # ^O
    if not silent:
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

def edit_file(filename):
  with fileinput.input(files=(filename,), inplace=True) as f:
    for line in f:
      yield line.rstrip('\n')

def mkaurball():
  run_cmd(['mkaurball'], use_pty=True)
