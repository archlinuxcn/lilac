from contextlib import contextmanager

from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.declarative import DeclarativeMeta, DeferredReflection

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
