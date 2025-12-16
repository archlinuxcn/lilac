from typing import Dict, Tuple
from zlib import decompress

from nvchecker.api import GetVersionError, session

BIOC_TEMPLATE = 'https://bioconductor.org/packages/release/%s/src/contrib/PACKAGES.gz'

URL_MAP = {
  'cran': 'https://cran.r-project.org/src/contrib/PACKAGES.gz',
  'bioc': BIOC_TEMPLATE % 'bioc',
  'bioc-data-annotation': BIOC_TEMPLATE % 'data/annotation',
  'bioc-data-experiment': BIOC_TEMPLATE % 'data/experiment',
  'bioc-workflows': BIOC_TEMPLATE % 'workflows',
}

PKG_FIELD = b'Package: '
VER_FIELD = b'Version: '
MD5_FIELD = b'MD5sum: '

PKG_FLEN = len(PKG_FIELD)
VER_FLEN = len(VER_FIELD)
MD5_FLEN = len(MD5_FIELD)

async def get_versions(repo: str) -> Dict[str, Tuple[str, str]]:
  url = URL_MAP.get(repo)
  if url is None:
    raise GetVersionError('Unknown repo', repo = repo)
  res = await session.get(url)
  data = decompress(res.body, wbits = 31)

  result = {}
  for section in data.split(b'\n\n'):
    pkg = ver = md5 = None
    for line in section.split(b'\n'):
      if line.startswith(PKG_FIELD):
        pkg = line[PKG_FLEN:].decode('utf8')
      elif line.startswith(VER_FIELD):
        ver = line[VER_FLEN:].decode('utf8')
      elif line.startswith(MD5_FIELD):
        md5 = line[MD5_FLEN:].decode('utf8')
    if pkg is None or ver is None or md5 is None:
      raise GetVersionError('Invalid package data', pkg = pkg, ver = ver, md5 = md5)
    if pkg not in result: # don't let packages in other "Path"s override
      result[pkg] = (ver, md5)

  return result

async def get_version(name, conf, *, cache, **kwargs):
  pkgname = conf.get('pkgname', name)
  repo = conf['repo']
  versions = await cache.get(repo, get_versions)
  data = versions.get(pkgname)
  if data is None:
    raise GetVersionError(f'Package {pkgname} not found in repo {repo}')
  add_md5 = conf.get('md5', False)
  ver, md5 = data
  return f'{ver}#{md5}' if add_md5 else ver
