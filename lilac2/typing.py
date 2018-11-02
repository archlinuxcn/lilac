import types
from typing import Union, Dict, Tuple, Type, List
from typing import NamedTuple, Any
from pathlib import Path

class LilacMod(types.ModuleType):
  time_limit_hours: float
  pkgbase: str
  _G: types.SimpleNamespace
  build_prefix: str
  makechrootpkg_args: List[str]
  # these are not methods but mypy doesn't understand
  pre_build: Any
  post_build: Any
  post_build_always: Any

LilacMods = Dict[str, LilacMod]

ExcInfo = Tuple[Type[BaseException], BaseException, types.TracebackType]

Cmd = List[Union[str, Path]]
PathLike = Union[str, Path]

class Maintainer(NamedTuple):
  name: str
  email: str

  def __str__(self):
    return f'{self.name} <{self.email}>'
