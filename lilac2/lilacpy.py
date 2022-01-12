from __future__ import annotations

import sys
import contextlib
import importlib.util
from pathlib import Path
from typing import Generator, cast

from .typing import LilacMod
from . import lilacyaml
from . import api

@contextlib.contextmanager
def load_lilac(dir: Path) -> Generator[LilacMod, None, None]:
  try:
    spec = importlib.util.spec_from_file_location(
      'lilac.py', dir / 'lilac.py')
    if spec is None:
      raise RuntimeError('lilac.py spec is None')
    mod = importlib.util.module_from_spec(spec)

    yamlconf = lilacyaml.load_lilac_yaml(dir)
    g = None
    for k, v in yamlconf.items():
      if k.endswith('_script'):
        name = k[:-len('_script')]
        if name == 'post_build_always':
          code = [f'def {name}(success):']
        else:
          code = [f'def {name}():']
        for line in v.splitlines():
          code.append(f'  {line}')
        if g is None:
          g = vars(mod)
          # "import" lilac2.api
          g.update({a: b for a, b in api.__dict__.items()
                    if not a.startswith('_')})
        code_str = '\n'.join(code)
        # run code in `mod` namespace
        exec(code_str, g)
      else:
        setattr(mod, k, v)

    assert spec.loader
    try:
      spec.loader.exec_module(mod)
    except FileNotFoundError:
      pass

    mod = cast(LilacMod, mod)
    mod.pkgbase = dir.absolute().name

    if hasattr(mod, 'update_on'):
      mod.update_on = lilacyaml.parse_update_on(yamlconf['update_on'])[0]

    yield mod

  finally:
    try:
      del sys.modules['lilac.py']
    except KeyError:
      pass
