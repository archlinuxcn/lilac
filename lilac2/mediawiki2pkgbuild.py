import datetime
from urllib.parse import quote

import httpx

from .vendor.htmlutils import parse_document_from_httpx

template = '''\
_name={name}
pkgname=mediawiki-{name_lower}
pkgver={version}
pkgrel=1
pkgdesc="MediaWiki extension that {desc}"
arch=(any)
url="https://www.mediawiki.org/wiki/Extension:{name}"
license=('{license}')
depends=('mediawiki>={mwver_cur}' 'mediawiki<{mwver_next}')
source=("$_name-$pkgver-$pkgrel.tar.gz::{link}")
sha256sums=()

build() {{
  true
}}

package() {{
  cd "$srcdir"
  mkdir -p "$pkgdir/usr/share/webapps/mediawiki/extensions/"
  cp -ar $_name "$pkgdir/usr/share/webapps/mediawiki/extensions/"
}}
'''

URL = 'https://www.mediawiki.org/wiki/Special:ExtensionDistributor?extdistname=%s&extdistversion=REL%s'
def get_link(name: str, mwver: str, s: httpx.Client) -> str:
  url = URL % (quote(name), mwver.replace('.', '_'))
  doc = parse_document_from_httpx(url, s)
  link = doc.xpath('//a[starts-with(@href, "https://extdist.wmflabs.org/dist/extensions/")]')[0]
  return link.get('href')

def gen_pkgbuild(
  name: str,
  mwver: str,
  desc: str,
  license: str | list[str],
  s: httpx.Client,
) -> str:
  major, minor = mwver.split('.')
  mwver_next = f'{major}.{int(minor)+1}'
  link = get_link(name, mwver, s)
  if isinstance(license, str):
    license = [license]
  license_str = ' '.join(f"'{x}'" for x in license)
  vars = {
    'name': name,
    'name_lower': name.lower(),
    'version': datetime.datetime.now(tz=datetime.UTC).strftime('%Y%m%d'),
    'desc': desc[0].lower() + desc[1:],
    'link': link,
    'mwver_cur': mwver,
    'mwver_next': mwver_next,
    'license': license_str,
  }
  return template.format_map(vars)
