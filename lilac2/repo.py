import subprocess
import os

from .mail import MailService

class Repo:
  def __init__(self, config):
    self.myaddress = config.get('lilac', 'email')
    self.mymaster = config.get('lilac', 'master')
    self.repomail = config.get('repository', 'email')

    self.repodir = os.path.expanduser(
      config.get('repository', 'repodir'))

    self.ms = MailService(config)

  def find_maintainer(self, file='*'):
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

  def report_error(self, subject, msg):
    self.ms.sendmail(self.mymaster, subject, msg)

  def sendmail(self, who, subject, msg):
    self.ms.sendmail(who, subject, msg)

  def send_repo_mail(self, subject, msg):
    self.ms.sendmail(self.repomail, subject, msg)

