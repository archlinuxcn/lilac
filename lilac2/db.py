from contextlib import contextmanager
import datetime
import re
import logging
from functools import partial

import psycopg2
import psycopg2.pool

from .typing import RUsage, OnBuildEntry, OnBuildVers

logger = logging.getLogger(__name__)

USE = False
Pool = None

def connect_with_schema(schema, dsn):
  conn = psycopg2.connect(dsn)
  schema = schema or 'lilac'
  if "'" in schema:
    raise ValueError('bad schema', schema)
  with conn.cursor() as cur:
    cur.execute(f"set search_path to '{schema}'")
  return conn

def setup(dsn, schema):
  global USE, Pool
  Pool = psycopg2.pool.ThreadedConnectionPool(
    1, 10, dsn, partial(connect_with_schema, schema))
  USE = True

@contextmanager
def get_session():
  conn = Pool.getconn()
  try:
    with conn:
      with conn.cursor() as cur:
        yield cur
  finally:
    Pool.putconn(conn)

def build_updated(s) -> None:
  s.execute('notify build_updated')

def is_last_build_failed(pkgbase: str) -> bool:
  with get_session() as s:
    s.execute(
      '''select result from pkglog
         where pkgbase = %s
         order by ts desc limit 1''', (pkgbase,))
    r = s.fetchall()

  return r and r[0] == 'failed'

def mark_pkg_as(s, pkg: str, status: str) -> None:
  s.execute('update pkgcurrent set status = %s where pkgbase = %s', (status, pkg))

def get_pkgs_last_success_times(pkgs: list[str]) -> list[tuple[str, datetime.datetime]]:
  if not pkgs:
    return []

  with get_session() as s:
    s.execute(
      '''select pkgbase, max(ts) from pkglog
         where pkgbase = any(%s) and result in ('successful', 'staged')
         group by pkgbase''', (pkgs,))
    r = s.fetchall()
  return r

def get_pkgs_last_rusage(pkgs: list[str]) -> dict[str, RUsage]:
  if not pkgs:
    return {}

  with get_session() as s:
    s.execute('''
      select pkgbase, cputime, memory from  (
        select pkgbase, cputime, memory, row_number() over (partition by pkgbase order by ts desc) as k
        from pkglog
        where pkgbase = any(%s) and result in ('successful', 'staged')
      ) as w where k = 1''', (pkgs,))
    rs = s.fetchall()
    ret = {r[0]: RUsage(r[1], r[2]) for r in rs}

  return ret

def _get_last_two_versions(s, pkg: str) -> tuple[str, str]:
  s.execute(
    '''select pkg_version from pkglog
       where pkgbase = %s and result in ('successful', 'staged')
       order by ts desc limit 2''', (pkg,))
  r = s.fetchall()

  if len(r) == 1:
    return '', r[0][0]
  elif len(r) == 2:
    return r[1][0], r[0][0]
  elif len(r) == 0:
    return '', ''
  else:
    raise RuntimeError('limit 2 returns more?!')

def get_update_on_build_vers(
  update_on_build: list[OnBuildEntry],
) -> OnBuildVers:
  ret = []

  with get_session() as s:
    for on_build in update_on_build:
      old, new = _get_last_two_versions(s, on_build.pkgbase)
      if not old and not new:
        logger.warning('no built info for %s but try to build on build it?',
                       on_build.pkgbase)

      if (regex := on_build.from_pattern) and (repl := on_build.to_pattern):
        old = re.sub(regex, repl, old)
        new = re.sub(regex, repl, new)
      ret.append((old, new))

  return ret
