from __future__ import annotations

import types
from typing import (
  Union, Dict, Tuple, Type, List, NamedTuple, Optional,
  Sequence,
)
from pathlib import Path

class LilacMod(types.ModuleType):
  """
  A module to be built by lilac
  """
  time_limit_hours: float
  pkgbase: str
  _G: types.SimpleNamespace
  makechrootpkg_args: List[str]
  makepkg_args: List[str]
  build_args: List[str]
  update_on: List[Dict[str, str]]

LilacMods = Dict[str, LilacMod]
""" dict from module name(str) to LilacMod object """

ExcInfo = Tuple[Type[BaseException], BaseException, types.TracebackType]
""" exception info """

Cmd = Sequence[Union[str, Path]]
""" command to be executed """
PathLike = Union[str, Path]
""" path or str """

class Maintainer(NamedTuple):
  """
  Maintainer object, contains info about a maintainer
  """
  name: str
  email: str
  github: Optional[str]

  def __str__(self) -> str:
    """
    format maintainer
    :return: $name <$email>
    """
    return f'{self.name} <{self.email}>'

  @classmethod
  def from_email_address(
    cls, s: str, github: Optional[str] = None,
  ) -> 'Maintainer':
    if '<' in s:
      name, email = s.split('<', 1)
      name = name.strip('" ')
      email = email.rstrip('>')
    else:
      name = s.rsplit('@', 1)[0]
      email = s
    return cls(name, email, github)

PkgRel = Union[int, str]
""" pkgrel, either a int or a string """
