from __future__ import annotations

import types
from typing import (
    Union,
    Dict,
    Tuple,
    Type,
    List,
    NamedTuple,
    Optional,
    Sequence,
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
        return f"{self.name} <{self.email}>"

    @classmethod
    def from_email_address(cls, s: str, github: Optional[str] = None,) -> "Maintainer":
        if "<" in s:
            name, email = s.split("<", 1)
            name = name.strip('" ')
            email = email.rstrip(">")
        else:
            name = s.rsplit("@", 1)[0]
            email = s
        return cls(name, email, github)


PkgRel = Union[int, str]
