import subprocess
from pathlib import Path
from typing import Optional, Tuple, List, Union, Dict
import logging
from functools import lru_cache

from github import GitHub

from .mail import MailService
from .typing import LilacMod, Maintainer
from .tools import ansi_escape_re
from . import api
from .building import build_output

import gettext
_ = gettext.gettext

logger = logging.getLogger(__name__)

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

  @lru_cache()
  def maintainer_from_github(self, username: str) -> Optional[Maintainer]:
    if self.gh is None:
      raise ValueError(_('Please set the github token in config.ini to fetch the public emails of maintainers from GitHub.'))

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
            errors.append(_('Can not fetch the public email of maintainers from GitHub：{e}').format(e=repr(e)))
          else:
            if u is None:
              errors.append(_('Maintainer {m} have no public email on GitHub').format(m=m["github"]))
            else:
              ret.append(u)
        else:
          logger.error('unsupported maintainer info: %r', m)
          errors.append(_('Unsupported maintainer information：{m}').format(m=repr(m)))
          continue

    if not ret or errors:
      # fallback to git
      dir = self.repodir / mod.pkgbase
      git_maintainer = self.find_maintainer_by_git(dir)

    if errors:
      error_str = '\n'.join(errors)
      self.sendmail(
        git_maintainer,
        subject = _('Can not parse the maintainer information for package {pkgbase}').format(pkgbase=mod.pkgbase),
        msg = _("Please fix the following maintainer information.\n\n{error_str}\n").format(error_str=error_str),
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
        subject_real = subject or _('Can not build package %s')
        msgs.append(_('Error occurs when executing command.\n\nCommand %r aborted with error code %d.') \
                    _('Outputs:\n\n%s') % (
                      exception.cmd, exception.returncode, exception.output))
                    msgs.append(_('Traceback:\n\n') + tb)
      elif isinstance(exception, api.AurDownloadError):
        subject_real = subject or _('Can not fetch %s from AUR')
        msgs.append(_('Error occurs when fetching source files from AUR.\n\n'))
        msgs.append(_('Traceback:\n\n') + tb)
      else:
        subject_real = subject or _('Can not build package %s')
        msgs.append(_('Traceback:\n\n') + tb)
    else:
      if subject is None:
        raise ValueError('subject should be given but not')
      subject_real = subject

    if '%s' in subject_real:
      subject_real = subject_real % pkgbase

    if build_output:
      msgs.append(_('Build log:\n\n') + build_output)

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

