from __future__ import annotations

import os
from collections import namedtuple
import subprocess
import re
from typing import Tuple, List, Dict

from pkg_resources import parse_version as _parse_version


def parse_arch_version(v: str) -> Tuple[int, Tuple[str, ...]]:
    if ":" in v:
        epoch = int(v.split(":", 1)[0])
    else:
        epoch = 0
    return epoch, _parse_version(v)


class PkgNameInfo(namedtuple("PkgNameInfo", "name, version, release, arch")):
    def __lt__(self, other) -> bool:
        if self.name != other.name or self.arch != other.arch:
            return NotImplemented
        if self.version != other.version:
            return parse_arch_version(self.version) < parse_arch_version(other.version)
        return float(self.release) < float(other.release)

    def __gt__(self, other) -> bool:
        # No, try the other side please.
        return NotImplemented

    @property
    def fullversion(self) -> str:
        return "%s-%s" % (self.version, self.release)

    @classmethod
    def parseFilename(cls, filename: str) -> "PkgNameInfo":
        return cls(*trimext(filename, 3).rsplit("-", 3))


def trimext(name: str, num: int = 1) -> str:
    for i in range(num):
        name = os.path.splitext(name)[0]
    return name


def get_pkgname_with_bash(PKGBUILD: str) -> List[str]:
    script = (
        """\
. '%s'
echo ${pkgname[*]}"""
        % PKGBUILD
    )
    # Python 3.4 has 'input' arg for check_output
    p = subprocess.Popen(["bash"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    output = p.communicate(script.encode("latin1"))[0].decode("latin1")
    ret = p.wait()
    if ret != 0:
        raise subprocess.CalledProcessError(ret, ["bash"], output)
    return output.split()


def _run_bash(script: str) -> None:
    p = subprocess.Popen(["bash"], stdin=subprocess.PIPE)
    p.communicate(script.encode("latin1"))
    ret = p.wait()
    if ret != 0:
        raise subprocess.CalledProcessError(ret, ["bash"])


def get_aur_pkgbuild_with_bash(name: str) -> None:
    script = (
        """\
. /usr/lib/yaourt/util.sh
. /usr/lib/yaourt/aur.sh
init_color
aur_get_pkgbuild '%s' """
        % name
    )
    _run_bash(script)


def get_abs_pkgbuild_with_bash(name: str) -> None:
    script = (
        """\
. /usr/lib/yaourt/util.sh
. /usr/lib/yaourt/abs.sh
init_paths
init_color
arg=$(pacman -Sp --print-format '%%r/%%n' '%s')
RSYNCOPT="$RSYNCOPT -O"
abs_get_pkgbuild "$arg" """
        % name
    )
    _run_bash(script)


pkgfile_pat = re.compile(r"(?:^|/).+-[^-]+-[\d.]+-(?:\w+)\.pkg\.tar\.(?:xz|zst)$")


def _strip_ver(s: str) -> str:
    return re.sub(r"[<>=].*", "", s)


def get_package_dependencies(name: str) -> List[str]:
    outb = subprocess.check_output(["package-query", "-Sii", "-f", "%D", name])
    out = outb.decode("latin1")
    return [_strip_ver(x) for x in out.split() if x != "-"]


def get_package_info(name: str, local: bool = False) -> Dict[str, str]:
    old_lang = os.environ["LANG"]
    os.environ["LANG"] = "C"
    args = "-Qi" if local else "-Si"
    try:
        outb = subprocess.check_output(["pacman", args, name])
        out = outb.decode("latin1")
    finally:
        os.environ["LANG"] = old_lang

    ret = {}
    for l in out.splitlines():
        if not l:
            continue
        if l[0] not in " \t":
            key, value = l.split(":", 1)
            key = key.strip()
            value = value.strip()
            ret[key] = value
        else:
            ret[key] += " " + l.strip()
    return ret


def get_package_repository(name: str) -> str:
    try:
        out = subprocess.check_output(["package-query", "-Sii", "-f", "%r", name])
        repo = out.strip().decode("latin1")
    except subprocess.CalledProcessError:
        repo = "local"
    return repo


def is_official(name: str) -> bool:
    repo = get_package_repository(name)
    return repo in ("core", "extra", "community", "multilib", "testing")
