from __future__ import annotations

import os
import logging
from collections import defaultdict, UserList
import subprocess
import json
from pathlib import Path
from typing import (
  List, NamedTuple, Tuple, Set, Dict,
  Optional, Any, Union, Iterable, TYPE_CHECKING,
  DefaultDict
)

import tomli_w

from .cmd import run_cmd
from .const import mydir
from .typing import LilacInfos, PathLike
from .tools import reap_zombies

if TYPE_CHECKING:
  from .repo import Repo, Maintainer
  del Repo, Maintainer

logger = logging.getLogger(__name__)

NVCHECKER_FILE: Path = mydir / 'nvchecker.toml'
KEY_FILE: Path = mydir / 'nvchecker_keyfile.toml'
OLDVER_FILE = mydir / 'oldver'
NEWVER_FILE = mydir / 'newver'

class NvResult(NamedTuple):
  oldver: Optional[str]
  newver: Optional[str]

class NvResults(UserList):
  data: List[NvResult]

  def to_list(self) -> list[tuple[Optional[str], Optional[str]]]:
    return [tuple(x) for x in self.data] # type: ignore

  @classmethod
  def from_list(cls, l) -> NvResults:
    return cls([NvResult(o, n) for o, n in l])

  @property
  def oldver(self) -> Optional[str]:
    if self.data:
      return self.data[0].oldver
    return None

  @property
  def newver(self) -> Optional[str]:
    if self.data:
      return self.data[0].newver
    return None

def _gen_config_from_lilacinfos(
  infos: LilacInfos,
) -> Tuple[Dict[str, Any], Dict[str, int], Dict[str, str]]:
  errors = {}
  newconfig = {}
  counts = {}
  for name, info in infos.items():
    confs = info.update_on
    if not confs:
      errors[name] = 'unknown'
      continue

    for i, conf in enumerate(confs):
      if not isinstance(conf, dict):
        errors[name] = 'not array of dicts'
        break
      if i == 0:
        newconfig[f'{name}'] = conf
      else:
        newconfig[f'{name}:{i}'] = conf
      # Avoid empty-value keys as nvchecker can't handle that
      for key, value in conf.items():
        if value in [None, '']:
          conf[key] = name
    counts[name] = len(confs)

  return newconfig, counts, errors

def packages_need_update(
  repo: Repo,
  proxy: Optional[str] = None,
  care_pkgs: set[str] = set(),
) -> Tuple[Dict[str, NvResults], Set[str], Set[str]]:
  if care_pkgs:
    lilacinfos = {k: v for k, v in repo.lilacinfos.items() if k in care_pkgs}
  else:
    lilacinfos = repo.lilacinfos
  newconfig, update_on_counts, update_on_errors = _gen_config_from_lilacinfos(lilacinfos)

  if not OLDVER_FILE.exists():
    open(OLDVER_FILE, 'a').close()

  newconfig['__config__'] = {
    'oldver': str(OLDVER_FILE),
    'newver': str(NEWVER_FILE),
  }
  if proxy:
    newconfig['__config__']['proxy'] = proxy

  with open(NVCHECKER_FILE, 'wb') as f:
    tomli_w.dump(newconfig, f)

  # vcs source needs to be run in the repo, so cwd=...
  rfd, wfd = os.pipe()
  cmd: List[Union[str, PathLike]] = [
    'nvchecker', '--logger', 'both', '--json-log-fd', str(wfd),
    '-c', NVCHECKER_FILE]
  if KEY_FILE.exists():
    cmd.extend(['--keyfile', KEY_FILE])

  env = os.environ.copy()
  env['PYTHONPATH'] = str(Path(__file__).resolve().parent.parent)

  logger.info('Running nvchecker...')
  process = subprocess.Popen(
    cmd, cwd=repo.repodir, pass_fds=(wfd,), env=env)
  os.close(wfd)

  output = os.fdopen(rfd)
  # pkgbase => index => NvResult
  nvdata_nested: Dict[str, Dict[int, NvResult]] = {}
  errors: DefaultDict[Optional[str], List[Dict[str, Any]]] = defaultdict(list)
  rebuild = set()
  for l in output:
    j = json.loads(l)
    pkg = j.get('name')
    if pkg and ':' in pkg:
      pkg, i = pkg.split(':', 1)
      i = int(i)
    else:
      i = 0
    if pkg not in nvdata_nested:
      nvdata_nested[pkg] = {}

    event = j['event']
    if event == 'updated':
      nvdata_nested[pkg][i] = NvResult(j['old_version'], j['version'])
      if i != 0:
        rebuild.add(pkg)
    elif event == 'up-to-date':
      nvdata_nested[pkg][i] = NvResult(j['version'], j['version'])
    elif j['level'] in ['warning', 'warn', 'error', 'exception', 'critical']:
      errors[pkg].append(j)

  # don't rebuild if part of its checks have failed
  rebuild -= errors.keys()

  ret = process.wait()
  reap_zombies()
  if ret != 0:
    raise subprocess.CalledProcessError(ret, cmd)

  error_owners: DefaultDict[Maintainer, List[Dict[str, Any]]] = defaultdict(list)
  for pkg, pkgerrs in errors.items():
    if pkg is None:
      continue
    pkg = pkg.split(':', 1)[0]

    maintainers = repo.find_maintainers(lilacinfos[pkg])
    for maintainer in maintainers:
      error_owners[maintainer].extend(pkgerrs)

  for pkg, error in update_on_errors.items():
    maintainers = repo.find_maintainers(lilacinfos[pkg])
    for maintainer in maintainers:
      error_owners[maintainer].append({
        'name': pkg,
        'error': error,
        'event': 'wrong or missing `update_on` config',
      })

  for who, their_errors in error_owners.items():
    logger.warning('send nvchecker report for %r packages to %s',
                   {x['name'] for x in their_errors}, who)
    repo.sendmail(who, 'nvchecker error report',
                  '\n'.join(_format_error(e) for e in their_errors))

  if None in errors: # errors belong to unknown packages
    subject = 'nvchecker problem'
    msg = 'Face some errors while checking updates：\n\n' + '\n'.join(
      _format_error(e) for e in errors[None]) + '\n'
    repo.send_repo_mail(subject, msg)

  nvdata: Dict[str, NvResults] = {}

  for pkgbase, d in nvdata_nested.items():
    if pkgbase is None:
      # from events without a name
      continue
    n = update_on_counts[pkgbase]
    nrs = nvdata[pkgbase] = NvResults()
    for i in range(n):
      if i in d:
        nrs.append(d[i])
      else:
        # item at this index has failed; insert a dummy one
        nrs.append(NvResult(None, None))

  for pkgbase in lilacinfos:
    if pkgbase not in nvdata:
      # we know nothing about these versions
      # maybe nvchecker has failed
      nvdata[pkgbase] = NvResults()

  return nvdata, set(update_on_errors.keys()), rebuild

def _format_error(error) -> str:
  if 'exception' in error:
    exception = error['exception']
    error = error.copy()
    del error['exception']
  else:
    exception = None

  ret = json.dumps(error, ensure_ascii=False)
  if exception:
    ret += '\n' + exception + '\n'
  return ret

def nvtake(L: Iterable[str], infos: LilacInfos) -> None:
  names: List[str] = []
  for name in L:
    confs = infos[name].update_on
    if confs:
      names += [f'{name}:{i}' for i in range(len(confs))]
      names[-len(confs)] = name
    else:
      names.append(name)

  run_cmd(['nvtake', '--ignore-nonexistent', '-c', NVCHECKER_FILE] # type: ignore
          + names)
  # mypy can't infer List[Union[str, Path]]
  # and can't understand List[str] is a subtype of it
