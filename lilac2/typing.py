import types
from typing import (
  Union, Dict, Tuple, Type, NamedTuple, Optional,
  Sequence, TYPE_CHECKING,
)
from pathlib import Path
import dataclasses
import datetime

if TYPE_CHECKING:
  from .workerman import WorkerManager

class LilacMod(types.ModuleType):
  time_limit_hours: float
  pkgbase: str
  _G: types.SimpleNamespace
  makechrootpkg_args: list[str]
  makepkg_args: list[str]
  build_args: list[str]
  update_on: NvEntries

NvEntry = dict[str, str]
NvEntries = list[NvEntry]

@dataclasses.dataclass
class OnBuildEntry:
  pkgbase: str
  from_pattern: Optional[str] = None
  to_pattern: Optional[str] = None

@dataclasses.dataclass
class LilacInfo:
  pkgbase: str
  maintainers: list[dict[str, str]]
  update_on: NvEntries
  update_on_build: list[OnBuildEntry]
  throttle_info: dict[int, datetime.timedelta]
  repo_depends: list[tuple[str, str]]
  repo_makedepends: list[tuple[str, str]]
  time_limit_hours: float
  staging: bool
  managed: bool
  allowed_workers: list[str]

LilacInfos = Dict[str, LilacInfo]

ExcInfo = Tuple[Type[BaseException], BaseException, types.TracebackType]

Cmd = Sequence[Union[str, Path]]
PathLike = Union[str, Path]

class Maintainer(NamedTuple):
  name: str
  email: str
  github: Optional[str]

  def __str__(self) -> str:
    return f'{self.name} <{self.email}>'

  @classmethod
  def from_email_address(
    cls, s: str, github: Optional[str] = None,
  ) -> Maintainer:
    if '<' in s:
      name, email = s.split('<', 1)
      name = name.strip('" ')
      email = email.rstrip('>')
    else:
      name = s.rsplit('@', 1)[0]
      email = s
    return cls(name, email, github)

PkgRel = Union[int, str]

class PkgVers(NamedTuple):
  epoch: Optional[str]
  pkgver: str
  pkgrel: str

  def __str__(self) -> str:
    if self.epoch:
      return f'{self.epoch}:{self.pkgver}-{self.pkgrel}'
    else:
      return f'{self.pkgver}-{self.pkgrel}'

class RUsage(NamedTuple):
  cputime: float
  memory: int

class UsedResource(NamedTuple):
  cputime: float
  memory: int
  elapsed: int

class Rusages:
  def __init__(self, data: dict[str, dict[str, UsedResource]]) -> None:
    '''data: pkgbase -> builder -> UsedResource'''
    self.data = data

  def for_package(
    self,
    pkgbase: str,
    builder_hints: list[str],
  ) -> Optional[UsedResource]:
    if a := self.data.get(pkgbase):
      for builder in builder_hints:
        if b := a.get(builder):
          return b
      if a:
        return next(iter(a.values()))

    return None

OnBuildVers = list[tuple[str, str]]

@dataclasses.dataclass
class PkgToBuild:
  pkgbase: str
  on_build_vers: OnBuildVers = dataclasses.field(default_factory=list)
  workerman: Optional[WorkerManager] = None

@dataclasses.dataclass
class Report:
  subject: str
  msg: str
  sendlog: bool = True
