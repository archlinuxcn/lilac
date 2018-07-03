import configparser
import os
import traceback
import logging
from collections import namedtuple, defaultdict
import subprocess
import json

from myutils import at_dir

from .cmd import run_cmd
from .const import mydir

logger = logging.getLogger(__name__)

NVCHECKER_FILE = mydir / 'nvchecker.ini'
OLDVER_FILE = mydir / 'oldver'
NEWVER_FILE = mydir / 'newver'

NvResult = namedtuple('NvResult', 'oldver newver')

def packages_need_update(repo, U):
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

  if not OLDVER_FILE.exists():
    open(OLDVER_FILE, 'a').close()

  newconfig = {k: full[k] for k in U & all_known}
  newconfig['__config__'] = {
    'oldver': OLDVER_FILE,
    'newver': NEWVER_FILE,
  }
  new = configparser.ConfigParser(dict_type=dict, allow_no_value=True)
  new.read_dict(newconfig)
  with open(NVCHECKER_FILE, 'w') as f:
    new.write(f)

  # vcs source needs to be run in the repo, so cwd=...
  rfd, wfd = os.pipe()
  output = subprocess.Popen(
    ['nvchecker', '--logger', 'both', '--json-log-fd', str(wfd),
     NVCHECKER_FILE],
    cwd=repo.repodir, pass_fds=(wfd,))
  os.close(wfd)

  output = os.fdopen(rfd)
  nvdata = {}
  errors = defaultdict(list)
  for l in output:
    j = json.loads(l)
    pkg = j.get('name')
    event = j['event']
    if event == 'updated':
      nvdata[pkg] = NvResult(j['old_version'], j['version'])
    elif event == 'up-to-date':
      nvdata[pkg] = NvResult(j['version'], j['version'])
    elif j['level'] in ['warn', 'error', 'exception', 'critical']:
      errors[pkg].append(j)

  missing = []
  error_owners = defaultdict(list)
  for pkg, pkgerrs in errors.items():
    if pkg is None:
      continue

    dir = repo.repodir / pkg
    if not dir.is_dir():
      missing.append(pkg)
      continue

    with at_dir(dir):
      who = repo.find_maintainer()
    error_owners[who].extend(pkgerrs)

  for who, errors in error_owners.items():
    logger.info('send nvchecker report for %r packages to %s',
                {x['name'] for x in errors}, who)
    repo.sendmail(who, '[lilac] nvchecker 错误报告',
                  '\n'.join(_format_error(e) for e in errors))

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

  for name in U:
    if name not in nvdata:
      # we know nothing about these versions
      # maybe nvchecker has failed
      nvdata[name] = NvResult(None, None)

  return nvdata, unknown

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

def nvtake(L):
  run_cmd(['nvtake', NVCHECKER_FILE] + L)
