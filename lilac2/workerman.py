from pathlib import Path
from typing import override, Callable, Optional
import logging

from . import tools
from .typing import PkgToBuild, Rusages

logger = logging.getLogger(__name__)

class WorkerManager:
  name: str
  max_concurrency: int
  workers_before_me: int = 0
  current_task_count: int = 0

  def get_resource_usage(self) -> tuple[float, int]:
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

  def prepare(self) -> None:
    raise NotImplementedError

  def sync_depended_packages(self, depends):
    raise NotImplementedError

  def build_package(self):
    raise NotImplementedError

class LocalWorkerManager(WorkerManager):
  name: str = 'local'
  max_concurrency: int

  def __init__(self, max_concurrency) -> None:
    self.max_concurrency = max_concurrency

  @override
  def get_resource_usage(self) -> tuple[float, int]:
    cpu_ratio = tools.get_running_task_cpu_ratio()
    memory_avail = tools.get_avail_memory()
    return cpu_ratio, memory_avail

  @override
  def prepare(self):
    # git pull
    ...

  @override
  def sync_depended_packages(self, depends):
    ...

  @override
  def build_package(self):
    ...

class RemoteWorkerManager(WorkerManager):
  name: str
  max_concurrency: int
  repodir: Path

  def get_resource_usage(self) -> tuple[float, int]:
    raise NotImplementedError

  @override
  def prepare(self):
    # git pull
    ...

  @override
  def sync_depended_packages(self, depends):
    ...

  @override
  def build_package(self):
    ...
