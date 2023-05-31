import re

from nvchecker.api import GetVersionError

PKG_URL = 'https://archlinux.org/packages/%s/files/json/'

async def get_version(name, conf, *, cache, **kwargs):
  key = conf['pkgpart']
  regex = re.compile(conf['filename'])
  j = await cache.get_json(PKG_URL % key)

  for f in j['files']:
    fn = f.rsplit('/', 1)[-1]
    if regex.fullmatch(fn):
      return fn

  raise GetVersionError('no file matches specified regex')
