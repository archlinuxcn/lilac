import sys
import contextlib
import importlib
import pathlib

from myutils import at_dir

def load_all(repodir):
  repodir = pathlib.Path(repodir)
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
      except Exception as e:
        errors[x.name] = e

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


