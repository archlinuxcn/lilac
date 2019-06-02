import subprocess
from pathlib import Path
from typing import Optional, Tuple, List, Union, Dict, Set
import logging
from functools import lru_cache
import traceback

from github import GitHub
import structlog

from .mail import MailService
from .typing import LilacMod, Maintainer
from .tools import ansi_escape_re
from . import api, lilacpy
from .building import build_output
from .typing import LilacMods

logger = logging.getLogger(__name__)
build_logger_old = logging.getLogger('build')
build_logger = structlog.get_logger(logger_name='build')

class Repo:
  def __init__(self, config):
    self.myaddress = config.get('lilac', 'email')
    self.mymaster = config.get('lilac', 'master')
    self.repomail = config.get('repository', 'email')
    self.name = config.get('repository', 'name')
    self.trim_ansi_codes = not config.getboolean(
      'smtp', 'use_ansi', fallback=False)

    self.repodir = Path(config.get('repository', 'repodir')).expanduser()

    self.ms = MailService(config)
    github_token = config.get('lilac', 'github_token', fallback=None)
    if github_token:
      self.gh = GitHub(config.get('lilac', 'github_token', fallback=None))
    else:
      self.gh = None

    self.mods: LilacMods = {}  # to be filled by self.load_all_lilac_and_report()

  @lru_cache()
  def maintainer_from_github(self, username: str) -> Optional[Maintainer]:
    if self.gh is None:
      raise ValueError('未设置 github token，无法从 GitHub 取得用户 Email 地址')

    userinfo = self.gh.get_user_info(username)
    if userinfo['email']:
      return Maintainer(userinfo['name'], userinfo['email'], username)
    else:
      return None

  @lru_cache()
  def find_maintainers(self, mod: LilacMod) -> List[Maintainer]:
    ret = []
    errors = []

    maintainers: List[Dict[str, str]] = getattr(mod, 'maintainers', None)
    if maintainers is not None:
      for m in maintainers:
        if 'github' in m and 'email' in m:
          ret.append(
            Maintainer.from_email_address(m['email'], m['github'])
          )
        elif 'github' in m:
          try:
            u = self.maintainer_from_github(m['github'])
          except Exception as e:
            errors.append(f'从 GitHub 获取用户 Email 地址时出错：{e!r}')
          else:
            if u is None:
              errors.append(f'GitHub 用户 {m["github"]} 未公开 Email 地址')
            else:
              ret.append(u)
        else:
          logger.error('unsupported maintainer info: %r', m)
          errors.append(f'不支持的格式：{m!r}')
          continue

    if not ret or errors:
      # fallback to git
      dir = self.repodir / mod.pkgbase
      git_maintainer = self.find_maintainer_by_git(dir)

    if errors:
      error_str = '\n'.join(errors)
      self.sendmail(
        git_maintainer,
        subject = f'{mod.pkgbase} 的 maintainers 信息有误',
        msg = f"以下 maintainers 信息有误，请修正。\n\n{error_str}\n",
      )

    if not ret:
      logger.warning("lilac doesn't give out maintainers for %s, "
                     "fallback to git.", mod.pkgbase)
      return [git_maintainer]
    else:
      return ret

  def find_maintainer_by_git(
    self,
    dir: Path = Path('.'),
    file: str = '*',
  ) -> Maintainer:

    me = self.myaddress

    cmd = [
      "git", "log", "--format=%H %an <%ae>", "--", file,
    ]
    p = subprocess.Popen(
      cmd, stdout=subprocess.PIPE, universal_newlines=True,
      cwd = dir,
    )

    try:
      while True:
        line = p.stdout.readline()
        commit, author = line.rstrip().split(None, 1)
        if me not in author:
          return Maintainer.from_email_address(author)
    finally:
      p.terminate()

  def report_error(self, subject: str, msg: str) -> None:
    self.ms.sendmail(self.mymaster, subject, msg)

  def send_error_report(
    self,
    mod: Union[LilacMod, str], *,
    msg: Optional[str] = None,
    exc: Optional[Tuple[Exception, str]] = None,
    subject: Optional[str] = None,
  ) -> None:
    if msg is None and exc is None:
      raise TypeError('send_error_report received inefficient args')

    if isinstance(mod, str):
      maintainers = [self.find_maintainer_by_git(file=mod)]
      pkgbase = mod
    else:
      maintainers = self.find_maintainers(mod)
      pkgbase = mod.pkgbase

    msgs = []
    if msg is not None:
      msgs.append(msg)

    if exc is not None:
      exception, tb = exc
      if isinstance(exception, subprocess.CalledProcessError):
        subject_real = subject or '在编译软件包 %s 时发生错误'
        msgs.append('命令执行失败！\n\n命令 %r 返回了错误号 %d。' \
                    '命令的输出如下：\n\n%s' % (
                      exception.cmd, exception.returncode, exception.output))
        msgs.append('调用栈如下：\n\n' + tb)
      elif isinstance(exception, api.AurDownloadError):
        subject_real = subject or '在获取AUR包 %s 时发生错误'
        msgs.append('获取AUR包失败！\n\n')
        msgs.append('调用栈如下：\n\n' + tb)
      else:
        subject_real = subject or '在编译软件包 %s 时发生未知错误'
        msgs.append('发生未知错误！调用栈如下：\n\n' + tb)
    else:
      if subject is None:
        raise ValueError('subject should be given but not')
      subject_real = subject

    if '%s' in subject_real:
      subject_real = subject_real % pkgbase

    if build_output:
      msgs.append('编译命令输出如下：\n\n' + build_output)

    msg = '\n'.join(msgs)
    if self.trim_ansi_codes:
      msg = ansi_escape_re.sub('', msg)

    addresses = [str(x) for x in maintainers]
    logger.debug('mail to %s:\nsubject: %s\nbody: %s',
                 addresses, subject_real, msg[:200])
    self.sendmail(addresses, subject_real, msg)

  def sendmail(self, who: Union[str, List[str], Maintainer],
               subject: str, msg: str) -> None:
    if isinstance(who, Maintainer):
      who = str(who)
    self.ms.sendmail(who, subject, msg)

  def send_repo_mail(self, subject: str, msg: str) -> None:
    self.ms.sendmail(self.repomail, subject, msg)

  def manages(self, dep) -> bool:
    return dep.pkgdir.name in self.mods

  def load_all_lilac_and_report(self) -> Set[str]:
    self.mods, errors = lilacpy.load_all(self.repodir)
    failed = set(errors)
    for name, exc_info in errors.items():
      tb_lines = traceback.format_exception(*exc_info)
      tb = ''.join(tb_lines)
      logger.error('error while loading lilac.py for %s', name, exc_info=exc_info)
      exc = exc_info[1]
      if not isinstance(exc, Exception):
        raise
      self.send_error_report(name, exc=(exc, tb),
                             subject='为软件包 %s 载入 lilac.py 时失败')
      build_logger_old.error('%s failed', name)
      build_logger.exception('lilac.py error', pkgbase = name)

    return failed
