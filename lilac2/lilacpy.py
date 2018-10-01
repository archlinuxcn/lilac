import sys
import contextlib
import importlib.util
from pathlib import Path

from myutils import at_dir

def load_all(repodir: Path):
  mods = {}
  errors = {}

  for x in repodir.iterdir():
    if not x.is_dir():
      continue

    if x.name[0] == '.':
      continue

    with at_dir(x):
      try:
        with load_lilac() as mod:
          mods[x.name] = mod
        if hasattr(mod, 'time_limit_hours') and mod.time_limit_hours < 0:
          raise ValueError('time_limit_hours should be positive.')
      except FileNotFoundError:
        pass
      except Exception:
        errors[x.name] = sys.exc_info()

  return mods, errors

@contextlib.contextmanager
def load_lilac():
  try:
    spec = importlib.util.spec_from_file_location(
      'lilac.py', 'lilac.py')
    mod = spec.loader.load_module()
    yield mod
  finally:
    try:
      del sys.modules['lilac.py']
    except KeyError:
      pass


