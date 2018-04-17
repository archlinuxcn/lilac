import sys
import contextlib
import importlib

def load_all(repodir):
  raise NotImplementedError

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


