import types
from typing import Union, Dict, Tuple, Type, List
from typing import NamedTuple
from pathlib import Path

Floatlike = Union[int, float]

class LilacMod(types.ModuleType):
  time_limit_hours: Floatlike
  pkgbase: str

LilacMods = Dict[str, LilacMod]

ExcInfo = Tuple[Type[BaseException], BaseException, types.TracebackType]

Cmd = List[Union[str, Path]]
PathLike = Union[str, Path]

class Maintainer(NamedTuple):
  name: str
  email: str
