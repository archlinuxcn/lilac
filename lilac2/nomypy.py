# type: ignore

class BuildResult:
  rusage = None

  def __init__(self) -> None:
    if __class__ is self.__class__:
      raise TypeError('use subclasses')

  def __bool__(self) -> bool:
    return self.__class__ in [self.successful, self.staged]

  def __init_subclass__(cls):
    setattr(__class__, cls.__name__, cls)

  def __repr__(self) -> str:
    name = self.__class__.__name__
    return f'<BuildResult.{name}; rusage={self.rusage}>'

class successful(BuildResult):
  pass

class staged(BuildResult):
  pass

class failed(BuildResult):
  def __init__(self, exc: Exception) -> None:
    self.exc = exc

  def __repr__(self) -> str:
    name = self.__class__.__name__
    return f'<BuildResult.{name}: {self.exc!r}; rusage={self.rusage}>'

class skipped(BuildResult):
  def __init__(self, reason: str) -> None:
    self.reason = reason

  def __repr__(self) -> str:
    name = self.__class__.__name__
    return f'<BuildResult.{name}: {self.reason!r}; rusage={self.rusage}>'

del successful, staged, failed, skipped

