import smtplib

from mailutils import assemble_mail

class MailService:
  def __init__(self, config):
    self.config = config
    self.mailtag = config.get('lilac', 'name')
    self.send_email = config.getboolean('lilac', 'send_email')

  def smtp_connect(self):
    config = self.config
    host = config.get('smtp', 'host', fallback='')
    port = config.getint('smtp', 'port', fallback=0)
    username = config.get('smtp', 'username', fallback='')
    password = config.get('smtp', 'password', fallback='')
    if config.getboolean('smtp', 'use_ssl', fallback=False):
      smtp_cls = smtplib.SMTP_SSL
    else:
      smtp_cls = smtplib.SMTP
    connection = smtp_cls(host, port)
    if not host:
      # __init__ doesn't connect; let's do it
      connection.connect()
    if username != '' and password != '':
      connection.login(username, password)
    return connection

  def sendmail(self, to, from_, subject, msg):
    if not self.send_email:
      return

    s = self.smtp_connect()
    if len(msg) > 5 * 1024 ** 2:
      msg = msg[:1024 ** 2] + '\n\n日志过长，省略ing……\n\n' + \
          msg[-1024 ** 2:]
    msg = assemble_mail('[%s] %s' % (
      self.mailtag, subject), to, from_, text=msg)
    s.send_message(msg)
    s.quit()

