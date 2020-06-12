from __future__ import annotations

import os
from typing import List
import logging

import pyalpm

logger = logging.getLogger(__name__)

PKG_CACHE_DIR = '/var/cache/pacman/pkg'
# PKG_CACHE_DIR = '/tmp'

class RepoDownloader:
  _last_dl_name = None
  _last_dl_percent = 0

  def __init__(self, name: str, servers: List[str]) -> None:
    self.name = name

    dir = os.path.expanduser('~/pacmandb')
    os.makedirs(dir, exist_ok=True)

    self._handle = pyalpm.Handle('/', dir)
    self._db = db = self._handle.register_syncdb(name, 0)
    db.servers = servers
    db.update(False)

  def download(self, pkg_names: List[str]) -> List[str]:
    logger.info('Downloading packages repo %s: %r',
                self.name, pkg_names)
    db = self._db
    pkgs = [db.get_pkg(p) for p in pkg_names]

    h = self._handle
    h.cachedirs = [PKG_CACHE_DIR]
    h.dlcb = self.cb_dl

    tx = h.init_transaction(nodeps=True, downloadonly=True)
    try:
      for pkg in pkgs:
        tx.add_pkg(pkg)
      tx.prepare()
      tx.commit()
    finally:
      self._last_dl_name = None
      self._last_dl_percent = 0
      tx.release()

    return [
      os.path.join(PKG_CACHE_DIR, pkg.filename)
      for pkg in pkgs
    ]

  def cb_dl(self, filename: str, tx: int, total: int) -> None:
    if self._last_dl_name == filename:
      if not total:
        return
      p = tx * 100 // total
      print('.' * (p-self._last_dl_percent),
            end='', flush=True)
      self._last_dl_percent = p
      if p == 100:
        print('done')
    else:
      self._last_dl_name = filename
      self._last_dl_percent = 0
      print(f'Downloading {filename}', end='', flush=True)

