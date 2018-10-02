import types
from typing import Union, Dict, Tuple, Type, List
from pathlib import Path

Floatlike = Union[int, float]

class LilacMod(types.ModuleType):
  time_limit_hours: Floatlike

LilacMods = Dict[str, LilacMod]

ExcInfo = Tuple[Type[BaseException], BaseException, types.TracebackType]

Cmd = List[Union[str, Path]]
PathLike = Union[str, Path]
