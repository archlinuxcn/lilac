from __future__ import annotations

import types
from typing import (
  Union, Dict, Tuple, Type, NamedTuple, Optional,
  Sequence,
)
from pathlib import Path
import dataclasses
import datetime

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

OnBuildVers = list[tuple[str, str]]
class PkgToBuild(NamedTuple):
  pkgbase: str
  on_build_vers: OnBuildVers = []
