import subprocess
import pathlib
from typing import Optional, Tuple, List, Union
import logging

from myutils import at_dir

from .mail import MailService
from .typing import LilacMod, Maintainer
from .tools import ansi_escape_re
from . import api

logger = logging.getLogger(__name__)

class Repo:
  def __init__(self, config):
    self.myaddress = config.get('lilac', 'email')
    self.mymaster = config.get('lilac', 'master')
    self.repomail = config.get('repository', 'email')
    self.trim_ansi_codes = not config.getboolean(
      'smtp', 'use_ansi', fallback=False)

    self.repodir = pathlib.Path(
      config.get('repository', 'repodir')).expanduser()

    self.ms = MailService(config)

  def find_maintainers(self, mod: LilacMod) -> List[Maintainer]:
    with at_dir(self.repodir / mod.pkgbase):
      maintainer = self.find_maintainer_by_git()
    return [maintainer]

  def find_maintainer_by_git(self, file: str = '*') -> Maintainer:
    me = self.myaddress

    cmd = [
      "git", "log", "--format=%H %an <%ae>", "--", file,
    ]
    p = subprocess.Popen(
      cmd, stdout=subprocess.PIPE, universal_newlines=True)

    try:
      while True:
        line = p.stdout.readline()
        commit, author = line.rstrip().split(None, 1)
        if me not in author:
          name, email = author.split('<', 1)
          name = name.strip('" ')
          email = email.rstrip('>')
          return Maintainer(name, email)
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
    build_output: Optional[str] = None,
  ):
    if msg is None and exc is None:
      raise TypeError('send_error_report received inefficient args')

    if isinstance(mod, str):
      maintainers = [self.find_maintainer_by_git(mod)]
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

