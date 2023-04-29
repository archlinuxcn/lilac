from __future__ import annotations

import smtplib
from typing import Union, Type, List, Dict, Any

from .vendor.mailutils import assemble_mail

SMTPClient = Union[smtplib.SMTP, smtplib.SMTP_SSL]

class MailService:
  def __init__(self, config: Dict[str, Any]) -> None:
    self.smtp_config = config['smtp']
    self.mailtag = config['lilac']['name']
    self.send_email = config['lilac']['send_email']

    myname = config['lilac']['name']
    myaddress = config['lilac']['email']
    self.from_ = f'{myname} <{myaddress}>'
    self.unsub = config['lilac'].get('unsubscribe_address')

  def smtp_connect(self) -> SMTPClient:
    config = self.smtp_config
    host = config.get('host', '')
    port = config.get('port', 0)
    username = config.get('username')
    password = config.get('password')
    smtp_cls: Type[SMTPClient]
    if config.get('use_ssl', False):
      smtp_cls = smtplib.SMTP_SSL
    else:
      smtp_cls = smtplib.SMTP
    connection = smtp_cls(host, port)
    if not host:
      # __init__ doesn't connect; let's do it
      connection.connect()
    if username and password:
      connection.login(username, password)
    return connection

  def sendmail(self, to: Union[str, List[str]],
               subject: str, msg: str) -> None:
    if not self.send_email:
      return

    s = self.smtp_connect()
    if len(msg) > 5 * 1024 ** 2:
      msg = msg[:1024 ** 2] + '\n\nLog is quite long and omitted.\n\n' + \
          msg[-1024 ** 2:]
    mail = assemble_mail('[%s] %s' % (
      self.mailtag, subject), to, self.from_, text=msg)
    if self.unsub:
      mail['List-Unsubscribe'] = f'<mailto:{self.unsub}?subject=unsubscribe>'
    s.send_message(mail)
    s.quit()

