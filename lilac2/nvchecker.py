import configparser
import os
import traceback
import logging
from collections import defaultdict
import subprocess
import json
from pathlib import Path
from typing import List, NamedTuple, Tuple, Set, Dict
from typing import Optional, Any, Union, Iterable

from .cmd import run_cmd
from .const import mydir
from .typing import LilacMods, PathLike
from .repo import Repo, Maintainer

logger = logging.getLogger(__name__)

NVCHECKER_FILE: Path = mydir / 'nvchecker.ini'
OLDVER_FILE = mydir / 'oldver'
NEWVER_FILE = mydir / 'newver'

class NvResult(NamedTuple):
  oldver: Optional[str]
  newver: Optional[str]

def _gen_config_from_ini(repo, U):
  full = configparser.ConfigParser(dict_type=dict, allow_no_value=True)
  nvchecker_full = repo.repodir / 'nvchecker.ini'
  try:
    full.read([nvchecker_full])
  except Exception:
    tb = traceback.format_exc()
    try:
      who = repo.find_maintainer(file='nvchecker.ini')
      more = ''
    except Exception:
      who = repo.mymaster
      more = traceback.format_exc()

    subject = 'nvchecker 配置文件错误'
    msg = '调用栈如下：\n\n' + tb
    if more:
      msg += '\n获取维护者信息也失败了！调用栈如下：\n\n' + more
    repo.sendmail(who, subject, msg)
    raise

  all_known = set(full.sections())
  unknown = U - all_known
  if unknown:
    logger.warn('unknown packages: %r', unknown)

  newconfig = {k: full[k] for k in U & all_known}

  return newconfig, unknown

def _gen_config_from_mods(
  repo: Repo, mods: LilacMods,
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

  return newconfig, unknown

def packages_need_update(
  repo: Repo, mods: LilacMods,
) -> Tuple[Dict[str, NvResult], Set[str], Set[str]]:
  newconfig, left = _gen_config_from_mods(repo, mods)
  newconfig2, unknown = _gen_config_from_ini(repo, left)
  newconfig.update(newconfig2)
  del newconfig2, left

  if not OLDVER_FILE.exists():
    open(OLDVER_FILE, 'a').close()

  newconfig['__config__'] = {
    'oldver': OLDVER_FILE,
    'newver': NEWVER_FILE,
  }

  new = configparser.ConfigParser( # type: ignore
    dict_type=dict, allow_no_value=True)
  new.read_dict(newconfig)
  with open(NVCHECKER_FILE, 'w') as f:
    new.write(f)

  # vcs source needs to be run in the repo, so cwd=...
  rfd, wfd = os.pipe()
  cmd: List[Union[str, PathLike]] = [
    'nvchecker', '--logger', 'both', '--json-log-fd', str(wfd),
    NVCHECKER_FILE]
  process = subprocess.Popen(
    cmd, cwd=repo.repodir, pass_fds=(wfd,))
  os.close(wfd)

  output = os.fdopen(rfd)
  nvdata = {}
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
    event = j['event']
    if event == 'updated':
      if i == 0:
        nvdata[pkg] = NvResult(j['old_version'], j['version'])
      else:
        rebuild.add(pkg)
    elif event == 'up-to-date':
      if i == 0:
        nvdata[pkg] = NvResult(j['version'], j['version'])
    elif j['level'] in ['warn', 'error', 'exception', 'critical']:
      errors[pkg].append(j)

  ret = process.wait()
  if ret != 0:
    raise subprocess.CalledProcessError(ret, cmd)

  missing = []
  error_owners: Dict[Maintainer, List[Dict[str, Any]]] = defaultdict(list)
  for pkg, pkgerrs in errors.items():
    if pkg is None:
      continue
    pkg = pkg.split(':', 1)[0]

    dir = repo.repodir / pkg
    if not dir.is_dir():
      missing.append(pkg)
      continue

    maintainers = repo.find_maintainers(mods[pkg])
    for maintainer in maintainers:
      error_owners[maintainer].extend(pkgerrs)

  for who, their_errors in error_owners.items():
    logger.info('send nvchecker report for %r packages to %s',
                {x['name'] for x in their_errors}, who)
    repo.sendmail(who, 'nvchecker 错误报告',
                  '\n'.join(_format_error(e) for e in their_errors))

  if unknown or None in errors or missing:
    subject = 'nvchecker 问题'
    msg = ''
    if unknown:
      msg += '以下软件包没有相应的更新配置信息：\n\n' + ''.join(
        x + '\n' for x in sorted(unknown)) + '\n'
    if None in errors:
      msg += '在更新检查时出现了一些错误：\n\n' + '\n'.join(
        _format_error(e) for e in errors[None]) + '\n'
    if missing:
      msg += '以下软件包没有所对应的目录：\n\n' + \
          '\n'.join( missing) + '\n'
    repo.send_repo_mail(subject, msg)

  for name in mods:
    if name not in nvdata:
      # we know nothing about these versions
      # maybe nvchecker has failed
      nvdata[name] = NvResult(None, None)

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
          + names)
  # mypy can't infer List[Union[str, Path]]
  # and can't understand List[str] is a subtype of it
