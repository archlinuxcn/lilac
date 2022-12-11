# type: ignore

from typing import Union

from .typing import OnBuildEntry

class SumType:
  _intermediate = True

  def __init__(self) -> None:
    if self.__class__.__dict__.get('_intermediate', False):
      raise TypeError('use subclasses')

  def __init_subclass__(cls):
    if not cls.__dict__.get('_intermediate', False):
      setattr(cls.__mro__[1], cls.__name__, cls)

  def __repr__(self) -> str:
    cname = self.__class__.__mro__[1].__name__
    name = self.__class__.__name__
    if e := self._extra_info():
      return f'<{cname}.{name}: {e}>'
    else:
      return f'<{cname}.{name}>'

  def _extra_info(self):
    return ''

class BuildResult(SumType):
  _intermediate = True
  rusage = None
  elapsed = 0

  def __bool__(self) -> bool:
    return self.__class__ in [self.successful, self.staged]

  def _extra_info(self):
    return f'rusage={self.rusage}'

class successful(BuildResult):
  pass

class staged(BuildResult):
  pass

class failed(BuildResult):
  def __init__(self, error: Union[Exception, str]) -> None:
    self.error = error

  def _extra_info(self) -> str:
    if isinstance(self.error, Exception):
      msg = repr(self.error)
    else:
      msg = self.error
    return f'{msg}; {super()._extra_info()}'

class skipped(BuildResult):
  def __init__(self, reason: str) -> None:
    self.reason = reason

  def _extra_info(self) -> str:
    return f'{self.reason!r}; {super()._extra_info()}'

del successful, staged, failed, skipped

class BuildReason(SumType):
  _intermediate = True

  def to_dict(self) -> str:
    d = {k: v for k, v in self.__dict__.items()
         if not k.startswith('_')}
    d['name'] = self.__class__.__name__
    return d

class NvChecker(BuildReason):
  def __init__(self, items: list[tuple[int, str]]) -> None:
    '''items: list of (nvchecker entry index, source name)'''
    self.items = items

  def _extra_info(self) -> str:
    return repr(self.items)

class UpdatedFailed(BuildReason):
  '''previously failed package gets updated'''

class UpdatedPkgrel(BuildReason): pass

class Depended(BuildReason):
  def __init__(self, depender):
    self.depender = depender

  def _extra_info(self) -> str:
    return self.depender

class FailedByDeps(BuildReason):
  def __init__(self, deps: tuple[str]) -> None:
    self.deps = deps

class Cmdline(BuildReason): pass

class OnBuild(BuildReason):
  def __init__(self, update_on_build: list[OnBuildEntry]) -> None:
    self.update_on_build = update_on_build

  def _extra_info(self) -> str:
    return repr(self.update_on_build)

del NvChecker, UpdatedFailed, UpdatedPkgrel, Depended, FailedByDeps, Cmdline, OnBuild
