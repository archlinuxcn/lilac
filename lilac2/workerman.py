from typing import override, Callable, Optional, Any
import logging
import subprocess
import os
import json
import signal
import sys
import tempfile

from .typing import PkgToBuild, Rusages

logger = logging.getLogger(__name__)

class WorkerManager:
  name: str
  max_concurrency: int
  workers_before_me: int = 0
  current_task_count: int = 0

  def get_worker_cmd(self, pkgbase: str) -> list[str]:
    raise NotImplementedError

  def get_resource_usage(self) -> tuple[float, int]:
    raise NotImplementedError

  def sync_depended_packages(self, depends: list[str]) -> None:
    raise NotImplementedError

  def prepare_batch(
    self,
    pacman_conf: Optional[str],
  ) -> None:
    raise NotImplementedError

  def finish_batch(self) -> None:
    raise NotImplementedError

  def try_accept_package(
    self,
    ready_to_build: list[str],
    rusages: Rusages,
    priority_func: Callable[[str], int],
    check_buildability: Callable[[str], Optional[PkgToBuild]],
  ) -> list[PkgToBuild]:
    if self.current_task_count >= self.max_concurrency:
      return []

    cpu_ratio, memory_avail = self.get_resource_usage()

    if cpu_ratio > 1.0 and self.current_task_count > 0:
      return []

    def sort_key(pkg):
      p = priority_func(pkg)
      r = rusages.for_package(pkg, [self.name])
      if r is not None:
        cpu = r.cputime / r.elapsed
      else:
        cpu = 1.0
      return (p, cpu)
    ready_to_build.sort(key=sort_key)
    logger.debug('[%s] sorted ready_to_build: %r',
                 self.name, ready_to_build)

    if cpu_ratio < 0.9:
      # low cpu usage, build a big package
      p = priority_func(ready_to_build[0])
      for idx, pkg in enumerate(ready_to_build):
        if priority_func(pkg) != p:
          if idx > 2:
            ready_to_build.insert(0, ready_to_build.pop(idx-1))
          break
    else:
      logger.info('high cpu usage (%.2f), preferring low-cpu-usage builds', cpu_ratio)

    ret: list[PkgToBuild] = []

    limited_by_memory = False
    for pkg in ready_to_build:
      r = rusages.for_package(pkg, [self.name])
      if r and r.memory > memory_avail:
        logger.debug('package %s used %d memory last time, but now only %d is available', pkg, r.memory, memory_avail)
        limited_by_memory = True
        continue

      to_build = check_buildability(pkg)
      if to_build is None:
        continue

      to_build.workerman = self
      ret.append(to_build)
      if len(ret) + self.current_task_count >= self.max_concurrency:
        break

      if r:
        memory_avail -= r.memory
      else:
        memory_avail -= 10 * 1024 ** 3

    if not ret and limited_by_memory:
      logger.info('insufficient memory, not starting another concurrent build (available: %d)', memory_avail)

    self.current_task_count += len(ret)
    return ret

  @staticmethod
  def from_name(config: dict[str, Any], name: str):
    if name == 'local':
      max_concurrency = config['lilac'].get('max_concurrency', 1)
      return LocalWorkerManager(max_concurrency)
    else:
      remote = [
        x for x in config['remoteworker']
        if x.get('enabled', False) and x['name'] == name
      ][0]
      return RemoteWorkerManager(remote)

class LocalWorkerManager(WorkerManager):
  name: str = 'local'
  max_concurrency: int

  def __init__(self, max_concurrency) -> None:
    self.max_concurrency = max_concurrency

  @override
  def get_worker_cmd(self, pkgbase: str) -> list[str]:
    return [
      sys.executable,
      '-Xno_debug_ranges', # save space
      '-P', # don't prepend cwd to sys.path where unexpected directories may exist
      '-m', 'lilac2.worker', pkgbase,
    ]

  @override
  def get_resource_usage(self) -> tuple[float, int]:
    from . import tools
    cpu_ratio = tools.get_running_task_cpu_ratio()
    memory_avail = tools.get_avail_memory()
    return cpu_ratio, memory_avail

  @override
  def sync_depended_packages(self, depends: list[str]) -> None:
    pass

  @override
  def prepare_batch(
    self,
    pacman_conf: Optional[str],
  ) -> None:
    from . import pkgbuild
    pkgbuild.update_data(pacman_conf)

  @override
  def finish_batch(self) -> None:
    pass

class RemoteWorkerManager(WorkerManager):
  name: str
  max_concurrency: int
  repodir: str
  host: str
  config: dict[str, Any]

  def __init__(self, remote: dict[str, Any]) -> None:
    self.name = remote['name']
    self.repodir = remote['repodir']
    self.host = remote['host']
    self.max_concurrency = remote.get('max_concurrency', 1)
    self.config = remote

  @override
  def get_worker_cmd(self, pkgbase: str) -> list[str]:
    return [
      sys.executable,
      '-Xno_debug_ranges', # save space
      '-P', # don't prepend cwd to sys.path where unexpected directories may exist
      '-m', 'lilac2.remote.worker', pkgbase, self.name,
    ]

  @override
  def get_resource_usage(self) -> tuple[float, int]:
    sshcmd = self.get_sshcmd_prefix() + ['python', '-m', 'lilac2.tools']
    out = subprocess.check_output(sshcmd, text=True)
    cpu, mem = out.split()
    return float(cpu), int(mem)

  @override
  def sync_depended_packages(self, depends: list[str]) -> None:
    if not depends:
      return

    includes = ''.join(f'/{p.rsplit('/', 2)[1]}\n' for p in depends)
    rsync_cmd = [
      'rsync', '-avi',
      '--include-from=-',
      '--exclude=/.*', '--exclude=*/', '--include=*.pkg.tar.zst', '--exclude=*/*',
      '--delete',
      './', f'{self.host}:{self.repodir.removesuffix('/')}',
    ]
    logger.info('[%s] sync_depended_packages: %s', self.name, rsync_cmd)
    subprocess.run(rsync_cmd, text=True, input=includes, check=True)

  @override
  def prepare_batch(
    self,
    pacman_conf: Optional[str],
  ) -> None:
    # update pacman databases
    sshcmd = self.get_sshcmd_prefix() + [
      'python', '-m', 'lilac2.pkgbuild', pacman_conf or '',
    ]
    subprocess.check_call(sshcmd)

    sshcmd = self.get_sshcmd_prefix() + [
      'python', '-m', 'lilac2.remote.git_pull', f'"{self.repodir}"',
    ]
    subprocess.run(sshcmd, check=True)
    
    if prerun := self.config.get('prerun'):
      self.run_cmds(prerun)

  @override
  def finish_batch(self) -> None:
    out = subprocess.check_output(['git', 'remote'], text=True)
    remotes = out.splitlines()
    if self.name not in remotes:
      sshcmd = self.get_sshcmd_prefix() + [
        f'cd "{self.repodir}" && git rev-parse --show-prefix'
      ]
      out = subprocess.check_output(sshcmd, text=True).strip('\n/')
      if out:
        reporoot = self.repodir.removesuffix(out).rstrip('/')
      else:
        reporoot = self.repodir
      subprocess.check_call([
        'git', 'remote', 'add', self.name, f'{self.host}:{reporoot}',
      ])
    subprocess.check_call([
      'git', 'pull', '--no-edit', self.name, 'master',
    ])

    if postrun := self.config.get('postrun'):
      self.run_cmds(postrun)

  def fetch_files(self, pkgname: str) -> None:
    # run in remote.worker
    rsync_cmd = [
      'rsync', '-avi',
      '--include=*.pkg.tar.zst', '--exclude=*',
      f'{self.host}:{self.repodir.removesuffix('/')}/{pkgname}/',
      '.',
    ]
    logger.info('[%s] fetch_files: %s', self.name, rsync_cmd)
    subprocess.run(rsync_cmd, check=True)

  def run_remote(
    self,
    pkgname: str,
    deadline: float,
    worker_no: int,
    input: dict[str, Any],
  ) -> dict[str, Any]:
    # run in remote.worker

    setenv = {
      'MAKEFLAGS': os.environ.get('MAKEFLAGS', ''),
      'PACKAGER': os.environ.get('PACKAGER', ''),
      'LANG': os.environ.get('LANG', 'C.UTF-8'),
    }
    if tz := os.environ.get('TZ'):
      setenv['TZ'] = tz

    name = f'lilac-worker-{worker_no}'

    fd, resultpath = tempfile.mkstemp(prefix=f'{name}-', suffix='.lilac')
    os.close(fd)

    input = {
      'name': name,
      'deadline': deadline,
      'result': resultpath,
      'pkgdir': os.path.join(self.repodir, pkgname),
      'setenv': setenv,
      **input,
    }

    input_bytes = json.dumps(input).encode()
    sshcmd: list[str] = self.get_sshcmd_prefix(pty=True) + [
      'python',
      '-Xno_debug_ranges', # save space
      '-P', # don't prepend cwd to sys.path where unexpected directories may exist
      '-m', 'lilac2.remote.runner', pkgname, str(worker_no),
    ]
    p = subprocess.Popen(
      sshcmd,
      stdin = subprocess.PIPE,
    )
    p.stdin.write(input_bytes) # type: ignore
    p.stdin.close() # type: ignore

    e: Optional[BaseException] = None
    stop_countdown = None
    while True:
      try:
        # timeout tor waiting subprocess to terminate
        if stop_countdown is not None:
          stop_countdown -= 1
        if stop_countdown == 0:
          break

        try:
          code = p.wait(10)
        except subprocess.TimeoutExpired:
          st = os.stat(1)
          if st.st_size > 1024 ** 3: # larger than 1G
            logger.error('\n\nToo much output, killed.')
        else:
          if code != 0 and e is None:
            e = subprocess.CalledProcessError(code, 'lilac2.remote.runner')
          break
      except KeyboardInterrupt as e2:
        logger.info('SIGINT received, relaying to remoteworker')
        p.send_signal(signal.SIGINT)
        stop_countdown = 6
        e = e2
    p.wait()

    try:
      sshcmd = self.get_sshcmd_prefix() + ['cat', resultpath]
      out = subprocess.check_output(sshcmd, text=True)
      r = json.loads(out)
      return r
    finally:
      if e:
        raise e

  def get_sshcmd_prefix(self, pty: bool = False) -> list[str]:
    if pty:
      return ['ssh', '-t', self.host]
    else:
      return ['ssh', '-T', self.host]

  def run_cmds(self, cmds: list[str]) -> None:
    for cmd in cmds:
      subprocess.check_call(self.get_sshcmd_prefix() + [cmd])
