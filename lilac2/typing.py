import types
from typing import Union, Dict, Tuple, Type, List, NamedTuple
from pathlib import Path

class LilacMod(types.ModuleType):
  time_limit_hours: float
  pkgbase: str
  _G: types.SimpleNamespace
  makechrootpkg_args: List[str]

LilacMods = Dict[str, LilacMod]

ExcInfo = Tuple[Type[BaseException], BaseException, types.TracebackType]

Cmd = List[Union[str, Path]]
PathLike = Union[str, Path]

class Maintainer(NamedTuple):
  name: str
  email: str

  def __str__(self):
    return f'{self.name} <{self.email}>'

  @classmethod
  def from_email_address(cls, s: str) -> 'Maintainer':
    name, email = s.split('<', 1)
    name = name.strip('" ')
    email = email.rstrip('>')
    return cls(name, email)

