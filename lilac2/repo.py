import subprocess
import traceback
import pathlib
from typing import Optional, Tuple, List

from myutils import at_dir

from .mail import MailService
from .typing import PathLike, LilacMod, Maintainer

class Repo:
  def __init__(self, config):
    self.myaddress = config.get('lilac', 'email')
    self.mymaster = config.get('lilac', 'master')
    self.repomail = config.get('repository', 'email')

    self.repodir = pathlib.Path(
      config.get('repository', 'repodir')).expanduser()

    self.ms = MailService(config)

  def find_maintainers(self, mod: LilacMod) -> List[Maintainer]:
    maintainer = self.find_maintainer()
    name, email = maintainer.split('<', 1)
    name = name.strip('" ')
    email = email.rstrip('>')
    return [Maintainer(name, email)]

  def find_maintainer(self, file: str = '*') -> str:
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
          return author
    finally:
      p.terminate()

  def find_maintainer_or_admin(self, package: Optional[str] = None
                              ) -> Tuple[str, str]:
    path: PathLike
    if package is not None:
      path = self.repodir / package
    else:
      path = '.'

    with at_dir(path):
      try:
        who = self.find_maintainer()
        more = ''
      except Exception:
        who = self.mymaster
        more = traceback.format_exc()

    return who, more

  def report_error(self, subject, msg):
    self.ms.sendmail(self.mymaster, subject, msg)

  def sendmail(self, who, subject, msg):
    self.ms.sendmail(who, subject, msg)

  def send_repo_mail(self, subject: str, msg) -> None:
    self.ms.sendmail(self.repomail, subject, msg)

