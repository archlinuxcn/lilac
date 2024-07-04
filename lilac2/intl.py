import os
import locale

from fluent.runtime import FluentLocalization, FluentResourceLoader

cache = {}

def get_l10n(name):
  if name not in cache:
    d = os.path.dirname(__file__)
    loc = locale.getlocale()[0]
    loader = FluentResourceLoader(f'{d}/l10n/{{locale}}')
    l10n = FluentLocalization([loc, "en"], [f'{name}.ftl'], loader)
    cache[name] = l10n
  return cache[name]
