import json
import urllib.request
from typing import (
  Dict, Optional, Iterable, List, Any, Tuple,
)

template = '''\
_name={name}
pkgname={pkgname}
pkgver={pkgver}
pkgrel=1
pkgdesc="{summary}"
arch=({arch})
url="{home_page}"
license=({license})
{depends}
{conflicts}{provides}{source}
sha256sums=('{sha256sum}')
{prepare}
build() {{
{build}
}}

package() {{
{package}

  # make sure we don't install any world-writable or root-readable-only files
  # we shouldn't need to fix ownership as we extract tarballs as a non-root user
  # https://github.com/pypa/setuptools/issues/1328
  # https://github.com/LonamiWebs/Telethon/issues/1605
  chmod u=rwX,go=rX -R "$pkgdir"
  # make sure we don't install annoying files
  local _site_packages=$(python -c "import site; print(site.getsitepackages()[0])")
  rm -rf "$pkgdir/$_site_packages/tests/"
}}
{check}
'''

pkg_license_tmpl = '''\
  install -Dm644 {license_file} "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
'''

pkg_whl_tmpl = '''\
  cd "$srcdir"
  python -m installer --destdir="$pkgdir" '{whl}'
'''

class PyPIException(Exception): pass

def to_sharray(arr: Iterable[str]) -> str:
  return ' '.join(f"'{x}'" for x in arr)

def get_pypi_info(name: str) -> Dict[str, Any]:
  url = f'https://pypi.org/pypi/{name}/json'
  res = urllib.request.urlopen(url)
  data = res.read().decode('utf-8')
  j = json.loads(data)
  return j

def gen_pkgbuild(
  pypi_name: str,
  pkgname: Optional[str] = None,
  depends: Optional[List[str]] = None,
  python2: bool = False,
  arch: Optional[Iterable[str]] = None,
  makedepends: Optional[List[str]] = None,
  optdepends: Optional[List[str]] = None,
  depends_setuptools: bool = False,
  check: Optional[str] = None,
  provides: Optional[Iterable[str]] = None,
  conflicts: Optional[Iterable[str]] = None,
  license: Optional[str] = None,
  license_file: Optional[str] = None,
  prepare: Optional[str] = None,
  pep517: bool = False,
) -> Tuple[str, str]:
  j = get_pypi_info(pypi_name)
  version = j['info']['version']

  source_release: List[Dict[str, Any]] = []
  whl_release: List[Dict[str, Any]] = []
  source_release = [
    x for x in j['releases'][version]
    if x['packagetype'] == 'sdist']
  if not source_release:
    whl_release = [
    x for x in j['releases'][version]
    if x['packagetype'] == 'bdist_wheel']
    if not whl_release:
      raise PyPIException('no release of known type')

  if not source_release and license_file:
    raise PyPIException('no source code available so cannot install license_file')

  makedepends2 = makedepends or []
  if whl_release:
    makedepends2.extend(['python-installer'])
  elif pep517:
    makedepends2.extend(['python-build', 'python-installer'])
  else:
    makedepends2.append('python-setuptools')

  depends2 = depends or ['python']
  if depends_setuptools:
    depends2.append('python-setuptools')

  depends_str = []
  if depends2:
    depends_str.append(f'depends=({to_sharray(depends2)})')
  if makedepends2:
    depends_str.append(
      f'makedepends=({to_sharray(makedepends2)})')
  if optdepends:
    depends_str.append(
      f'optdepends=({to_sharray(optdepends)})')

  src_dir = '$_name-$pkgver'

  if source_release:
    r = source_release[-1]
    filename = r['filename']
    if filename.endswith('.zip'):
      src_dir = filename.removesuffix('.zip')
    else:
      src_dir = filename.rsplit('.tar', 1)[0]
    # filename name may be different from pypi name, e.g. django-post-office
    # Use "predictable" URL instead of `r['url']` to make AUR users happy...
    source_line = 'source=("https://files.pythonhosted.org/packages/source/${_name::1}/${_name}/%s")' % filename

    if pep517:
      build_code = f'''\
  cd "$srcdir/{src_dir}"
  python -m build --wheel --no-isolation
'''
      package_code = f'''\
  cd "$srcdir/{src_dir}"
  python -m installer --destdir="$pkgdir" dist/*.whl
'''
    else:
      build_code = f'''\
  cd "$srcdir/{src_dir}"
  python3 setup.py build
'''
      package_code = f'''\
  cd "$srcdir/{src_dir}"
  python3 setup.py install --root=$pkgdir --optimize=1 --skip-build
'''

    if license_file:
      package_code += pkg_license_tmpl.format(
        license_file = license_file)

  elif whl_release:
    r = whl_release[-1]
    whl_pyver = r['python_version']
    whl = r['url'].rsplit('/')[-1]
    source_line = f'source=("https://files.pythonhosted.org/packages/{whl_pyver}/${{_name::1}}/$_name/{whl}")'
    build_code = '  true'
    package_code = pkg_whl_tmpl.format(whl=whl)

  if check is not None:
    if check == 'nose':
      depends_str.append("checkdepends=('python-nose')")
      check_code = f'''
check() {{
  cd "$srcdir/{src_dir}"
  python -m unittest discover tests
}}'''
    else:
      raise ValueError('unrecognized check value', check)
  else:
    check_code = ''

  if prepare is not None:
    prepare_code = f'''
prepare() {{
  cd "$srcdir/{src_dir}"
{prepare}
}}
'''
  else:
    prepare_code = ''

  vars1 = {
    'name': j['info']['name'],
    'pkgname': pkgname or f'python-{pypi_name.lower()}',
    'pkgver': version,
    'summary': j['info']['summary'],
    'arch': to_sharray(arch) if arch else 'any',
    'home_page': j['info']['home_page'] or j['info']['project_urls'].get('Homepage', ''),
    'license': license or "'%s'" % j['info']['license'].replace("'", ''),
    'depends': '\n'.join(depends_str),
    'provides': f'provides=({to_sharray(provides)})\n' if provides else '',
    'conflicts': f'conflicts=({to_sharray(conflicts)})\n' if conflicts else '',
    'source': source_line,
    'sha256sum': r['digests']['sha256'],
    'build': build_code.rstrip(),
    'package': package_code.rstrip(),
    'check': check_code.rstrip(),
    'prepare': prepare_code,
  }

  pkgbuild = template.format_map(vars1)
  return version, pkgbuild

