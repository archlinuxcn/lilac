import pathlib
import sys

import pytest

# sys.path does not support `Path`s yet
this_dir = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(this_dir.parents[1]))
sys.path.insert(0, str(this_dir.parents[1] / 'pylib'))

from lilaclib import (
  update_pkgrel,
)

from myutils import at_dir


@pytest.mark.parametrize('pkgbuild, expected_pkgbuild, kwargs', [
  ('pkgrel=1', 'pkgrel=2', {}),
  ('pkgrel=10', 'pkgrel=11', {}),
  ('pkgrel=1.1', 'pkgrel=2', {}),
  ('pkgrel="1"', 'pkgrel=2', {}),
  ('pkgrel=1', 'pkgrel=3', {'rel': 3}),
])
def test_update_pkgrel(tmpdir, pkgbuild, expected_pkgbuild, kwargs):
  with at_dir(tmpdir):
    with open('PKGBUILD', 'w') as f:
      f.write(pkgbuild)
    update_pkgrel(**kwargs)
    with open('PKGBUILD', 'r') as f:
      new_pkgbuild = f.read()
    assert new_pkgbuild == expected_pkgbuild
