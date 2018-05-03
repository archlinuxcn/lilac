import configparser
import os
import traceback
import logging
from collections import namedtuple

from .cmd import run_cmd
from .const import mydir

logger = logging.getLogger(__name__)

NVCHECKER_FILE = mydir / 'nvchecker.ini'
OLDVER_FILE = mydir / 'oldver'
NEWVER_FILE = mydir / 'newver'

NvResult = namedtuple('NvResult', 'oldver newver')

def packages_need_update(repo, U):
  full = configparser.ConfigParser(dict_type=dict, allow_no_value=True)
  nvchecker_full = os.path.join(repo.repodir, 'nvchecker.ini')
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
  output = run_cmd(['nvchecker', NVCHECKER_FILE])

  error = False
  errorlines = []
  for l in output.splitlines():
    if l.startswith('[E'):
      error = True
    elif l.startswith('['):
      error = False
    if error:
      errorlines.append(l)

  if unknown or errorlines:
    subject = 'nvchecker 问题'
    msg = ''
    if unknown:
      msg += '以下软件包没有相应的更新配置信息：\n\n' + ''.join(
        x + '\n' for x in sorted(unknown)) + '\n'
    if errorlines:
      msg += '以下软件包在更新检查时出错了：\n\n' + '\n'.join(
        errorlines) + '\n'
    repo.send_repo_mail(subject, msg)

  nvdata = {}
  for x in run_cmd(['nvcmp', NVCHECKER_FILE]).splitlines():
    oldver, newver = x.split(' -> ')
    pkg, oldver = oldver.split(' ', 1)
    if oldver == 'None':
      oldver = None
    nvdata[pkg] = NvResult(oldver, newver)

  with open(NEWVER_FILE) as f:
    for x in f:
      name, version = x.rstrip().split(None, 1)
      if name not in nvdata:
        nvdata[name] = NvResult(None, version)

  return nvdata, unknown

def nvtake(L):
  run_cmd(['nvtake', NVCHECKER_FILE] + L)
