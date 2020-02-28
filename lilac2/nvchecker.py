from __future__ import annotations

import configparser
import os
import logging
from collections import defaultdict, UserList
import subprocess
import json
from pathlib import Path
from typing import List, NamedTuple, Tuple, Set, Dict
from typing import Optional, Any, Union, Iterable
from typing import TYPE_CHECKING

from .cmd import run_cmd
from .const import mydir
from .typing import LilacMods, PathLike

if TYPE_CHECKING:
  from .repo import Repo, Maintainer
  del Repo, Maintainer

logger = logging.getLogger(__name__)

NVCHECKER_FILE: Path = mydir / 'nvchecker.ini'
OLDVER_FILE = mydir / 'oldver'
NEWVER_FILE = mydir / 'newver'

class NvResult(NamedTuple):
  oldver: Optional[str]
  newver: Optional[str]

class NvResults(UserList):
  data: List[NvResult]

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

def _gen_config_from_mods(
  mods: LilacMods,
) -> Tuple[Dict[str, Any], Set[str]]:
  unknown = set()
  newconfig = {}
  for name, mod in mods.items():
    confs = getattr(mod, 'update_on', None)
    if not confs:
      unknown.add(name)
      continue

    for i, conf in enumerate(confs):
      if i == 0:
        newconfig[f'{name}'] = conf
      else:
        newconfig[f'{name}:{i}'] = conf
        # Avoid valueless keys under numbered name
        # as nvchecker can't handle that
        for key, value in conf.items():
          if not value:
            conf[key] = name

  return newconfig, unknown

def packages_need_update(
  repo: Repo,
) -> Tuple[Dict[str, NvResults], Set[str], Set[str]]:
  newconfig, unknown = _gen_config_from_mods(repo.mods)

  if not OLDVER_FILE.exists():
    open(OLDVER_FILE, 'a').close()

  newconfig['__config__'] = {
    'oldver': OLDVER_FILE,
    'newver': NEWVER_FILE,
  }

  new = configparser.ConfigParser(
    dict_type=dict, allow_no_value=True,
    interpolation=None,
  )
  new.read_dict(newconfig)
  with open(NVCHECKER_FILE, 'w') as f:
    new.write(f)

  # vcs source needs to be run in the repo, so cwd=...
  rfd, wfd = os.pipe()
  cmd: List[Union[str, PathLike]] = [
    'nvchecker', '--logger', 'both', '--json-log-fd', str(wfd),
    NVCHECKER_FILE]
  logger.info('Running nvchecker...')
  process = subprocess.Popen(
    cmd, cwd=repo.repodir, pass_fds=(wfd,))
  os.close(wfd)

  output = os.fdopen(rfd)
  nvdata_unord: Dict[str, Dict[int, NvResult]] = {}
  errors: Dict[Optional[str], List[Dict[str, Any]]] = defaultdict(list)
  rebuild = set()
  for l in output:
    j = json.loads(l)
    pkg = j.get('name')
    if pkg and ':' in pkg:
      pkg, i = pkg.split(':', 1)
      i = int(i)
    else:
      i = 0
    if pkg not in nvdata_unord:
      nvdata_unord[pkg] = {}

    event = j['event']
    if event == 'updated':
      nvdata_unord[pkg][i] = NvResult(j['old_version'], j['version'])
      if i != 0:
        rebuild.add(pkg)
    elif event == 'up-to-date':
      nvdata_unord[pkg][i] = NvResult(j['version'], j['version'])
    elif j['level'] in ['warning', 'warn', 'error', 'exception', 'critical']:
      errors[pkg].append(j)

  # don't rebuild if part of its checks have failed
  rebuild -= errors.keys()

  ret = process.wait()
  if ret != 0:
    raise subprocess.CalledProcessError(ret, cmd)

  error_owners: Dict[Maintainer, List[Dict[str, Any]]] = defaultdict(list)
  for pkg, pkgerrs in errors.items():
    if pkg is None:
      continue
    pkg = pkg.split(':', 1)[0]

    maintainers = repo.find_maintainers(repo.mods[pkg])
    for maintainer in maintainers:
      error_owners[maintainer].extend(pkgerrs)

  for pkg in unknown:
    maintainers = repo.find_maintainers(repo.mods[pkg])
    for maintainer in maintainers:
      error_owners[maintainer].extend(pkgerrs)

  for who, their_errors in error_owners.items():
    logger.warning('send nvchecker report for %r packages to %s',
                   {x['name'] for x in their_errors}, who)
    repo.sendmail(who, 'nvchecker 错误报告',
                  '\n'.join(_format_error(e) for e in their_errors))

  if None in errors: # errors belong to unknown packages
    subject = 'nvchecker 问题'
    msg = '在更新检查时出现了一些错误：\n\n' + '\n'.join(
      _format_error(e) for e in errors[None]) + '\n'
    repo.send_repo_mail(subject, msg)

  nvdata: Dict[str, NvResults] = {}

  for name, d in nvdata_unord.items():
    nrs = nvdata[name] = NvResults()
    for i, (j, nr) in enumerate(sorted(d.items())):
      if i != j:
        logger.warning('mismatched nvdata_unord item for %s: %d != %d in %r', 
                       name, i, j, d)
        # maybe previous items have failed; insert a dummy one
        nrs.append(NvResult(None, None))
      else:
        nrs.append(nr)

  for name in repo.mods:
    if name not in nvdata:
      # we know nothing about these versions
      # maybe nvchecker has failed
      nvdata[name] = NvResults()

  return nvdata, unknown, rebuild

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

def nvtake(L: Iterable[str], mods: LilacMods) -> None:
  names: List[str] = []
  for name in L:
    confs = getattr(mods[name], 'update_on', None)
    if confs:
      names += [f'{name}:{i}' for i in range(len(confs))]
      names[-len(confs)] = name
    else:
      names.append(name)

  run_cmd(['nvtake', '--ignore-nonexistent', NVCHECKER_FILE] # type: ignore
          + names) # type: ignore
  # mypy can't infer List[Union[str, Path]]
  # and can't understand List[str] is a subtype of it
