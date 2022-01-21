from contextlib import contextmanager
import datetime

from sqlalchemy import update, select, func
from sqlalchemy.sql import functions
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.declarative import DeclarativeMeta, DeferredReflection

from .typing import RUsage

Base: DeclarativeMeta = declarative_base(cls=DeferredReflection)

class PkgLog(Base):
  __tablename__ = 'pkglog'
  __table_args__ = {'schema': 'lilac'}

class Batch(Base):
  __tablename__ = 'batch'
  __table_args__ = {'schema': 'lilac'}

class PkgCurrent(Base):
  __tablename__ = 'pkgcurrent'
  __table_args__ = {'schema': 'lilac'}

USE = False

def setup(engine):
  global USE
  Session.configure(bind=engine)
  Base.prepare(engine)
  USE = True

Session = sessionmaker()

@contextmanager
def get_session():
  session = Session()
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
