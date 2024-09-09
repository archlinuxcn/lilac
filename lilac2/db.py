from contextlib import contextmanager
import datetime
import re
import logging
from typing import Optional, Any

from sqlalchemy import update, select, func
from sqlalchemy.sql import functions
from sqlalchemy.types import BigInteger, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker, MappedAsDataclass, DeclarativeBase, mapped_column, Mapped
from sqlalchemy.dialects.postgresql import JSONB

from .typing import RUsage, OnBuildEntry

logger = logging.getLogger(__name__)

class Base(MappedAsDataclass, DeclarativeBase):
  pass

class PkgLog(Base):
  __tablename__ = 'pkglog'
  __table_args__ = {'schema': 'lilac'}
  id: Mapped[int] = mapped_column(Integer, init=False, primary_key=True)
  ts: Mapped[datetime.datetime] = mapped_column(DateTime, init=False, nullable=False)
  pkgbase: Mapped[str]
  nv_version: Mapped[Optional[str]]
  pkg_version: Mapped[Optional[str]]
  elapsed: Mapped[int]
  result: Mapped[str]
  cputime: Mapped[Optional[int]]
  memory: Mapped[Optional[int]] = mapped_column(BigInteger)
  msg: Mapped[Optional[str]]
  build_reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
  maintainers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)

class Batch(Base):
  __tablename__ = 'batch'
  __table_args__ = {'schema': 'lilac'}
  id: Mapped[int] = mapped_column(Integer, init=False, primary_key=True)
  ts: Mapped[datetime.datetime] = mapped_column(DateTime, init=False, nullable=False)
  event: Mapped[str]
  logdir: Mapped[Optional[str]] = mapped_column(String, default=None)

class PkgCurrent(Base):
  __tablename__ = 'pkgcurrent'
  __table_args__ = {'schema': 'lilac'}
  id: Mapped[int] = mapped_column(Integer, init=False, primary_key=True)
  ts: Mapped[datetime.datetime] = mapped_column(DateTime, init=False, nullable=False)
  updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, init=False, nullable=False)
  pkgbase: Mapped[str]
  index: Mapped[int]
  status: Mapped[str]
  build_reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)

USE = False
SCHEMA = None

def setup(engine, schema):
  global USE, SCHEMA
  Session.configure(bind=engine)
  Base.prepare(engine)
  USE = True
  if schema:
    SCHEMA = schema

Session = sessionmaker()

@contextmanager
def get_session():
  session = Session()
  if SCHEMA:
    session.connection(
      execution_options = {
        "schema_translate_map": {"lilac": SCHEMA}
      }
    )
  try:
    yield session
    session.commit()
  except:
    session.rollback()
    raise
  finally:
    session.close()

def build_updated(s) -> None:
  if s.bind.dialect.name != 'postgresql':
    return

  from sqlalchemy import text
  s.execute(text('notify build_updated'))

def is_last_build_failed(pkgbase: str) -> bool:
  with get_session() as s:
    r = s.query(PkgLog.result).filter(
      PkgLog.pkgbase == pkgbase,
    ).order_by(PkgLog.ts.desc()).limit(1).one_or_none()

  return r and r[0] == 'failed'

def mark_pkg_as(s, pkg: str, status: str) -> None:
  stmt = update(
    PkgCurrent
  ).where(
    PkgCurrent.pkgbase == pkg,
  ).values(
    status = status,
  )
  s.execute(stmt)

def get_pkgs_last_success_times(pkgs: list[str]) -> list[tuple[str, datetime.datetime]]:
  with get_session() as s:
    r = s.query(
      PkgLog.pkgbase, functions.max(PkgLog.ts),
    ).filter(
      PkgLog.pkgbase.in_(pkgs),
      PkgLog.result.in_(['successful', 'staged']),
    ).group_by(PkgLog.pkgbase).all()
  return r

def get_pkgs_last_rusage(pkgs: list[str]) -> dict[str, RUsage]:
  # select pkgbase, cputime from  (
  #   select id, pkgbase, row_number() over (partition by pkgbase order by ts desc) as k
  #   from pkglog
  #   where pkgbase in ('vim-lily', 'julia-git')
  # ) as w where k = 1
  with get_session() as s:
    w = select(
      func.row_number().over(
        partition_by = PkgLog.pkgbase,
        order_by = PkgLog.ts.desc(),
      ).label('k'),
      PkgLog.pkgbase, PkgLog.cputime, PkgLog.memory,
    ).where(
      PkgLog.pkgbase.in_(pkgs),
      PkgLog.result.in_(['successful', 'staged']),
    ).subquery()

    stmt = select(
      w.c.pkgbase, w.c.cputime, w.c.memory,
    ).select_from(w).where(w.c.k == 1)

    rs = s.execute(stmt).all()
    ret = {r[0]: RUsage(r[1], r[2]) for r in rs}

  return ret

def _get_last_two_versions(s, pkg: str) -> tuple[str, str]:
  r = s.query(
    PkgLog.pkg_version,
  ).filter(
    PkgLog.pkgbase == pkg,
    PkgLog.result.in_(['successful', 'staged']),
  ).order_by(PkgLog.ts.desc()).limit(2).all()

  if len(r) == 1:
    return '', r[0][0]
  elif len(r) == 2:
    return r[1][0], r[0][0]
  elif len(r) == 0:
    return '', ''
  else:
    raise RuntimeError('limit 2 returns more?!')

def check_update_on_build(
  update_on_build: list[OnBuildEntry],
) -> bool:
  with get_session() as s:
    for on_build in update_on_build:
      if (regex := on_build.from_pattern) and (repl := on_build.to_pattern):
        old, new = _get_last_two_versions(s, on_build.pkgbase)
        if not old and not new:
          logger.warning('no built info for %s but try to build on build it?',
                         on_build.pkgbase)
          continue
        old = re.sub(regex, repl, old)
        new = re.sub(regex, repl, new)
        if old != new:
          return True
      else:
        return True

    # all not triggered
    return False
