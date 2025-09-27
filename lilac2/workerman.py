from pathlib import Path
from typing import override

class WorkerManager:
  name: str
  max_concurrency: int

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
