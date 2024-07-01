from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import (
  Optional, Tuple, List, Union, Dict, TYPE_CHECKING, Any,
)
import logging
from functools import lru_cache
import traceback
import string
import time
from contextlib import suppress

import structlog

from .vendor.github import GitHub

from .mail import MailService
from .tools import ansi_escape_re
from . import api, lilacyaml
from .typing import LilacMod, Maintainer, LilacInfos, LilacInfo
from .nomypy import BuildResult # type: ignore
if TYPE_CHECKING:
  from .packages import Dependency
  del Dependency

logger = logging.getLogger(__name__)
build_logger_old = logging.getLogger('build')
build_logger = structlog.get_logger(logger_name='build')

class Repo:
  gh: Optional[GitHub]

  def __init__(self, config: dict[str, Any]) -> None:
    self.myaddress = config['lilac']['email']
    self.mymaster = config['lilac']['master']
    self.logurl_template = config['lilac'].get('logurl')
    self.repomail = config['repository']['email']
    self.name = config['repository']['name']
    self.trim_ansi_codes = not config['smtp'].get('use_ansi', False)
    self.commit_msg_prefix = config['lilac'].get('commit_msg_prefix', '')

    self.repodir = Path(config['repository']['repodir']).expanduser()
    self.bindmounts = self._get_bindmounts(config.get('bindmounts'))
    self.tmpfs = config.get('misc', {}).get('tmpfs', [])

    self.ms = MailService(config)
    github_token = config['lilac'].get('github_token')
    if github_token:
      self.gh = GitHub(github_token)
    else:
      self.gh = None

    self.on_built_cmds = config.get('misc', {}).get('postbuild', [])

    self.lilacinfos: LilacInfos = {}  # to be filled by self.load_all_lilac_and_report()
    self.yamls: dict[str, Any] = {}
    self._maint_cache: dict[str, list[Maintainer]] = {}

  @lru_cache()
  def maintainer_from_github(self, username: str) -> Optional[Maintainer]:
    if self.gh is None:
      raise ValueError('github token is not configured, can\'t get user\'s Email address from GitHub')

    userinfo = self.gh.get_user_info(username)
    if userinfo['email']:
      return Maintainer(userinfo['name'] or username, userinfo['email'], username)
    else:
      return None

  def parse_maintainers(
    self,
    ms: List[Dict[str, str]],
  ) -> Tuple[List[Maintainer], List[str]]:
    ret = []
    errors = []

    for m in ms:
      if 'github' in m and 'email' in m:
        ret.append(
          Maintainer.from_email_address(m['email'], m['github'])
        )
      elif 'github' in m:
        try:
          u = self.maintainer_from_github(m['github'])
        except Exception as e:
          errors.append(f'Face error while getting user\'s Email address from GitHub：{e!r}')
        else:
          if u is None:
            errors.append(f'There is no public Email address belonging to GitHub user {m["github"]}')
          else:
            ret.append(u)
      else:
        logger.error('unsupported maintainer info: %r', m)
        errors.append(f'unsupported format：{m!r}')
        continue

    return ret, errors

  def find_dependents(
    self, pkgbase: str,
  ) -> List[str]:
    if self.lilacinfos:
      return self._find_dependents_heavy(pkgbase)
    else:
      return self._find_dependents_lite(pkgbase)

  def _find_dependents_heavy(
    self, pkgbase: str,
  ) -> List[str]:
    '''find_dependents for main process'''
    ret = []

    for info in self.lilacinfos.values():
      ds = info.repo_depends
      if any(x == pkgbase for x, y in ds):
        ret.append(info.pkgbase)

    return ret

  def _find_dependents_lite(
    self, pkgbase: str,
  ) -> List[str]:
    '''find_dependents for worker process'''
    ret = []
    self._load_yamls_ignore_errors()

    for p, yamlconf in self.yamls.items():
      ds = yamlconf.get('repo_depends', ())
      if any(x == pkgbase for x, y in ds):
        ret.append(p)

    return ret

  def _load_yamls_ignore_errors(self) -> None:
    if self.yamls:
      return

    for dir in lilacyaml.iter_pkgdir(self.repodir):
      try:
        yamlconf = lilacyaml.load_lilac_yaml(dir)
      except Exception:
        pass
      else:
        self.yamls[dir.name] = yamlconf

  def find_maintainers(
    self, mod: Union[LilacInfo, LilacMod],
    fallback_git: bool = True,
  ) -> List[Maintainer]:
    if mod.pkgbase not in self._maint_cache:
      mts = self._find_maintainers_impl(
        mod.pkgbase,
        maintainers = getattr(mod, 'maintainers', None),
        fallback_git = fallback_git,
      )
      self._maint_cache[mod.pkgbase] = mts
    return self._maint_cache[mod.pkgbase]

  def _find_maintainers_impl(
    self,
    pkgbase: str,
    maintainers: Optional[List[Dict[str, str]]],
    fallback_git: bool = True,
  ) -> List[Maintainer]:
    ret: List[Maintainer] = []
    errors: List[str] = []

    if maintainers is not None:
      if maintainers:
        ret, errors = self.parse_maintainers(maintainers)
      else:
        dependents = self.find_dependents(pkgbase)
        for pkg in dependents:
          if self.lilacinfos:
            maintainers = self.lilacinfos[pkg].maintainers
          else:
            maintainers = self.yamls[pkg].get('maintainers')
          dmaints = self._find_maintainers_impl(
            pkg, maintainers, fallback_git=False,
          )
          ret.extend(dmaints)

    if (not ret and fallback_git) or errors:
      # fallback to git
      dir = self.repodir / pkgbase
      git_maintainer = self.find_maintainer_by_git(dir)

    if errors:
      error_str = '\n'.join(errors)
      self.sendmail(
        git_maintainer,
        subject = f'{pkgbase}\'s maintainers info error',
        msg = f"The folloing info of maintainers is error, please check and correct them.\n\n{error_str}\n",
      )

    if not ret and fallback_git:
      logger.warning("lilac doesn't give out maintainers for %s, "
                     "fallback to git.", pkgbase)
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
      stdout = p.stdout
      assert stdout
      while True:
        line = stdout.readline()
        if not line:
          logger.error('history exhausted while finding maintainer, stop.')
          raise Exception('maintainer cannot be found')
        commit, author = line.rstrip().split(None, 1)
        if me not in author:
          return Maintainer.from_email_address(author)
    finally:
      p.terminate()

  def report_error(self, subject: str, msg: str) -> None:
    self.ms.sendmail(self.mymaster, subject, msg)

  def send_error_report(
    self,
    mod: Union[LilacInfo, LilacMod, str], *,
    msg: Optional[str] = None,
    exc: Optional[Exception] = None,
    subject: Optional[str] = None,
    logfile: Optional[Path] = None,
  ) -> None:
    '''
    the mod argument can be a LilacInfo, or LilacMod (for worker), or a str in case the module cannot be loaded,
    in that case we use git to find a maintainer.
    '''
    if msg is None and exc is None:
      raise TypeError('send_error_report received insufficient args')

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
      tb = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
      if isinstance(exc, subprocess.CalledProcessError):
        subject_real = subject or 'Face error while packaging %s'
        msgs.append('CMD face error！\n\ncommand %r return singal %d。' % (
          exc.cmd, exc.returncode))
        if exc.output:
          msgs.append('Outpur of command：\n\n%s' % exc.output)
        msgs.append('Call stack(s) are following：\n\n' + tb)
      elif isinstance(exc, api.AurDownloadError):
        subject_real = subject or 'Error while pulling package %s from AUR'
        msgs.append('Pulling AUR package failed\n\n')
        msgs.append('Call stack(s) are following:\n\n' + tb)
      elif isinstance(exc, TimeoutError):
        subject_real = subject or 'Packaging pkg %s timeout'
      else:
        subject_real = subject or 'Face unknown error while packaging %s'
        msgs.append('Unknown error occurs, call stack(s) are following：\n\n' + tb)
    else:
      if subject is None:
        raise ValueError('subject should be given but not')
      subject_real = subject

    if '%s' in subject_real:
      subject_real = subject_real % pkgbase

    if logfile:
      with suppress(FileNotFoundError):
        # we need to replace error characters because the mail will be
        # strictly encoded, disallowing surrogate pairs
        with logfile.open(errors='replace') as f:
          build_output = f.read()
        if build_output:
          log_header = 'Packaging Log：'
          with suppress(ValueError, KeyError): # invalid template or wrong key
            if self.logurl_template and len(logfile.parts) >= 2:
              # assume the directory name is the time stamp for now.
              logurl = string.Template(self.logurl_template).substitute(
                datetime = logfile.parts[-2],
                timestamp = int(time.time()),
                pkgbase = pkgbase,
              )
              log_header += ' ' + logurl
          msgs.append(log_header)
          msgs.append('\n' + build_output)

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

  def manages(self, dep: Dependency) -> bool:
    return dep.pkgdir.name in self.lilacinfos

  def load_managed_lilac_and_report(self) -> dict[str, tuple[str, ...]]:
    self.lilacinfos, errors = lilacyaml.load_managed_lilacinfos(self.repodir)
    failed: dict[str, tuple[str, ...]] = {p: () for p in errors}
    for name, exc_info in errors.items():
      logger.error('error while loading lilac.yaml for %s', name, exc_info=exc_info)
      exc = exc_info[1]
      if not isinstance(exc, Exception):
        raise
      self.send_error_report(name, exc=exc,
                             subject='Loading lilac.py for package %s face error')
      build_logger_old.error('%s failed', name)
      build_logger.exception('lilac.yaml error', pkgbase = name, exc_info=exc_info)

    return failed

  def on_built(self, pkg: str, result: BuildResult, version: Optional[str]) -> None:
    if not self.on_built_cmds:
      return

    env = os.environ.copy()
    env['PKGBASE'] = pkg
    env['RESULT'] = result.__class__.__name__
    env['VERSION'] = version or ''
    for cmd in self.on_built_cmds:
      try:
        subprocess.check_call(cmd, env=env)
      except Exception:
        logger.exception('postbuild cmd error for %r', cmd)

  def _get_bindmounts(
    self, bindmounts: Optional[dict[str, str]],
  ) -> list[str]:
    if bindmounts is None:
      return []

    items = [(os.path.expanduser(src), dst)
            for src, dst in bindmounts.items()]
    items.sort(reverse=True)
    return [f'{src}:{dst}' for src, dst in items]
