from __future__ import annotations

import types
from typing import (
  Union, Dict, Tuple, Type, List, NamedTuple, Optional,
  Sequence, Literal,
)
from pathlib import Path

class LilacMod(types.ModuleType):
  time_limit_hours: float
  pkgbase: str
  _G: types.SimpleNamespace
  makechrootpkg_args: List[str]
  makepkg_args: List[str]
  build_args: List[str]
  update_on: List[Dict[str, str]]

LilacMods = Dict[str, LilacMod]

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

class BuildResult:
  _lit_created = False

  def __bool__(self) -> bool:
    return self.ty in ['successful', 'staged']

  def __new__(
    cls,
    ty: Literal['successful', 'failed', 'skipped', 'staged'],
    reason: Optional[str] = None,
    exc: Optional[Exception] = None,
  ) -> BuildResult:
    if ty in ['successful', 'staged'] and \
       cls._lit_created:
      return getattr(cls, ty)

    inst = super().__new__(cls)
    inst.__init__(ty, reason)
    return inst

  def __init__(
    self,
    ty: Literal['successful', 'failed', 'skipped', 'staged'],
    reason: Optional[str] = None,
    exc: Optional[Exception] = None,
  ) -> None:
    self.ty = ty
    self.reason = reason
    self.exc = exc

  @classmethod
  def skipped(cls, reason: str) -> BuildResult:
    return cls('skipped', reason = reason)

  @classmethod
  def failed(cls, exc: Exception) -> BuildResult:
    return cls('failed', exc = exc)

  def __repr__(self) -> str:
    name = self.__class__.__name__
    if self.ty == 'failed':
      s = f'<{name}: {self.ty}({self.exc!r})>'
    elif self.ty == 'skipped':
      s = f'<{name}: {self.ty}({self.reason!r})>'
    else:
      s = f'<{name}: {self.ty}>'
    return s

  successful: BuildResult
  staged: BuildResult

BuildResult.successful = BuildResult('successful')
BuildResult.staged = BuildResult('staged')
BuildResult._lit_created = True
